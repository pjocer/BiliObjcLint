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
# 在 Xcode Build Phase 中使用 (将此脚本复制到项目的 scripts 目录后):
#   "${SRCROOT}/scripts/bootstrap.sh" -w "${WORKSPACE_PATH}" -p "${PROJECT_FILE_PATH}" -t "${TARGET_NAME}"
#
# 注意: ${WORKSPACE_PATH} 是 workspace 完整路径，${PROJECT_FILE_PATH} 是 .xcodeproj 完整路径
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

    # 通过 Homebrew tap 安装
    info "添加 tap 并安装..."
    brew tap pjocer/biliobjclint
    brew install biliobjclint

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
    # 如果不支持 --check-update（旧版本），返回 99 表示需要直接安装
    local result exit_code

    # 先检查 biliobjclint-xcode 是否支持 --check-update
    if ! biliobjclint-xcode --help 2>&1 | grep -q "check-update"; then
        warn "当前版本不支持 --check-update，将直接安装/更新"
        return 99
    fi

    # Capture both output and exit code (use ; not || to preserve exit code)
    result=$(biliobjclint-xcode "$XCODE_PATH" $PROJECT_ARG -t "$TARGET" --check-update 2>&1); exit_code=$?

    echo "$result"
    return $exit_code
}

# Step 4: Install or update lint phase
install_lint_phase() {
    info "正在安装 Lint Build Phase..."

    # 检查是否支持 -p 参数（旧版本不支持）
    local supports_project_arg=false
    if biliobjclint-xcode --help 2>&1 | grep -q "\-\-project"; then
        supports_project_arg=true
    fi

    if [ "$supports_project_arg" = true ] && [ -n "$PROJECT_ARG" ]; then
        biliobjclint-xcode "$XCODE_PATH" $PROJECT_ARG -t "$TARGET" --override
    else
        if [ -n "$PROJECT_ARG" ]; then
            warn "当前版本不支持 -p 参数，将直接使用项目路径"
        fi
        biliobjclint-xcode "$XCODE_PATH" -t "$TARGET" --override
    fi

    info "Lint Build Phase 安装完成"
}

# ==================== Homebrew 静默自动更新 ====================

UPDATE_STATE_FILE="$HOME/.biliobjclint_update_state"
UPDATE_CHECK_INTERVAL=86400  # 24小时

# 读取更新状态
load_update_state() {
    if [ -f "$UPDATE_STATE_FILE" ]; then
        source "$UPDATE_STATE_FILE"
    fi
}

# 保存更新状态
save_update_state() {
    echo "LAST_CHECK_TIMESTAMP=$(date +%s)" > "$UPDATE_STATE_FILE"
}

# 检查是否需要检测更新
should_check_update() {
    load_update_state
    local current_time
    current_time=$(date +%s)
    local time_diff=$((current_time - ${LAST_CHECK_TIMESTAMP:-0}))
    [ $time_diff -ge ${UPDATE_CHECK_INTERVAL:-86400} ]
}

# 获取远端最新版本（通过 GitHub Tags API）
get_remote_version() {
    curl -s --connect-timeout 3 --max-time 5 \
        "https://api.github.com/repos/pjocer/BiliObjcLint/tags" 2>/dev/null \
        | grep '"name"' | head -1 | sed 's/.*"name": *"\([^"]*\)".*/\1/'
}

# 获取本地安装版本
get_local_version() {
    local brew_prefix
    brew_prefix=$(brew --prefix biliobjclint 2>/dev/null)

    if [ -f "$brew_prefix/libexec/VERSION" ]; then
        echo "v$(cat "$brew_prefix/libexec/VERSION")"
    elif [ -f "$brew_prefix/VERSION" ]; then
        echo "v$(cat "$brew_prefix/VERSION")"
    fi
}

# 比较版本号（$1 > $2 返回 0）
version_gt() {
    test "$(printf '%s\n' "$1" "$2" | sort -V | head -n 1)" != "$1"
}

# 获取指定版本的 CHANGELOG
get_changelog_for_version() {
    local version="$1"
    local changelog

    # 从 GitHub 获取 CHANGELOG
    changelog=$(curl -s --connect-timeout 3 --max-time 5 \
        "https://raw.githubusercontent.com/pjocer/BiliObjcLint/main/CHANGELOG.md" 2>/dev/null)

    if [ -z "$changelog" ]; then
        echo "查看: github.com/pjocer/BiliObjcLint/releases"
        return
    fi

    # 提取指定版本的更新内容（简化版，取前几条）
    echo "$changelog" | awk -v ver="$version" '
        /^## / {
            if (found) exit
            if (index($0, ver)) found=1
            next
        }
        found && /^- / { gsub(/^- /, "• "); print }
    ' | head -5
}

