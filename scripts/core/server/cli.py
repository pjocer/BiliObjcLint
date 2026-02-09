#!/usr/bin/env python3
"""
BiliObjCLint Local Server - CLI 入口

提供本地服务的启动/停止/重启/状态查询。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from http.server import HTTPServer
from pathlib import Path
from typing import Any, Dict

_SCRIPT_DIR = Path(__file__).parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent.parent
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"

if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from core.server.utils import (
    ensure_dir, default_config_path, default_pid_path, template_config_path,
    get_local_ips, get_primary_ip, is_port_in_use, find_process_using_port
)
from core.server.db import Database
from core.server.auth import SessionStore
from core.server.handlers import RequestHandler, ServerState


# ------------------------- 配置 -------------------------

def load_config(path: Path) -> Dict[str, Any]:
    """加载配置文件"""
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def init_config(path: Path) -> None:
    """初始化配置文件（如不存在则从模板复制）"""
    if path.exists():
        return
    template = template_config_path()
    if not template.exists():
        raise FileNotFoundError(f"Config template missing: {template}")
    ensure_dir(path.parent)
    path.write_text(template.read_text())


def setup_logger(log_path: Path, level: str) -> logging.Logger:
    """设置日志记录器"""
    ensure_dir(log_path.parent)
    logger = logging.getLogger("biliobjclint.server")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        file_handler.setFormatter(fmt)
        file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        logger.addHandler(file_handler)
    return logger


# ------------------------- 进程管理 -------------------------

def read_pid(pid_path: Path) -> int:
    """读取 PID 文件"""
    if not pid_path.exists():
        return 0
    try:
        return int(pid_path.read_text().strip())
    except ValueError:
        return 0


def is_running(pid: int) -> bool:
    """检查进程是否运行中"""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# ------------------------- 服务器操作 -------------------------

def run_server(config_path: Path) -> int:
    """前台运行服务器"""
    config = load_config(config_path)
    server_cfg = config.get("server", {})
    host = server_cfg.get("host", "127.0.0.1")
    port = int(server_cfg.get("port", 18080))

    # 检查端口是否被占用
    if is_port_in_use(port, host if host != "0.0.0.0" else "127.0.0.1"):
        pid, proc_name = find_process_using_port(port)
        print("")
        print("=" * 60)
        print(f"  错误: 端口 {port} 已被占用")
        print("=" * 60)
        if pid:
            print(f"\n  占用进程: {proc_name} (PID: {pid})")
            print(f"\n  解决方案:")
            print(f"    1. 停止占用进程: kill {pid}")
            print(f"    2. 或修改配置使用其他端口")
        else:
            print(f"\n  解决方案:")
            print(f"    1. 查找占用进程: lsof -i :{port}")
            print(f"    2. 停止占用进程或修改配置使用其他端口")
        print(f"\n  配置文件: {config_path}")
        print("=" * 60)
        print("")
        return 1

    logging_cfg = config.get("logging", {})
    log_path = Path(os.path.expanduser(logging_cfg.get("path", "~/.biliobjclint/lintserver.log")))
    log_level = logging_cfg.get("level", "info")
    logger = setup_logger(log_path, log_level)

    if sys.stdout.isatty():
        print("")
        print("=" * 60)
        print("  BiliObjCLint Server 正在前台运行")
        print("=" * 60)
        print("")

        # 显示可访问地址
        if host == "0.0.0.0":
            print("  监听地址: 0.0.0.0 (所有网络接口)")
            print("")
            print("  可访问地址:")
            print(f"    - http://127.0.0.1:{port}/login (本机)")
            local_ips = get_local_ips()
            if local_ips:
                for iface, ip in local_ips:
                    print(f"    - http://{ip}:{port}/login ({iface})")
            print("")
            print("  客户端配置 (.biliobjclint/config.yaml):")
            if local_ips:
                primary_ip = local_ips[0][1]
                print(f"    metrics:")
                print(f"      enabled: true")
                print(f"      endpoint: \"http://{primary_ip}:{port}\"")
                print(f"      token: \"<与服务端 ingest.token 一致>\"")
            else:
                print(f"    metrics.endpoint: \"http://<服务器IP>:{port}\"")
        else:
            print(f"  Dashboard: http://{host}:{port}/login")
            if host == "127.0.0.1":
                print("")
                print("  提示: 当前仅监听本机回环地址，其他机器无法访问")
                print("        如需远程访问，请修改配置文件中的 server.host 为 \"0.0.0.0\"")

        print("")
        print(f"  配置文件: {config_path}")
        print(f"  日志文件: {log_path}")
        print("")
        print("  按 Ctrl+C 停止服务")
        print("=" * 60)
        print("")
        sys.stdout.flush()

    storage_cfg = config.get("storage", {})
    storage_type = storage_cfg.get("type", "sqlite")
    if storage_type != "sqlite":
        logger.warning(f"Unsupported storage type: {storage_type}, fallback to sqlite")
    db_path = Path(os.path.expanduser(storage_cfg.get("path", "~/.biliobjclint/lintserver.db")))
    db = Database(db_path, logger)

    auth_cfg = config.get("auth", {})
    if auth_cfg.get("enabled", True):
        admin_user = auth_cfg.get("admin_user", "admin")
        admin_password = auth_cfg.get("admin_password", "")
        if admin_password == "":
            logger.warning("Admin password is empty. Please update config for security.")
        db.ensure_admin(admin_user, admin_password)

    sessions = SessionStore()
    httpd = HTTPServer((host, port), RequestHandler)
    httpd.state = ServerState(config=config, db=db, sessions=sessions, logger=logger)  # type: ignore[attr-defined]

    def handle_term(signum, frame):
        logger.info("Received signal, shutting down...")
        httpd.shutdown()

    signal.signal(signal.SIGTERM, handle_term)

    logger.info("Server starting on %s:%s", host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server interrupted")
    finally:
        httpd.server_close()
        logger.info("Server stopped")
    return 0


def start_server(config_path: Path, pid_path: Path) -> int:
    """后台启动服务器"""
    if pid_path.exists():
        pid = read_pid(pid_path)
        if is_running(pid):
            print(f"Server already running (pid={pid})")
            return 0
        pid_path.unlink()

    init_config(config_path)

    cmd = [sys.executable, str(Path(__file__).resolve()), "--run", "--config", str(config_path)]
    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        print(f"Failed to start server: {e}")
        return 1

    pid_path.write_text(str(proc.pid))
    print(f"Server started (pid={proc.pid})")
    return 0


def stop_server(pid_path: Path) -> int:
    """停止服务器"""
    pid = read_pid(pid_path)
    if pid <= 0 or not is_running(pid):
        print("Server not running")
        if pid_path.exists():
            pid_path.unlink()
        return 0

    # 先尝试 SIGTERM 优雅退出
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception as e:
        print(f"Failed to stop server: {e}")
        return 1

    # 等待 2 秒
    for _ in range(20):
        if not is_running(pid):
            break
        time.sleep(0.1)

    # 如果还在运行，强制 SIGKILL
    if is_running(pid):
        print(f"Server not responding to SIGTERM, sending SIGKILL (pid={pid})")
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception as e:
            print(f"Failed to kill server: {e}")
            return 1
        # 再等待 1 秒
        for _ in range(10):
            if not is_running(pid):
                break
            time.sleep(0.1)

    if is_running(pid):
        print(f"Failed to stop server (pid={pid})")
        return 1

    pid_path.unlink(missing_ok=True)
    print("Server stopped")
    return 0


def status_server(pid_path: Path) -> int:
    """查看服务器状态"""
    pid = read_pid(pid_path)
    if is_running(pid):
        print(f"Server running (pid={pid})")
        return 0
    print("Server not running")
    return 1


def clear_data(pid_path: Path, force: bool = False) -> int:
    """清空本地缓存数据"""
    import shutil

    data_dir = Path(os.path.expanduser("~/.biliobjclint"))

    if not data_dir.exists():
        print("No data to clear (directory does not exist)")
        return 0

    # 检查服务器是否在运行
    pid = read_pid(pid_path)
    if is_running(pid):
        print("Server is running. Please stop it first: biliobjclint-server stop")
        return 1

    # 列出将要删除的内容
    items = list(data_dir.iterdir())
    if not items:
        print("No data to clear (directory is empty)")
        return 0

    print("")
    print("=" * 60)
    print("  WARNING: This will permanently delete the following data:")
    print("=" * 60)
    print(f"\n  Directory: {data_dir}\n")

    total_size = 0
    for item in sorted(items):
        if item.is_file():
            size = item.stat().st_size
            total_size += size
            print(f"    - {item.name} ({_format_size(size)})")
        elif item.is_dir():
            dir_size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
            total_size += dir_size
            print(f"    - {item.name}/ ({_format_size(dir_size)})")

    print(f"\n  Total size: {_format_size(total_size)}")
    print("")
    print("  This includes:")
    print("    - SQLite database (all lint history)")
    print("    - Configuration file")
    print("    - Log files")
    print("    - PID file")
    print("    - Metrics spool data")
    print("")
    print("=" * 60)
    print("")

    if not force:
        try:
            response = input("Are you sure you want to delete all data? (type 'yes' to confirm): ")
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return 1

        if response.strip().lower() != "yes":
            print("Aborted.")
            return 1

    # 执行删除
    try:
        shutil.rmtree(data_dir)
        print(f"Cleared all data in {data_dir}")
        return 0
    except Exception as e:
        print(f"Failed to clear data: {e}")
        return 1


def _format_size(size: int) -> str:
    """格式化文件大小"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# ------------------------- CLI -------------------------

