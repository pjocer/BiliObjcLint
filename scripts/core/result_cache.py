"""
Result Cache Module - 规则检查结果缓存

支持持久化缓存，跨进程复用检查结果，减少重复计算。

缓存失效策略：
- 文件 mtime 变化
- 规则配置变化（通过 config_hash 判断）
"""
import os
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from threading import RLock

from .logger import get_logger


@dataclass
class CachedResult:
    """缓存的检查结果"""
    file_path: str
    mtime: float
    config_hash: str
    violations: List[Dict[str, Any]]  # 序列化的 Violation 列表


class ResultCache:
    """规则检查结果缓存"""

    def __init__(self, cache_dir: str, enabled: bool = True):
        """
        Args:
            cache_dir: 缓存目录路径
            enabled: 是否启用缓存
        """
        self.cache_dir = Path(cache_dir)
        self.enabled = enabled
        self.logger = get_logger("biliobjclint")
        self._lock = RLock()
        self._memory_cache: Dict[str, CachedResult] = {}
        self._hits = 0
        self._misses = 0

        if self.enabled:
            self._ensure_cache_dir()
            self._load_cache()

    def _ensure_cache_dir(self):
        """确保缓存目录存在"""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.warning(f"Failed to create cache dir: {e}")
            self.enabled = False

    def _get_cache_file(self) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / "result_cache.json"

    def _load_cache(self):
        """从磁盘加载缓存"""
        cache_file = self._get_cache_file()
        if not cache_file.exists():
            return

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for key, value in data.items():
                    self._memory_cache[key] = CachedResult(**value)
            self.logger.debug(f"Loaded {len(self._memory_cache)} cached results from disk")
        except Exception as e:
            self.logger.warning(f"Failed to load result cache: {e}")
            self._memory_cache = {}

    def save(self):
        """保存缓存到磁盘"""
        if not self.enabled:
            return

        with self._lock:
            cache_file = self._get_cache_file()
            try:
                data = {k: asdict(v) for k, v in self._memory_cache.items()}
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False)
                self.logger.debug(f"Saved {len(self._memory_cache)} cached results to disk")
            except Exception as e:
                self.logger.warning(f"Failed to save result cache: {e}")

    @staticmethod
    def compute_config_hash(rules_config: Dict[str, Any]) -> str:
        """计算规则配置的 hash 值"""
        # 序列化配置并计算 MD5
        config_str = json.dumps(rules_config, sort_keys=True, default=str)
        return hashlib.md5(config_str.encode()).hexdigest()[:16]

    def _get_cache_key(self, file_path: str) -> str:
        """生成缓存键"""
        # 使用文件路径的 hash 作为键，避免路径过长
        return hashlib.md5(file_path.encode()).hexdigest()

    def get(self, file_path: str, config_hash: str) -> Optional[List[Dict[str, Any]]]:
        """
        获取缓存的检查结果

        Args:
            file_path: 文件路径
            config_hash: 规则配置 hash

        Returns:
            缓存的 violations 列表，如果缓存未命中返回 None
        """
        if not self.enabled:
            return None

        with self._lock:
            key = self._get_cache_key(file_path)
            cached = self._memory_cache.get(key)

            if cached is None:
                self._misses += 1
                return None

            # 检查文件 mtime 是否变化
            try:
                current_mtime = os.path.getmtime(file_path)
            except OSError:
                self._misses += 1
                return None

            if cached.mtime != current_mtime:
                self._misses += 1
                self.logger.debug(f"Cache miss (mtime changed): {file_path}")
                return None

            # 检查配置 hash 是否变化
            if cached.config_hash != config_hash:
                self._misses += 1
                self.logger.debug(f"Cache miss (config changed): {file_path}")
                return None

            self._hits += 1
            self.logger.debug(f"Cache hit: {file_path}")
            return cached.violations

    def put(self, file_path: str, config_hash: str, violations: List[Dict[str, Any]]):
        """
        存储检查结果到缓存

        Args:
            file_path: 文件路径
            config_hash: 规则配置 hash
            violations: violations 列表（已序列化为 dict）
        """
        if not self.enabled:
            return

        try:
            mtime = os.path.getmtime(file_path)
        except OSError:
            return

        with self._lock:
            key = self._get_cache_key(file_path)
            self._memory_cache[key] = CachedResult(
                file_path=file_path,
                mtime=mtime,
                config_hash=config_hash,
                violations=violations
            )

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._memory_cache.clear()
            self._hits = 0
            self._misses = 0
            cache_file = self._get_cache_file()
            if cache_file.exists():
                try:
                    cache_file.unlink()
                except Exception:
                    pass

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0
            return {
                "enabled": self.enabled,
                "entries": len(self._memory_cache),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{hit_rate:.1%}"
            }


# 全局缓存实例
_result_cache: Optional[ResultCache] = None


def get_result_cache(cache_dir: str = None, enabled: bool = True) -> ResultCache:
    """获取全局结果缓存实例"""
    global _result_cache
    if _result_cache is None:
        if cache_dir is None:
            # 默认缓存目录：项目根目录下的 .biliobjclint_cache
            cache_dir = ".biliobjclint_cache"
        _result_cache = ResultCache(cache_dir, enabled)
    return _result_cache


def reset_result_cache():
    """重置全局缓存实例"""
    global _result_cache
    _result_cache = None
