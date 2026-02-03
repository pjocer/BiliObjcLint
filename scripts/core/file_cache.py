"""
File Content Cache - 文件内容缓存层

基于 mtime 的缓存失效策略，避免重复读取文件。
线程安全设计，支持并行检查。
"""
import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, List
from threading import RLock

from .logger import get_logger


@dataclass
class CachedFile:
    """缓存的文件内容"""
    content: str
    lines: List[str]
    mtime: float
    size: int


class FileContentCache:
    """
    文件内容缓存

    线程安全的文件内容缓存，支持 mtime 失效检测。
    """

    def __init__(self, max_size_mb: int = 100):
        """
        Args:
            max_size_mb: 缓存最大容量（MB）
        """
        self._cache: Dict[str, CachedFile] = {}
        self._lock = RLock()
        self._max_size = max_size_mb * 1024 * 1024
        self._current_size = 0
        self.logger = get_logger("biliobjclint")
        self._hit_count = 0
        self._miss_count = 0

    def get(self, file_path: str) -> Optional[Tuple[str, List[str]]]:
        """
        获取文件内容（带缓存）

        Args:
            file_path: 文件绝对路径

        Returns:
            (content, lines) 或 None（文件不存在或读取失败）
        """
        with self._lock:
            # 检查缓存是否存在且有效
            if file_path in self._cache:
                cached = self._cache[file_path]
                try:
                    current_mtime = os.path.getmtime(file_path)
                    if cached.mtime == current_mtime:
                        self._hit_count += 1
                        return cached.content, cached.lines
                    # mtime 变化，需要重新读取
                except OSError:
                    pass

            # 缓存未命中，读取文件
            self._miss_count += 1
            return self._read_and_cache(file_path)

    def _read_and_cache(self, file_path: str) -> Optional[Tuple[str, List[str]]]:
        """读取文件并缓存"""
        try:
            stat = os.stat(file_path)
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            lines = content.split('\n')
            size = len(content.encode('utf-8'))

            # 检查是否需要淘汰旧缓存
            self._evict_if_needed(size)

            # 更新或添加缓存
            if file_path in self._cache:
                self._current_size -= self._cache[file_path].size

            self._cache[file_path] = CachedFile(
                content=content,
                lines=lines,
                mtime=stat.st_mtime,
                size=size
            )
            self._current_size += size

            return content, lines
        except Exception as e:
            self.logger.debug(f"Failed to read file {file_path}: {e}")
            return None

    def _evict_if_needed(self, new_size: int):
        """LRU 淘汰策略（简化版：删除最早添加的）"""
        while self._current_size + new_size > self._max_size and self._cache:
            oldest_key = next(iter(self._cache))
            oldest = self._cache.pop(oldest_key)
            self._current_size -= oldest.size
            self.logger.debug(f"Evicted from cache: {oldest_key}")

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._current_size = 0
            self._hit_count = 0
            self._miss_count = 0

    def invalidate(self, file_path: str):
        """使特定文件的缓存失效"""
        with self._lock:
            if file_path in self._cache:
                self._current_size -= self._cache[file_path].size
                del self._cache[file_path]

    def get_stats(self) -> Dict[str, float]:
        """获取缓存统计"""
        with self._lock:
            total = self._hit_count + self._miss_count
            hit_rate = (self._hit_count / total * 100) if total > 0 else 0
            return {
                "cached_files": len(self._cache),
                "cache_size_mb": self._current_size / 1024 / 1024,
                "hit_count": self._hit_count,
                "miss_count": self._miss_count,
                "hit_rate": hit_rate
            }


# 全局缓存实例（单例）
_global_cache: Optional[FileContentCache] = None
_cache_lock = RLock()


def get_file_cache(max_size_mb: int = 100) -> FileContentCache:
    """获取全局文件缓存实例"""
    global _global_cache
    with _cache_lock:
        if _global_cache is None:
            _global_cache = FileContentCache(max_size_mb)
        return _global_cache


def reset_file_cache():
    """重置全局缓存（用于测试）"""
    global _global_cache
    with _cache_lock:
        if _global_cache:
            _global_cache.clear()
        _global_cache = None
