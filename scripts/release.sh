#!/bin/bash
#
# BiliObjCLint Release Script
# Usage:
#   ./scripts/release.sh          # Auto increment patch version (v1.0.0 -> v1.0.1)
#   ./scripts/release.sh minor    # Auto increment minor version (v1.0.0 -> v1.1.0)
#   ./scripts/release.sh major    # Auto increment major version (v1.0.0 -> v2.0.0)
#   ./scripts/release.sh v1.2.3   # Specify exact version
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
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

info() { echo -e "${GREEN}[INFO]${NC} $1" >&2; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1" >&2; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

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

    # Copy Formula file
    cp "$FORMULA_FILE" "$HOMEBREW_TAP_FORMULA"

    # Commit and push in tap repository
    cd "$HOMEBREW_TAP_DIR"

    if git diff --quiet "$HOMEBREW_TAP_FORMULA" 2>/dev/null; then
        info "No changes in homebrew tap Formula"
        cd "$PROJECT_ROOT"
        return 0
    fi

    git add "$HOMEBREW_TAP_FORMULA"
    git commit -m "Bump version to ${version}

Co-Authored-By: Claude (claude-4.5-opus) <noreply@anthropic.com>"
    git push

    info "Homebrew tap synced successfully"
    cd "$PROJECT_ROOT"
}

# Main
main() {
    cd "$PROJECT_ROOT"

    # Check for uncommitted changes
    if ! git diff-index --quiet HEAD --; then
        error "You have uncommitted changes. Please commit or stash them first."
    fi

    # Get current version
    local current_version
    current_version=$(get_current_version)
    info "Current version: $current_version"

    # Determine new version
    local new_version
    local input=${1:-patch}

    if [[ $input =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        # Exact version specified
        new_version=$input
    else
        # Increment version
        new_version=$(increment_version "$current_version" "$input")
    fi

    info "New version: $new_version"

    # Confirm
    echo ""
    read -p "Release $new_version? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        info "Aborted."
        exit 0
    fi

    # Create and push tag
    info "Creating tag $new_version ..."
    git tag "$new_version"
    git push origin "$new_version"

    # Calculate SHA256
    local sha256
    sha256=$(calculate_sha256 "$new_version")
    info "SHA256: $sha256"

    # Update VERSION file
    update_version_file "$new_version"

    # Update Formula
    update_formula "$new_version" "$sha256"

    # Commit and push updates
    info "Committing version updates..."
    git add "$VERSION_FILE" "$FORMULA_FILE"
    git commit -m "Bump version to ${new_version}

Co-Authored-By: Claude (claude-4.5-opus) <noreply@anthropic.com>"
    git push

    # Sync to homebrew tap repository
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
