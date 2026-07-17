"""Coordinate safe, Codex-first automatic repair of lint violations."""

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

_SCRIPT_DIR = Path(__file__).parent.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from auto_fix.dialogs import DialogError, show_dialog
from auto_fix.edit_plan import EditPlanError, RepairSession
from auto_fix.html_report import HtmlReportGenerator, open_html_report
from auto_fix.http_server import (
    find_available_port,
    set_all_violations,
    set_fixer_instance,
    set_ignore_cache,
    shutdown_server,
    start_action_server,
    wait_for_user_action,
)
from auto_fix.models import FixViolation, normalize_violations
from auto_fix.prompt_builder import build_fix_prompt
from auto_fix.providers import AutoFixProviderRunner, AutoFixUnavailableError
from auto_fix.scope import resolve_repair_scopes, validate_repair_postconditions
from core.lint.ignore_cache import IgnoreCache
from core.lint.logger import get_logger, log_auto_fix_end, log_auto_fix_start

logger = get_logger("auto_fix")


class AutofixTracker:
    """Collect provider-independent automatic repair metrics."""

    def __init__(self):
        self.enabled = True
        self.trigger = "any"
        self.mode = "silent"
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

    def record_action(self, action: Dict[str, Any]) -> None:
        event = dict(action)
        event.setdefault("occurred_at", datetime.now().astimezone().isoformat())
        event.setdefault("flow", self.flow)
        event.setdefault("include_in_summary", True)
        self.actions.append(event)
        if not event["include_in_summary"]:
            return
        self.summary["attempts"] += 1
        self.summary["target_total"] += int(event.get("target_count", 0))
        if event.get("result") == "success":
            self.summary["success"] += 1
        elif event.get("result") in {"failed", "timeout", "not_available"}:
            self.summary["failed"] += 1
        elif event.get("result") == "cancelled":
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
            "summary": dict(self.summary),
        }


