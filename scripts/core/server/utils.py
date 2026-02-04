"""
BiliObjCLint Server - 工具函数
"""
from __future__ import annotations

import os
from pathlib import Path


def ensure_dir(path: Path) -> None:
    """确保目录存在"""
    path.mkdir(parents=True, exist_ok=True)


def default_config_path() -> Path:
    """默认配置文件路径"""
    return Path(os.path.expanduser("~/.biliobjclint/biliobjclint_server_config.json"))


def default_pid_path() -> Path:
    """默认 PID 文件路径"""
    return Path(os.path.expanduser("~/.biliobjclint/lintserver.pid"))


def project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent.parent.parent


def template_config_path() -> Path:
    """配置模板文件路径"""
    return project_root() / "config" / "biliobjclint_server_config.json"
