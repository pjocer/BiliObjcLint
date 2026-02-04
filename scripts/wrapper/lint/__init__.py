"""BiliObjCLint Lint 模块

提供代码规范检查的核心功能。

主要组件:
- BiliObjCLint: 主 lint 类
- main: 命令行入口函数
"""
from .linter import BiliObjCLint
from .cli import main, parse_args

__all__ = [
    'BiliObjCLint',
    'main',
    'parse_args',
]
