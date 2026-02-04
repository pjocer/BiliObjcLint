"""BiliObjCLint Scripts Package

Bilibili Objective-C 代码规范检查工具的核心脚本包。

主要模块:
- core/lint: 核心 lint 功能（规则引擎、配置、报告等）
- core/server: 统计数据服务器
- wrapper/lint: lint 命令行入口
- wrapper/xcode: Xcode 集成
- wrapper/update: 版本更新模块
- claude: Claude AI 自动修复模块
"""
from .wrapper.lint import BiliObjCLint
from .wrapper.xcode import XcodeIntegrator, SCRIPT_VERSION
from .wrapper.update import check_version_update

__all__ = [
    'BiliObjCLint',
    'XcodeIntegrator',
    'SCRIPT_VERSION',
    'check_version_update',
]
