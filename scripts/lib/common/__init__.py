"""
Common utilities module
"""
from .project_store import (
    # 数据结构
    ProjectConfig,
    # 存储类（多工程配置 CRUD）
    ProjectStore,
    # 上下文单例（运行时当前项目）
    ProjectContext,
    # 便捷函数
    get_project_key,
    get_project_name,
    get_project_root,
    # 工具函数
    make_key,
    normalize_path,
)

__all__ = [
    # 数据结构
    "ProjectConfig",
    # 存储类
    "ProjectStore",
    # 上下文单例
    "ProjectContext",
    # 便捷函数
    "get_project_key",
    "get_project_name",
    "get_project_root",
    # 工具函数
    "make_key",
    "normalize_path",
]
