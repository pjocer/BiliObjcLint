#!/usr/bin/env python3
"""
项目配置持久化模块（重定向到 lib/common/project_store）

此模块已迁移到 lib/common/project_store.py
保留此文件仅为向后兼容，请使用新模块：

    from lib.common import project_store
    # 或
    from lib.common.project_store import ProjectConfig, ProjectStore, get_project_key, get_project_name
"""
import sys
from pathlib import Path

# 添加 scripts 目录到路径
SCRIPT_DIR = Path(__file__).parent
SCRIPTS_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPTS_ROOT))

# 重定向所有导出到新模块
from lib.common.project_store import (
    CONFIG_STORE,
    ProjectConfig,
    ProjectStore,
    normalize_path,
    make_key,
    save,
    get,
    get_scripts_srcroot_path,
    delete,
    list_all,
    get_project_key,
    get_project_name,
    get_project_root,
    ensure_config,
)

__all__ = [
    "CONFIG_STORE",
    "ProjectConfig",
    "ProjectStore",
    "normalize_path",
    "make_key",
    "save",
    "get",
    "get_scripts_srcroot_path",
    "delete",
    "list_all",
    "get_project_key",
    "get_project_name",
    "get_project_root",
    "ensure_config",
]
