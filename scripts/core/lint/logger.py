"""
BiliObjCLint Logger Module - 统一日志记录

日志文件存储在 BiliObjCLint/logs/ 目录下，按日期和模块分类：
- biliobjclint_YYYYMMDD_HHMMSS.log  # 主 lint 日志
- claude_fix_YYYYMMDD_HHMMSS.log   # Claude 修复日志
- xcode_YYYYMMDD_HHMMSS.log        # Xcode 集成日志

Usage:
    from core.lint.logger import get_logger, LogContext

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
from pathlib import Path
from typing import Optional
from contextlib import contextmanager
from functools import wraps
import traceback


# 日志目录
def get_logs_dir() -> Path:
    """获取日志目录路径

    统一使用 ~/.biliobjclint/logs/，避免依赖脚本自身位置推算。
    解决 brew Cellar 目录在升级时被删除导致日志丢失的问题。
    """
    logs_dir = Path.home() / ".biliobjclint" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


# 日志格式
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
LOG_FORMAT_DETAILED = "%(asctime)s [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class BiliObjCLintLogger:
    """BiliObjCLint 日志记录器"""

    _instances = {}
    _session_id = None

    def __init__(self, name: str, log_file: Optional[str] = None):
        self.name = name
        self.logger = logging.getLogger(f"biliobjclint.{name}")
        self.logger.setLevel(logging.DEBUG)

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
        if os.environ.get('BILIOBJCLINT_VERBOSE'):
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
            self.logger.addHandler(console_handler)

        self.log_file = log_file

    def _get_default_log_file(self) -> str:
        """获取默认日志文件路径"""
        logs_dir = get_logs_dir()

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


class LogContext:
    """日志上下文管理器"""

    def __init__(self, logger: BiliObjCLintLogger, context_name: str):
        self.logger = logger
        self.context_name = context_name
        self.start_time = None

    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.debug(f"[{self.context_name}] Started")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if exc_type:
            self.logger.error(f"[{self.context_name}] Failed after {elapsed:.2f}s: {exc_val}")
            self.logger.debug(f"[{self.context_name}] Traceback: {traceback.format_exc()}")
        else:
            self.logger.debug(f"[{self.context_name}] Completed in {elapsed:.2f}s")
        return False  # 不抑制异常


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


def get_current_log_file(name: str = "biliobjclint") -> Optional[str]:
    """获取当前日志文件路径"""
    if name in BiliObjCLintLogger._instances:
        return BiliObjCLintLogger._instances[name].log_file
    return None


def cleanup_old_logs(max_days: int = 7):
    """清理旧日志文件"""
    logs_dir = get_logs_dir()
    now = datetime.now()

    for log_file in logs_dir.glob("*.log"):
        try:
            # 从文件名解析日期
            # 格式: name_YYYYMMDD_HHMMSS.log
            parts = log_file.stem.split('_')
            if len(parts) >= 2:
                date_str = parts[-2]  # YYYYMMDD
                file_date = datetime.strptime(date_str, "%Y%m%d")
                age_days = (now - file_date).days
                if age_days > max_days:
                    log_file.unlink()
        except (ValueError, IndexError):
            continue


# 便捷函数
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
