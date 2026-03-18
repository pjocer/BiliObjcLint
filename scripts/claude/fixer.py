"""
Claude Fixer - 主修复器模块

ClaudeFixer 类负责协调整个 Claude 自动修复流程
"""
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# 添加 scripts 目录到路径以支持绝对导入
_SCRIPT_DIR = Path(__file__).parent.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from core.lint.logger import get_logger, log_claude_fix_start, log_claude_fix_end
from core.lint.ignore_cache import IgnoreCache

from claude.dialogs import DialogError, show_dialog, show_progress_notification
from claude.prompt_builder import build_fix_prompt
from claude.html_report import HtmlReportGenerator, open_html_report
from claude.http_server import (
    find_available_port,
    start_action_server,
    wait_for_user_action,
    shutdown_server,
    set_ignore_cache,
    set_fixer_instance,
    set_all_violations
)

logger = get_logger("claude_fix")


class AutofixTracker:
    """记录 Claude 自动修复统计"""

    def __init__(self, enabled: bool, trigger: str, mode: str):
        self.enabled = enabled
        self.trigger = trigger
        self.mode = mode
        self.triggered = False
        self.flow = "none"
        self.decision = "pending"
        self.cli_available: Optional[bool] = None
        self.actions: List[Dict[str, Any]] = []
        self.summary = {
            "attempts": 0,
            "success": 0,
            "failed": 0,
            "cancelled": 0,
            "target_total": 0,
        }

    def set_triggered(self, value: bool):
        self.triggered = value

    def set_flow(self, value: str):
        self.flow = value

    def set_decision(self, value: str):
        self.decision = value

    def set_cli_available(self, value: bool):
        self.cli_available = value

    def record_action(self, action: Dict[str, Any]):
        event = dict(action)
        event.setdefault("occurred_at", datetime.now().astimezone().isoformat())
        event.setdefault("flow", self.flow)
        event.setdefault("include_in_summary", True)
        self.actions.append(event)
        if not event.get("include_in_summary", True):
            return
        self.summary["attempts"] += 1
        self.summary["target_total"] += int(event.get("target_count", 0))
        result = event.get("result")
        if result == "success":
            self.summary["success"] += 1
        elif result in ("failed", "timeout", "not_available"):
            self.summary["failed"] += 1
        elif result == "cancelled":
            self.summary["cancelled"] += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "trigger": self.trigger,
            "mode": self.mode,
            "triggered": self.triggered,
            "flow": self.flow,
            "decision": self.decision,
            "cli_available": self.cli_available,
            "actions": self.actions,
            "summary": self.summary,
        }


