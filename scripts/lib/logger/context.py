"""
BiliObjCLint Logger Context

日志上下文管理器，用于记录代码块的执行时间和状态。
"""
from datetime import datetime
import traceback
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .python_logger import BiliObjCLintLogger


class LogContext:
    """日志上下文管理器

    Usage:
        with LogContext(logger, "config_loading"):
            logger.debug("Loading config from path")
    """

    def __init__(self, logger: "BiliObjCLintLogger", context_name: str):
        """
        Args:
            logger: BiliObjCLintLogger 实例
            context_name: 上下文名称，用于日志标识
        """
        self.logger = logger
        self.context_name = context_name
        self.start_time: datetime = None

    def __enter__(self) -> "LogContext":
        self.start_time = datetime.now()
        self.logger.debug(f"[{self.context_name}] Started")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if exc_type:
            self.logger.error(f"[{self.context_name}] Failed after {elapsed:.2f}s: {exc_val}")
            self.logger.debug(f"[{self.context_name}] Traceback: {traceback.format_exc()}")
        else:
            self.logger.debug(f"[{self.context_name}] Completed in {elapsed:.2f}s")
        return False  # 不抑制异常
