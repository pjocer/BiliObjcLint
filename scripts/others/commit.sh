#!/bin/bash
#
# BiliObjCLint Commit Script
# 同时提交改动到主仓库和 Homebrew tap 仓库
#
# Usage:
#   ./scripts/others/commit.sh "commit message"
#   ./scripts/others/commit.sh -m "commit message"
#   ./scripts/others/commit.sh                      # 交互式输入 commit message
#
# 保持BILIOBJCLINT工程和BILIOBJCLINT Homebrew Tap工程在同一目录下
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# 仓库路径
MAIN_REPO="$PROJECT_ROOT"
HOMEBREW_TAP_REPO="$PROJECT_ROOT/../homebrew-biliobjclint"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }
header() { echo -e "${BLUE}=== $1 ===${NC}"; }

# 检查仓库是否有改动
check_changes() {
    local repo_path="$1"
    local repo_name="$2"

    cd "$repo_path"
    if git diff --quiet && git diff --cached --quiet; then
        return 1  # 没有改动
    fi
    return 0  # 有改动
}

# 显示仓库状态
show_status() {
    local repo_path="$1"
    local repo_name="$2"

    cd "$repo_path"
    header "$repo_name"
    git status --short
    echo ""
}

# 提交仓库
commit_repo() {
    local repo_path="$1"
    local repo_name="$2"
    local message="$3"

    cd "$repo_path"

    if ! check_changes "$repo_path" "$repo_name"; then
        info "$repo_name: 没有需要提交的改动"
        return 0
    fi

    header "提交 $repo_name"

    # 显示将要提交的文件
    echo "将要提交的改动："
    git status --short
    echo ""

    # 添加所有改动
    git add -A

    # 提交
    git commit -m "$message

Co-Authored-By: Claude (claude-4.5-opus) <noreply@anthropic.com>"

    # 推送
    info "推送到远程..."
    git push

    info "$repo_name: 提交完成"
    echo ""
}

# 解析参数
parse_args() {
    local message=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            -m|--message)
                message="$2"
                shift 2
                ;;
            -h|--help)
                echo "Usage: $0 [-m \"commit message\"] [commit message]"
                echo ""
                echo "Options:"
                echo "  -m, --message    Commit message"
                echo "  -h, --help       Show this help"
                echo ""
                echo "Examples:"
                echo "  $0 \"Fix bug in lint check\""
                echo "  $0 -m \"Fix bug in lint check\""
                exit 0
                ;;
            *)
                # 非选项参数作为 commit message
                if [ -z "$message" ]; then
                    message="$1"
                fi
                shift
                ;;
        esac
    done

    echo "$message"
}

main() {
    local commit_message
    commit_message=$(parse_args "$@")

    # 检查两个仓库是否都存在
    if [ ! -d "$MAIN_REPO/.git" ]; then
        error "主仓库不存在: $MAIN_REPO"
    fi

    # 显示当前状态
    echo ""
    info "检查仓库状态..."
    echo ""

    local main_has_changes=false
    local tap_has_changes=false

    if check_changes "$MAIN_REPO" "BiliObjCLint"; then
        main_has_changes=true
        show_status "$MAIN_REPO" "BiliObjCLint (主仓库)"
    fi

    if [ -d "$HOMEBREW_TAP_REPO/.git" ]; then
        if check_changes "$HOMEBREW_TAP_REPO" "homebrew-biliobjclint"; then
            tap_has_changes=true
            show_status "$HOMEBREW_TAP_REPO" "homebrew-biliobjclint (Tap 仓库)"
        fi
    else
        warn "Homebrew tap 仓库不存在: $HOMEBREW_TAP_REPO"
    fi

    # 如果两个仓库都没有改动
    if [ "$main_has_changes" = false ] && [ "$tap_has_changes" = false ]; then
        info "两个仓库都没有需要提交的改动"
        exit 0
    fi

    # 如果没有提供 commit message，交互式输入
    if [ -z "$commit_message" ]; then
        echo ""
        read -p "请输入 commit message: " commit_message
        if [ -z "$commit_message" ]; then
            error "Commit message 不能为空"
        fi
    fi

    echo ""
    info "Commit message: $commit_message"
    echo ""

    # 确认
    read -p "确认提交? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        info "已取消"
        exit 0
    fi

    echo ""

    # 提交主仓库
    if [ "$main_has_changes" = true ]; then
        commit_repo "$MAIN_REPO" "BiliObjCLint" "$commit_message"
    fi

    # 提交 tap 仓库
    if [ "$tap_has_changes" = true ]; then
        commit_repo "$HOMEBREW_TAP_REPO" "homebrew-biliobjclint" "$commit_message"
    fi

    echo ""
    info "=========================================="
    info "所有仓库提交完成!"
    info "=========================================="
}

main "$@"
