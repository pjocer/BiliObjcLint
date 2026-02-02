#!/bin/bash
#
# BiliObjCLint Commit Script
# 同时提交改动到主仓库和 Homebrew tap 仓库
#
# Usage:
#   ./scripts/others/commit.sh                                    # 交互式输入
#   ./scripts/others/commit.sh -t feat -s "规则" -d "新增xxx规则"  # CLI 参数
#   ./scripts/others/commit.sh -y -t fix -d "修复xxx问题"          # 非交互式
#   ./scripts/others/commit.sh -m "完整的提交信息"                 # 直接指定完整信息
#
# Options:
#   -t, --type       提交类型: feat|fix|docs|style|refactor|perf|test|chore
#   -s, --scope      作用域（可选）: 如 规则, 配置, 脚本 等
#   -d, --desc       简短描述（必填）
#   -b, --body       详细说明（可选，多行）
#   -m, --message    完整的提交信息（跳过格式化）
#   -y, --yes        跳过确认提示（非交互式模式）
#   -h, --help       显示帮助信息
#
# Commit Format:
#   <type>[(<scope>)]: <description>
#
#   [body]
#
#   Co-Authored-By: Claude (claude-4.5-opus) <noreply@anthropic.com>
#
# 保持 BILIOBJCLINT 工程和 homebrew-biliobjclint 工程在同一目录下
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
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# 全局变量
SKIP_CONFIRM=false
COMMIT_TYPE=""
COMMIT_SCOPE=""
COMMIT_DESC=""
COMMIT_BODY=""
COMMIT_MESSAGE=""  # 完整的提交信息（跳过格式化）

# 支持的提交类型
COMMIT_TYPES=("feat" "fix" "docs" "style" "refactor" "perf" "test" "chore")
COMMIT_TYPE_DESC=(
    "feat:     新功能"
    "fix:      Bug 修复"
    "docs:     文档更新"
    "style:    代码格式（不影响功能）"
    "refactor: 重构（既不是新功能也不是修复）"
    "perf:     性能优化"
    "test:     测试相关"
    "chore:    构建/工具/依赖等杂项"
)

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }
header() { echo -e "${BLUE}=== $1 ===${NC}"; }

# 检查仓库是否有改动
check_changes() {
    local repo_path="$1"

    cd "$repo_path"
    if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
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

    if ! check_changes "$repo_path"; then
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
    git commit -m "$message"

    # 推送
    info "推送到远程..."
    git push

    info "$repo_name: 提交完成"
    echo ""
}

show_help() {
    cat << 'EOF'
Usage: commit.sh [OPTIONS]

同时提交改动到主仓库和 Homebrew tap 仓库，支持 Conventional Commits 格式

Options:
  -t, --type TYPE     提交类型 (必填，交互模式下会提示选择)
                      可选值: feat|fix|docs|style|refactor|perf|test|chore
  -s, --scope SCOPE   作用域 (可选)
                      示例: 规则, 配置, 脚本, Claude, Xcode
  -d, --desc DESC     简短描述 (必填，交互模式下会提示输入)
  -b, --body BODY     详细说明 (可选，支持多行)
  -m, --message MSG   完整的提交信息 (跳过格式化，直接使用)
  -y, --yes           跳过确认提示（非交互式模式）
  -h, --help          显示帮助信息

Commit Types:
  feat      新功能
  fix       Bug 修复
  docs      文档更新
  style     代码格式（不影响功能）
  refactor  重构（既不是新功能也不是修复）
  perf      性能优化
  test      测试相关
  chore     构建/工具/依赖等杂项

Examples:
  # 交互式输入
  commit.sh

  # CLI 参数（完整）
  commit.sh -t feat -s "规则" -d "新增 method_parameter 规则"

  # CLI 参数（简化）
  commit.sh -t fix -d "修复增量检查失效问题"

  # 带详细说明
  commit.sh -t feat -s "Claude" -d "添加 API 配置支持" -b "支持内部网关和官方 API 两种方式"

  # 非交互式
  commit.sh -y -t chore -d "更新依赖"

  # 直接指定完整信息（跳过格式化）
  commit.sh -m "feat: 新增功能"

Output Format:
  <type>[(<scope>)]: <description>

  [body]

  Co-Authored-By: Claude (claude-4.5-opus) <noreply@anthropic.com>
EOF
    exit 0
}

# 验证提交类型
validate_type() {
    local type="$1"
    for valid_type in "${COMMIT_TYPES[@]}"; do
        if [ "$type" = "$valid_type" ]; then
            return 0
        fi
    done
    return 1
}

# 交互式选择提交类型
select_commit_type() {
    echo ""
    echo -e "${CYAN}${BOLD}选择提交类型:${NC}"
    echo ""
    for i in "${!COMMIT_TYPE_DESC[@]}"; do
        printf "  ${GREEN}%d${NC}) %s\n" "$((i+1))" "${COMMIT_TYPE_DESC[$i]}"
    done
    echo ""

    while true; do
        read -p "请选择 [1-${#COMMIT_TYPES[@]}]: " choice
        if [[ "$choice" =~ ^[1-8]$ ]]; then
            COMMIT_TYPE="${COMMIT_TYPES[$((choice-1))]}"
            break
        else
            echo -e "${RED}无效选择，请输入 1-${#COMMIT_TYPES[@]}${NC}"
        fi
    done
}

# 交互式输入作用域
input_scope() {
    echo ""
    echo -e "${CYAN}${BOLD}输入作用域 (可选，直接回车跳过):${NC}"
    echo -e "  示例: 规则, 配置, 脚本, Claude, Xcode, Formula"
    read -p "> " COMMIT_SCOPE
}