class ClaudeFixer:
    """Claude 自动修复器"""

    def __init__(self, config: dict, project_root: str, run_id: Optional[str] = None, project: Optional[dict] = None):
        self.config = config
        self.project_root = Path(project_root).resolve()
        self.autofix_config = config.get('claude_autofix', {})
        self.trigger = self.autofix_config.get('trigger', 'any')
        self.mode = self.autofix_config.get('mode', 'silent')
        self.timeout = self.autofix_config.get('timeout', 120)
        # Claude Code API 配置
        self.api_base_url = self.autofix_config.get('api_base_url', '')
        self.api_token = self.autofix_config.get('api_token', '')
        self.api_key = self.autofix_config.get('api_key', '')
        self.model = self.autofix_config.get('model', '')
        self.disable_nonessential_traffic = self.autofix_config.get('disable_nonessential_traffic', True)
        self.start_time = None
        self._claude_path = None
        self.run_id = run_id
        self.project = project or {}
        self.metrics_config = self._build_metrics_config(config)
        self.project_key = self.project.get("key") or self.metrics_config.project_key or self.project_root.name
        self.project_name = self.project.get("name") or self.metrics_config.project_name or self.project_root.name
        self.tool_version = self._read_version()
        self.autofix_tracker = AutofixTracker(
            enabled=self.trigger != "disable",
            trigger=self.trigger,
            mode=self.mode,
        )

        logger.debug(f"ClaudeFixer initialized: project_root={self.project_root}")
        logger.debug(f"Config: trigger={self.trigger}, mode={self.mode}, timeout={self.timeout}")
        logger.debug(f"API config: base_url={self.api_base_url or '(default)'}, model={self.model or '(default)'}")

    def _read_version(self) -> str:
        version_file = self.project_root / "VERSION"
        if version_file.exists():
            return version_file.read_text().strip()
        return "unknown"

    def _build_metrics_config(self, config: dict):
        metrics_cfg = config.get("metrics", {}) if isinstance(config, dict) else {}
        from core.lint.config import MetricsConfig
        return MetricsConfig(
            enabled=metrics_cfg.get("enabled", False),
            endpoint=metrics_cfg.get("endpoint", "http://127.0.0.1:18080"),
            token=metrics_cfg.get("token", ""),
            project_key=metrics_cfg.get("project_key", ""),
            project_name=metrics_cfg.get("project_name", ""),
            mode=metrics_cfg.get("mode", "push"),
            spool_dir=metrics_cfg.get("spool_dir", "~/.biliobjclint/metrics_spool"),
            timeout_ms=metrics_cfg.get("timeout_ms", 2000),
            retry_max=metrics_cfg.get("retry_max", 3),
        )

    def get_autofix_report(self) -> Dict[str, Any]:
        return self.autofix_tracker.to_dict()

    def record_autofix_action(
        self,
        action_type: str,
        result: str,
        target_count: int = 0,
        message: str = "",
        flow: Optional[str] = None,
        target_rule: Optional[str] = None,
        include_in_summary: bool = True,
        occurred_at: Optional[str] = None,
    ) -> None:
        action = {
            "type": action_type,
            "result": result,
            "target_count": target_count,
            "message": message,
            "include_in_summary": include_in_summary,
        }
        if flow is not None:
            action["flow"] = flow
        if target_rule:
            action["target_rule"] = target_rule
        if occurred_at:
            action["occurred_at"] = occurred_at
        self.autofix_tracker.record_action(action)

    def ignore_all_violations(
        self,
        violations: List[Dict],
        ignore_cache: Optional[IgnoreCache] = None,
        flow: str = "dialog",
        occurred_at: Optional[str] = None,
    ) -> Tuple[bool, str, int, int]:
        """将违规批量加入忽略列表，并记录行为。"""
        cache = ignore_cache or IgnoreCache(project_root=str(self.project_root))
        total = len(violations)
        ignored = 0
        failed = 0

        for item in violations:
            if hasattr(item, "file_path"):
                file_path = item.file_path
                line = item.line
                rule = item.rule_id
                message = item.message
                related_lines = item.related_lines
            else:
                file_path = item.get("file_path") or item.get("file") or ""
                line = item.get("line", 0)
                rule = item.get("rule_id") or item.get("rule") or ""
                message = item.get("message", "")
                related_lines = item.get("related_lines")
                if isinstance(related_lines, list) and len(related_lines) == 2:
                    related_lines = tuple(related_lines)

            if not file_path or not line or not rule or not related_lines:
                failed += 1
                continue

            try:
                if cache.add_ignore_from_request(file_path, line, rule, message, related_lines):
                    ignored += 1
                else:
                    failed += 1
            except Exception as e:
                logger.warning(f"Failed to ignore violation: {e}")
                failed += 1

        success = ignored > 0
        result = "success" if success else "failed"
        message = f"已忽略 {ignored}/{total} 个问题" if success else f"所有 {total} 个问题忽略失败"
        self.record_autofix_action(
            action_type="ignore_all",
            result=result,
            target_count=total,
            message=message,
            flow=flow,
            include_in_summary=True,
            occurred_at=occurred_at,
        )
        return success, message, ignored, failed

    def _find_claude_path(self) -> Optional[str]:
        """
        查找 claude CLI 的完整路径

        Returns:
            claude 的完整路径，如果找不到返回 None
        """
        logger.debug("Searching for Claude CLI path...")

        # 常见的安装路径
        common_paths = [
            os.path.expanduser("~/.local/bin/claude"),
            "/usr/local/bin/claude",
            "/opt/homebrew/bin/claude",
            os.path.expanduser("~/bin/claude"),
        ]

        # 先检查常见路径
        for path in common_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                logger.debug(f"Found Claude CLI at: {path}")
                return path

        # 尝试 which 命令（扩展 PATH）
        env = os.environ.copy()
        env['PATH'] = f"{os.path.expanduser('~/.local/bin')}:/usr/local/bin:/opt/homebrew/bin:{env.get('PATH', '')}"

        result = subprocess.run(
            ['which', 'claude'],
            capture_output=True,
            text=True,
            env=env
        )
        if result.returncode == 0:
            path = result.stdout.strip()
            logger.debug(f"Found Claude CLI via which: {path}")
            return path

        logger.warning("Claude CLI not found in any known path")
        return None

    def _build_claude_env(self) -> Dict[str, str]:
        """
        构建 Claude Code CLI 所需的环境变量

        优先级：yaml 配置 > shell 配置文件 > 系统环境变量

        Returns:
            环境变量字典
        """
        env_vars = {}

        # 1. 首先从 yaml 配置读取
        if self.api_base_url:
            env_vars['ANTHROPIC_BASE_URL'] = self.api_base_url
            logger.debug(f"Using api_base_url from yaml: {self.api_base_url}")

        # api_token 和 api_key 都设置，兼容不同的环境变量名
        if self.api_token:
            env_vars['ANTHROPIC_AUTH_TOKEN'] = self.api_token
            env_vars['ANTHROPIC_AUTH_KEY'] = self.api_token
            logger.debug("Using api_token from yaml")
        elif self.api_key:
            env_vars['ANTHROPIC_API_KEY'] = self.api_key
            logger.debug("Using api_key from yaml")

        if self.model:
            env_vars['ANTHROPIC_MODEL'] = self.model
            env_vars['ANTHROPIC_SMALL_FAST_MODEL'] = self.model
            logger.debug(f"Using model from yaml: {self.model}")

        if self.disable_nonessential_traffic:
            env_vars['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'] = '1'

        # 2. 如果 yaml 配置不完整，从 shell 配置文件补充
        if not env_vars.get('ANTHROPIC_AUTH_TOKEN') and not env_vars.get('ANTHROPIC_API_KEY'):
            shell_env = self._load_shell_env()
            for key, value in shell_env.items():
                if key not in env_vars:
                    env_vars[key] = value

        if env_vars:
            logger.info(f"Built {len(env_vars)} env vars for Claude CLI")
        else:
            logger.warning("No Claude API credentials configured")

        return env_vars

    def _load_shell_env(self) -> Dict[str, str]:
        """
        从用户的 shell 配置文件读取环境变量

        作为 yaml 配置的后备方案，当 yaml 中未配置 API 凭证时使用

        Returns:
            环境变量字典
        """
        env_vars = {}
        home = os.path.expanduser("~")

        # 要读取的配置文件列表
        config_files = [
            os.path.join(home, ".zshrc"),
            os.path.join(home, ".bashrc"),
            os.path.join(home, ".bash_profile"),
            os.path.join(home, ".profile"),
        ]

        # 要提取的环境变量前缀
        prefixes = ("ANTHROPIC_", "CLAUDE_", "API_TIMEOUT")

        export_pattern = re.compile(r'^export\s+([A-Z_][A-Z0-9_]*)=(.+)$')

        for config_file in config_files:
            if not os.path.isfile(config_file):
                continue

            try:
                with open(config_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        # 跳过注释行
                        if line.startswith('#'):
                            continue

                        match = export_pattern.match(line)
                        if match:
                            key, value = match.groups()
                            # 只提取相关的环境变量
                            if any(key.startswith(p) for p in prefixes):
                                # 移除引号
                                value = value.strip('"\'')
                                env_vars[key] = value
                                logger.debug(f"Loaded env from {config_file}: {key}={value[:20]}...")
            except Exception as e:
                logger.warning(f"Failed to read {config_file}: {e}")

        if env_vars:
            logger.debug(f"Loaded {len(env_vars)} env vars from shell config (fallback)")

        return env_vars

    def check_claude_available(self) -> Tuple[bool, Optional[str]]:
        """
        检测 Claude Code CLI 是否可用

        Returns:
            (is_available, error_message)
        """
        logger.info("Checking Claude CLI availability...")

        # 调试日志
        with open("/tmp/biliobjclint_debug.log", "a") as f:
            f.write("check_claude_available: start\n")

        # 1. 查找 claude 路径
        claude_path = self._find_claude_path()

        with open("/tmp/biliobjclint_debug.log", "a") as f:
            f.write(f"check_claude_available: claude_path={claude_path}\n")

        if not claude_path:
            logger.error("Claude CLI not installed")
            return False, "Claude Code CLI 未安装\n请访问 https://claude.ai/code 安装"

        # 保存路径供后续使用
        self._claude_path = claude_path
        logger.debug(f"Using Claude CLI at: {claude_path}")

        # 2. 跳过验证，直接认为可用（验证可能会卡住）
        with open("/tmp/biliobjclint_debug.log", "a") as f:
            f.write("check_claude_available: skipping verification, assuming available\n")

        logger.info("Claude CLI found, skipping verification")
        return True, None

    def should_trigger(self, violations: List[Dict]) -> bool:
        """
        判断是否应该触发修复提示

        Args:
            violations: 违规列表

        Returns:
            是否应该触发
        """
        if self.trigger == 'disable':
            return False

        if self.trigger == 'error':
            # 只有存在 error 级别才触发
            return any(v.get('severity') == 'error' for v in violations)

        # trigger == 'any'
        return len(violations) > 0

    def fix_violations_silent(
        self,
        violations: List[Dict],
        action_type: str = "fix_all",
        target_rule: Optional[str] = None,
        occurred_at: Optional[str] = None,
        flow: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        静默模式修复违规

        Returns:
            (success, message)
        """
        logger.info(f"Starting silent fix for {len(violations)} violations")
        fix_start_time = time.time()

        prompt = build_fix_prompt(violations)
        logger.debug(f"Generated fix prompt ({len(prompt)} chars)")

        # 获取 claude 路径
        claude_path = self._claude_path
        if not claude_path:
            claude_path = self._find_claude_path()
            if not claude_path:
                logger.error("Claude CLI path not found for fix")
                return False, "Claude Code CLI 未找到"

        # 将 prompt 写入临时文件以避免命令行长度限制
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(prompt)
            prompt_file = f.name
        logger.debug(f"Prompt written to temp file: {prompt_file}")

        try:
            # 每次创建新的 session ID，避免与其他 Claude 会话冲突
            session_id = str(uuid.uuid4())
            logger.info(f"Executing Claude fix (timeout={self.timeout}s, session={session_id[:8]}...)...")

            # 构建环境变量，优先使用 yaml 配置，其次从 shell 配置文件读取
            env = os.environ.copy()
            env.update(self._build_claude_env())
            # 禁用 thinking 模式以加速响应
            env['MAX_THINKING_TOKENS'] = '0'

            # 使用 -p 非交互模式执行修复
            result = subprocess.run(
                [
                    claude_path,
                    '-p', prompt,
                    '--allowedTools', 'Read,Edit',
                    '--session-id', session_id,
                    '--no-session-persistence',
                    '--dangerously-skip-permissions'  # 跳过权限检查以加速
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.project_root),
                env=env
            )

            elapsed = time.time() - fix_start_time
            if result.returncode == 0:
                logger.info(f"Fix completed successfully in {elapsed:.2f}s")
                logger.debug(f"Claude stdout: {result.stdout[:500]}..." if len(result.stdout) > 500 else f"Claude stdout: {result.stdout}")
                self.autofix_tracker.record_action({
                    "type": action_type,
                    "target_count": len(violations),
                    "target_rule": target_rule,
                    "result": "success",
                    "elapsed_ms": int(elapsed * 1000),
                    "message": "Fix completed",
                    "occurred_at": occurred_at,
                    "flow": flow or self.autofix_tracker.flow,
                })
                return True, "修复完成"
            else:
                error_output = result.stderr.strip() or result.stdout.strip() or f"退出码 {result.returncode}"
                logger.error(f"Fix failed (exit code {result.returncode})")
                logger.error(f"stderr: {result.stderr}")
                logger.error(f"stdout: {result.stdout}")
                self.autofix_tracker.record_action({
                    "type": action_type,
                    "target_count": len(violations),
                    "target_rule": target_rule,
                    "result": "failed",
                    "elapsed_ms": int(elapsed * 1000),
                    "message": error_output,
                    "occurred_at": occurred_at,
                    "flow": flow or self.autofix_tracker.flow,
                })
                return False, f"修复失败: {error_output}"

        except subprocess.TimeoutExpired:
            elapsed = time.time() - fix_start_time
            logger.error(f"Fix timed out after {elapsed:.2f}s (limit: {self.timeout}s)")
            self.autofix_tracker.record_action({
                "type": action_type,
                "target_count": len(violations),
                "target_rule": target_rule,
                "result": "timeout",
                "elapsed_ms": int(elapsed * 1000),
                "message": f"Timeout {self.timeout}s",
                "occurred_at": occurred_at,
                "flow": flow or self.autofix_tracker.flow,
            })
            return False, f"修复超时（{self.timeout}秒）"
        except Exception as e:
            logger.exception(f"Fix exception: {e}")
            self.autofix_tracker.record_action({
                "type": action_type,
                "target_count": len(violations),
                "target_rule": target_rule,
                "result": "failed",
                "elapsed_ms": int((time.time() - fix_start_time) * 1000),
                "message": str(e),
                "occurred_at": occurred_at,
                "flow": flow or self.autofix_tracker.flow,
            })
            return False, f"修复异常: {e}"
        finally:
            # 清理临时文件
            try:
                os.unlink(prompt_file)
                logger.debug(f"Cleaned up temp file: {prompt_file}")
            except:
                pass

    def fix_violations_terminal(self, violations: List[Dict]) -> Tuple[bool, str]:
        """
        终端模式修复违规 - 打开 Terminal.app 与 Claude 交互

        Returns:
            (success, message)
        """
        prompt = build_fix_prompt(violations)

        # 将 prompt 写入临时文件
        prompt_file = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.txt',
            delete=False,
            prefix='claude_fix_'
        )
        prompt_file.write(prompt)
        prompt_file.close()

        # 构建环境变量导出命令
        env_exports = []
        claude_env = self._build_claude_env()
        for key, value in claude_env.items():
            env_exports.append(f"export {key}='{value}'")
        env_export_cmd = ' && '.join(env_exports) if env_exports else 'true'

        # 使用 AppleScript 打开 Terminal 并执行 claude
        script = f'''
        tell application "Terminal"
            activate
            do script "echo '🔧 正在修复中，不要关闭本窗口...' && echo '' && cd '{self.project_root}' && {env_export_cmd} && claude -p \\"$(cat '{prompt_file.name}')\\" --allowedTools Read,Edit && rm -f '{prompt_file.name}' && echo '' && echo '✅ 修复完成！'"
        end tell
        '''

        try:
            subprocess.run(['osascript', '-e', script], check=True)
            return True, "已在 Terminal 中打开 Claude"
        except Exception as e:
            return False, f"打开 Terminal 失败: {e}"

    def fix_violations_vscode(self, violations: List[Dict]) -> Tuple[bool, str]:
        """
        VSCode 模式修复违规 - 在 VSCode 中打开项目并复制 prompt

        Returns:
            (success, message)
        """
        prompt = build_fix_prompt(violations)

        # 复制 prompt 到剪贴板
        try:
            process = subprocess.Popen(
                ['pbcopy'],
                stdin=subprocess.PIPE
            )
            process.communicate(prompt.encode('utf-8'))
        except Exception as e:
            return False, f"复制到剪贴板失败: {e}"

        # 打开 VSCode
        try:
            subprocess.run(['code', str(self.project_root)], check=True)
        except Exception:
            # 如果 code 命令不可用，尝试使用 open
            try:
                subprocess.run([
                    'open', '-a', 'Visual Studio Code',
                    str(self.project_root)
                ], check=True)
            except Exception as e:
                return False, f"打开 VSCode 失败: {e}"

        return True, "已在 VSCode 中打开项目\n修复 Prompt 已复制到剪贴板\n请在 Claude Code 面板中粘贴执行"

    def run(self, violations: List[Dict]) -> int:
        """
        执行修复流程

        Args:
            violations: 违规列表

        Returns:
            退出码
        """
        self.start_time = time.time()
        logger.log_separator("Claude Fix Session Start")

        if not violations:
            logger.info("No violations to fix")
            return 0

        # 检查是否应该触发
        should = self.should_trigger(violations)
        self.autofix_tracker.set_triggered(should)
        with open("/tmp/biliobjclint_debug.log", "a") as f:
            f.write(f"should_trigger: {should}, trigger_mode={self.trigger}\n")
        if not should:
            logger.info(f"Trigger condition not met (trigger={self.trigger})")
            self.autofix_tracker.set_decision("skip")
            return 0

        # 统计
        error_count = sum(1 for v in violations if v.get('severity') == 'error')
        warning_count = len(violations) - error_count
        log_claude_fix_start(len(violations), str(self.project_root))
        logger.info(f"Violations: {len(violations)} total ({error_count} errors, {warning_count} warnings)")

        # 检测 Claude 是否可用
        available, error_msg = self.check_claude_available()
        self.autofix_tracker.set_cli_available(available)
        if not available:
            logger.error(f"Claude not available: {error_msg}")
            show_dialog(
                "BiliObjCLint",
                f"无法使用 Claude 自动修复\n\n{error_msg}",
                ["确定"],
                icon="stop"
            )
            log_claude_fix_end(False, error_msg, time.time() - self.start_time)
            self.autofix_tracker.set_decision("not_available")
            self.autofix_tracker.record_action({
                "type": "fix_all",
                "target_count": len(violations),
                "result": "not_available",
                "elapsed_ms": int((time.time() - self.start_time) * 1000),
                "message": error_msg,
            })
            return 1

        # 先显示对话框
        self.autofix_tracker.set_flow("dialog")
        try:
            # AppleScript display dialog 最多支持 3 个按钮。
            # “取消”使用标准的关闭窗口 / Esc 路径处理，避免四按钮直接报 -50。
            dialog_result = show_dialog(
                "BiliObjCLint",
                f"发现 {len(violations)} 个代码问题\n（{error_count} errors, {warning_count} warnings）\n\n是否让 Claude 尝试自动修复？",
                ["查看详情", "忽略全部", "自动修复"],
                icon="caution",
                raise_on_error=True
            )
        except DialogError as e:
            logger.error(f"Initial dialog failed, fallback to HTML report: {e}")
            self.autofix_tracker.set_flow("html")
            user_action = self._show_html_report_and_wait(violations)
            if user_action == 'cancel' or user_action is None:
                logger.info("User cancelled or timed out from HTML")
                log_claude_fix_end(False, "User cancelled", time.time() - self.start_time)
                self.autofix_tracker.set_decision("cancel")
                return 0
            if user_action == 'done':
                logger.info("User finished reviewing (done)")
                log_claude_fix_end(True, "User finished", time.time() - self.start_time)
                self.autofix_tracker.set_decision("done")
                return 0
            if user_action == 'fix':
                self.autofix_tracker.set_decision("fix")
                dialog_result = "自动修复"
            elif user_action == 'ignore_all':
                dialog_result = "忽略全部"
            else:
                logger.info(f"Unknown HTML action: {user_action}")
                return 0
        dialog_occurred_at = datetime.now().astimezone().isoformat()

        with open("/tmp/biliobjclint_debug.log", "a") as f:
            f.write(f"Initial dialog result: {dialog_result}\n")

        if dialog_result is None or dialog_result == "取消":
            logger.info("User cancelled from dialog")
            log_claude_fix_end(False, "User cancelled", time.time() - self.start_time)
            self.autofix_tracker.set_decision("cancel")
            self.record_autofix_action(
                action_type="cancel",
                result="cancelled",
                target_count=len(violations),
                message="User cancelled",
                flow="dialog",
                include_in_summary=True,
                occurred_at=dialog_occurred_at,
            )
            return 0

        # 用户选择直接修复
        if dialog_result == "自动修复":
            self.record_autofix_action(
                action_type="choose_fix",
                result="success",
                target_count=len(violations),
                message="User chose fix",
                flow="dialog",
                include_in_summary=False,
                occurred_at=dialog_occurred_at,
            )
            user_action = 'fix'
            self.autofix_tracker.set_decision("fix")
        # 用户选择查看详情
        elif dialog_result == "查看详情":
            self.record_autofix_action(
                action_type="view_detail",
                result="success",
                target_count=len(violations),
                message="User opened HTML details",
                flow="dialog",
                include_in_summary=False,
                occurred_at=dialog_occurred_at,
            )
            self.autofix_tracker.set_flow("html")
            user_action = self._show_html_report_and_wait(violations)
            if user_action == 'cancel' or user_action is None:
                logger.info("User cancelled or timed out from HTML")
                log_claude_fix_end(False, "User cancelled", time.time() - self.start_time)
                self.autofix_tracker.set_decision("cancel")
                return 0
            if user_action == 'done':
                logger.info("User finished reviewing (done)")
                log_claude_fix_end(True, "User finished", time.time() - self.start_time)
                self.autofix_tracker.set_decision("done")
                return 0
            if user_action == 'fix':
                self.autofix_tracker.set_decision("fix")
        elif dialog_result == "忽略全部":
            success, message, ignored, failed = self.ignore_all_violations(
                violations,
                flow="dialog",
                occurred_at=dialog_occurred_at,
            )
            if success:
                logger.info(f"User ignored all from dialog: {ignored}/{len(violations)} ignored, {failed} failed")
                log_claude_fix_end(True, message, time.time() - self.start_time)
                self.autofix_tracker.set_decision("ignore_all")
                return 0
            logger.error("Ignore-all from dialog failed")
            show_dialog(
                "BiliObjCLint",
                message,
                ["确定"],
                icon="stop"
            )
            log_claude_fix_end(False, message, time.time() - self.start_time)
            self.autofix_tracker.set_decision("ignore_all_failed")
            return 1
        else:
            # 未知结果
            logger.info(f"Unknown dialog result: {dialog_result}")
            return 0

        # user_action == 'fix'
        return self._execute_fix(violations, occurred_at=dialog_occurred_at, flow="dialog")

    def _show_html_report_and_wait(self, violations: List[Dict]) -> Optional[str]:
        """显示 HTML 报告并等待用户操作"""
        html_report_path = None
        server = None

        # 初始化全局变量供 HTTP 处理器使用
        ignore_cache = IgnoreCache(project_root=str(self.project_root))
        set_ignore_cache(ignore_cache)
        set_fixer_instance(self)
        set_all_violations(violations)  # 供"修复全部"功能使用

        try:
            # 找到可用端口并启动服务器
            server_port = find_available_port()
            server = start_action_server(server_port)

            logger.info(f"Started action server on port {server_port}")

            # 生成带按钮的 HTML 报告
            report_generator = HtmlReportGenerator(self.project_root)
            html_report_path = report_generator.generate(violations, port=server_port)

            # 调试日志
            with open("/tmp/biliobjclint_debug.log", "a") as f:
                f.write(f"Opening HTML report with interactive buttons, port={server_port}\n")

            # 在浏览器中打开报告
            open_html_report(html_report_path)

            # 等待用户操作（超时 5 分钟）
            logger.info("Waiting for user action in browser...")
            user_action = wait_for_user_action(server, timeout=300)

            # 调试：记录用户操作结果
            with open("/tmp/biliobjclint_debug.log", "a") as f:
                f.write(f"User action from HTML: {user_action}\n")

            return user_action

        finally:
            # 关闭服务器
            if server:
                shutdown_server(server)
            # 清理临时文件
            if html_report_path and os.path.exists(html_report_path):
                try:
                    os.remove(html_report_path)
                except Exception:
                    pass

    def _execute_fix(
        self,
        violations: List[Dict],
        occurred_at: Optional[str] = None,
        flow: Optional[str] = None,
    ) -> int:
        """执行修复操作"""
        logger.info(f"User confirmed fix, mode={self.mode}")

        # 根据模式执行修复
        if self.mode == 'silent':
            # 显示进度通知
            show_progress_notification("Claude 正在修复代码问题...")

            # 执行修复
            success, result_msg = self.fix_violations_silent(
                violations,
                action_type="fix_all",
                occurred_at=occurred_at,
                flow=flow,
            )

            # 显示结果
            if success:
                logger.info("Fix completed successfully")
                show_dialog(
                    "BiliObjCLint",
                    f"Claude 已完成修复！\n\n请重新编译以验证修复结果",
                    ["确定"],
                    icon="note"
                )
                log_claude_fix_end(True, "Fix completed", time.time() - self.start_time)
            else:
                logger.error(f"Fix failed: {result_msg}")
                show_dialog(
                    "BiliObjCLint",
                    f"修复过程中出现问题\n\n{result_msg}",
                    ["确定"],
                    icon="stop"
                )
                log_claude_fix_end(False, result_msg, time.time() - self.start_time)
                return 1

        elif self.mode == 'terminal':
            self.autofix_tracker.record_action({
                "type": "fix_all",
                "target_count": len(violations),
                "result": "started",
                "elapsed_ms": 0,
                "message": "Terminal opened",
                "occurred_at": occurred_at,
                "flow": flow or self.autofix_tracker.flow,
            })
            success, result_msg = self.fix_violations_terminal(violations)
            logger.info(f"Terminal mode result: success={success}, msg={result_msg}")
            if not success:
                show_dialog(
                    "BiliObjCLint",
                    result_msg,
                    ["确定"],
                    icon="stop"
                )
                log_claude_fix_end(False, result_msg, time.time() - self.start_time)
                return 1
            log_claude_fix_end(True, "Terminal opened", time.time() - self.start_time)

        elif self.mode == 'vscode':
            self.autofix_tracker.record_action({
                "type": "fix_all",
                "target_count": len(violations),
                "result": "started",
                "elapsed_ms": 0,
                "message": "VSCode opened",
                "occurred_at": occurred_at,
                "flow": flow or self.autofix_tracker.flow,
            })
            success, result_msg = self.fix_violations_vscode(violations)
            logger.info(f"VSCode mode result: success={success}, msg={result_msg}")
            show_dialog(
                "BiliObjCLint",
                result_msg,
                ["确定"],
                icon="note" if success else "stop"
            )
            if not success:
                log_claude_fix_end(False, result_msg, time.time() - self.start_time)
                return 1
            log_claude_fix_end(True, "VSCode opened", time.time() - self.start_time)

        logger.log_separator("Claude Fix Session End")
        return 0

    def run_silent_fix(self, violations: List[Dict]) -> int:
        """
        直接执行静默修复，不显示询问对话框

        用于 Build Phase 脚本已经处理过对话框的情况

        Args:
            violations: 违规列表

        Returns:
            退出码
        """
        self.start_time = time.time()
        logger.log_separator("Claude Silent Fix Start")
        logger.info(f"Silent fix requested for {len(violations)} violations")

        if not violations:
            logger.info("No violations to fix")
            return 0

        self.autofix_tracker.set_flow("skip_dialog")
        self.autofix_tracker.set_decision("fix")
        self.autofix_tracker.set_triggered(True)
        occurred_at = datetime.now().astimezone().isoformat()

        log_claude_fix_start(len(violations), str(self.project_root))

        # 检测 Claude 是否可用
        available, error_msg = self.check_claude_available()
        self.autofix_tracker.set_cli_available(available)
        if not available:
            logger.error(f"Claude not available: {error_msg}")
            print(f"Claude 不可用: {error_msg}", file=sys.stderr)
            log_claude_fix_end(False, error_msg, time.time() - self.start_time)
            self.autofix_tracker.record_action({
                "type": "fix_all",
                "target_count": len(violations),
                "result": "not_available",
                "elapsed_ms": int((time.time() - self.start_time) * 1000),
                "message": error_msg,
            })
            return 1

        # 直接执行修复
        success, result_msg = self.fix_violations_silent(
            violations,
            action_type="fix_all",
            occurred_at=occurred_at,
            flow="skip_dialog",
        )

        elapsed = time.time() - self.start_time
        if success:
            logger.info(f"Silent fix completed in {elapsed:.2f}s")
            print("修复完成")
            log_claude_fix_end(True, "Fix completed", elapsed)
            return 0
        else:
            logger.error(f"Silent fix failed: {result_msg}")
            print(f"修复失败: {result_msg}", file=sys.stderr)
            log_claude_fix_end(False, result_msg, elapsed)
            return 1
