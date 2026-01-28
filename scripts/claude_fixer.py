#!/usr/bin/env python3
"""
Claude 自动修复模块

功能：
- 检测 Claude Code CLI 是否可用
- 显示 macOS 原生对话框
- 调用 Claude Code 修复代码违规

Usage:
    python3 claude_fixer.py --violations <file> --config <config> --project-root <path>
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
import threading
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Tuple, Optional, List, Dict

# 添加 scripts 目录到路径
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from core.logger import get_logger, LogContext, log_claude_fix_start, log_claude_fix_end


# 全局变量用于 HTTP 服务器通信
_user_action = None
_server_should_stop = False


class ActionRequestHandler(BaseHTTPRequestHandler):
    """处理来自 HTML 页面的用户操作请求"""

    def log_message(self, format, *args):
        """禁止默认的 HTTP 日志输出"""
        pass

    def do_GET(self):
        global _user_action, _server_should_stop

        if self.path == '/fix':
            _user_action = 'fix'
            _server_should_stop = True
            self._send_response("正在启动自动修复...")
        elif self.path == '/cancel':
            _user_action = 'cancel'
            _server_should_stop = True
            self._send_response("已取消")
        elif self.path == '/status':
            self._send_response("running")
        else:
            self.send_error(404)

    def _send_response(self, message: str):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        html = f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>BiliObjCLint</title>
<style>
body {{ font-family: -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #f5f5f5; }}
.message {{ text-align: center; padding: 40px; background: white; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
@media (prefers-color-scheme: dark) {{ body {{ background: #1a1a2e; }} .message {{ background: #16213e; color: #e0e0e0; }} }}
</style></head>
<body><div class="message"><h2>{message}</h2><p>可以关闭此页面</p></div></body></html>'''
        self.wfile.write(html.encode('utf-8'))


class ClaudeFixer:
    """Claude 自动修复器"""

    def __init__(self, config: dict, project_root: str):
        self.config = config
        self.project_root = Path(project_root).resolve()
        self.autofix_config = config.get('claude_autofix', {})
        self.trigger = self.autofix_config.get('trigger', 'any')
        self.mode = self.autofix_config.get('mode', 'silent')
        self.timeout = self.autofix_config.get('timeout', 120)
        self.logger = get_logger("claude_fix")
        self.start_time = None

        self.logger.debug(f"ClaudeFixer initialized: project_root={self.project_root}")
        self.logger.debug(f"Config: trigger={self.trigger}, mode={self.mode}, timeout={self.timeout}")

    def _find_claude_path(self) -> Optional[str]:
        """
        查找 claude CLI 的完整路径

        Returns:
            claude 的完整路径，如果找不到返回 None
        """
        self.logger.debug("Searching for Claude CLI path...")

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
                self.logger.debug(f"Found Claude CLI at: {path}")
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
            self.logger.debug(f"Found Claude CLI via which: {path}")
            return path

        self.logger.warning("Claude CLI not found in any known path")
        return None

    def _load_shell_env(self) -> Dict[str, str]:
        """
        从用户的 shell 配置文件读取环境变量

        Xcode Build Phase 后台进程不会加载 .zshrc/.bashrc，
        需要手动读取相关的 ANTHROPIC_* 等环境变量

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

        import re
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
                                self.logger.debug(f"Loaded env from {config_file}: {key}={value[:20]}...")
            except Exception as e:
                self.logger.warning(f"Failed to read {config_file}: {e}")

        if env_vars:
            self.logger.info(f"Loaded {len(env_vars)} env vars from shell config")
        else:
            self.logger.warning("No ANTHROPIC_*/CLAUDE_* env vars found in shell config")

        return env_vars

    def check_claude_available(self) -> Tuple[bool, Optional[str]]:
        """
        检测 Claude Code CLI 是否可用

        Returns:
            (is_available, error_message)
        """
        self.logger.info("Checking Claude CLI availability...")

        # 调试日志
        with open("/tmp/biliobjclint_debug.log", "a") as f:
            f.write("check_claude_available: start\n")

        # 1. 查找 claude 路径
        claude_path = self._find_claude_path()

        with open("/tmp/biliobjclint_debug.log", "a") as f:
            f.write(f"check_claude_available: claude_path={claude_path}\n")

        if not claude_path:
            self.logger.error("Claude CLI not installed")
            return False, "Claude Code CLI 未安装\n请访问 https://claude.ai/code 安装"

        # 保存路径供后续使用
        self._claude_path = claude_path
        self.logger.debug(f"Using Claude CLI at: {claude_path}")

        # 2. 跳过验证，直接认为可用（验证可能会卡住）
        # 如果实际修复时失败，会在那时报错
        with open("/tmp/biliobjclint_debug.log", "a") as f:
            f.write("check_claude_available: skipping verification, assuming available\n")

        self.logger.info("Claude CLI found, skipping verification")
        return True, None

    def show_dialog(self, title: str, message: str, buttons: List[str],
                    default_button: str = None, icon: str = "caution") -> Optional[str]:
        """
        显示 macOS 原生对话框

        Args:
            title: 对话框标题
            message: 消息内容
            buttons: 按钮列表
            default_button: 默认按钮
            icon: 图标类型 (stop, note, caution)

        Returns:
            用户点击的按钮名称，如果取消则返回 None
        """
        if default_button is None:
            default_button = buttons[-1]

        buttons_str = ', '.join(f'"{b}"' for b in buttons)

        # 处理消息中的换行符，使用 AppleScript 的 return 关键字
        # AppleScript 不支持 \ 续行符，必须在单行中构建
        escaped_message = message.replace('\n', '" & return & "')

        # 构建单行 AppleScript 命令（AppleScript 不支持 \ 续行符）
        script = f'display dialog "{escaped_message}" buttons {{{buttons_str}}} default button "{default_button}" with title "{title}" with icon {icon}'

        try:
            self.logger.debug(f"Showing dialog: {title}")
            self.logger.debug(f"AppleScript: {script}")
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True
            )
            self.logger.debug(f"Dialog result: returncode={result.returncode}, stdout={result.stdout}, stderr={result.stderr}")
            if result.returncode == 0:
                # 解析返回值，格式为 "button returned:按钮名"
                output = result.stdout.strip()
                if 'button returned:' in output:
                    return output.split('button returned:')[1].strip()
            return None
        except Exception as e:
            self.logger.exception(f"Dialog exception: {e}")
            return None

    def show_progress_notification(self, message: str) -> subprocess.Popen:
        """
        显示进度通知（非阻塞的通知横幅）

        Returns:
            进程对象，可用于后续关闭
        """
        script = f'''
        display notification "{message}" with title "BiliObjCLint" subtitle "Claude 自动修复"
        '''
        return subprocess.Popen(
            ['osascript', '-e', script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    def show_progress_dialog(self, message: str) -> subprocess.Popen:
        """
        显示进度对话框（带进度指示的对话框）

        使用 AppleScript 的 progress 特性显示一个模态进度窗口

        Returns:
            进程对象
        """
        # 使用一个简单的弹窗来显示进度状态
        # 注意：真正的进度条需要 Cocoa 应用，这里使用简化方案
        script = f'''
        tell application "System Events"
            display dialog "{message}" \\
                buttons {{"请稍候..."}} \\
                default button 1 \\
                with title "BiliObjCLint - Claude 修复中" \\
                with icon note \\
                giving up after 300
        end tell
        '''
        return subprocess.Popen(
            ['osascript', '-e', script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    def generate_html_report(self, violations: List[Dict], port: int = None) -> str:
        """
        生成 HTML 格式的违规报告

        Args:
            violations: 违规列表
            port: 本地服务器端口，如果提供则添加交互按钮

        Returns:
            HTML 文件路径
        """
        # 按文件分组
        by_file = {}
        for v in violations:
            file_path = v.get('file', '')
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append(v)

        # 统计
        error_count = sum(1 for v in violations if v.get('severity') == 'error')
        warning_count = len(violations) - error_count

        # 生成 HTML
        html_parts = ['''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BiliObjCLint - 代码问题报告</title>
    <style>
        :root {
            --bg-color: #ffffff;
            --text-color: #333333;
            --card-bg: #f8f9fa;
            --border-color: #e9ecef;
            --error-bg: #fff5f5;
            --error-border: #fc8181;
            --error-text: #c53030;
            --warning-bg: #fffaf0;
            --warning-border: #f6ad55;
            --warning-text: #c05621;
            --code-bg: #f1f3f5;
        }
        @media (prefers-color-scheme: dark) {
            :root {
                --bg-color: #1a1a2e;
                --text-color: #e0e0e0;
                --card-bg: #16213e;
                --border-color: #0f3460;
                --error-bg: #2d1f1f;
                --error-border: #c53030;
                --error-text: #fc8181;
                --warning-bg: #2d2a1f;
                --warning-border: #c05621;
                --warning-text: #f6ad55;
                --code-bg: #0f3460;
            }
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg-color);
            color: var(--text-color);
            line-height: 1.6;
            padding: 20px;
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            font-size: 24px;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .summary {
            font-size: 16px;
            color: var(--text-color);
            opacity: 0.8;
            margin-bottom: 30px;
        }
        .error-badge {
            background: var(--error-text);
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 14px;
        }
        .warning-badge {
            background: var(--warning-text);
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 14px;
        }
        .file-section {
            margin-bottom: 24px;
        }
        .file-header {
            font-size: 16px;
            font-weight: 600;
            padding: 12px 16px;
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px 8px 0 0;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .file-path {
            font-family: "SF Mono", Monaco, monospace;
            font-size: 14px;
            word-break: break-all;
        }
        .violations-list {
            border: 1px solid var(--border-color);
            border-top: none;
            border-radius: 0 0 8px 8px;
        }
        .violation {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            align-items: flex-start;
        }
        .violation:last-child {
            border-bottom: none;
            border-radius: 0 0 8px 8px;
        }
        .violation.error {
            background: var(--error-bg);
        }
        .violation.warning {
            background: var(--warning-bg);
        }
        .line-num {
            font-family: "SF Mono", Monaco, monospace;
            font-size: 13px;
            background: var(--code-bg);
            padding: 2px 8px;
            border-radius: 4px;
            white-space: nowrap;
        }
        .severity {
            font-size: 12px;
            font-weight: 600;
            padding: 2px 6px;
            border-radius: 4px;
            text-transform: uppercase;
        }
        .severity.error {
            background: var(--error-border);
            color: white;
        }
        .severity.warning {
            background: var(--warning-border);
            color: white;
        }
        .message {
            flex: 1;
            min-width: 200px;
        }
        .rule {
            font-family: "SF Mono", Monaco, monospace;
            font-size: 12px;
            color: var(--text-color);
            opacity: 0.6;
            background: var(--code-bg);
            padding: 2px 6px;
            border-radius: 4px;
        }
        .footer {
            margin-top: 30px;
            text-align: center;
            font-size: 12px;
            opacity: 0.6;
        }
        .action-bar {
            position: sticky;
            top: 0;
            background: var(--bg-color);
            padding: 16px 0;
            margin-bottom: 20px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: center;
            gap: 16px;
            z-index: 100;
        }
        .btn {
            padding: 12px 32px;
            font-size: 16px;
            font-weight: 600;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        .btn:active {
            transform: translateY(0);
        }
        .btn-cancel {
            background: var(--card-bg);
            color: var(--text-color);
            border: 1px solid var(--border-color);
        }
        .btn-fix {
            background: #4CAF50;
            color: white;
        }
        .btn-fix:hover {
            background: #43A047;
        }
        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        .notice-box {
            background: linear-gradient(135deg, #fff8e1 0%, #ffecb3 100%);
            border: 1px solid #ffc107;
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 24px;
            display: flex;
            align-items: flex-start;
            gap: 12px;
            box-shadow: 0 2px 8px rgba(255, 193, 7, 0.15);
        }
        .notice-box .icon {
            font-size: 24px;
            flex-shrink: 0;
            margin-top: 2px;
        }
        .notice-box .content {
            flex: 1;
        }
        .notice-box .title {
            font-weight: 600;
            font-size: 15px;
            color: #8d6e00;
            margin-bottom: 6px;
        }
        .notice-box .desc {
            font-size: 13px;
            color: #6d5600;
            line-height: 1.5;
        }
        @media (prefers-color-scheme: dark) {
            .notice-box {
                background: linear-gradient(135deg, #3d3200 0%, #2d2500 100%);
                border-color: #b38f00;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
            }
            .notice-box .title {
                color: #ffd54f;
            }
            .notice-box .desc {
                color: #ffcc80;
            }
        }
    </style>
</head>
<body>
    <h1>🔍 BiliObjCLint 代码问题报告</h1>
    <p class="summary">
        发现 <strong>''', str(len(violations)), '''</strong> 个问题
        ''']

        # 如果提供了端口，添加交互按钮和提示
        if port:
            html_parts.append(f'''
    </p>
    <div class="action-bar">
        <button class="btn btn-cancel" onclick="doAction('cancel')" id="btn-cancel">取消</button>
        <button class="btn btn-fix" onclick="doAction('fix')" id="btn-fix">🔧 自动修复</button>
    </div>
    <div class="notice-box">
        <span class="icon">⏳</span>
        <div class="content">
            <div class="title">Xcode 正在等待您的操作</div>
            <div class="desc">请查阅上方的代码审查结果，然后点击「取消」或「自动修复」继续。在您做出选择之前，Xcode 编译进程将保持等待状态。</div>
        </div>
    </div>
    <p class="summary">
        ''')
        else:
            html_parts.append('')  # 保持结构一致

        if error_count > 0:
            html_parts.append(f'<span class="error-badge">{error_count} errors</span> ')
        if warning_count > 0:
            html_parts.append(f'<span class="warning-badge">{warning_count} warnings</span>')

        html_parts.append('</p>')

        # 按文件输出违规
        for file_path, file_violations in by_file.items():
            # 获取相对路径用于显示
            try:
                display_path = str(Path(file_path).relative_to(self.project_root))
            except ValueError:
                display_path = file_path

            html_parts.append(f'''
    <div class="file-section">
        <div class="file-header">
            <span>📄</span>
            <span class="file-path">{display_path}</span>
        </div>
        <div class="violations-list">''')

            for v in sorted(file_violations, key=lambda x: x.get('line', 0)):
                severity = v.get('severity', 'warning')
                line = v.get('line', 0)
                message = v.get('message', '')
                rule = v.get('rule', '')

                html_parts.append(f'''
            <div class="violation {severity}">
                <span class="line-num">Line {line}</span>
                <span class="severity {severity}">{severity}</span>
                <span class="message">{message}</span>
                <span class="rule">{rule}</span>
            </div>''')

            html_parts.append('''
        </div>
    </div>''')

        # 添加 JavaScript（仅当有端口时）
        if port:
            html_parts.append(f'''
    <div class="footer">
        Generated by BiliObjCLint
    </div>
    <script>
        const SERVER_PORT = {port};
        let actionSent = false;

        async function doAction(action) {{
            if (actionSent) return;
            actionSent = true;

            const btnCancel = document.getElementById('btn-cancel');
            const btnFix = document.getElementById('btn-fix');
            btnCancel.disabled = true;
            btnFix.disabled = true;

            if (action === 'fix') {{
                btnFix.textContent = '正在启动修复...';
            }}

            try {{
                const response = await fetch(`http://localhost:${{SERVER_PORT}}/${{action}}`);
                if (response.ok) {{
                    // 请求成功，页面会自动跳转到结果页
                }}
            }} catch (e) {{
                console.error('请求失败:', e);
                alert('操作失败，请重试');
                actionSent = false;
                btnCancel.disabled = false;
                btnFix.disabled = false;
                btnFix.textContent = '🔧 自动修复';
            }}
        }}
    </script>
</body>
</html>''')
        else:
            html_parts.append('''
    <div class="footer">
        Generated by BiliObjCLint
    </div>
</body>
</html>''')

        # 写入临时文件
        html_content = ''.join(html_parts)
        report_path = '/tmp/biliobjclint_report.html'
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        self.logger.debug(f"Generated HTML report: {report_path}")
        return report_path

    def open_html_report(self, report_path: str):
        """
        在浏览器中打开 HTML 报告

        Args:
            report_path: HTML 文件路径
        """
        try:
            subprocess.run(['open', report_path], check=True)
            self.logger.debug(f"Opened HTML report in browser: {report_path}")
        except Exception as e:
            self.logger.error(f"Failed to open HTML report: {e}")

    def _find_available_port(self) -> int:
        """找到一个可用的端口"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('localhost', 0))
            return s.getsockname()[1]

    def _start_action_server(self, port: int) -> HTTPServer:
        """
        启动本地 HTTP 服务器监听用户操作

        Args:
            port: 监听端口

        Returns:
            HTTPServer 实例
        """
        server = HTTPServer(('localhost', port), ActionRequestHandler)
        server.timeout = 1  # 设置超时以便检查停止标志
        self.logger.debug(f"Started action server on port {port}")
        return server

    def _wait_for_user_action(self, server: HTTPServer, timeout: int = 300) -> Optional[str]:
        """
        等待用户在浏览器中的操作

        Args:
            server: HTTPServer 实例
            timeout: 超时时间（秒）

        Returns:
            用户操作 ('fix', 'cancel') 或 None（超时）
        """
        global _user_action, _server_should_stop
        _user_action = None
        _server_should_stop = False

        start_time = time.time()
        while not _server_should_stop:
            if time.time() - start_time > timeout:
                self.logger.warning(f"Action server timed out after {timeout}s")
                return None
            try:
                server.handle_request()
            except Exception as e:
                self.logger.warning(f"Server error: {e}")
                break

        return _user_action

    def _shutdown_server(self, server: HTTPServer):
        """关闭 HTTP 服务器"""
        if server:
            try:
                server.server_close()
                self.logger.debug("Action server shut down")
            except Exception as e:
                self.logger.warning(f"Error shutting down server: {e}")

    def cleanup_temp_files(self, *paths):
        """
        清理临时文件

        Args:
            paths: 要删除的文件路径列表
        """
        for path in paths:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                    self.logger.debug(f"Cleaned up temp file: {path}")
                except Exception as e:
                    self.logger.warning(f"Failed to cleanup temp file {path}: {e}")

    def build_fix_prompt(self, violations: List[Dict]) -> str:
        """
        构建修复 prompt

        Args:
            violations: 违规列表

        Returns:
            发送给 Claude 的 prompt
        """
        # 按文件分组
        by_file = {}
        for v in violations:
            file_path = v.get('file', '')
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append(v)

        prompt_parts = [
            "请修复以下 Objective-C 代码问题。",
            "",
            "## 违规列表",
            ""
        ]

        for file_path, file_violations in by_file.items():
            prompt_parts.append(f"### {file_path}")
            for v in file_violations:
                line = v.get('line', 0)
                severity = v.get('severity', 'warning')
                message = v.get('message', '')
                rule = v.get('rule', '')
                prompt_parts.append(f"- 行 {line} [{severity}] {message} ({rule})")
            prompt_parts.append("")

        prompt_parts.extend([
            "## 修复规则说明",
            "",
            "- **weak_delegate**: delegate/dataSource 属性应使用 weak 修饰，避免循环引用",
            "- **property_naming**: 属性名应使用 camelCase（小写字母开头）",
            "- **method_naming**: 方法名应以小写字母开头",
            "- **block_retain_cycle**: 在 block 中使用 self 前应声明 `__weak typeof(self) weakSelf = self;`",
            "- **hardcoded_credentials**: 移除硬编码的密码/密钥/token",
            "- **todo_fixme**: 处理或移除 TODO/FIXME 注释",
            "- **line_length**: 将超长行拆分为多行（每行不超过 120 字符）",
            "- **method_length**: 将过长方法拆分为多个小方法（每个方法不超过 80 行）",
            "- **constant_naming**: 常量应以 k 前缀开头或使用全大写",
            "",
            "请直接使用 Edit 工具修改文件，不需要解释。",
        ])

        return "\n".join(prompt_parts)

    def fix_violations_silent(self, violations: List[Dict]) -> Tuple[bool, str]:
        """
        静默模式修复违规

        Returns:
            (success, message)
        """
        self.logger.info(f"Starting silent fix for {len(violations)} violations")
        fix_start_time = time.time()

        prompt = self.build_fix_prompt(violations)
        self.logger.debug(f"Generated fix prompt ({len(prompt)} chars)")

        # 获取 claude 路径
        claude_path = getattr(self, '_claude_path', None)
        if not claude_path:
            claude_path = self._find_claude_path()
            if not claude_path:
                self.logger.error("Claude CLI path not found for fix")
                return False, "Claude Code CLI 未找到"

        # 将 prompt 写入临时文件以避免命令行长度限制
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(prompt)
            prompt_file = f.name
        self.logger.debug(f"Prompt written to temp file: {prompt_file}")

        try:
            # 每次创建新的 session ID，避免与其他 Claude 会话冲突
            session_id = str(uuid.uuid4())
            self.logger.info(f"Executing Claude fix (timeout={self.timeout}s, session={session_id[:8]}...)...")

            # 构建环境变量，从用户的 shell 配置文件读取 ANTHROPIC_* 变量
            # Xcode Build Phase 后台进程不会加载 .zshrc/.bashrc
            env = os.environ.copy()
            env.update(self._load_shell_env())

            # 使用 -p 非交互模式执行修复
            # --session-id: 使用独立的会话 ID，避免冲突
            # --no-session-persistence: 不保存会话到磁盘
            result = subprocess.run(
                [
                    claude_path,
                    '-p', prompt,
                    '--allowedTools', 'Read,Edit',
                    '--session-id', session_id,
                    '--no-session-persistence'
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.project_root),
                env=env
            )

            elapsed = time.time() - fix_start_time
            if result.returncode == 0:
                self.logger.info(f"Fix completed successfully in {elapsed:.2f}s")
                self.logger.debug(f"Claude stdout: {result.stdout[:500]}..." if len(result.stdout) > 500 else f"Claude stdout: {result.stdout}")
                return True, "修复完成"
            else:
                # 错误信息可能在 stdout 或 stderr 中
                error_output = result.stderr.strip() or result.stdout.strip() or f"退出码 {result.returncode}"
                self.logger.error(f"Fix failed (exit code {result.returncode})")
                self.logger.error(f"stderr: {result.stderr}")
                self.logger.error(f"stdout: {result.stdout}")
                return False, f"修复失败: {error_output}"

        except subprocess.TimeoutExpired:
            elapsed = time.time() - fix_start_time
            self.logger.error(f"Fix timed out after {elapsed:.2f}s (limit: {self.timeout}s)")
            return False, f"修复超时（{self.timeout}秒）"
        except Exception as e:
            self.logger.exception(f"Fix exception: {e}")
            return False, f"修复异常: {e}"
        finally:
            # 清理临时文件
            try:
                os.unlink(prompt_file)
                self.logger.debug(f"Cleaned up temp file: {prompt_file}")
            except:
                pass

    def fix_violations_terminal(self, violations: List[Dict]) -> Tuple[bool, str]:
        """
        终端模式修复违规 - 打开 Terminal.app 与 Claude 交互

        Returns:
            (success, message)
        """
        prompt = self.build_fix_prompt(violations)

        # 将 prompt 写入临时文件
        prompt_file = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.txt',
            delete=False,
            prefix='claude_fix_'
        )
        prompt_file.write(prompt)
        prompt_file.close()

        # 使用 AppleScript 打开 Terminal 并执行 claude
        # 需要添加 --allowedTools 参数允许读写文件
        script = f'''
        tell application "Terminal"
            activate
            do script "echo '🔧 正在修复中，不要关闭本窗口...' && echo '' && cd '{self.project_root}' && claude -p \\"$(cat '{prompt_file.name}')\\" --allowedTools Read,Edit && rm -f '{prompt_file.name}' && echo '' && echo '✅ 修复完成！'"
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
        prompt = self.build_fix_prompt(violations)

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

    def run(self, violations: List[Dict]) -> int:
        """
        执行修复流程

        Args:
            violations: 违规列表

        Returns:
            退出码
        """
        self.start_time = time.time()
        self.logger.log_separator("Claude Fix Session Start")

        if not violations:
            self.logger.info("No violations to fix")
            return 0

        # 检查是否应该触发
        should = self.should_trigger(violations)
        with open("/tmp/biliobjclint_debug.log", "a") as f:
            f.write(f"should_trigger: {should}, trigger_mode={self.trigger}\n")
        if not should:
            self.logger.info(f"Trigger condition not met (trigger={self.trigger})")
            return 0

        # 统计
        error_count = sum(1 for v in violations if v.get('severity') == 'error')
        warning_count = len(violations) - error_count
        log_claude_fix_start(len(violations), str(self.project_root))
        self.logger.info(f"Violations: {len(violations)} total ({error_count} errors, {warning_count} warnings)")

        # 检测 Claude 是否可用
        available, error_msg = self.check_claude_available()
        if not available:
            self.logger.error(f"Claude not available: {error_msg}")
            self.show_dialog(
                "BiliObjCLint",
                f"无法使用 Claude 自动修复\n\n{error_msg}",
                ["确定"],
                icon="stop"
            )
            log_claude_fix_end(False, error_msg, time.time() - self.start_time)
            return 1

        # 启动本地服务器并显示 HTML 报告
        html_report_path = None
        server = None
        server_port = None
        user_action = None

        try:
            # 找到可用端口并启动服务器
            server_port = self._find_available_port()
            server = self._start_action_server(server_port)

            self.logger.info(f"Started action server on port {server_port}")

            # 生成带按钮的 HTML 报告
            html_report_path = self.generate_html_report(violations, port=server_port)

            # 调试日志
            with open("/tmp/biliobjclint_debug.log", "a") as f:
                f.write(f"Opening HTML report with interactive buttons, port={server_port}\n")

            # 在浏览器中打开报告
            self.open_html_report(html_report_path)

            # 等待用户操作（超时 5 分钟）
            self.logger.info("Waiting for user action in browser...")
            user_action = self._wait_for_user_action(server, timeout=300)

            # 调试：记录用户操作结果
            with open("/tmp/biliobjclint_debug.log", "a") as f:
                f.write(f"User action: {user_action}\n")

            if user_action == 'cancel' or user_action is None:
                self.logger.info("User cancelled or timed out")
                log_claude_fix_end(False, "User cancelled", time.time() - self.start_time)
                return 0

            # user_action == 'fix'
            self.logger.info(f"User confirmed fix, mode={self.mode}")

            # 根据模式执行修复
            if self.mode == 'silent':
                # 显示进度通知
                self.show_progress_notification("Claude 正在修复代码问题...")

                # 执行修复
                success, result_msg = self.fix_violations_silent(violations)

                # 显示结果
                if success:
                    self.logger.info("Fix completed successfully")
                    self.show_dialog(
                        "BiliObjCLint",
                        f"Claude 已完成修复！\n\n请重新编译以验证修复结果",
                        ["确定"],
                        icon="note"
                    )
                    log_claude_fix_end(True, "Fix completed", time.time() - self.start_time)
                else:
                    self.logger.error(f"Fix failed: {result_msg}")
                    self.show_dialog(
                        "BiliObjCLint",
                        f"修复过程中出现问题\n\n{result_msg}",
                        ["确定"],
                        icon="stop"
                    )
                    log_claude_fix_end(False, result_msg, time.time() - self.start_time)
                    return 1

            elif self.mode == 'terminal':
                success, result_msg = self.fix_violations_terminal(violations)
                self.logger.info(f"Terminal mode result: success={success}, msg={result_msg}")
                if not success:
                    self.show_dialog(
                        "BiliObjCLint",
                        result_msg,
                        ["确定"],
                        icon="stop"
                    )
                    log_claude_fix_end(False, result_msg, time.time() - self.start_time)
                    return 1
                log_claude_fix_end(True, "Terminal opened", time.time() - self.start_time)

            elif self.mode == 'vscode':
                success, result_msg = self.fix_violations_vscode(violations)
                self.logger.info(f"VSCode mode result: success={success}, msg={result_msg}")
                self.show_dialog(
                    "BiliObjCLint",
                    result_msg,
                    ["确定"],
                    icon="note" if success else "stop"
                )
                if not success:
                    log_claude_fix_end(False, result_msg, time.time() - self.start_time)
                    return 1
                log_claude_fix_end(True, "VSCode opened", time.time() - self.start_time)

            self.logger.log_separator("Claude Fix Session End")
            return 0

        finally:
            # 关闭服务器并清理临时文件
            self._shutdown_server(server)
            self.cleanup_temp_files(html_report_path)

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
        self.logger.log_separator("Claude Silent Fix Start")
        self.logger.info(f"Silent fix requested for {len(violations)} violations")

        if not violations:
            self.logger.info("No violations to fix")
            return 0

        log_claude_fix_start(len(violations), str(self.project_root))

        # 检测 Claude 是否可用
        available, error_msg = self.check_claude_available()
        if not available:
            self.logger.error(f"Claude not available: {error_msg}")
            print(f"Claude 不可用: {error_msg}", file=sys.stderr)
            log_claude_fix_end(False, error_msg, time.time() - self.start_time)
            return 1

        # 直接执行修复
        success, result_msg = self.fix_violations_silent(violations)

        elapsed = time.time() - self.start_time
        if success:
            self.logger.info(f"Silent fix completed in {elapsed:.2f}s")
            print("修复完成")
            log_claude_fix_end(True, "Fix completed", elapsed)
            return 0
        else:
            self.logger.error(f"Silent fix failed: {result_msg}")
            print(f"修复失败: {result_msg}", file=sys.stderr)
            log_claude_fix_end(False, result_msg, elapsed)
            return 1


def load_config(config_path: str) -> dict:
    """加载配置文件"""
    if not config_path or not os.path.exists(config_path):
        return {}

    try:
        import yaml
        with open(config_path, 'r') as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # 如果没有 PyYAML，尝试简单解析
        return {}
    except Exception:
        return {}


def load_violations(violations_path: str) -> List[Dict]:
    """加载违规信息"""
    if not violations_path or not os.path.exists(violations_path):
        return []

    try:
        with open(violations_path, 'r') as f:
            content = f.read().strip()
            if not content:
                return []
            data = json.loads(content)
            return data.get('violations', [])
    except json.JSONDecodeError:
        return []
    except Exception:
        return []


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='Claude 自动修复工具'
    )

    parser.add_argument(
        '--violations',
        help='违规信息 JSON 文件路径',
        required=False
    )

    parser.add_argument(
        '--config',
        help='配置文件路径',
        required=False
    )

    parser.add_argument(
        '--project-root',
        help='项目根目录',
        default=os.getcwd()
    )

    parser.add_argument(
        '--check-only',
        action='store_true',
        help='仅检测 Claude CLI 是否可用'
    )

    parser.add_argument(
        '--skip-dialog',
        action='store_true',
        help='跳过询问对话框，直接执行修复（用于 Build Phase 脚本已处理对话框的情况）'
    )

    return parser.parse_args()


def main():
    """主入口"""
    # 调试：写入临时文件追踪执行
    import datetime
    debug_file = "/tmp/biliobjclint_debug.log"
    with open(debug_file, "a") as f:
        f.write(f"\n=== {datetime.datetime.now()} ===\n")
        f.write(f"claude_fixer.py started\n")
        f.write(f"sys.argv: {sys.argv}\n")

    args = parse_args()
    logger = get_logger("claude_fix")

    # 调试：记录参数
    with open(debug_file, "a") as f:
        f.write(f"args: {vars(args)}\n")

    logger.info(f"Claude fixer started: project_root={args.project_root}")
    logger.debug(f"Arguments: {vars(args)}")

    # 加载配置
    config = load_config(args.config)
    logger.debug(f"Config loaded from: {args.config}")

    # 创建修复器
    fixer = ClaudeFixer(config, args.project_root)

    # 仅检测模式
    if args.check_only:
        logger.info("Running in check-only mode")
        available, error_msg = fixer.check_claude_available()
        if available:
            print("Claude Code CLI 可用")
            logger.info("Check completed: Claude CLI is available")
            sys.exit(0)
        else:
            print(f"Claude Code CLI 不可用: {error_msg}", file=sys.stderr)
            logger.error(f"Check completed: Claude CLI not available - {error_msg}")
            sys.exit(1)

    # 加载违规信息
    violations = load_violations(args.violations)
    logger.info(f"Loaded {len(violations)} violations from: {args.violations}")

    if not violations:
        # 没有违规，直接退出
        logger.info("No violations to process, exiting")
        sys.exit(0)

    # 根据参数选择执行模式
    if args.skip_dialog:
        # 跳过对话框，直接执行静默修复
        logger.info("Running in skip-dialog mode (silent fix)")
        exit_code = fixer.run_silent_fix(violations)
    else:
        # 完整流程（包含询问对话框）
        logger.info("Running in full dialog mode")
        exit_code = fixer.run(violations)

    logger.info(f"Claude fixer completed with exit code: {exit_code}")
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
