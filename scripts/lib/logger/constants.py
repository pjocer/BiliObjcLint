"""
BiliObjCLint Logger Constants

日志模块路径常量定义（内部使用，零依赖）
只使用 Python 标准库，不导入任何业务模块。
"""
from pathlib import Path


# ==================== 全局目录 ====================

# 全局根目录 ~/.biliobjclint
GLOBAL_DIR = Path.home() / '.biliobjclint'

# 日志目录 ~/.biliobjclint/logs/
LOGS_DIR = GLOBAL_DIR / 'logs'


# ==================== 日志格式 ====================

# 日志文件命名格式
LOG_FILENAME_FORMAT = "{module}_{timestamp}.log"
LOG_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"

# 日志输出格式
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
LOG_FORMAT_DETAILED = "%(asctime)s [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# ==================== 日志配置 ====================

# 日志保留天数
LOG_RETENTION_DAYS = 7

# 环境变量名
ENV_VERBOSE = "BILIOBJCLINT_VERBOSE"


# ==================== 工具函数 ====================

def ensure_logs_dir() -> Path:
    """确保日志目录存在"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR
