"""
Xcode Build Phase 脚本模板和常量
"""
from pathlib import Path


def get_version() -> str:
    """从 VERSION 文件读取版本号"""
    # 从 wrapper/xcode/templates.py 到 scripts/../VERSION
    version_file = Path(__file__).parent.parent.parent.parent / 'VERSION'
    if version_file.exists():
        return version_file.read_text().strip()
    return "1.0.0"


# 脚本版本号（动态读取）
SCRIPT_VERSION = get_version()

# Phase 名称常量
PHASE_NAME = "[BiliObjcLint] Code Style Lint"
BOOTSTRAP_PHASE_NAME = "[BiliObjcLint] Package Manager"

# Build Phase 脚本模板（调用外部脚本）
# 用于 --bootstrap 模式，调用复制到项目中的 code_style_check.sh
LINT_SCRIPT_TEMPLATE = '''#!/bin/bash
# [BiliObjcLint] Code Style Check
# 代码规范审查
# Version: {version}

"{scripts_path}/code_style_check.sh"
'''

# Bootstrap Build Phase 脚本模板
# bootstrap.sh 直接从 Xcode 环境变量读取 PROJECT_FILE_PATH 和 TARGET_NAME
BOOTSTRAP_SCRIPT_TEMPLATE = '''#!/bin/bash
# [BiliObjcLint] Package Manager
# 自动安装和更新 BiliObjCLint

"{scripts_path}/bootstrap.sh"
'''
