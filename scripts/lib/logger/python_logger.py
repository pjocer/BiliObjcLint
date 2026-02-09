"""
BiliObjCLint Python Logger

Python 日志实现，从 core/lint/logger.py 迁移。
日志文件统一存储在 ~/.biliobjclint/logs/ 目录下。

Usage:
    from lib.logger import get_logger, LogContext

    logger = get_logger('biliobjclint')
    logger.info("Starting lint check")

    # 使用上下文记录
    with LogContext(logger, "config_loading"):
        logger.debug("Loading config from path")
"""
import logging
import os
import sys
from datetime import datetime
from functools import wraps
from typing import Optional

from .constants import (
    LOGS_DIR,
    LOG_FORMAT,
    LOG_FORMAT_DETAILED,
    DATE_FORMAT,
    ENV_VERBOSE,
    ensure_logs_dir,
)


class BiliObjCLintLogger:
    """BiliObjCLint 日志记录器"""

    _instances: dict = {}
    _session_id: Optional[str] = None

    def __init__(self, name: str, log_file: Optional[str] = None):
        self.name = name
        self.logger = logging.getLogger(f"biliobjclint.{name}")
        self.logger.setLevel(logging.DEBUG)
        self.log_file: Optional[str] = None

        # 确保不重复添加 handler
        if not self.logger.handlers:
            self._setup_handlers(log_file)

    def _setup_handlers(self, log_file: Optional[str] = None):
        """设置日志处理器"""
        # 文件处理器
        if log_file is None:
            log_file = self._get_default_log_file()

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT_DETAILED, DATE_FORMAT))
        self.logger.addHandler(file_handler)

        # 控制台处理器（仅 WARNING 及以上）- 可通过环境变量控制
        if os.environ.get(ENV_VERBOSE):
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
            self.logger.addHandler(console_handler)

        self.log_file = log_file

    def _get_default_log_file(self) -> str:
        """获取默认日志文件路径"""
        # 确保日志目录存在
        logs_dir = ensure_logs_dir()

        # 使用会话 ID 确保同一次运行的日志在同一个文件
        if BiliObjCLintLogger._session_id is None:
            BiliObjCLintLogger._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        session_id = BiliObjCLintLogger._session_id
        log_file = logs_dir / f"{self.name}_{session_id}.log"
        return str(log_file)

    def debug(self, msg: str, *args, **kwargs):
        """DEBUG 级别日志"""
        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        """INFO 级别日志"""
        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        """WARNING 级别日志"""
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        """ERROR 级别日志"""
        self.logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        """CRITICAL 级别日志"""
        self.logger.critical(msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs):
        """记录异常信息"""
        self.logger.exception(msg, *args, **kwargs)

    def log_separator(self, title: str = ""):
        """记录分隔线"""
        if title:
            self.info(f"{'=' * 20} {title} {'=' * 20}")
        else:
            self.info("=" * 60)

    def log_dict(self, title: str, data: dict, level: str = "debug"):
        """记录字典数据"""
        log_func = getattr(self, level, self.debug)
        log_func(f"{title}:")
        for key, value in data.items():
            log_func(f"  {key}: {value}")

    def log_list(self, title: str, items: list, level: str = "debug", max_items: int = 20):
        """记录列表数据"""
        log_func = getattr(self, level, self.debug)
        log_func(f"{title} ({len(items)} items):")
        for i, item in enumerate(items[:max_items]):
            log_func(f"  [{i}] {item}")
        if len(items) > max_items:
            log_func(f"  ... and {len(items) - max_items} more")


def get_logger(name: str, log_file: Optional[str] = None) -> BiliObjCLintLogger:
    """
    获取日志记录器（单例模式）

    Args:
        name: 日志记录器名称，如 'biliobjclint', 'claude_fix', 'xcode'
        log_file: 可选的日志文件路径

    Returns:
        BiliObjCLintLogger 实例
    """
    if name not in BiliObjCLintLogger._instances:
        BiliObjCLintLogger._instances[name] = BiliObjCLintLogger(name, log_file)
    return BiliObjCLintLogger._instances[name]


def reset_session():
    """重置会话（用于新的运行）"""
    BiliObjCLintLogger._session_id = None
    BiliObjCLintLogger._instances.clear()


def log_function(logger_name: str = "biliobjclint"):
    """函数装饰器，自动记录函数调用"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger(logger_name)
            func_name = func.__name__
            logger.debug(f"Calling {func_name}()")
            try:
                result = func(*args, **kwargs)
                logger.debug(f"{func_name}() completed successfully")
                return result
            except Exception as e:
                logger.error(f"{func_name}() failed: {e}")
                raise
        return wrapper
    return decorator


# ==================== 便捷函数 ====================

def log_lint_start(project_root: str, files_count: int, incremental: bool = False):
    """记录 lint 开始"""
    logger = get_logger("biliobjclint")
    logger.log_separator("BiliObjCLint Session Start")
    logger.info(f"Project root: {project_root}")
    logger.info(f"Files to check: {files_count}")
    logger.info(f"Incremental mode: {incremental}")


def log_lint_end(violations_count: int, errors_count: int, warnings_count: int, elapsed: float):
    """记录 lint 结束"""
    logger = get_logger("biliobjclint")
    logger.info(f"Lint completed in {elapsed:.2f}s")
    logger.info(f"Total violations: {violations_count} (errors: {errors_count}, warnings: {warnings_count})")
    logger.log_separator("BiliObjCLint Session End")


def log_claude_fix_start(violations_count: int, project_root: str):
    """记录 Claude 修复开始"""
    logger = get_logger("claude_fix")
    logger.log_separator("Claude Fix Session Start")
    logger.info(f"Project root: {project_root}")
    logger.info(f"Violations to fix: {violations_count}")


def log_claude_fix_end(success: bool, message: str, elapsed: float):
    """记录 Claude 修复结束"""
    logger = get_logger("claude_fix")
    status = "SUCCESS" if success else "FAILED"
    logger.info(f"Claude fix {status}: {message}")
    logger.info(f"Elapsed time: {elapsed:.2f}s")
    logger.log_separator("Claude Fix Session End")
