#!/bin/bash
#
# revert_versions.sh - 撤回已发布版本并重新整理发布
#
# 用途：
#   撤回一批已发布的版本（删除 tags），然后重新发布整理后的版本
#
# 使用方式：
#   ./revert_versions.sh --from v1.4.0 --to v1.4.14 --new v1.4.0,v1.4.1
#
# 前置条件：
#   1. CHANGELOG.md 已手动编辑好，包含新版本的条目
#   2. 当前工作目录干净（无未提交的更改）
#
# 流程：
#   1. 验证参数和前置条件
#   2. 删除指定范围内的本地和远程 tags
#   3. 按顺序发布新版本（更新 VERSION、提交、创建 tag、推送）
#   4. 更新 Homebrew tap Formula
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
step() { echo -e "\n${BLUE}=== $1 ===${NC}"; }

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TAP_REPO="${PROJECT_ROOT}/../homebrew-biliobjclint"

# 默认参数
FROM_VERSION=""
TO_VERSION=""
NEW_VERSIONS=""
DRY_RUN=false
YES_MODE=false

# 帮助信息
show_help() {
    cat << EOF
Usage: $(basename "$0") [options]

撤回已发布版本并重新整理发布

Options:
  --from VERSION      起始版本（要撤回的最小版本，如 v1.4.0）
  --to VERSION        结束版本（要撤回的最大版本，如 v1.4.14）
  --new VERSIONS      新版本列表（逗号分隔，按发布顺序，如 v1.4.0,v1.4.1）
  --dry-run           只显示将要执行的操作，不实际执行
  -y, --yes           非交互式模式，跳过确认
  -h, --help          显示此帮助信息

Example:
  # 撤回 v1.4.0 ~ v1.4.14，重新发布为 v1.4.0 和 v1.4.1
  $(basename "$0") --from v1.4.0 --to v1.4.14 --new v1.4.0,v1.4.1

Prerequisites:
  1. CHANGELOG.md 已包含新版本的条目（需手动编辑）
  2. 工作目录干净（无未提交的更改）

EOF
}

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --from)
            FROM_VERSION="$2"
            shift 2
            ;;
        --to)
            TO_VERSION="$2"
            shift 2
            ;;
        --new)
            NEW_VERSIONS="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -y|--yes)
            YES_MODE=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            error "未知参数: $1"
            show_help
            exit 1
            ;;
    esac
done

# 验证参数
if [[ -z "$FROM_VERSION" ]] || [[ -z "$TO_VERSION" ]] || [[ -z "$NEW_VERSIONS" ]]; then
    error "缺少必要参数"
    show_help
    exit 1
fi

# 标准化版本号（确保有 v 前缀）
normalize_version() {
    local v="$1"
    [[ "$v" != v* ]] && v="v$v"
    echo "$v"
}

FROM_VERSION=$(normalize_version "$FROM_VERSION")
TO_VERSION=$(normalize_version "$TO_VERSION")

# 解析新版本列表
IFS=',' read -ra NEW_VERSION_ARRAY <<< "$NEW_VERSIONS"
for i in "${!NEW_VERSION_ARRAY[@]}"; do
    NEW_VERSION_ARRAY[$i]=$(normalize_version "${NEW_VERSION_ARRAY[$i]}")
done

# 提取版本号数字部分用于生成范围
extract_version_numbers() {
    local v="$1"
    echo "$v" | sed 's/^v//' | tr '.' ' '
}

# 生成版本范围内的所有 tags
generate_version_range() {
    local from="$1"
    local to="$2"

    # 提取主版本和次版本
    local from_nums=($(extract_version_numbers "$from"))
    local to_nums=($(extract_version_numbers "$to"))

    local major="${from_nums[0]}"
    local minor="${from_nums[1]}"
    local from_patch="${from_nums[2]}"
    local to_patch="${to_nums[2]}"

    # 简化处理：假设只有 patch 版本不同
    for ((p=from_patch; p<=to_patch; p++)); do
        echo "v${major}.${minor}.${p}"
    done
}

# 检查 CHANGELOG 是否包含版本条目
check_changelog_entry() {
    local version="$1"
    if grep -q "^## $version" "$PROJECT_ROOT/CHANGELOG.md"; then
        return 0
    else
        return 1
    fi
}

# 执行命令（支持 dry-run）
run_cmd() {
    if [[ "$DRY_RUN" == true ]]; then
        echo "  [DRY-RUN] $*"
    else
        "$@"
    fi
}

# ==================== 主流程 ====================

cd "$PROJECT_ROOT"

step "验证前置条件"

# 检查工作目录是否干净
if [[ -n $(git status --porcelain) ]]; then
    error "工作目录有未提交的更改，请先提交或暂存"
    git status --short
    exit 1
fi
info "工作目录干净 ✓"

