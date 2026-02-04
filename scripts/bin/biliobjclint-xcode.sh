#!/bin/bash
#
# BiliObjCLint Xcode 集成安装脚本
#
# 用法:
#   biliobjclint-xcode <项目路径> [选项]
#
# 参数:
#   项目路径      .xcworkspace 或 .xcodeproj 路径
#
# 选项:
#   --project, -p NAME   指定项目名称（用于 workspace 中指定项目）
#   --target, -t NAME    指定 Target 名称（默认：主 Target）
#   --lint-path PATH     指定 BiliObjCLint 安装路径（默认：自动检测）
#   --remove             移除已添加的 Lint Phase
#   --override           强制覆盖已存在的 Lint Phase
#   --check-update       检查已注入脚本是否需要更新
#   --check-and-inject   检查版本更新并注入 Code Style Check Build Phase（由 bootstrap.sh 调用）
#   --scripts-dir PATH   项目 scripts 目录路径（与 --check-and-inject 配合使用）
#   --bootstrap          自动复制 bootstrap.sh 并注入 Package Manager Build Phase
#   --list-projects      列出 workspace 中所有项目
#   --list-targets       列出所有可用的 Targets
#   --dry-run            仅显示将要进行的修改，不实际执行
#   --manual             显示手动配置说明（不自动修改项目）
#   --help, -h           显示帮助
#
# 示例:
#   biliobjclint-xcode /path/to/MyApp.xcworkspace
#   biliobjclint-xcode /path/to/MyApp.xcworkspace -p MyProject -t MyTarget
#   biliobjclint-xcode /path/to/MyApp.xcodeproj --target MyApp
#   biliobjclint-xcode /path/to/MyApp.xcodeproj --list-targets
#   biliobjclint-xcode /path/to/MyApp.xcodeproj --remove
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

show_help() {
    echo "BiliObjCLint Xcode 集成安装脚本"
    echo ""
    echo "用法: $0 <项目路径> [选项]"
    echo ""
    echo "参数:"
    echo "  项目路径            .xcworkspace 或 .xcodeproj 路径"
    echo ""
    echo "选项:"
    echo "  --project, -p NAME  指定项目名称（用于 workspace 中指定项目）"
    echo "  --target, -t NAME   指定 Target 名称（默认：主 Target）"
    echo "  --lint-path PATH    指定 BiliObjCLint 安装路径（默认：自动检测）"
    echo "  --debug PATH        启用调试模式，使用指定的本地开发目录（与 --bootstrap 配合使用）"
    echo "  --remove            移除已添加的 Lint Phase"
    echo "  --override          强制覆盖已存在的 Lint Phase"
    echo "  --check-update      检查已注入脚本是否需要更新"
    echo "  --bootstrap         自动复制 bootstrap.sh 并注入 Package Manager Build Phase"
    echo "  --list-projects     列出 workspace 中所有项目"
    echo "  --list-targets      列出所有可用的 Targets"
    echo "  --dry-run           仅显示将要进行的修改，不实际执行"
    echo "  --manual            显示手动配置说明（不自动修改项目）"
    echo "  --help, -h          显示帮助"
    echo ""
    echo "示例:"
    echo "  $0 /path/to/MyApp.xcworkspace"
    echo "  $0 /path/to/MyApp.xcworkspace -p MyProject -t MyTarget"
    echo "  $0 /path/to/MyApp.xcodeproj --target MyApp"
    echo "  $0 /path/to/MyApp.xcodeproj --list-targets"
    echo "  $0 /path/to/MyApp.xcodeproj --remove"
    echo ""
    echo "调试模式示例:"
    echo "  $0 /path/to/MyApp.xcodeproj --bootstrap --debug /path/to/BiliObjCLint"
    exit 0
}

# 解析参数
PROJECT_PATH=""
XCODEPROJ_PATH=""
PROJECT_NAME=""
TARGET_NAME=""
LINT_PATH=""
SCRIPTS_DIR=""
DEBUG_PATH=""
ACTION="add"
DRY_RUN=""
OVERRIDE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            show_help
            ;;
        --manual)
            ACTION="manual"
            shift
            ;;
        --xcodeproj)
            XCODEPROJ_PATH="$2"
            shift 2
            ;;
        --project|-p)
            PROJECT_NAME="$2"
            shift 2
            ;;
        --target|-t)
            TARGET_NAME="$2"
            shift 2
            ;;
        --lint-path)
            LINT_PATH="$2"
            shift 2
            ;;
        --remove)
            ACTION="remove"
            shift
            ;;
        --override)
            OVERRIDE="--override"
            shift
            ;;
        --check-update)
            ACTION="check-update"
            shift
            ;;
        --check-and-inject)
            ACTION="check-and-inject"
            shift
            ;;
        --scripts-dir)
            SCRIPTS_DIR="$2"
            shift 2
            ;;
        --bootstrap)
            ACTION="bootstrap"
            shift
            ;;
        --debug)
            DEBUG_PATH="$2"
            shift 2
            ;;
        --list-projects)
            ACTION="list-projects"
            shift
            ;;
        --list-targets)
            ACTION="list-targets"
            shift
            ;;
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        -*)
            print_error "未知选项: $1"
            echo "使用 --help 查看帮助"
            exit 1
            ;;
        *)
            if [ -z "$PROJECT_PATH" ]; then
                PROJECT_PATH="$1"
            else
                print_error "多余的参数: $1"
                exit 1
            fi
            shift
            ;;
    esac
