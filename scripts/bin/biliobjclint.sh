#!/bin/bash
#
# BiliObjCLint - Objective-C 代码规范检查工具
#
# 用法:
#   biliobjclint [选项]
#
# 此脚本为 biliobjclint.py 的 shell wrapper，自动处理 venv 环境
#

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Python 脚本和虚拟环境路径
PYTHON_SCRIPT="$PROJECT_ROOT/scripts/biliobjclint.py"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python3"

# 检查 Python 脚本是否存在
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Error: biliobjclint.py not found: $PYTHON_SCRIPT" >&2
    exit 1
fi

# 检查 venv 是否存在
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: Python virtual environment not found" >&2
    echo "Please run: $PROJECT_ROOT/setup_env.sh" >&2
    exit 1
fi

# 执行 Python 脚本
exec "$VENV_PYTHON" "$PYTHON_SCRIPT" "$@"
