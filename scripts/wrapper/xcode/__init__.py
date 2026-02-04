"""BiliObjCLint Xcode 集成模块

提供 Xcode 项目的 Build Phase 注入和管理功能。

主要组件:
- XcodeIntegrator: 主集成器类
- SCRIPT_VERSION: 当前脚本版本
- PHASE_NAME: Lint Phase 名称
- BOOTSTRAP_PHASE_NAME: Bootstrap Phase 名称
"""
from .integrator import XcodeIntegrator
from .templates import (
    SCRIPT_VERSION,
    PHASE_NAME,
    BOOTSTRAP_PHASE_NAME,
    LINT_SCRIPT_TEMPLATE,
    BOOTSTRAP_SCRIPT_TEMPLATE,
    get_version,
)

__all__ = [
    'XcodeIntegrator',
    'SCRIPT_VERSION',
    'PHASE_NAME',
    'BOOTSTRAP_PHASE_NAME',
    'LINT_SCRIPT_TEMPLATE',
    'BOOTSTRAP_SCRIPT_TEMPLATE',
    'get_version',
]
