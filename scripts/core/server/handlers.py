"""
BiliObjCLint Server - HTTP 请求处理模块
"""
from __future__ import annotations

import json
import logging
import os
from http import cookies
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from .db import Database
from .auth import SessionStore
from .ui import render_dashboard, render_login, render_register, render_users


PROJECT_TOKEN_SEP = "|||"


class ServerState:
    """服务器状态"""

    def __init__(
        self,
        config: Dict[str, Any],
        db: Database,
        sessions: SessionStore,
        logger: logging.Logger
    ):
        self.config = config
        self.db = db
        self.sessions = sessions
        self.logger = logger


class RequestHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器"""

    server_version = "BiliObjCLintServer/0.2"

    def log_message(self, format, *args):
        """禁用默认日志"""
        return

    def _send_json(self, status: int, data: Dict[str, Any]) -> None:
        """发送 JSON 响应"""
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_html(self, status: int, html: str) -> None:
        """发送 HTML 响应"""
        payload = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _serve_static(self, filename: str) -> None:
        """提供静态文件服务"""
        # 静态文件目录: scripts/core/server/static/
        static_dir = Path(__file__).parent / "static"
        file_path = static_dir / filename

        # 安全检查: 防止路径遍历攻击
        try:
            file_path = file_path.resolve()
            if not str(file_path).startswith(str(static_dir.resolve())):
                self._send_json(403, {"error": "forbidden"})
                return
        except Exception:
            self._send_json(400, {"error": "invalid_path"})
            return

        if not file_path.exists() or not file_path.is_file():
            self._send_json(404, {"error": "not_found"})
            return

        # 根据文件扩展名确定 MIME 类型
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
            ".css": "text/css",
            ".js": "application/javascript",
        }
        ext = file_path.suffix.lower()
        content_type = mime_types.get(ext, "application/octet-stream")

        try:
            with open(file_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")  # 缓存 1 天
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            logging.error(f"Failed to serve static file {filename}: {e}")
            self._send_json(500, {"error": "internal_error"})

    def _redirect(self, location: str) -> None:
        """发送重定向响应"""
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def _get_state(self) -> ServerState:
        """获取服务器状态"""
        return self.server.state  # type: ignore[attr-defined]

    def _get_session(self) -> Optional[Tuple[str, str]]:
        """从 Cookie 获取会话信息"""
        cookie_header = self.headers.get("Cookie")
        if not cookie_header:
            return None
        c = cookies.SimpleCookie()
        c.load(cookie_header)
        if "session_id" not in c:
            return None
        session_id = c["session_id"].value
        return self._get_state().sessions.get(session_id)

    def _require_login(self) -> Optional[Tuple[str, str]]:
        """要求登录，返回 (username, role) 或 None"""
        state = self._get_state()
        auth_cfg = state.config.get("auth", {})
        if not auth_cfg.get("enabled", True):
            return ("anonymous", "admin")
        session = self._get_session()
        if session:
            return session
        self._redirect("/login")
        return None

    def _is_admin(self, role: str) -> bool:
        """检查是否为管理员"""
        return role == "admin"

    def do_GET(self):
        """处理 GET 请求"""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/healthz":
            self._send_json(200, {"status": "ok"})
            return

        # 静态文件服务
        if path.startswith("/static/"):
            self._serve_static(path[8:])  # 去掉 "/static/" 前缀
            return

        if path == "/login":
            # 检查是否刚注册成功
            registered = query.get("registered", [""])[0]
            success_msg = "注册成功！请登录。" if registered == "1" else ""
            self._send_html(200, render_login(success=success_msg))
            return

        if path == "/register":
            self._send_html(200, render_register())
            return

        if path == "/logout":
            self.send_response(302)
            self.send_header("Set-Cookie", "session_id=; Max-Age=0; Path=/; HttpOnly")
            self.send_header("Location", "/login")
            self.end_headers()
            return

        if path == "/" or path == "/dashboard":
            session = self._require_login()
            if not session:
                return
            self._handle_dashboard(session, query)
            return

        if path == "/admin/users":
            session = self._require_login()
            if not session:
                return
            username, role = session
            if not self._is_admin(role):
                self._send_html(403, "<h1>Forbidden</h1>")
                return
            delete_user = query.get("delete", [""])[0]
            if delete_user and delete_user != username:
                self._get_state().db.delete_user(delete_user)
                self._redirect("/admin/users")
                return
            users = self._get_state().db.list_users()
            self._send_html(200, render_users(users))
            return

        self._send_json(404, {"error": "not_found"})

    def _handle_dashboard(self, session: Tuple[str, str], query: Dict) -> None:
        """处理 Dashboard 页面"""
        username, role = session
        state = self._get_state()

        project_token = query.get("project", [""])[0].strip()
        project_key = None
        project_name = None
        if project_token:
            if PROJECT_TOKEN_SEP in project_token:
                parts = project_token.split(PROJECT_TOKEN_SEP, 1)
                project_key = parts[0] or None
                project_name = parts[1] or None
            else:
                project_key = project_token or None

        start_date = query.get("start", [""])[0].strip() or None
        end_date = query.get("end", [""])[0].strip() or None
        days = None
        if not start_date and not end_date:
            days_value = query.get("days", [""])[0].strip()
            if days_value:
                try:
                    days = int(days_value)
                except ValueError:
                    days = None

        projects = state.db.list_projects()
        daily = state.db.get_daily_stats(project_key, project_name, start_date, end_date, days)
        rules = state.db.get_rule_stats(project_key, project_name, start_date, end_date, days)
        autofix = state.db.get_autofix_summary(project_key, project_name, start_date, end_date, days)
        chart_days = None if (start_date or end_date) else 7
        chart_data = state.db.get_daily_stats(project_key, project_name, start_date, end_date, chart_days)

        self._send_html(
            200,
            render_dashboard(
                username,
                role,
                projects,
                daily,
                rules,
                autofix,
                project_token or None,
                start_date,
                end_date,
                chart_data,
            ),
        )

    def do_POST(self):
        """处理 POST 请求"""
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/login":
            self._handle_login()
            return

        if path == "/register":
            self._handle_register()
            return

        if path == "/admin/users":
            self._handle_create_user()
            return

        if path == "/api/v1/ingest":
            self._handle_ingest()
            return

        self._send_json(404, {"error": "not_found"})

    def _handle_login(self) -> None:
        """处理登录请求"""
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        form = parse_qs(body)
        username = (form.get("username") or [""])[0]
        password = (form.get("password") or [""])[0]

        role = self._get_state().db.verify_user(username, password)
        if role:
            session_id = self._get_state().sessions.create(username, role)
            self.send_response(302)
            # 根据 remember 参数设置 cookie 过期时间
            remember = (form.get("remember") or [""])[0]
            if remember == "1":
                # 记住密码：30天
                self.send_header("Set-Cookie", f"session_id={session_id}; Path=/; HttpOnly; Max-Age=2592000")
            else:
                # 不记住：会话 cookie
                self.send_header("Set-Cookie", f"session_id={session_id}; Path=/; HttpOnly")
            self.send_header("Location", "/dashboard")
            self.end_headers()
        else:
            self._send_html(401, render_login(error="用户名或密码错误"))

    def _handle_register(self) -> None:
        """处理注册请求"""
        import re
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        form = parse_qs(body)
        username = (form.get("username") or [""])[0].strip()
        password = (form.get("password") or [""])[0]
        confirm_password = (form.get("confirm_password") or [""])[0]

        # 验证用户名
        if not username or len(username) < 3 or len(username) > 32:
            self._send_html(400, render_register(error="用户名长度需为 3-32 个字符"))
            return
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            self._send_html(400, render_register(error="用户名只能包含字母、数字和下划线"))
            return

        # 验证密码
        if not password or len(password) < 6:
            self._send_html(400, render_register(error="密码长度至少 6 个字符"))
            return
        if password != confirm_password:
            self._send_html(400, render_register(error="两次输入的密码不一致"))
            return

        # 创建用户（默认角色为 readonly）
        db = self._get_state().db
        success, msg = db.create_user(username, password, "readonly")
        if success:
            # 注册成功后自动跳转到登录页
            self._redirect("/login?registered=1")
        else:
            self._send_html(400, render_register(error=msg))

    def _handle_create_user(self) -> None:
        """处理创建用户请求"""
        session = self._require_login()
        if not session:
            return
        username, role = session
        if not self._is_admin(role):
            self._send_html(403, "<h1>Forbidden</h1>")
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        form = parse_qs(body)
        new_user = (form.get("username") or [""])[0]
        new_pass = (form.get("password") or [""])[0]
        new_role = (form.get("role") or ["readonly"])[0]

        ok, msg = self._get_state().db.create_user(new_user, new_pass, new_role)
        if ok:
            self._redirect("/admin/users")
        else:
            users = self._get_state().db.list_users()
            self._send_html(200, render_users(users, error=msg))

    def _handle_ingest(self) -> None:
        """处理数据上报请求"""
        state = self._get_state()
        token = state.config.get("ingest", {}).get("token") or ""
        if token:
            header = self.headers.get("X-BiliObjCLint-Token")
            if header != token:
                self._send_json(401, {"error": "unauthorized"})
                return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid_json"})
            return

        ok, msg = state.db.upsert_run(payload)
        if not ok:
            self._send_json(400, {"error": msg})
            return

        retention_days = int(state.config.get("storage", {}).get("retention_days", 0) or 0)
        if retention_days > 0:
            state.db.cleanup_retention(retention_days)

        spool_path = state.config.get("ingest", {}).get("spool_path")
        if spool_path:
            from .utils import ensure_dir
            sp = Path(os.path.expanduser(spool_path))
            ensure_dir(sp.parent)
            with sp.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")

        self._send_json(200, {"success": True})
