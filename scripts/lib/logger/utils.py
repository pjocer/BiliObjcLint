"""
BiliObjCLint Logger Utilities

日志工具函数（清理、格式化等）
"""
from datetime import datetime
from typing import Optional

from .constants import LOGS_DIR, LOG_RETENTION_DAYS


def cleanup_old_logs(max_days: int = LOG_RETENTION_DAYS) -> int:
    """清理旧日志文件

    Args:
        max_days: 保留天数，默认 7 天

    Returns:
        删除的文件数量
    """
    if not LOGS_DIR.exists():
        return 0

    now = datetime.now()
    deleted_count = 0

    for log_file in LOGS_DIR.glob("*.log"):
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
                    deleted_count += 1
        except (ValueError, IndexError):
            continue

    return deleted_count


def get_current_log_file(name: str = "biliobjclint") -> Optional[str]:
    """获取当前日志文件路径

    Args:
        name: 日志记录器名称

    Returns:
        日志文件路径，如果不存在则返回 None
    """
    # 延迟导入避免循环依赖
    from .python_logger import BiliObjCLintLogger

    if name in BiliObjCLintLogger._instances:
        return BiliObjCLintLogger._instances[name].log_file
    return None


def generate_log_filename(module: str, timestamp: Optional[datetime] = None) -> str:
    """生成日志文件名

    Args:
        module: 模块名称
        timestamp: 时间戳，默认为当前时间

    Returns:
        日志文件名（不含路径）
    """
    if timestamp is None:
        timestamp = datetime.now()
    ts_str = timestamp.strftime("%Y%m%d_%H%M%S")
    return f"{module}_{ts_str}.log"
