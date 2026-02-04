#!/usr/bin/env python3
"""
兼容层：保留旧版本导入路径

v1.4.10 将 xcode_integrator.py 迁移到 wrapper/xcode/，
但旧版本（如 v1.4.9）的 background_upgrade.py 内联脚本仍然使用：
    from xcode_integrator import XcodeIntegrator, SCRIPT_VERSION

此文件作为兼容层，确保旧版本升级到新版本时不会因导入失败而中断。

WARNING: 此文件仅用于兼容性，请勿直接使用。新代码应使用：
    from wrapper.xcode import XcodeIntegrator, SCRIPT_VERSION
"""
import sys
from pathlib import Path

# 添加 scripts 目录到路径
SCRIPT_DIR = Path(__file__).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# 从新位置导入并重新导出
from wrapper.xcode import XcodeIntegrator, SCRIPT_VERSION
from wrapper.xcode.templates import (
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
