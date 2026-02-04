"""
BiliObjCLint Server - 认证模块
"""
from __future__ import annotations

import hashlib
import os
import secrets
import time
from typing import Dict, Optional, Tuple


def hash_password(password: str, salt_hex: Optional[str] = None) -> str:
    """
    使用 PBKDF2 哈希密码

    Args:
        password: 明文密码
        salt_hex: 可选的盐值（十六进制字符串），不提供则自动生成

    Returns:
        格式为 "salt$hash" 的字符串
    """
    if salt_hex:
        salt = bytes.fromhex(salt_hex)
    else:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return f"{salt.hex()}${dk.hex()}"


def verify_password(stored: str, password: str) -> bool:
    """
    验证密码

    Args:
        stored: 存储的密码哈希（格式为 "salt$hash"）
        password: 待验证的明文密码

    Returns:
        密码是否匹配
    """
    try:
        salt_hex, hash_hex = stored.split("$", 1)
    except ValueError:
        return False
    new_hash = hash_password(password, salt_hex).split("$", 1)[1]
    return secrets.compare_digest(hash_hex, new_hash)


class SessionStore:
    """会话存储"""

    def __init__(self, ttl_seconds: int = 3600 * 12):
        """
        初始化会话存储

        Args:
            ttl_seconds: 会话有效期（秒），默认 12 小时
        """
        self.ttl = ttl_seconds
        self.sessions: Dict[str, Tuple[str, str, float]] = {}

    def create(self, username: str, role: str) -> str:
        """
        创建新会话

        Args:
            username: 用户名
            role: 用户角色

        Returns:
            会话 ID
        """
        session_id = secrets.token_hex(16)
        self.sessions[session_id] = (username, role, time.time())
        return session_id

    def get(self, session_id: str) -> Optional[Tuple[str, str]]:
        """
        获取会话信息

        Args:
            session_id: 会话 ID

        Returns:
            (username, role) 元组，会话无效或过期则返回 None
        """
        data = self.sessions.get(session_id)
        if not data:
            return None
        username, role, created_at = data
        if time.time() - created_at > self.ttl:
            self.sessions.pop(session_id, None)
            return None
        return username, role

    def clear(self, session_id: str) -> None:
        """清除会话"""
        self.sessions.pop(session_id, None)