class AutoFixer:
    """Create, validate, apply, and verify a provider-generated repair plan."""

    def __init__(
        self,
        config: dict,
        project_root: str,
        run_id: Optional[str] = None,
        project: Optional[dict] = None,
        provider_runner: Optional[AutoFixProviderRunner] = None,
        verification_runner: Optional[
            Callable[[Sequence[FixViolation]], Tuple[bool, str]]
        ] = None,
        config_path: Optional[str] = None,
    ):
        self.config = config if isinstance(config, dict) else {}
        self.project_root = Path(project_root).resolve()
        self.timeout = 120
        self.start_time: Optional[float] = None
        self.run_id = run_id
        self.project = project or {}
        self.config_path = str(Path(config_path).resolve()) if config_path else None
        self.provider_runner = provider_runner or AutoFixProviderRunner(
            self.project_root, timeout=self.timeout
        )
        self.verification_runner = verification_runner or self._verify_targets
        self.selected_provider: Optional[str] = None
        self._repair_lock = threading.Lock()

        self.metrics_config = self._build_metrics_config(self.config)
        self.project_key = (
            self.project.get("key") or self.metrics_config.project_key or self.project_root.name
        )
        self.project_name = (
            self.project.get("name") or self.metrics_config.project_name or self.project_root.name
        )
        self.tool_version = self._read_version()
        self.autofix_tracker = AutofixTracker()

    def _read_version(self) -> str:
        version_file = _SCRIPT_DIR.parent / "VERSION"
        if version_file.is_file():
            return version_file.read_text(encoding="utf-8").strip()
        return "unknown"

    @staticmethod
    def _build_metrics_config(config: dict):
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
        report = self.autofix_tracker.to_dict()
        report["provider"] = self.selected_provider
        return report

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
        elapsed_ms: Optional[int] = None,
    ) -> None:
        action: Dict[str, Any] = {
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
        if elapsed_ms is not None:
            action["elapsed_ms"] = elapsed_ms
        self.autofix_tracker.record_action(action)

    def check_auto_fix_available(self) -> Tuple[bool, Optional[str]]:
        provider = self.provider_runner.preferred_provider()
        available = provider is not None
        self.autofix_tracker.cli_available = available
        if available:
            self.selected_provider = provider
            return True, None
        return False, "Codex CLI 和 Claude Code CLI 均不可用"

    def fix_violations_silent(
        self,
        violations: List[Dict],
        action_type: str = "fix_all",
        target_rule: Optional[str] = None,
        occurred_at: Optional[str] = None,
        flow: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Serialize repairs so concurrent HTML actions cannot overwrite each other."""
        with self._repair_lock:
            return self._fix_violations_silent(
                violations,
                action_type=action_type,
                target_rule=target_rule,
                occurred_at=occurred_at,
                flow=flow,
            )

    def _fix_violations_silent(
        self,
        violations: List[Dict],
        action_type: str = "fix_all",
        target_rule: Optional[str] = None,
        occurred_at: Optional[str] = None,
        flow: Optional[str] = None,
    ) -> Tuple[bool, str]:
        started = time.time()
        targets, errors = normalize_violations(violations)
        if errors:
            return self._finish_attempt(
                False,
                "修复输入无效: " + "; ".join(errors),
                action_type,
                len(violations),
                started,
                target_rule,
                occurred_at,
                flow,
            )
        if not targets:
            return False, "没有可修复的问题"
        targets = resolve_repair_scopes(targets)

        try:
            session = RepairSession(targets)
            prompt = build_fix_prompt(targets)
            provider_result = self.provider_runner.run(prompt)
            self.selected_provider = provider_result.provider
            apply_result = session.apply(provider_result.plan)
            if apply_result.applied_edits == 0:
                return self._finish_attempt(
                    False,
                    "未生成可应用的修改",
                    action_type,
                    len(targets),
                    started,
                    target_rule,
                    occurred_at,
                    flow,
                )

            try:
                postconditions_valid, postcondition_message = validate_repair_postconditions(targets)
            except Exception as error:
                try:
                    session.rollback()
                except Exception as rollback_error:
                    return self._finish_attempt(
                        False,
                        f"修复完整性验证异常且回滚失败: {error}; {rollback_error}",
                        action_type,
                        len(targets),
                        started,
                        target_rule,
                        occurred_at,
                        flow,
                    )
                return self._finish_attempt(
                    False,
                    f"修复完整性验证异常，已回滚: {error}",
                    action_type,
                    len(targets),
                    started,
                    target_rule,
                    occurred_at,
                    flow,
                )
            if not postconditions_valid:
                session.rollback()
                return self._finish_attempt(
                    False,
                    f"修复完整性验证失败，已回滚: {postcondition_message}",
                    action_type,
                    len(targets),
                    started,
                    target_rule,
                    occurred_at,
                    flow,
                )

            try:
                verified, verification_message = self.verification_runner(targets)
            except Exception as error:
                try:
                    session.rollback()
                except Exception as rollback_error:
                    return self._finish_attempt(
                        False,
                        f"修复验证异常且回滚失败: {error}; {rollback_error}",
                        action_type,
                        len(targets),
                        started,
                        target_rule,
                        occurred_at,
                        flow,
                    )
                return self._finish_attempt(
                    False,
                    f"修复验证异常，已回滚: {error}",
                    action_type,
                    len(targets),
                    started,
                    target_rule,
                    occurred_at,
                    flow,
                )
            if not verified:
                session.rollback()
                return self._finish_attempt(
                    False,
                    f"修复验证失败，已回滚: {verification_message}",
                    action_type,
                    len(targets),
                    started,
                    target_rule,
                    occurred_at,
                    flow,
                )

            provider_label = "Codex" if provider_result.provider == "codex" else "Claude"
            message = (
                f"{provider_label} 已验证修复 {apply_result.applied_edits} 处修改"
                f"（{apply_result.affected_files} 个文件）"
            )
            return self._finish_attempt(
                True,
                message,
                action_type,
                len(targets),
                started,
                target_rule,
                occurred_at,
                flow,
            )
        except AutoFixUnavailableError as error:
            return self._finish_attempt(
                False, str(error), action_type, len(targets), started,
                target_rule, occurred_at, flow, result="not_available"
            )
        except (EditPlanError, ValueError, OSError, UnicodeError) as error:
            return self._finish_attempt(
                False, f"修复计划无效: {error}", action_type, len(targets), started,
                target_rule, occurred_at, flow
            )
        except Exception as error:
            logger.exception(f"Automatic repair failed: {error}")
            return self._finish_attempt(
                False, f"修复异常: {error}", action_type, len(targets), started,
                target_rule, occurred_at, flow
            )

    def _finish_attempt(
        self,
        success: bool,
        message: str,
        action_type: str,
        target_count: int,
        started: float,
        target_rule: Optional[str],
        occurred_at: Optional[str],
        flow: Optional[str],
        result: Optional[str] = None,
    ) -> Tuple[bool, str]:
        self.record_autofix_action(
            action_type=action_type,
            result=result or ("success" if success else "failed"),
            target_count=target_count,
            message=message,
            flow=flow,
            target_rule=target_rule,
            occurred_at=occurred_at,
            elapsed_ms=int((time.time() - started) * 1000),
        )
        return success, message

    def _verify_targets(self, targets: Sequence[FixViolation]) -> Tuple[bool, str]:
        linter = _SCRIPT_DIR / "wrapper" / "lint" / "cli.py"
        command = [
            sys.executable,
            str(linter),
            "--project-root",
            str(self.project_root),
            "--files",
            *sorted({target.file_path for target in targets}),
            "--json-output",
        ]
        if self.config_path and Path(self.config_path).is_file():
            command[2:2] = ["--config", self.config_path]

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.project_root),
            )
        except subprocess.TimeoutExpired:
            return False, f"lint 验证超时（{self.timeout} 秒）"
        if completed.returncode not in {0, 1}:
            detail = (completed.stderr or completed.stdout or "unknown error").strip()
            return False, f"lint 验证执行失败: {detail}"
        try:
            payload = json.loads(completed.stdout)
            remaining = payload["violations"]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            return False, f"lint 验证结果无效: {error}"

        for target in targets:
            if any(self._matches_target(item, target) for item in remaining):
                return False, f"目标问题仍存在: {target.violation_id}"
        return True, "目标问题已消除"

    @staticmethod
    def _matches_target(item: Dict[str, Any], target: FixViolation) -> bool:
        try:
            item_file = str(Path(item.get("file_path", "")).expanduser().resolve())
        except (OSError, TypeError):
            return False
        if item.get("violation_id") == target.violation_id:
            return True
        if item_file != target.file_path or item.get("rule_id") != target.rule_id:
            return False
        if (item.get("sub_type") or None) != target.sub_type:
            return False
        related = item.get("related_lines")
        if isinstance(related, list) and len(related) == 2:
            return related[0] <= target.related_lines[1] and target.related_lines[0] <= related[1]
        line = item.get("line")
        return isinstance(line, int) and target.related_lines[0] <= line <= target.related_lines[1]

    def ignore_all_violations(
        self,
        violations: List[Dict],
        ignore_cache: Optional[IgnoreCache] = None,
        flow: str = "dialog",
        occurred_at: Optional[str] = None,
    ) -> Tuple[bool, str, int, int]:
        cache = ignore_cache or IgnoreCache(project_root=str(self.project_root))
        ignored = 0
        failed = 0
        for item in violations:
            if hasattr(item, "file_path"):
                file_path, line, rule, message, related_lines = (
                    item.file_path, item.line, item.rule_id, item.message, item.related_lines
                )
            else:
                file_path = item.get("file_path") or item.get("file") or ""
                line = item.get("line", 0)
                rule = item.get("rule_id") or item.get("rule") or ""
                message = item.get("message", "")
                related_lines = item.get("related_lines")
            if not file_path or not line or not rule or not related_lines:
                failed += 1
                continue
            try:
                if cache.add_ignore_from_request(
                    file_path, line, rule, message, tuple(related_lines)
                ):
                    ignored += 1
                else:
                    failed += 1
            except Exception as error:
                logger.warning(f"Failed to ignore violation: {error}")
                failed += 1

        total = len(violations)
        success = ignored > 0
        message = f"已忽略 {ignored}/{total} 个问题" if success else f"所有 {total} 个问题忽略失败"
        self.record_autofix_action(
            "ignore_all", "success" if success else "failed", total, message,
            flow=flow, occurred_at=occurred_at
        )
        return success, message, ignored, failed

    def run(self, violations: List[Dict]) -> int:
        self.start_time = time.time()
        if not violations:
            return 0
        self.autofix_tracker.triggered = True
        log_auto_fix_start(len(violations), str(self.project_root))
        available, error_message = self.check_auto_fix_available()
        if not available:
            self.autofix_tracker.decision = "not_available"
            self.record_autofix_action(
                "fix_all", "not_available", len(violations), error_message or "unavailable"
            )
            show_dialog(
                "BiliObjCLint", f"无法使用自动修复\n\n{error_message}", ["确定"], icon="stop"
            )
            log_auto_fix_end(False, error_message or "unavailable", time.time() - self.start_time)
            return 1

        error_count = sum(1 for item in violations if item.get("severity") == "error")
        warning_count = len(violations) - error_count
        self.autofix_tracker.flow = "dialog"
        try:
            result = show_dialog(
                "BiliObjCLint",
                f"发现 {len(violations)} 个代码问题\n（{error_count} errors, {warning_count} warnings）\n\n查看详情后可执行忽略或自动修复。",
                ["取消", "查看详情"],
                icon="caution",
                raise_on_error=True,
            )
        except DialogError:
            result = "查看详情"

        if not result or result == "取消":
            self.autofix_tracker.decision = "cancel"
            self.record_autofix_action("cancel", "cancelled", len(violations), "User cancelled")
            log_auto_fix_end(False, "User cancelled", time.time() - self.start_time)
            return 0

        self.record_autofix_action(
            "view_detail", "success", len(violations), "User opened HTML details",
            include_in_summary=False
        )
        self.autofix_tracker.flow = "html"
        action = self._show_html_report_and_wait(violations)
        self.autofix_tracker.decision = action or "timeout"
        log_auto_fix_end(action == "done", action or "timeout", time.time() - self.start_time)
        return 0

    def _show_html_report_and_wait(self, violations: List[Dict]) -> Optional[str]:
        report_path: Optional[str] = None
        server = None
        set_ignore_cache(IgnoreCache(project_root=str(self.project_root)))
        set_fixer_instance(self)
        set_all_violations(violations)
        try:
            port = find_available_port()
            server = start_action_server(port)
            report_path = HtmlReportGenerator(self.project_root).generate(violations, port=port)
            open_html_report(report_path)
            return wait_for_user_action(server, timeout=300)
        finally:
            if server:
                shutdown_server(server)
            if report_path:
                try:
                    Path(report_path).unlink()
                except OSError:
                    pass

    def run_silent_fix(self, violations: List[Dict]) -> int:
        self.start_time = time.time()
        if not violations:
            return 0
        self.autofix_tracker.flow = "skip_dialog"
        self.autofix_tracker.decision = "fix"
        self.autofix_tracker.triggered = True
        log_auto_fix_start(len(violations), str(self.project_root))
        available, error_message = self.check_auto_fix_available()
        if not available:
            self.record_autofix_action(
                "fix_all", "not_available", len(violations), error_message or "unavailable"
            )
            print(f"自动修复不可用: {error_message}", file=sys.stderr)
            log_auto_fix_end(False, error_message or "unavailable", time.time() - self.start_time)
            return 1
        success, message = self.fix_violations_silent(violations, flow="skip_dialog")
        print(message, file=sys.stdout if success else sys.stderr)
        log_auto_fix_end(success, message, time.time() - self.start_time)
        return 0 if success else 1