# 交互式输入描述
input_description() {
    echo ""
    echo -e "${CYAN}${BOLD}输入简短描述 (必填):${NC}"
    while true; do
        read -p "> " COMMIT_DESC
        if [ -n "$COMMIT_DESC" ]; then
            break
        else
            echo -e "${RED}描述不能为空${NC}"
        fi
    done
}

# 交互式输入详细说明
input_body() {
    echo ""
    echo -e "${CYAN}${BOLD}输入详细说明 (可选，直接回车跳过，输入多行以空行结束):${NC}"
    local body_lines=""
    local line_count=0

    while true; do
        read -p "> " line
        if [ -z "$line" ]; then
            if [ $line_count -eq 0 ]; then
                # 第一行就是空，跳过
                break
            else
                # 空行表示结束
                break
            fi
        fi
        if [ -n "$body_lines" ]; then
            body_lines="${body_lines}\n${line}"
        else
            body_lines="$line"
        fi
        ((line_count++))
    done

    COMMIT_BODY="$body_lines"
}

# 构建格式化的提交信息
build_commit_message() {
    local message=""

    # 构建标题行
    if [ -n "$COMMIT_SCOPE" ]; then
        message="${COMMIT_TYPE}(${COMMIT_SCOPE}): ${COMMIT_DESC}"
    else
        message="${COMMIT_TYPE}: ${COMMIT_DESC}"
    fi

    # 添加详细说明
    if [ -n "$COMMIT_BODY" ]; then
        message="${message}

$(echo -e "$COMMIT_BODY")"
    fi

    # 添加 Co-Author
    message="${message}

Co-Authored-By: Claude (claude-4.5-opus) <noreply@anthropic.com>"

    echo "$message"
}

# 解析参数
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -t|--type)
                COMMIT_TYPE="$2"
                shift 2
                ;;
            -s|--scope)
                COMMIT_SCOPE="$2"
                shift 2
                ;;
            -d|--desc)
                COMMIT_DESC="$2"
                shift 2
                ;;
            -b|--body)
                COMMIT_BODY="$2"
                shift 2
                ;;
            -m|--message)
                COMMIT_MESSAGE="$2"
                shift 2
                ;;
            -y|--yes)
                SKIP_CONFIRM=true
                shift
                ;;
            -h|--help)
                show_help
                ;;
            -*)
                error "未知选项: $1\n使用 -h 或 --help 查看帮助"
                ;;
            *)
                # 兼容旧的直接传参方式
                if [ -z "$COMMIT_MESSAGE" ]; then
                    COMMIT_MESSAGE="$1"
                fi
                shift
                ;;
        esac
    done
}

main() {
    parse_args "$@"

    # 检查主仓库是否存在
    if [ ! -d "$MAIN_REPO/.git" ]; then
        error "主仓库不存在: $MAIN_REPO"
    fi

    # 显示当前状态
    echo ""
    info "检查仓库状态..."
    echo ""

    local main_has_changes=false
    local tap_has_changes=false

    if check_changes "$MAIN_REPO"; then
        main_has_changes=true
        show_status "$MAIN_REPO" "BiliObjCLint (主仓库)"
    fi

    if [ -d "$HOMEBREW_TAP_REPO/.git" ]; then
        if check_changes "$HOMEBREW_TAP_REPO"; then
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

    # 如果提供了完整的提交信息，直接使用
    if [ -n "$COMMIT_MESSAGE" ]; then
        # 如果信息中没有 Co-Author，添加它
        if [[ "$COMMIT_MESSAGE" != *"Co-Authored-By:"* ]]; then
            COMMIT_MESSAGE="${COMMIT_MESSAGE}

Co-Authored-By: Claude (claude-4.5-opus) <noreply@anthropic.com>"
        fi
    else
        # 需要格式化提交信息

        # 验证或获取提交类型
        if [ -n "$COMMIT_TYPE" ]; then
            if ! validate_type "$COMMIT_TYPE"; then
                error "无效的提交类型: $COMMIT_TYPE\n有效值: ${COMMIT_TYPES[*]}"
            fi
        else
            if [ "$SKIP_CONFIRM" = true ]; then
                error "非交互式模式下必须提供提交类型 (-t 参数)"
            fi
            select_commit_type
        fi

        # 获取作用域（交互模式下）
        if [ -z "$COMMIT_SCOPE" ] && [ "$SKIP_CONFIRM" = false ]; then
            input_scope
        fi

        # 验证或获取描述
        if [ -z "$COMMIT_DESC" ]; then
            if [ "$SKIP_CONFIRM" = true ]; then
                error "非交互式模式下必须提供描述 (-d 参数)"
            fi
            input_description
        fi

        # 获取详细说明（交互模式下）
        if [ -z "$COMMIT_BODY" ] && [ "$SKIP_CONFIRM" = false ]; then
            input_body
        fi

        # 构建提交信息
        COMMIT_MESSAGE=$(build_commit_message)
    fi

    # 显示提交信息预览
    echo ""
    header "提交信息预览"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo "$COMMIT_MESSAGE"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    # 确认（除非指定了 -y）
    if [ "$SKIP_CONFIRM" = false ]; then
        read -p "确认提交? (y/N) " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            info "已取消"
            exit 0
        fi
        echo ""
    fi

    # 提交主仓库
    if [ "$main_has_changes" = true ]; then
        commit_repo "$MAIN_REPO" "BiliObjCLint" "$COMMIT_MESSAGE"
    fi

    # 提交 tap 仓库
    if [ "$tap_has_changes" = true ]; then
        commit_repo "$HOMEBREW_TAP_REPO" "homebrew-biliobjclint" "$COMMIT_MESSAGE"
    fi

    echo ""
    info "=========================================="
    info "所有仓库提交完成!"
    info "=========================================="
}

main "$@"