# 检查 CHANGELOG 是否包含新版本条目
for v in "${NEW_VERSION_ARRAY[@]}"; do
    if ! check_changelog_entry "$v"; then
        error "CHANGELOG.md 缺少 $v 的条目"
        error "请先手动编辑 CHANGELOG.md，添加新版本的更新说明"
        exit 1
    fi
    info "CHANGELOG 包含 $v ✓"
done

# 检查 tap 仓库
if [[ ! -d "$TAP_REPO" ]]; then
    error "Homebrew tap 仓库不存在: $TAP_REPO"
    exit 1
fi
info "Tap 仓库存在 ✓"

# 生成要删除的版本列表
VERSIONS_TO_DELETE=($(generate_version_range "$FROM_VERSION" "$TO_VERSION"))

step "操作预览"

echo "要删除的 tags (${#VERSIONS_TO_DELETE[@]} 个):"
for v in "${VERSIONS_TO_DELETE[@]}"; do
    echo "  - $v"
done

echo ""
echo "要发布的新版本 (${#NEW_VERSION_ARRAY[@]} 个):"
for v in "${NEW_VERSION_ARRAY[@]}"; do
    echo "  - $v"
done

# 确认
if [[ "$YES_MODE" != true ]] && [[ "$DRY_RUN" != true ]]; then
    echo ""
    read -p "确认执行以上操作? [y/N] " confirm
    if [[ "$confirm" != "y" ]] && [[ "$confirm" != "Y" ]]; then
        info "已取消"
        exit 0
    fi
fi

step "删除本地 tags"

for v in "${VERSIONS_TO_DELETE[@]}"; do
    if git tag -l | grep -q "^$v$"; then
        run_cmd git tag -d "$v"
        info "已删除本地 tag: $v"
    else
        warn "本地 tag 不存在: $v"
    fi
done

step "删除远程 tags"

for v in "${VERSIONS_TO_DELETE[@]}"; do
    if git ls-remote --tags origin | grep -q "refs/tags/$v$"; then
        run_cmd git push origin --delete "$v" 2>/dev/null || warn "远程 tag 可能不存在: $v"
        info "已删除远程 tag: $v"
    else
        warn "远程 tag 不存在: $v"
    fi
done

step "发布新版本"

for v in "${NEW_VERSION_ARRAY[@]}"; do
    info "发布 $v ..."

    # 提取纯版本号
    version_num="${v#v}"

    # 更新 VERSION 文件
    if [[ "$DRY_RUN" != true ]]; then
        echo "$version_num" > "$PROJECT_ROOT/VERSION"
    else
        echo "  [DRY-RUN] echo '$version_num' > VERSION"
    fi

    # 提交
    run_cmd git add VERSION CHANGELOG.md

    # 从 CHANGELOG 提取版本标题作为提交信息
    commit_title=$(grep "^## $v" "$PROJECT_ROOT/CHANGELOG.md" | head -1 | sed 's/^## //')
    run_cmd git commit -m "Bump VERSION to $v" --allow-empty

    # 创建 tag
    run_cmd git tag "$v"

    # 推送
    run_cmd git push origin main
    run_cmd git push origin "$v"

    info "$v 发布完成 ✓"
done

step "更新 Homebrew tap"

# 获取最新版本
LATEST_VERSION="${NEW_VERSION_ARRAY[-1]}"
LATEST_VERSION_NUM="${LATEST_VERSION#v}"

info "计算 SHA256 ..."
if [[ "$DRY_RUN" != true ]]; then
    SHA256=$(curl -sL "https://github.com/pjocer/BiliObjcLint/archive/refs/tags/${LATEST_VERSION}.tar.gz" | shasum -a 256 | cut -d' ' -f1)
    info "SHA256: $SHA256"

    # 更新 Formula
    FORMULA_FILE="$TAP_REPO/Formula/biliobjclint.rb"
    sed -i '' "s|url \"https://github.com/pjocer/BiliObjcLint/archive/refs/tags/v[^\"]*\.tar\.gz\"|url \"https://github.com/pjocer/BiliObjcLint/archive/refs/tags/${LATEST_VERSION}.tar.gz\"|" "$FORMULA_FILE"
    sed -i '' "s|sha256 \"[^\"]*\"|sha256 \"$SHA256\"|" "$FORMULA_FILE"

    # 提交 tap 更新
    cd "$TAP_REPO"
    git add Formula/biliobjclint.rb
    git commit -m "Update Formula for ${LATEST_VERSION}"
    git push origin main
    cd "$PROJECT_ROOT"

    info "Homebrew tap 已更新到 ${LATEST_VERSION} ✓"
else
    echo "  [DRY-RUN] 更新 Formula 到 ${LATEST_VERSION}"
fi

step "完成"

echo ""
info "版本整理完成！"
echo ""
echo "已删除: ${#VERSIONS_TO_DELETE[@]} 个旧版本"
echo "已发布: ${#NEW_VERSION_ARRAY[@]} 个新版本"
echo ""
echo "用户可执行以下命令更新:"
echo "  brew update && brew upgrade biliobjclint"
