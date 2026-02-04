"""BiliObjCLint Update Module

负责版本检查、后台升级和 Build Phase 更新。

主要组件:
- checker: 版本检查和注入逻辑
- upgrader: 后台升级执行
- phase_updater: Build Phase 独立更新脚本（由子进程调用）
"""
from .checker import (
    check_version_update,
    get_local_version,
    get_remote_version,
    do_check_and_inject,
)

__all__ = [
    'check_version_update',
    'get_local_version',
    'get_remote_version',
    'do_check_and_inject',
]
