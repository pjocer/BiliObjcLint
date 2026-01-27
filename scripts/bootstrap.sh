#!/bin/bash
#
# BiliObjCLint Bootstrap Script
#
# 通用引导脚本，用于在 Xcode Build Phase 中自动安装和配置 BiliObjCLint
# 可在多个项目中复用，通过参数指定项目和 Target
#
# Usage:
#   ./bootstrap.sh --workspace path/to/App.xcworkspace --project MyProject --target MyTarget
#   ./bootstrap.sh --project path/to/App.xcodeproj --target MyTarget
#   ./bootstrap.sh -w App.xcworkspace -p MyProject -t MyTarget
#
# 在 Xcode Build Phase 中使用:
#   "${SRCROOT}/scripts/bootstrap.sh" -w "${WORKSPACE_PATH}" -p "ProjectName" -t "${TARGET_NAME}"
#

set -e

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

# Default values
WORKSPACE=""
PROJECT=""
TARGET=""
AUTO_UPDATE=true

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
        --no-auto-update)
            AUTO_UPDATE=false
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  -w, --workspace PATH    Workspace 路径 (.xcworkspace)"
            echo "  -p, --project NAME      项目名称（workspace 中的项目）或项目路径 (.xcodeproj)"
            echo "  -t, --target NAME       Target 名称"
            echo "  --no-auto-update        禁用自动更新检查"
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
if [ -n "$WORKSPACE" ]; then
    XCODE_PATH="$WORKSPACE"
    PROJECT_ARG=""
    if [ -n "$PROJECT" ]; then
        PROJECT_ARG="-p $PROJECT"
    fi
else
    XCODE_PATH="$PROJECT"
    PROJECT_ARG=""
fi

info "Workspace/Project: $XCODE_PATH"
info "Target: $TARGET"

# Step 1: Check if biliobjclint is installed
check_biliobjclint_installed() {
    if command -v biliobjclint &> /dev/null; then
        return 0
    fi
    return 1
}

# Step 2: Install biliobjclint via Homebrew
install_biliobjclint() {
    info "BiliObjCLint 未安装，正在通过 Homebrew 安装..."

    # Check if Homebrew is available
    if ! command -v brew &> /dev/null; then
        error "Homebrew 未安装，请先安装 Homebrew: https://brew.sh"
    fi

    brew install pjocer/biliobjclint/biliobjclint

    if check_biliobjclint_installed; then
        info "BiliObjCLint 安装成功"
    else
        error "BiliObjCLint 安装失败"
    fi
}

# Step 3: Check if lint phase exists in target
check_lint_phase_exists() {
    # Use biliobjclint-xcode --check-update to check
    # Exit code: 0 = exists and up to date, 1 = not exists, 2 = needs update
    local result
    result=$(biliobjclint-xcode "$XCODE_PATH" $PROJECT_ARG -t "$TARGET" --check-update 2>&1) || true
    local exit_code=$?

    echo "$result"
    return $exit_code
}

# Step 4: Install or update lint phase
install_lint_phase() {
    info "正在安装 Lint Build Phase..."
    biliobjclint-xcode "$XCODE_PATH" $PROJECT_ARG -t "$TARGET" --override
    info "Lint Build Phase 安装完成"
}

# Main logic
main() {
    # Step 1: Check/Install biliobjclint
    if ! check_biliobjclint_installed; then
        install_biliobjclint
    else
        info "BiliObjCLint 已安装"
    fi

    # Step 2: Check lint phase status
    info "检查 Lint Phase 状态..."

    local check_result
    check_result=$(check_lint_phase_exists)
    local check_exit=$?

    case $check_exit in
        0)
            # Already installed and up to date
            info "Lint Phase 已是最新版本"
            ;;
        1)
            # Not installed
            info "Lint Phase 未安装"
            install_lint_phase
            ;;
        2)
            # Needs update
            if [ "$AUTO_UPDATE" = true ]; then
                warn "Lint Phase 需要更新"
                echo "$check_result"
                install_lint_phase
            else
                warn "Lint Phase 需要更新（已禁用自动更新）"
                echo "$check_result"
            fi
            ;;
        *)
            # Unknown error, try to install
            warn "无法检测 Lint Phase 状态，尝试安装..."
            install_lint_phase
            ;;
    esac

    info "Bootstrap 完成"
}

main
