#!/bin/bash
#
# BiliObjCLint Bootstrap Script
#
# 通用引导脚本，用于在 Xcode Build Phase 中检查版本更新并注入 Code Style Lint Phase
# 可在多个项目中复用，通过参数指定项目和 Target
#
# Usage:
#   ./bootstrap.sh --workspace path/to/App.xcworkspace --project MyProject --target MyTarget
#   ./bootstrap.sh --project path/to/App.xcodeproj --target MyTarget
#   ./bootstrap.sh -w App.xcworkspace -p MyProject -t MyTarget
#
# 在 Xcode Build Phase 中使用 (将此脚本复制到项目的 scripts 目录后):
#   "${SRCROOT}/scripts/bootstrap.sh" -w "${WORKSPACE_PATH}" -p "${PROJECT_FILE_PATH}" -t "${TARGET_NAME}"
#
# 注意: ${WORKSPACE_PATH} 是 workspace 完整路径，${PROJECT_FILE_PATH} 是 .xcodeproj 完整路径
#
# 前提条件: biliobjclint 已通过 Homebrew 安装
#   brew tap pjocer/biliobjclint && brew install biliobjclint
#

set -e

# Setup PATH for Homebrew (Xcode Build Phase 环境中可能没有)
# Apple Silicon Mac
if [ -f "/opt/homebrew/bin/brew" ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
# Intel Mac
elif [ -f "/usr/local/bin/brew" ]; then
    eval "$(/usr/local/bin/brew shellenv)"
fi

# Colors (only for terminal output)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    NC='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    NC=''
fi

info() { echo -e "${GREEN}[BiliObjCLint]${NC} $1"; }
warn() { echo -e "${YELLOW}[BiliObjCLint]${NC} $1"; }
error() { echo -e "${RED}[BiliObjCLint]${NC} $1"; exit 1; }

# 获取脚本所在目录（项目的 scripts 目录）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Default values
WORKSPACE=""
PROJECT=""
TARGET=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -w|--workspace)
            WORKSPACE="$2"
            shift 2
            ;;
        -p|--project)
            PROJECT="$2"
            shift 2
            ;;
        -t|--target)
            TARGET="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  -w, --workspace PATH    Workspace 路径 (.xcworkspace)"
            echo "  -p, --project NAME      项目名称（workspace 中的项目）或项目路径 (.xcodeproj)"
            echo "  -t, --target NAME       Target 名称"
            echo "  -h, --help              显示帮助"
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            ;;
    esac
done

# Validate arguments
if [ -z "$TARGET" ]; then
    error "必须指定 --target/-t 参数"
fi

if [ -z "$WORKSPACE" ] && [ -z "$PROJECT" ]; then
    error "必须指定 --workspace/-w 或 --project/-p 参数"
fi

# Determine the project/workspace path for biliobjclint-xcode
# 智能处理路径：
# 1. 如果 WORKSPACE 是有效的 .xcworkspace 路径，使用它
# 2. 如果 PROJECT 是有效的 .xcodeproj 路径，使用它
# 3. 否则尝试从名称构建路径

if [ -n "$WORKSPACE" ] && [[ "$WORKSPACE" == *.xcworkspace ]]; then
    # WORKSPACE 是完整路径
    XCODE_PATH="$WORKSPACE"
    PROJECT_ARG=""
    # 如果 PROJECT 是名称（不是路径），作为 -p 参数
    if [ -n "$PROJECT" ] && [[ "$PROJECT" != *.xcodeproj ]]; then
        PROJECT_ARG="-p $PROJECT"
    elif [ -n "$PROJECT" ] && [[ "$PROJECT" == *.xcodeproj ]]; then
        # PROJECT 是 .xcodeproj 路径，提取项目名作为 -p 参数
        PROJECT_NAME=$(basename "$PROJECT" .xcodeproj)
        PROJECT_ARG="-p $PROJECT_NAME"
    fi
elif [ -n "$PROJECT" ] && [[ "$PROJECT" == *.xcodeproj ]]; then
    # PROJECT 是完整的 .xcodeproj 路径
    XCODE_PATH="$PROJECT"
    PROJECT_ARG=""
else
    # 参数不是完整路径，报错
    error "请提供完整路径。在 Xcode Build Phase 中使用: -w \"\${WORKSPACE_PATH}\" -p \"\${PROJECT_FILE_PATH}\" -t \"\${TARGET_NAME}\""
fi

# 验证路径存在
if [ ! -e "$XCODE_PATH" ]; then
    error "路径不存在: $XCODE_PATH"
fi

info "Xcode 项目: $XCODE_PATH"
info "Target: $TARGET"

# ==================== Main ====================

main() {
    # 检查 biliobjclint 是否已安装
    if ! command -v biliobjclint-xcode &> /dev/null; then
        error "biliobjclint 未安装，请先安装: brew tap pjocer/biliobjclint && brew install biliobjclint"
    fi

    info "调用 biliobjclint-xcode --check-and-inject..."

    # 调用 biliobjclint-xcode 检查版本更新并注入 Build Phase
    # 版本更新、脚本复制、Build Phase 注入全部由 check_update.py 处理
    biliobjclint-xcode "$XCODE_PATH" $PROJECT_ARG -t "$TARGET" \
        --check-and-inject \
        --scripts-dir "$SCRIPT_DIR"

    info "Bootstrap 完成"
}

main
