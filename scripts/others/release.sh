#!/bin/bash
#
# BiliObjCLint Release Script
#
# Usage:
#   ./scripts/others/release.sh              # 自动递增 patch 版本 (v1.0.0 -> v1.0.1)
#   ./scripts/others/release.sh minor        # 自动递增 minor 版本 (v1.0.0 -> v1.1.0)
#   ./scripts/others/release.sh major        # 自动递增 major 版本 (v1.0.0 -> v2.0.0)
#   ./scripts/others/release.sh v1.2.3       # 指定精确版本
#   ./scripts/others/release.sh -y           # 非交互式（跳过确认）
#   ./scripts/others/release.sh -y minor     # 非交互式递增 minor 版本
#
# Options:
#   -y, --yes      跳过确认提示（非交互式模式）
#   -h, --help     显示帮助信息
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
FORMULA_FILE="$PROJECT_ROOT/Formula/biliobjclint.rb"
VERSION_FILE="$PROJECT_ROOT/VERSION"
REPO_URL="https://github.com/pjocer/BiliObjcLint"

# Homebrew tap repository (relative to PROJECT_ROOT)
HOMEBREW_TAP_DIR="$PROJECT_ROOT/../homebrew-biliobjclint"
HOMEBREW_TAP_FORMULA="$HOMEBREW_TAP_DIR/Formula/biliobjclint.rb"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 全局变量
SKIP_CONFIRM=false
VERSION_INPUT=""

info() { echo -e "${GREEN}[INFO]${NC} $1" >&2; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1" >&2; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

show_help() {
    cat << EOF
Usage: $0 [OPTIONS] [VERSION_TYPE|VERSION]

发布新版本，自动更新 VERSION 文件、创建 Git tag、更新 Formula 并同步到 Homebrew tap

Arguments:
  VERSION_TYPE   版本递增类型: patch (默认), minor, major
  VERSION        指定精确版本号，如 v1.2.3

Options:
  -y, --yes      跳过确认提示（非交互式模式）
  -h, --help     显示帮助信息

Examples:
  $0                    # 自动递增 patch 版本 (v1.0.0 -> v1.0.1)
  $0 minor              # 自动递增 minor 版本 (v1.0.0 -> v1.1.0)
  $0 major              # 自动递增 major 版本 (v1.0.0 -> v2.0.0)
  $0 v1.2.3             # 指定精确版本
  $0 -y                 # 非交互式递增 patch 版本
  $0 -y minor           # 非交互式递增 minor 版本
  $0 --yes v2.0.0       # 非交互式指定版本

Note:
  - 脚本会检查是否有未提交的改动，如有则拒绝发布
  - 如果不提供 -y/--yes 参数，脚本会在发布前要求确认
EOF
    exit 0
}

# 解析参数
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
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
                # 非选项参数作为版本类型或版本号
                if [ -z "$VERSION_INPUT" ]; then
                    VERSION_INPUT="$1"
                fi
                shift
                ;;
        esac
    done

    # 默认为 patch
    if [ -z "$VERSION_INPUT" ]; then
        VERSION_INPUT="patch"
    fi
}

# Get current version from git tags
get_current_version() {
    git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0"
}

# Parse version string to components
parse_version() {
    local version=$1
    version=${version#v}  # Remove 'v' prefix
    echo "$version"
}

# Increment version
increment_version() {
    local version=$1
    local type=$2

    IFS='.' read -r major minor patch <<< "$(parse_version "$version")"

    case $type in
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        patch|*)
            patch=$((patch + 1))
            ;;
    esac

    echo "v${major}.${minor}.${patch}"
}

