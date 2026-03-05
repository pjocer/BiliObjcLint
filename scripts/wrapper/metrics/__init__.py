"""BiliObjCLint Metrics 上报模块

提供 metrics 后台上报功能。

主要组件:
- main: 后台上报入口函数
"""
from .upload import main

__all__ = [
    'main',
]
