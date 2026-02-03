#!/bin/bash
#
# BiliObjCLint Bootstrap Script
#
# 在 Xcode Build Phase 中运行，检查版本更新并注入 Code Style Lint Phase
#
# 此脚本直接从 Xcode 环境变量获取项目信息：
#   - PROJECT_FILE_PATH: .xcodeproj 完整路径
#   - TARGET_NAME: Target 名称
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

# 检查是否为调试模式
DEBUG_FILE="$SCRIPT_DIR/.biliobjclint_debug"
DEBUG_MODE=false
if [ -f "$DEBUG_FILE" ]; then
    DEBUG_MODE=true
    DEBUG_PATH=$(cat "$DEBUG_FILE")
fi

# ==================== Main ====================

main() {
    # 调试模式：跳过版本检查，避免覆盖本地开发代码
    if [ "$DEBUG_MODE" = true ]; then
        info "[DEBUG MODE] 使用本地开发目录: $DEBUG_PATH"
        info "[DEBUG MODE] 跳过版本检查和脚本更新"
        return 0
    fi

    # 检查 Xcode 环境变量
    if [ -z "$PROJECT_FILE_PATH" ]; then
        error "PROJECT_FILE_PATH 环境变量未设置，请确保在 Xcode Build Phase 中运行"
    fi

    if [ -z "$TARGET_NAME" ]; then
        error "TARGET_NAME 环境变量未设置，请确保在 Xcode Build Phase 中运行"
    fi

    # 检查 biliobjclint 是否已安装
    if ! command -v biliobjclint-xcode &> /dev/null; then
        error "biliobjclint 未安装，请先安装: brew tap pjocer/biliobjclint && brew install biliobjclint"
    fi

    # 标准化路径
    XCODEPROJ_PATH="$(realpath "$PROJECT_FILE_PATH" 2>/dev/null || echo "$PROJECT_FILE_PATH")"

    info "Project: $XCODEPROJ_PATH"
    info "Target: $TARGET_NAME"

    # 调用 biliobjclint-xcode 检查版本更新并注入 Build Phase
    # 使用 PROJECT_FILE_PATH 和 TARGET_NAME 作为配置查找的 key
    biliobjclint-xcode --check-and-inject \
        --xcodeproj "$XCODEPROJ_PATH" \
        --target "$TARGET_NAME" \
        --scripts-dir "$SCRIPT_DIR"

    info "Bootstrap 完成"
}

main