# Calculate SHA256 of release tarball
calculate_sha256() {
    local version=$1
    local url="${REPO_URL}/archive/refs/tags/${version}.tar.gz"

    info "Calculating SHA256 for $url ..."

    # Wait a bit for GitHub to process the tag
    sleep 2

    local sha256
    sha256=$(curl -sL "$url" | shasum -a 256 | cut -d' ' -f1)

    if [ -z "$sha256" ] || [ "$sha256" = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" ]; then
        error "Failed to calculate SHA256. The release might not be available yet."
    fi

    echo "$sha256"
}

# Update VERSION file
update_version_file() {
    local version=$1
    local version_num=${version#v}  # Remove 'v' prefix

    info "Updating VERSION file..."
    echo "$version_num" > "$VERSION_FILE"
    info "VERSION file updated to ${version_num}"
}

# Update Formula file
update_formula() {
    local version=$1
    local sha256=$2

    info "Updating Formula file..."

    # Update URL
    sed -i '' "s|archive/refs/tags/v[0-9]*\.[0-9]*\.[0-9]*\.tar\.gz|archive/refs/tags/${version}.tar.gz|g" "$FORMULA_FILE"

    # Update SHA256
    sed -i '' "s|sha256 \"[a-f0-9]*\"|sha256 \"${sha256}\"|g" "$FORMULA_FILE"

    info "Formula updated to ${version}"
}

# Sync Formula to homebrew tap repository
sync_homebrew_tap() {
    local version=$1

    if [ ! -d "$HOMEBREW_TAP_DIR" ]; then
        warn "Homebrew tap directory not found: $HOMEBREW_TAP_DIR"
        warn "Skipping homebrew tap sync. Please manually update the tap repository."
        return 1
    fi

    info "Syncing Formula to homebrew tap repository..."

    cd "$HOMEBREW_TAP_DIR"

    # 先拉取远程最新代码，避免冲突
    info "Pulling latest changes from remote..."
    if ! git pull --rebase origin main 2>/dev/null; then
        warn "Failed to pull from remote, trying to reset to origin/main..."
        git fetch origin
        git reset --hard origin/main
    fi

    # Copy Formula file
    cp "$FORMULA_FILE" "$HOMEBREW_TAP_FORMULA"

    # Check if there are changes
    if git diff --quiet "$HOMEBREW_TAP_FORMULA" 2>/dev/null; then
        info "No changes in homebrew tap Formula"
        cd "$PROJECT_ROOT"
        return 0
    fi

    git add "$HOMEBREW_TAP_FORMULA"
    git commit -m "Update Formula for ${version}

Co-Authored-By: Claude (claude-4.5-opus) <noreply@anthropic.com>"
    git push

    info "Homebrew tap synced successfully"
    cd "$PROJECT_ROOT"
}

# Main
main() {
    cd "$PROJECT_ROOT"

    parse_args "$@"

    # Check for uncommitted changes
    if ! git diff-index --quiet HEAD --; then
        error "You have uncommitted changes. Please commit or stash them first.\n\nUse: ./scripts/others/commit.sh -y -m \"your message\""
    fi

    # Get current version
    local current_version
    current_version=$(get_current_version)
    info "Current version: $current_version"

    # Determine new version
    local new_version

    if [[ $VERSION_INPUT =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        # Exact version specified
        new_version=$VERSION_INPUT
    else
        # Increment version
        new_version=$(increment_version "$current_version" "$VERSION_INPUT")
    fi

    info "New version: $new_version"

    # Confirm (unless -y is specified)
    if [ "$SKIP_CONFIRM" = false ]; then
        echo ""
        read -p "Release $new_version? (y/N) " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            info "Aborted."
            exit 0
        fi
    fi

    # Step 1: Update VERSION file first (so tag includes correct version)
    update_version_file "$new_version"

    # Step 2: Commit VERSION update
    info "Committing VERSION update..."
    git add "$VERSION_FILE"
    git commit -m "Bump VERSION to ${new_version}

Co-Authored-By: Claude (claude-4.5-opus) <noreply@anthropic.com>"
    git push

    # Step 3: Create and push tag (now tag includes correct VERSION)
    info "Creating tag $new_version ..."
    git tag "$new_version"
    git push origin "$new_version"

    # Step 4: Calculate SHA256
    local sha256
    sha256=$(calculate_sha256 "$new_version")
    info "SHA256: $sha256"

    # Step 5: Update Formula with new SHA256
    update_formula "$new_version" "$sha256"

    # Step 6: Commit Formula update
    info "Committing Formula update..."
    git add "$FORMULA_FILE"
    git commit -m "Update Formula for ${new_version}

Co-Authored-By: Claude (claude-4.5-opus) <noreply@anthropic.com>"
    git push

    # Step 7: Sync to homebrew tap repository
    sync_homebrew_tap "$new_version"

    echo ""
    info "=========================================="
    info "Released ${new_version} successfully!"
    info "=========================================="
    echo ""
    echo "Users can update via:"
    echo "  brew update && brew upgrade biliobjclint"
    echo ""
    echo "Or install fresh:"
    echo "  brew tap pjocer/biliobjclint && brew install biliobjclint"
    echo ""
}

main "$@"
