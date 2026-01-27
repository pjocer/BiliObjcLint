#!/bin/bash
#
# OCLint 编译脚本
#
# 用法:
#   ./build_oclint.sh [选项]
#
# 选项:
#   --clean       清理后重新编译
#   --release     编译 Release 版本
#   --jobs N      并行编译任务数 (默认: CPU 核心数)
#   --help        显示帮助
#

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OCLINT_DIR="$PROJECT_ROOT/oclint"
BUILD_DIR="$PROJECT_ROOT/build"

# 默认参数
CLEAN=false
BUILD_TYPE="Debug"
JOBS=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_help() {
    echo "OCLint 编译脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --clean       清理后重新编译"
    echo "  --release     编译 Release 版本"
    echo "  --jobs N      并行编译任务数 (默认: $JOBS)"
    echo "  --help        显示帮助"
    exit 0
}

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --clean)
            CLEAN=true
            shift
            ;;
        --release)
            BUILD_TYPE="Release"
            shift
            ;;
        --jobs)
            JOBS="$2"
            shift 2
            ;;
        --help|-h)
            show_help
            ;;
        *)
            print_error "未知选项: $1"
            show_help
            ;;
    esac
done

# 检查依赖
check_dependencies() {
    print_info "检查依赖..."

    # 检查 CMake
    if ! command -v cmake &> /dev/null; then
        print_error "CMake 未安装，请先安装 CMake"
        echo "  brew install cmake"
        exit 1
    fi

    # 检查 Ninja (可选，但更快)
    if command -v ninja &> /dev/null; then
        USE_NINJA=true
        print_info "检测到 Ninja，将使用 Ninja 构建"
    else
        USE_NINJA=false
        print_warn "未检测到 Ninja，使用 Make 构建 (建议安装 Ninja 以加速编译: brew install ninja)"
    fi

    # 检查 Xcode Command Line Tools
    if ! xcode-select -p &> /dev/null; then
        print_error "Xcode Command Line Tools 未安装"
        echo "  xcode-select --install"
        exit 1
    fi

    print_info "依赖检查通过"
}

# 下载 LLVM/Clang 预编译包
download_llvm() {
    print_info "检查 LLVM/Clang..."

    LLVM_DIR="$OCLINT_DIR/build/llvm"

    if [ -d "$LLVM_DIR" ] && [ -f "$LLVM_DIR/bin/clang" ]; then
        print_info "LLVM/Clang 已存在，跳过下载"
        return 0
    fi

    print_info "使用 OCLint 脚本下载 LLVM..."

    cd "$OCLINT_DIR/oclint-scripts"

    # OCLint 的 build 脚本会自动下载 LLVM
    if [ -f "bundle" ]; then
        chmod +x bundle
    fi
}

# 编译 OCLint
build_oclint() {
    print_info "开始编译 OCLint..."
    print_info "编译类型: $BUILD_TYPE"
    print_info "并行任务数: $JOBS"

    cd "$OCLINT_DIR/oclint-scripts"

    # 清理
    if [ "$CLEAN" = true ]; then
        print_info "清理旧的编译文件..."
        rm -rf "$OCLINT_DIR/build"
    fi

    # 使用 OCLint 自带的编译脚本
    print_info "运行 OCLint 编译脚本..."

    # 设置环境变量
    export MAKEFLAGS="-j$JOBS"

    # 编译
    ./make

    # 复制编译结果到项目 build 目录
    if [ -d "$OCLINT_DIR/build/oclint-release" ]; then
        print_info "复制编译结果..."
        mkdir -p "$BUILD_DIR/bin"
        cp -r "$OCLINT_DIR/build/oclint-release/bin/"* "$BUILD_DIR/bin/" 2>/dev/null || true
        cp -r "$OCLINT_DIR/build/oclint-release/lib" "$BUILD_DIR/" 2>/dev/null || true
    fi

    print_info "OCLint 编译完成!"
}

# 验证编译结果
verify_build() {
    print_info "验证编译结果..."

    OCLINT_BIN="$BUILD_DIR/bin/oclint"

    if [ -f "$OCLINT_BIN" ]; then
        print_info "OCLint 可执行文件: $OCLINT_BIN"
        print_info "版本信息:"
        "$OCLINT_BIN" --version 2>&1 || true
        print_info "编译成功!"
    else
        # 检查 OCLint 内部 build 目录
        if [ -f "$OCLINT_DIR/build/oclint-release/bin/oclint" ]; then
            print_info "OCLint 已编译到: $OCLINT_DIR/build/oclint-release/bin/oclint"
            mkdir -p "$BUILD_DIR/bin"
            cp "$OCLINT_DIR/build/oclint-release/bin/oclint"* "$BUILD_DIR/bin/"
            print_info "已复制到: $BUILD_DIR/bin/"
        else
            print_warn "OCLint 可执行文件未找到"
            print_warn "您可以手动安装 OCLint: brew install oclint"
        fi
    fi
}

# 主流程
main() {
    echo "=========================================="
    echo "       BiliObjCLint - OCLint 编译"
    echo "=========================================="
    echo ""

    check_dependencies
    download_llvm
    build_oclint
    verify_build

    echo ""
    echo "=========================================="
    echo "              编译完成"
    echo "=========================================="
}

main "$@"
