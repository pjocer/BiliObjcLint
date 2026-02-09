"""
BiliObjCLint Logger Module

统一日志模块，日志文件存储在 ~/.biliobjclint/logs/ 目录下。

Usage:
    from lib.logger import get_logger, LogContext

    logger = get_logger("biliobjclint")
    logger.info("Starting lint check")

    # 使用上下文记录
    with LogContext(logger, "config_loading"):
        logger.debug("Loading config...")

Available loggers:
    - biliobjclint: 主 lint 日志
    - claude_fix: Claude 修复日志
    - xcode: Xcode 集成日志
    - check_update: 版本检查日志
    - background_upgrade: 后台升级日志
"""
from .python_logger import (
    BiliObjCLintLogger,
    get_logger,
    reset_session,
    log_function,
    log_lint_start,
    log_lint_end,
    log_claude_fix_start,
    log_claude_fix_end,
)
from .context import LogContext
from .utils import cleanup_old_logs, get_current_log_file
from .constants import LOGS_DIR, GLOBAL_DIR

__all__ = [
    # 核心类和函数
    'BiliObjCLintLogger',
    'get_logger',
    'LogContext',
    'reset_session',
    'log_function',

    # 便捷函数
    'log_lint_start',
    'log_lint_end',
    'log_claude_fix_start',
    'log_claude_fix_end',

    # 工具函数
    'cleanup_old_logs',
    'get_current_log_file',

    # 常量
    'LOGS_DIR',
    'GLOBAL_DIR',
]
