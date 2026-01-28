"""
Ignore Cache Module - 忽略缓存管理

基于代码内容哈希的忽略机制，不依赖行号，能够正确处理代码变更后的行号偏移。
"""
import os
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Set
from datetime import datetime

from .logger import get_logger


class IgnoreCache:
    """忽略缓存管理器"""

    VERSION = 1

    def __init__(self, cache_dir: str = None, project_root: str = None):
        """
        初始化忽略缓存

        Args:
            cache_dir: 缓存目录，默认 ~/.biliobjclint
            project_root: 项目根目录，用于计算相对路径
        """
        self.cache_dir = cache_dir or os.path.expanduser("~/.biliobjclint")
        self.cache_file = os.path.join(self.cache_dir, "ignore_cache.json")
        self.project_root = Path(project_root) if project_root else None
        self._cache: Optional[Dict] = None
        self.logger = get_logger("biliobjclint")

    def _ensure_cache_dir(self):
        """确保缓存目录存在"""
        os.makedirs(self.cache_dir, exist_ok=True)

    def load(self) -> List[dict]:
        """加载缓存"""
        if self._cache is not None:
            return self._cache.get("ignores", [])

        if not os.path.exists(self.cache_file):
            self._cache = {"version": self.VERSION, "ignores": []}
            return []

        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                self._cache = json.load(f)

            # 版本迁移
            if self._cache.get("version", 0) < self.VERSION:
                self._cache = {"version": self.VERSION, "ignores": []}

            return self._cache.get("ignores", [])
        except Exception as e:
            self.logger.warning(f"Failed to load ignore cache: {e}")
            self._cache = {"version": self.VERSION, "ignores": []}
            return []

    def save(self):
        """保存缓存"""
        if self._cache is None:
            return

        try:
            self._ensure_cache_dir()
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
            self.logger.debug(f"Saved ignore cache: {len(self._cache.get('ignores', []))} items")
        except Exception as e:
            self.logger.warning(f"Failed to save ignore cache: {e}")

    def _get_relative_path(self, file_path: str) -> str:
        """获取相对路径"""
        try:
            if self.project_root:
                return str(Path(file_path).relative_to(self.project_root))
        except ValueError:
            pass
        return file_path

    def _calculate_code_hash(self, file_path: str, line: int, rule_id: str, context_lines: int = 2) -> Optional[str]:
        """
        计算违规的代码哈希

        使用违规行及其上下文（前后各 N 行）的内容哈希。
        这样即使行号变化，只要代码内容不变，签名就不变。

        Args:
            file_path: 文件路径
            line: 违规行号
            rule_id: 规则 ID
            context_lines: 上下文行数

        Returns:
            MD5 哈希字符串，失败返回 None
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            # 计算上下文范围
            start = max(0, line - 1 - context_lines)
            end = min(len(lines), line + context_lines)

            # 获取上下文代码
            context = lines[start:end]

            # 去除空白字符的影响，但保留代码结构
            normalized = ''.join(l.strip() for l in context)

            # 计算哈希
            hash_input = f"{rule_id}:{normalized}"
            return hashlib.md5(hash_input.encode()).hexdigest()
        except Exception as e:
            self.logger.debug(f"Failed to calculate code hash for {file_path}:{line}: {e}")
            return None

    def add_ignore(self, file_path: str, line: int, rule_id: str, message: str) -> bool:
        """
        添加忽略项

        Args:
            file_path: 文件绝对路径
            line: 违规行号
            rule_id: 规则 ID
            message: 违规消息

        Returns:
            是否成功添加
        """
        self.load()  # 确保缓存已加载

        # 计算代码哈希
        code_hash = self._calculate_code_hash(file_path, line, rule_id)
        if not code_hash:
            return False

        # 获取相对路径用于存储
        rel_path = self._get_relative_path(file_path)

        # 检查是否已存在
        for ignore in self._cache.get("ignores", []):
            if (ignore.get("file_path") == rel_path and
                ignore.get("rule_id") == rule_id and
                ignore.get("code_hash") == code_hash):
                self.logger.debug(f"Ignore already exists: {rel_path}:{line} [{rule_id}]")
                return True

        # 添加新忽略项
        ignore_entry = {
            "file_path": rel_path,
            "rule_id": rule_id,
            "code_hash": code_hash,
            "message": message,
            "original_line": line,  # 仅供参考
            "created_at": datetime.now().isoformat()
        }

        self._cache["ignores"].append(ignore_entry)
        self.save()

        self.logger.info(f"Added ignore: {rel_path}:{line} [{rule_id}]")
        return True

    def is_ignored(self, file_path: str, line: int, rule_id: str) -> bool:
        """
        检查违规是否被忽略

        Args:
            file_path: 文件绝对路径
            line: 违规行号
            rule_id: 规则 ID

        Returns:
            是否被忽略
        """
        self.load()

        # 计算当前代码哈希
        current_hash = self._calculate_code_hash(file_path, line, rule_id)
        if not current_hash:
            return False

        # 获取相对路径
        rel_path = self._get_relative_path(file_path)

        # 在缓存中查找匹配项
        for ignore in self._cache.get("ignores", []):
            if (ignore.get("file_path") == rel_path and
                ignore.get("rule_id") == rule_id and
                ignore.get("code_hash") == current_hash):
                return True

        return False

    def remove_ignore(self, file_path: str, line: int, rule_id: str) -> bool:
        """
        移除忽略项

        Args:
            file_path: 文件绝对路径
            line: 违规行号
            rule_id: 规则 ID

        Returns:
            是否成功移除
        """
        self.load()

        # 计算当前代码哈希
        current_hash = self._calculate_code_hash(file_path, line, rule_id)
        if not current_hash:
            return False

        rel_path = self._get_relative_path(file_path)

        # 查找并移除
        ignores = self._cache.get("ignores", [])
        for i, ignore in enumerate(ignores):
            if (ignore.get("file_path") == rel_path and
                ignore.get("rule_id") == rule_id and
                ignore.get("code_hash") == current_hash):
                ignores.pop(i)
                self.save()
                self.logger.info(f"Removed ignore: {rel_path}:{line} [{rule_id}]")
                return True

        return False

    def cleanup_stale(self, current_violations: List[dict] = None):
        """
        清理过期的忽略记录

        移除条件：
        - 文件已删除
        - 对应的代码哈希在当前违规中完全不存在

        Args:
            current_violations: 当前违规列表，每项应包含 file_path, line, rule_id
        """
        self.load()

        if not self._cache.get("ignores"):
            return

        # 构建当前有效哈希集合
        valid_hashes: Set[str] = set()
        if current_violations:
            for v in current_violations:
                code_hash = self._calculate_code_hash(
                    v.get("file_path", ""),
                    v.get("line", 0),
                    v.get("rule_id", "")
                )
                if code_hash:
                    key = f"{self._get_relative_path(v['file_path'])}:{v['rule_id']}:{code_hash}"
                    valid_hashes.add(key)

        # 过滤无效的忽略记录
        original_count = len(self._cache["ignores"])
        valid_ignores = []

        for ignore in self._cache["ignores"]:
            file_path = ignore.get("file_path", "")
            rule_id = ignore.get("rule_id", "")
            code_hash = ignore.get("code_hash", "")

            # 检查文件是否存在
            abs_path = file_path
            if self.project_root and not os.path.isabs(file_path):
                abs_path = str(self.project_root / file_path)

            if not os.path.exists(abs_path):
                self.logger.debug(f"Removing stale ignore (file deleted): {file_path}")
                continue

            # 如果有当前违规列表，检查哈希是否仍然匹配
            # 注意：只有当代码完全改变时才移除，否则保留
            # 这里我们保守处理：只移除文件已删除的情况
            valid_ignores.append(ignore)

        self._cache["ignores"] = valid_ignores
        removed_count = original_count - len(valid_ignores)

        if removed_count > 0:
            self.save()
            self.logger.info(f"Cleaned up {removed_count} stale ignore entries")

    def get_all_ignores(self) -> List[dict]:
        """获取所有忽略项"""
        return self.load()

    def clear_all(self):
        """清空所有忽略项"""
        self._cache = {"version": self.VERSION, "ignores": []}
        self.save()
        self.logger.info("Cleared all ignore entries")
