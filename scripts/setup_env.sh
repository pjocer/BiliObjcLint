#!/bin/bash
#
# 环境初始化脚本
#
# 用法:
#   ./setup_env.sh
#
# 此脚本会:
# 1. 创建 Python 虚拟环境
# 2. 安装必要的依赖
#

set -e

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# 检查 Python3
if ! command -v python3 &> /dev/null; then
    echo "Error: Python3 未安装"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1)
print_info "Python 版本: $PYTHON_VERSION"

# 创建虚拟环境
VENV_DIR="$PROJECT_ROOT/.venv"

if [ -d "$VENV_DIR" ]; then
    print_warn "虚拟环境已存在: $VENV_DIR"
    read -p "是否重新创建? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$VENV_DIR"
        print_info "已删除旧的虚拟环境"
    else
        print_info "使用现有虚拟环境"
        source "$VENV_DIR/bin/activate"
        pip install -r requirements.txt
        print_info "依赖已更新"
        exit 0
    fi
fi

print_info "创建虚拟环境..."
python3 -m venv "$VENV_DIR"

print_info "激活虚拟环境..."
source "$VENV_DIR/bin/activate"

print_info "安装依赖..."
pip install --upgrade pip
pip install -r requirements.txt

print_info "环境初始化完成!"
echo ""
echo "使用方法:"
echo "  激活环境:  source $VENV_DIR/bin/activate"
echo "  运行 lint: python scripts/biliobjclint.py --help"
echo ""
