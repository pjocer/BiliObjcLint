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
from core.ignore_cache import IgnoreCache


# 全局变量用于 HTTP 服务器通信
_user_action = None
_server_should_stop = False
_timeout_reset_time = None  # 用于重置超时计时
_ignore_cache = None  # 忽略缓存实例
_fixer_instance = None  # ClaudeFixer 实例引用


class ActionRequestHandler(BaseHTTPRequestHandler):
    """处理来自 HTML 页面的用户操作请求"""

    def log_message(self, format, *args):
        """禁止默认的 HTTP 日志输出"""
        pass

    def do_GET(self):
        global _user_action, _server_should_stop, _ignore_cache, _fixer_instance
        from urllib.parse import urlparse, parse_qs, unquote

        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == '/fix':
            _user_action = 'fix'
            _server_should_stop = True
            self._send_response("正在启动自动修复...")
        elif path == '/cancel':
            _user_action = 'cancel'
            _server_should_stop = True
            self._send_response("已取消")
        elif path == '/done':
            # 完成并继续编译
            _user_action = 'done'
            _server_should_stop = True
            self._send_response("已完成")
        elif path == '/status':
            self._send_response("running")
        elif path == '/open':
            # 在 Xcode 中打开文件
            file_path = params.get('file', [''])[0]
            line = params.get('line', ['1'])[0]
            self._open_in_xcode(file_path, line)
        elif path == '/ignore':
            # 忽略单个违规
            self._handle_ignore(params)
        elif path == '/fix-single':
            # 修复单个违规
            self._handle_fix_single(params)
        else:
            self.send_error(404)

    def _handle_ignore(self, params: dict):
        """处理忽略单个违规的请求"""
        global _ignore_cache, _timeout_reset_time
        from urllib.parse import unquote

        file_path = unquote(params.get('file', [''])[0])
        line = int(params.get('line', ['0'])[0])
        rule = params.get('rule', [''])[0]
        message = unquote(params.get('message', [''])[0])

        if not file_path or not line or not rule:
            self._send_json_response({'success': False, 'message': '参数不完整'})
            return

        try:
            if _ignore_cache:
                success = _ignore_cache.add_ignore(file_path, line, rule, message)
                if success:
                    _timeout_reset_time = time.time()  # 重置超时
                    self._send_json_response({'success': True, 'message': '已添加到忽略列表'})
                else:
                    self._send_json_response({'success': False, 'message': '添加忽略失败'})
            else:
                self._send_json_response({'success': False, 'message': '忽略缓存未初始化'})
        except Exception as e:
            self._send_json_response({'success': False, 'message': str(e)})

    def _handle_fix_single(self, params: dict):
        """处理修复单个违规的请求"""
        global _fixer_instance, _timeout_reset_time
        from urllib.parse import unquote
        import threading

        file_path = unquote(params.get('file', [''])[0])
        line = int(params.get('line', ['0'])[0])
        rule = params.get('rule', [''])[0]
        message = unquote(params.get('message', [''])[0])

        if not file_path or not line or not rule:
            self._send_json_response({'success': False, 'message': '参数不完整'})
            return

        # 立即返回，异步执行修复
        _timeout_reset_time = time.time()  # 重置超时

        # 构建单个违规
        violation = {
            'file': file_path,
            'line': line,
            'rule': rule,
            'message': message,
            'severity': 'warning'
        }

        def do_fix():
            if _fixer_instance:
                success, msg = _fixer_instance.fix_violations_silent([violation])
                # 修复结果可以通过轮询 /fix-status 获取（简化版直接假设成功）

        # 在后台线程执行修复
        threading.Thread(target=do_fix, daemon=True).start()
        self._send_json_response({'success': True, 'status': 'started'})

    def _open_in_xcode(self, file_path: str, line: str):
        """使用 xed 命令在 Xcode 中打开文件"""
        global _timeout_reset_time
        try:
            if file_path and os.path.exists(file_path):
                # 使用 xed 命令打开文件并跳转到指定行
                subprocess.Popen(['xed', '--line', str(line), file_path],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
                # 重置超时计时
                _timeout_reset_time = time.time()
                self._send_json_response({'success': True, 'message': '已在 Xcode 中打开'})
            else:
                self._send_json_response({'success': False, 'message': '文件不存在'})
        except Exception as e:
            self._send_json_response({'success': False, 'message': str(e)})

    def _send_json_response(self, data: dict):
        """发送 JSON 响应"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

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

    def _read_code_context(self, file_path: str, line: int, context_lines: int = 3) -> List[Tuple[int, str]]:
        """
        读取代码上下文

        Args:
            file_path: 文件路径
            line: 目标行号
            context_lines: 上下文行数

        Returns:
            [(line_number, code_line), ...]
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                all_lines = f.readlines()

            start = max(0, line - context_lines - 1)
            end = min(len(all_lines), line + context_lines)

            result = []
            for i in range(start, end):
                result.append((i + 1, all_lines[i].rstrip('\n\r')))
            return result
        except Exception as e:
            self.logger.warning(f"Failed to read code context from {file_path}: {e}")
            return []

    def _escape_html(self, text: str) -> str:
        """转义 HTML 特殊字符"""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))

    def _highlight_objc(self, code: str) -> str:
        """
        简单的 Objective-C 语法高亮

        使用占位符系统保护字符串和注释，避免后续正则匹配到已生成的 HTML 属性

        Args:
            code: 代码文本

        Returns:
            带有 HTML 高亮标记的代码
        """
        import re

        # 使用占位符保护字符串和注释
        # 重要：必须在 HTML 转义之前提取，因为转义后 " 变成 &quot; 会破坏正则匹配
        placeholders = []

        def save_and_escape(match, match_type):
            """保存匹配内容并转义 HTML"""
            idx = len(placeholders)
            # 对提取的内容进行 HTML 转义
            escaped_content = self._escape_html(match.group(0))
            placeholders.append((match_type, escaped_content))
            return f'\x00{match_type}_{idx}\x00'

        # 1. 先提取注释（优先级最高，避免字符串匹配到注释内容）
        code = re.sub(r'//.*?$', lambda m: save_and_escape(m, 'COMMENT'), code)

        # 2. 提取字符串（在 HTML 转义之前，使用原始引号匹配）
        code = re.sub(r'@"[^"]*"', lambda m: save_and_escape(m, 'STRING'), code)  # ObjC 字符串 @"..."
        code = re.sub(r'"(?:[^"\\]|\\.)*"', lambda m: save_and_escape(m, 'STRING'), code)  # C 字符串 "..."

        # 3. 现在对剩余代码进行 HTML 转义
        code = self._escape_html(code)

        # 4. 处理关键字等，不会匹配到字符串和注释（它们已被占位符替代）
        # 关键字
        keywords = r'\b(if|else|for|while|do|switch|case|default|break|continue|return|goto|typedef|struct|enum|union|sizeof|static|extern|const|volatile|inline|register|auto|signed|unsigned|void|char|short|int|long|float|double|bool|BOOL|YES|NO|nil|NULL|self|super|id|Class|SEL|IMP|instancetype|NS_ASSUME_NONNULL_BEGIN|NS_ASSUME_NONNULL_END)\b'
        code = re.sub(keywords, r'<span class="hl-keyword">\1</span>', code)

        # @关键字
        at_keywords = r'(@interface|@implementation|@end|@protocol|@property|@synthesize|@dynamic|@class|@public|@private|@protected|@package|@selector|@encode|@try|@catch|@finally|@throw|@synchronized|@autoreleasepool|@optional|@required|@import|@available)'
        code = re.sub(at_keywords, r'<span class="hl-at-keyword">\1</span>', code)

        # 属性关键字
        prop_keywords = r'\b(nonatomic|atomic|strong|weak|copy|assign|retain|readonly|readwrite|getter|setter|nullable|nonnull)\b'
        code = re.sub(prop_keywords, r'<span class="hl-prop">\1</span>', code)

        # 数字
        code = re.sub(r'\b(\d+\.?\d*[fFlL]?)\b', r'<span class="hl-number">\1</span>', code)

        # 预处理指令
        code = re.sub(r'^(\s*)(#\w+)', r'\1<span class="hl-preprocessor">\2</span>', code)

        # 5. 恢复字符串和注释，并添加高亮
        for i, (match_type, escaped_content) in enumerate(placeholders):
            placeholder = f'\x00{match_type}_{i}\x00'
            if match_type == 'COMMENT':
                code = code.replace(placeholder, f'<span class="hl-comment">{escaped_content}</span>')
            elif match_type == 'STRING':
                code = code.replace(placeholder, f'<span class="hl-string">{escaped_content}</span>')

        return code

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
            overflow: hidden;
        }
        .violation {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
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
        .violation.ignored {
            opacity: 0.5;
        }
        .violation.fixed {
            opacity: 0.6;
            background: rgba(76, 175, 80, 0.1);
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
        /* 可点击的违规项 */
        .violation-header {
            cursor: pointer;
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            align-items: center;
            width: 100%;
        }
        .violation-header:hover {
            opacity: 0.9;
        }
        .expand-icon {
            transition: transform 0.2s;
            font-size: 12px;
            opacity: 0.6;
        }
        .violation.expanded .expand-icon {
            transform: rotate(90deg);
        }
        /* 代码预览区域 */
        .code-preview {
            display: none;
            margin-top: 12px;
            border-radius: 8px;
            overflow: hidden;
            background: #1e1e1e;
            width: 100%;
            box-sizing: border-box;
        }
        .violation.expanded .code-preview {
            display: block;
        }
        .code-actions {
            display: flex;
            justify-content: flex-end;
            gap: 8px;
            padding: 10px 12px;
            background: #2d2d2d;
            border-bottom: 1px solid #404040;
        }
        /* 操作按钮通用样式 */
        .btn-action {
            padding: 6px 14px;
            font-size: 13px;
            font-weight: 500;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn-action:disabled {
            cursor: not-allowed;
            opacity: 0.7;
        }
        /* 忽略按钮 */
        .btn-ignore {
            background: #78909C;
            color: white;
        }
        .btn-ignore:hover:not(:disabled) {
            background: #607D8B;
        }
        .btn-ignore[data-state="ignored"] {
            background: #B0BEC5;
            cursor: default;
        }
        /* 修复按钮 */
        .btn-fix-single {
            background: #4CAF50;
            color: white;
        }
        .btn-fix-single:hover:not(:disabled) {
            background: #43A047;
        }
        .btn-fix-single[data-state="fixing"] {
            background: #FFA726;
            cursor: wait;
        }
        .btn-fix-single[data-state="fixed"] {
            background: #66BB6A;
            cursor: default;
        }
        .btn-fix-single[data-state="failed"] {
            background: #EF5350;
        }
        /* Xcode 按钮 */
        .btn-xcode {
            padding: 6px 14px;
            font-size: 13px;
            font-weight: 500;
            background: #007AFF;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
            transition: background 0.2s;
        }
        .btn-xcode:hover {
            background: #0056CC;
        }
        /* 底部完成按钮 */
        .footer-actions {
            position: sticky;
            bottom: 0;
            background: var(--bg-color);
            padding: 20px;
            border-top: 1px solid var(--border-color);
            text-align: center;
            margin-top: 30px;
        }
        .btn-done, .btn-download {
            padding: 14px 40px;
            font-size: 16px;
            font-weight: 600;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
            margin: 0 8px;
        }
        .btn-done {
            background: #4CAF50;
        }
        .btn-done:hover {
            background: #43A047;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        .btn-download {
            background: #2196F3;
        }
        .btn-download:hover {
            background: #1976D2;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        .btn-done:disabled, .btn-download:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        .code-block {
            padding: 12px 0;
            overflow-x: auto;
            font-family: "SF Mono", Monaco, Menlo, monospace;
            font-size: 13px;
            line-height: 1.5;
        }
        .code-line {
            display: flex;
            padding: 2px 12px;
        }
        .code-line.highlighted {
            background: rgba(255, 200, 0, 0.2);
        }
        .code-line-num {
            min-width: 45px;
            padding-right: 12px;
            text-align: right;
            color: #858585;
            user-select: none;
            border-right: 1px solid #404040;
            margin-right: 12px;
        }
        .code-line-content {
            white-space: pre;
            color: #d4d4d4;
        }
        /* ObjC 语法高亮 */
        .hl-keyword { color: #569cd6; }
        .hl-at-keyword { color: #c586c0; }
        .hl-prop { color: #4ec9b0; }
        .hl-string { color: #ce9178; }
        .hl-number { color: #b5cea8; }
        .hl-comment { color: #6a9955; font-style: italic; }
        .hl-preprocessor { color: #c586c0; }
        @media (prefers-color-scheme: light) {
            .code-preview {
                background: #f5f5f5;
            }
            .code-actions {
                background: #e8e8e8;
                border-bottom-color: #d0d0d0;
            }
            .code-line.highlighted {
                background: rgba(255, 200, 0, 0.3);
            }
            .code-line-num {
                color: #6e6e6e;
                border-right-color: #d0d0d0;
            }
            .code-line-content {
                color: #1e1e1e;
            }
            .hl-keyword { color: #0000ff; }
            .hl-at-keyword { color: #af00db; }
            .hl-prop { color: #267f99; }
            .hl-string { color: #a31515; }
            .hl-number { color: #098658; }
            .hl-comment { color: #008000; }
            .hl-preprocessor { color: #af00db; }
        }
    </style>
</head>
<body>
    <h1>🔍 BiliObjCLint 代码问题报告</h1>
    <p class="summary">
        发现 <strong>''', str(len(violations)), '''</strong> 个问题
        ''']

        # 如果提供了端口，添加交互提示
        if port:
            html_parts.append(f'''
    </p>
    <div class="notice-box">
        <span class="icon">⏳</span>
        <div class="content">
            <div class="title">Xcode 正在等待您的操作</div>
            <div class="desc">请阅读下方的代码审查结果，可以对每个问题单独「忽略」或「修复」。处理完成后点击底部的「完成并继续编译」按钮。</div>
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

            for idx, v in enumerate(sorted(file_violations, key=lambda x: x.get('line', 0))):
                severity = v.get('severity', 'warning')
                line = v.get('line', 0)
                message = v.get('message', '')
                rule = v.get('rule', '')
                violation_id = f"v-{hash(file_path)}-{idx}"

                # 读取代码上下文
                code_lines = self._read_code_context(file_path, line)

                # 生成代码预览 HTML
                code_html = ''
                if code_lines:
                    code_html = '<div class="code-block">'
                    for ln, content in code_lines:
                        highlighted = 'highlighted' if ln == line else ''
                        highlighted_content = self._highlight_objc(content)
                        code_html += f'<div class="code-line {highlighted}"><span class="code-line-num">{ln}</span><span class="code-line-content">{highlighted_content}</span></div>'
                    code_html += '</div>'

                # 转义文件路径用于 JavaScript
                escaped_file_path = file_path.replace('\\', '\\\\').replace("'", "\\'")

                # 转义消息用于 JavaScript
                escaped_message = message.replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"').replace('\n', ' ')

                html_parts.append(f'''
            <div class="violation {severity}" id="{violation_id}" onclick="toggleViolation('{violation_id}')">
                <div class="violation-header">
                    <span class="expand-icon">▶</span>
                    <span class="line-num">Line {line}</span>
                    <span class="severity {severity}">{severity}</span>
                    <span class="message">{self._escape_html(message)}</span>
                    <span class="rule">{rule}</span>
                </div>
                <div class="code-preview" onclick="event.stopPropagation()">
                    <div class="code-actions">
                        <button class="btn-action btn-ignore" onclick="ignoreViolation(this, '{escaped_file_path}', {line}, '{rule}', '{escaped_message}')" data-state="normal">
                            忽略
                        </button>
                        <button class="btn-action btn-fix-single" onclick="fixSingleViolation(this, '{escaped_file_path}', {line}, '{rule}', '{escaped_message}')" data-state="normal">
                            修复
                        </button>
                        <button class="btn-xcode" onclick="openInXcode('{escaped_file_path}', {line})">
                            <span>📱</span> 在 Xcode 中打开
                        </button>
                    </div>
                    {code_html}
                </div>
            </div>''')

            html_parts.append('''
        </div>
    </div>''')

        # 添加 JavaScript 和底部按钮（仅当有端口时）
        if port:
            html_parts.append(f'''
    <div class="footer-actions">
        <button class="btn-download" onclick="downloadReport()" id="btn-download">📥 下载报告</button>
        <button class="btn-done" onclick="finishAndContinue()" id="btn-done">✓ 完成并继续编译</button>
    </div>
    <div class="footer">
        Generated by BiliObjCLint
    </div>
    <script>
        const SERVER_PORT = {port};
        let actionSent = false;

        // 展开/折叠违规项
        function toggleViolation(id) {{
            const el = document.getElementById(id);
            if (el) {{
                el.classList.toggle('expanded');
            }}
        }}

        // 在 Xcode 中打开文件
        async function openInXcode(file, line) {{
            try {{
                const response = await fetch(`http://localhost:${{SERVER_PORT}}/open?file=${{encodeURIComponent(file)}}&line=${{line}}`);
                const result = await response.json();
                if (!result.success) {{
                    alert('打开失败: ' + result.message);
                }}
            }} catch (e) {{
                console.error('打开 Xcode 失败:', e);
                alert('打开 Xcode 失败，请重试');
            }}
        }}

        // 忽略单个违规
        async function ignoreViolation(btn, file, line, rule, message) {{
            event.stopPropagation();
            btn.disabled = true;
            btn.textContent = '处理中...';

            try {{
                const response = await fetch(
                    `http://localhost:${{SERVER_PORT}}/ignore?` +
                    `file=${{encodeURIComponent(file)}}&line=${{line}}&rule=${{rule}}&message=${{encodeURIComponent(message)}}`
                );
                const result = await response.json();
                if (result.success) {{
                    btn.textContent = '已忽略';
                    btn.dataset.state = 'ignored';
                    btn.closest('.violation').classList.add('ignored');
                }} else {{
                    btn.textContent = '忽略';
                    btn.disabled = false;
                    alert('忽略失败: ' + result.message);
                }}
            }} catch (e) {{
                btn.textContent = '忽略';
                btn.disabled = false;
                alert('操作失败');
            }}
        }}

        // 修复单个违规
        async function fixSingleViolation(btn, file, line, rule, message) {{
            event.stopPropagation();
            btn.disabled = true;
            btn.textContent = '修复中...';
            btn.dataset.state = 'fixing';

            try {{
                const response = await fetch(
                    `http://localhost:${{SERVER_PORT}}/fix-single?` +
                    `file=${{encodeURIComponent(file)}}&line=${{line}}&` +
                    `rule=${{rule}}&message=${{encodeURIComponent(message)}}`
                );
                const result = await response.json();
                if (result.success) {{
                    // 修复已启动，等待一段时间后更新状态
                    setTimeout(() => {{
                        btn.textContent = '已修复';
                        btn.dataset.state = 'fixed';
                        btn.closest('.violation').classList.add('fixed');
                    }}, 3000);
                }} else {{
                    btn.textContent = '重试';
                    btn.dataset.state = 'failed';
                    btn.disabled = false;
                }}
            }} catch (e) {{
                btn.textContent = '重试';
                btn.dataset.state = 'failed';
                btn.disabled = false;
            }}
        }}

        // 下载报告
        function downloadReport() {{
            // 克隆整个文档
            const doc = document.documentElement.cloneNode(true);

            // 移除所有操作按钮区域
            doc.querySelectorAll('.code-actions').forEach(el => el.remove());

            // 移除底部操作按钮
            doc.querySelectorAll('.footer-actions').forEach(el => el.remove());

            // 移除提示框
            doc.querySelectorAll('.notice-box').forEach(el => el.remove());

            // 移除所有 script 标签
            doc.querySelectorAll('script').forEach(el => el.remove());

            // 移除 onclick 属性（展开功能也禁用）
            doc.querySelectorAll('[onclick]').forEach(el => {{
                el.removeAttribute('onclick');
            }});

            // 默认展开所有代码预览
            doc.querySelectorAll('.violation').forEach(el => {{
                el.classList.add('expanded');
            }});

            // 移除展开图标
            doc.querySelectorAll('.expand-icon').forEach(el => el.remove());

            // 移除 violation-header 的 cursor pointer 样式
            const style = doc.querySelector('style');
            if (style) {{
                style.textContent += `
                    .violation-header {{ cursor: default !important; }}
                    .code-preview {{ display: block !important; }}
                `;
            }}

            // 生成文件名（包含日期时间）
            const now = new Date();
            const dateStr = now.toISOString().slice(0, 19).replace(/[T:]/g, '-');
            const filename = `BiliObjCLint_Report_${{dateStr}}.html`;

            // 创建完整的 HTML 文档
            const htmlContent = '<!DOCTYPE html>\\n<html>' + doc.innerHTML + '</html>';

            // 创建 Blob 并下载
            const blob = new Blob([htmlContent], {{ type: 'text/html;charset=utf-8' }});
            const url = URL.createObjectURL(blob);

            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }}

        // 完成并继续编译
        async function finishAndContinue() {{
            if (actionSent) return;
            actionSent = true;

            const btnDone = document.getElementById('btn-done');
            btnDone.disabled = true;
            btnDone.textContent = '正在关闭...';

            try {{
                const response = await fetch(`http://localhost:${{SERVER_PORT}}/done`);
                if (response.ok) {{
                    // 请求成功，尝试关闭页面
                    window.close();
                    // 如果无法关闭，显示提示
                    setTimeout(() => {{
                        document.body.innerHTML = '<div style="display:flex;justify-content:center;align-items:center;height:100vh;font-family:-apple-system,sans-serif;"><div style="text-align:center;padding:40px;background:var(--card-bg,#f8f9fa);border-radius:12px;"><h2>✓ 已完成</h2><p style="opacity:0.6;margin-top:10px;">可以关闭此页面</p></div></div>';
                    }}, 100);
                }}
            }} catch (e) {{
                console.error('请求失败:', e);
                alert('操作失败，请重试');
                actionSent = false;
                btnDone.disabled = false;
                btnDone.textContent = '✓ 完成并继续编译';
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
        global _user_action, _server_should_stop, _timeout_reset_time
        _user_action = None
        _server_should_stop = False
        _timeout_reset_time = None

        start_time = time.time()
        while not _server_should_stop:
            # 检查是否需要重置超时（用户点击了"在 Xcode 中打开"）
            effective_start = _timeout_reset_time if _timeout_reset_time else start_time
            if time.time() - effective_start > timeout:
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
            "# 代码修复任务（最小化修改）",
            "",
            "## ⚠️ 严格限制 - 必须遵守",
            "",
            "**你的任务是做最小限度的修改来修复指定问题。**",
            "",
            "### 禁止行为（违反将导致任务失败）：",
            "- ❌ 禁止重构代码",
            "- ❌ 禁止优化代码",
            "- ❌ 禁止重写代码",
            "- ❌ 禁止改变代码结构",
            "- ❌ 禁止修改未列出的代码行",
            "- ❌ 禁止添加新功能",
            "- ❌ 禁止删除未涉及的代码",
            "- ❌ 禁止修改代码风格或格式",
            "- ❌ 禁止添加注释或文档",
            "- ❌ 禁止修复未在下方列表中明确指出的问题",
            "",
            "### 允许行为：",
            "- ✅ 只修改下方列表中指定行号的代码",
            "- ✅ 做最小限度的字符级别修改",
            "- ✅ 例如：将 `strong` 改为 `weak`，仅此而已",
            "",
            "## 需要修复的问题（仅修复这些）",
            ""
        ]

        for file_path, file_violations in by_file.items():
            prompt_parts.append(f"### 文件: {file_path}")
            prompt_parts.append("")
            for v in file_violations:
                line = v.get('line', 0)
                message = v.get('message', '')
                rule = v.get('rule', '')
                prompt_parts.append(f"- **行 {line}**: {message} [{rule}]")
            prompt_parts.append("")

        prompt_parts.extend([
            "## 修复方法参考",
            "",
            "| 规则 | 修复方法 | 示例 |",
            "|------|----------|------|",
            "| weak_delegate | 将 `strong` 改为 `weak` | `@property (nonatomic, strong)` → `@property (nonatomic, weak)` |",
            "| property_naming | 将首字母改为小写 | `URL` → `url` |",
            "| constant_naming | 添加 `k` 前缀 | `Constant` → `kConstant` |",
            "",
            "## 执行指令",
            "",
            "1. 读取文件，定位到指定行号",
            "2. 仅修改该行中与问题相关的最小部分",
            "3. 使用 Edit 工具提交修改",
            "4. 不要做任何额外的修改",
            "",
            "**再次强调：只做最小修改，不要重写或优化任何代码！**"
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

        # 先显示对话框
        dialog_result = self.show_dialog(
            "BiliObjCLint",
            f"发现 {len(violations)} 个代码问题\n（{error_count} errors, {warning_count} warnings）\n\n是否让 Claude 尝试自动修复？",
            ["取消", "查看详情", "自动修复"],
            icon="caution"
        )

        with open("/tmp/biliobjclint_debug.log", "a") as f:
            f.write(f"Initial dialog result: {dialog_result}\n")

        if dialog_result == "取消":
            self.logger.info("User cancelled from dialog")
            log_claude_fix_end(False, "User cancelled", time.time() - self.start_time)
            return 0

        # 用户选择直接修复
        if dialog_result == "自动修复":
            user_action = 'fix'
        # 用户选择查看详情
        elif dialog_result == "查看详情":
            # 启动本地服务器并显示 HTML 报告
            html_report_path = None
            server = None
            server_port = None

            # 初始化全局变量供 HTTP 处理器使用
            global _ignore_cache, _fixer_instance
            _ignore_cache = IgnoreCache(project_root=str(self.project_root))
            _fixer_instance = self

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
                    f.write(f"User action from HTML: {user_action}\n")

            finally:
                # 关闭服务器
                if server:
                    self._shutdown_server(server)
                # 清理临时文件
                if html_report_path and os.path.exists(html_report_path):
                    try:
                        os.remove(html_report_path)
                    except Exception:
                        pass

            if user_action == 'cancel' or user_action is None:
                self.logger.info("User cancelled or timed out from HTML")
                log_claude_fix_end(False, "User cancelled", time.time() - self.start_time)
                return 0

            if user_action == 'done':
                self.logger.info("User finished reviewing (done)")
                log_claude_fix_end(True, "User finished", time.time() - self.start_time)
                return 0
        else:
            # 未知结果
            self.logger.info(f"Unknown dialog result: {dialog_result}")
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