done

# 如果指定了 --xcodeproj，使用它作为项目路径
if [ -n "$XCODEPROJ_PATH" ]; then
    PROJECT_PATH="$XCODEPROJ_PATH"
fi

# 检查项目路径
if [ -z "$PROJECT_PATH" ]; then
    print_error "请指定项目路径"
    echo ""
    echo "用法: $0 <项目路径> [选项]"
    echo "使用 --help 查看详细帮助"
    exit 1
fi

# 检查项目是否存在
if [ ! -e "$PROJECT_PATH" ]; then
    print_error "项目路径不存在: $PROJECT_PATH"
    exit 1
fi

# 检查 venv
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python3"
if [ ! -f "$PYTHON_BIN" ]; then
    print_error "venv 未初始化，请先运行:"
    echo "  $PROJECT_ROOT/setup_env.sh"
    exit 1
fi

echo "=========================================="
echo "     BiliObjCLint Xcode 集成"
echo "=========================================="
echo ""

# 构建命令参数
CMD_ARGS=("$PROJECT_PATH")

if [ -n "$PROJECT_NAME" ]; then
    CMD_ARGS+=("--project" "$PROJECT_NAME")
fi

if [ -n "$TARGET_NAME" ]; then
    CMD_ARGS+=("--target" "$TARGET_NAME")
fi

# check-and-inject 使用 check_update.py
if [ "$ACTION" = "check-and-inject" ]; then
    # 使用 --xcodeproj 参数传递路径（对应 Xcode 的 PROJECT_FILE_PATH）
    CHECK_ARGS=("--xcodeproj" "$PROJECT_PATH")
    if [ -n "$TARGET_NAME" ]; then
        CHECK_ARGS+=("--target" "$TARGET_NAME")
    fi
    if [ -n "$SCRIPTS_DIR" ]; then
        CHECK_ARGS+=("--scripts-dir" "$SCRIPTS_DIR")
    fi
    if [ -n "$DRY_RUN" ]; then
        CHECK_ARGS+=("$DRY_RUN")
    fi
    "$PYTHON_BIN" "$PROJECT_ROOT/scripts/wrapper/update/checker.py" "${CHECK_ARGS[@]}"
else
    # 其他操作使用 xcode_integrator.py
    if [ "$ACTION" = "remove" ]; then
        CMD_ARGS+=("--remove")
    elif [ "$ACTION" = "check-update" ]; then
        CMD_ARGS+=("--check-update")
    elif [ "$ACTION" = "bootstrap" ]; then
        CMD_ARGS+=("--bootstrap")
    elif [ "$ACTION" = "list-projects" ]; then
        CMD_ARGS+=("--list-projects")
    elif [ "$ACTION" = "list-targets" ]; then
        CMD_ARGS+=("--list-targets")
    elif [ "$ACTION" = "manual" ]; then
        CMD_ARGS+=("--manual")
    fi

    if [ -n "$DRY_RUN" ]; then
        CMD_ARGS+=("$DRY_RUN")
    fi

    if [ -n "$OVERRIDE" ]; then
        CMD_ARGS+=("$OVERRIDE")
    fi

    if [ -n "$LINT_PATH" ]; then
        CMD_ARGS+=("--lint-path" "$LINT_PATH")
    fi

    if [ -n "$DEBUG_PATH" ]; then
        CMD_ARGS+=("--debug" "$DEBUG_PATH")
    fi

    "$PYTHON_BIN" "$PROJECT_ROOT/scripts/wrapper/xcode/cli.py" "${CMD_ARGS[@]}"
fi

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ] && [ "$ACTION" = "add" ] && [ -z "$DRY_RUN" ]; then
    echo ""
    echo "=========================================="
    echo "              集成完成"
    echo "=========================================="
    echo ""
    echo "后续步骤:"
    echo "1. 打开 Xcode 项目，检查 Build Phases"
    echo "2. 编辑配置文件: .biliobjclint.yaml"
    echo "3. 编译项目，查看 Lint 结果"
    echo ""
fi

exit $EXIT_CODE