# 静默执行更新
silent_update() {
    local local_ver="$1"
    local remote_ver="$2"

    log_update "silent_update: Starting brew update..."

    # 静默执行 brew upgrade（重定向所有输出）
    brew update >/dev/null 2>&1
    local brew_update_exit=$?
    log_update "silent_update: brew update exit code: $brew_update_exit"

    brew upgrade biliobjclint >/dev/null 2>&1
    local brew_upgrade_exit=$?
    log_update "silent_update: brew upgrade exit code: $brew_upgrade_exit"

    if [ $brew_upgrade_exit -eq 0 ]; then
        log_update "silent_update: brew upgrade succeeded, preparing dialog..."

        # 获取更新内容
        local changelog
        changelog=$(get_changelog_for_version "$remote_ver")

        # 构建弹窗消息
        local message
        if [ -n "$changelog" ]; then
            message="版本: $remote_ver

更新内容:
$changelog"
        else
            message="版本: $remote_ver

查看更新详情: github.com/pjocer/BiliObjcLint/releases"
        fi

        log_update "silent_update: Showing dialog with message: ${message:0:100}..."

        # 显示弹窗对话框（不阻塞，独立进程）
        osascript -e "display dialog \"$message\" with title \"BiliObjCLint 已更新\" buttons {\"确定\"} default button \"确定\"" >/dev/null 2>&1 &
        log_update "silent_update: osascript launched"
    else
        log_update "silent_update: brew upgrade failed with exit code $brew_upgrade_exit"
    fi
}

# 更新日志文件
UPDATE_LOG_FILE="$HOME/.biliobjclint_update.log"

# 写入更新日志
log_update() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$UPDATE_LOG_FILE"
}

# 后台检测并更新
check_and_update_background() {
    log_update "=== Update check started ==="

    # 检查是否需要检测
    if ! should_check_update; then
        log_update "Skipped: within 24h cooldown"
        return 0
    fi

    log_update "Passed cooldown check, fetching versions..."

    # 获取版本信息
    local local_ver remote_ver
    local_ver=$(get_local_version)
    remote_ver=$(get_remote_version)

    log_update "Local version: $local_ver"
    log_update "Remote version: $remote_ver"

    # 版本检测失败则跳过（不保存状态，下次继续尝试）
    if [ -z "$remote_ver" ] || [ -z "$local_ver" ]; then
        log_update "Skipped: version fetch failed (local=$local_ver, remote=$remote_ver)"
        return 0
    fi

    # 成功获取版本后才保存检测时间戳
    save_update_state
    log_update "Saved update state"

    # 已是最新
    if [ "$local_ver" = "$remote_ver" ]; then
        log_update "Already up to date"
        return 0
    fi

    # 比较版本，确认远端更新
    if version_gt "$remote_ver" "$local_ver"; then
        log_update "Update available: $local_ver -> $remote_ver, starting silent_update..."
        silent_update "$local_ver" "$remote_ver"
        log_update "silent_update completed"
    else
        log_update "Local version is newer or equal"
    fi
}

# ==================== Main ====================

# Main logic
main() {
    # Step 1: Check/Install biliobjclint
    if ! check_biliobjclint_installed; then
        install_biliobjclint
    else
        info "BiliObjCLint 已安装"
        # 后台静默检测更新（使用 disown 确保进程不被 Xcode 终止）
        check_and_update_background &
        disown
    fi

    # Step 2: Check lint phase status
    info "检查 Lint Phase 状态..."

    local check_result check_exit

    # Temporarily disable exit on error to capture the exit code
    set +e
    check_result=$(check_lint_phase_exists)
    check_exit=$?
    set -e

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
                warn "Lint Phase 需要更新，正在自动更新..."
                echo "$check_result"
                install_lint_phase
                # 注意：更新会修改 project.pbxproj，首次会触发 Xcode "Build Canceled"
                # 这是正常行为，重新编译即可
                info "更新完成。如果 Xcode 提示 'Build Canceled'，请重新编译"
            else
                warn "Lint Phase 需要更新（已禁用自动更新）"
                echo "$check_result"
            fi
            ;;
        99)
            # Old version without --check-update support, install directly
            install_lint_phase
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