def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="BiliObjCLint Local Server")
    parser.add_argument("action", nargs="?", choices=["start", "stop", "restart", "status", "run", "clear"], help="Action")
    parser.add_argument("--start", action="store_true", help="Start server")
    parser.add_argument("--stop", action="store_true", help="Stop server")
    parser.add_argument("--restart", action="store_true", help="Restart server")
    parser.add_argument("--status", action="store_true", help="Show server status")
    parser.add_argument("--run", action="store_true", help="Run server in foreground")
    parser.add_argument("--clear", action="store_true", help="Clear all local data (interactive)")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation for clear")
    parser.add_argument("--config", help="Config file path")
    return parser.parse_args()


def main() -> int:
    """主入口"""
    args = parse_args()
    config_path = Path(args.config).expanduser() if args.config else default_config_path()
    pid_path = default_pid_path()

    if args.action and not any([args.start, args.stop, args.restart, args.status, args.run, args.clear]):
        if args.action == "start":
            args.start = True
        elif args.action == "stop":
            args.stop = True
        elif args.action == "restart":
            args.restart = True
        elif args.action == "status":
            args.status = True
        elif args.action == "run":
            args.run = True
        elif args.action == "clear":
            args.clear = True

    if args.clear:
        return clear_data(pid_path, force=args.yes)

    if args.run:
        init_config(config_path)
        return run_server(config_path)

    if args.restart:
        stop_server(pid_path)
        return start_server(config_path, pid_path)

    if args.start:
        return start_server(config_path, pid_path)

    if args.stop:
        return stop_server(pid_path)

    if args.status:
        return status_server(pid_path)

    print("No action specified. Use start/stop/restart/status/clear")
    return 1


if __name__ == "__main__":
    sys.exit(main())
