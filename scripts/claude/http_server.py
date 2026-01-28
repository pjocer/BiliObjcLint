"""
Claude Fixer - HTTP 服务器模块

处理来自 HTML 报告页面的用户操作请求
"""
import json
import os
import socket
import subprocess
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs, unquote

# 添加 scripts 目录到路径以支持绝对导入
_SCRIPT_DIR = Path(__file__).parent.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from core.logger import get_logger

logger = get_logger("claude_fix")

# 全局变量用于 HTTP 服务器通信
_user_action = None
_server_should_stop = False
_timeout_reset_time = None
_ignore_cache = None
_fixer_instance = None

# 修复任务状态跟踪
# 格式: {task_id: {'status': 'running'|'completed'|'failed', 'message': str}}
_fix_tasks = {}


def set_ignore_cache(cache):
    """设置忽略缓存实例"""
    global _ignore_cache
    _ignore_cache = cache


def set_fixer_instance(fixer):
    """设置 ClaudeFixer 实例引用"""
    global _fixer_instance
    _fixer_instance = fixer


def get_user_action():
    """获取用户操作"""
    return _user_action


def reset_server_state():
    """重置服务器状态"""
    global _user_action, _server_should_stop, _timeout_reset_time
    _user_action = None
    _server_should_stop = False
    _timeout_reset_time = None


class ActionRequestHandler(BaseHTTPRequestHandler):
    """处理来自 HTML 页面的用户操作请求"""

    def log_message(self, format, *args):
        """禁止默认的 HTTP 日志输出"""
        pass

    def do_GET(self):
        global _user_action, _server_should_stop, _ignore_cache, _fixer_instance, _timeout_reset_time

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
        elif path == '/fix-status':
            # 查询修复任务状态
            self._handle_fix_status(params)
        else:
            self.send_error(404)

    def _handle_ignore(self, params: dict):
        """处理忽略单个违规的请求"""
        global _ignore_cache, _timeout_reset_time

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
        global _fixer_instance, _timeout_reset_time, _fix_tasks
        import threading
        import uuid

        file_path = unquote(params.get('file', [''])[0])
        line = int(params.get('line', ['0'])[0])
        rule = params.get('rule', [''])[0]
        message = unquote(params.get('message', [''])[0])

        if not file_path or not line or not rule:
            self._send_json_response({'success': False, 'message': '参数不完整'})
            return

        # 重置超时
        _timeout_reset_time = time.time()

        # 创建任务 ID
        task_id = str(uuid.uuid4())[:8]
        _fix_tasks[task_id] = {'status': 'running', 'message': '正在修复...'}

        # 构建单个违规
        violation = {
            'file': file_path,
            'line': line,
            'rule': rule,
            'message': message,
            'severity': 'warning'
        }

        def do_fix():
            global _fix_tasks
            try:
                if _fixer_instance:
                    success, result_msg = _fixer_instance.fix_violations_silent([violation])
                    if success:
                        _fix_tasks[task_id] = {'status': 'completed', 'message': '修复完成'}
                    else:
                        _fix_tasks[task_id] = {'status': 'failed', 'message': result_msg}
                else:
                    _fix_tasks[task_id] = {'status': 'failed', 'message': 'Fixer 未初始化'}
            except Exception as e:
                _fix_tasks[task_id] = {'status': 'failed', 'message': str(e)}

        # 在后台线程执行修复
        threading.Thread(target=do_fix, daemon=True).start()
        self._send_json_response({'success': True, 'status': 'started', 'task_id': task_id})

    def _handle_fix_status(self, params: dict):
        """查询修复任务状态"""
        global _fix_tasks, _timeout_reset_time

        task_id = params.get('task_id', [''])[0]

        if not task_id:
            self._send_json_response({'success': False, 'message': '缺少 task_id'})
            return

        # 重置超时（用户正在等待修复完成）
        _timeout_reset_time = time.time()

        if task_id in _fix_tasks:
            task = _fix_tasks[task_id]
            self._send_json_response({
                'success': True,
                'status': task['status'],
                'message': task['message']
            })
        else:
            self._send_json_response({'success': False, 'message': '任务不存在'})

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


def find_available_port() -> int:
    """找到一个可用的端口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('localhost', 0))
        return s.getsockname()[1]


def start_action_server(port: int) -> HTTPServer:
    """
    启动本地 HTTP 服务器监听用户操作

    Args:
        port: 监听端口

    Returns:
        HTTPServer 实例
    """
    server = HTTPServer(('localhost', port), ActionRequestHandler)
    server.timeout = 1  # 设置超时以便检查停止标志
    logger.debug(f"Started action server on port {port}")
    return server


def wait_for_user_action(server: HTTPServer, timeout: int = 300) -> Optional[str]:
    """
    等待用户在浏览器中的操作

    Args:
        server: HTTPServer 实例
        timeout: 超时时间（秒）

    Returns:
        用户操作 ('fix', 'cancel', 'done') 或 None（超时）
    """
    global _user_action, _server_should_stop, _timeout_reset_time
    reset_server_state()

    start_time = time.time()
    while not _server_should_stop:
        # 检查是否需要重置超时（用户点击了"在 Xcode 中打开"）
        effective_start = _timeout_reset_time if _timeout_reset_time else start_time
        if time.time() - effective_start > timeout:
            logger.warning(f"Action server timed out after {timeout}s")
            return None
        try:
            server.handle_request()
        except Exception as e:
            logger.warning(f"Server error: {e}")
            break

    return _user_action


def shutdown_server(server: HTTPServer):
    """关闭 HTTP 服务器"""
    if server:
        try:
            server.server_close()
            logger.debug("Action server shut down")
        except Exception as e:
            logger.warning(f"Error shutting down server: {e}")
