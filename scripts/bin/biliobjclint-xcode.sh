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
#   --target, -t NAME    指定 Target 名称（默认：主 Target）
#   --remove             移除已添加的 Lint Phase
#   --override           强制覆盖已存在的 Lint Phase
#   --list-targets       列出所有可用的 Targets
#   --dry-run            仅显示将要进行的修改，不实际执行
#   --manual             显示手动配置说明（不自动修改项目）
#   --help, -h           显示帮助
#
# 示例:
#   biliobjclint-xcode /path/to/MyApp.xcworkspace
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
    echo "  --target, -t NAME   指定 Target 名称（默认：主 Target）"
    echo "  --remove            移除已添加的 Lint Phase"
    echo "  --override          强制覆盖已存在的 Lint Phase"
    echo "  --list-targets      列出所有可用的 Targets"
    echo "  --dry-run           仅显示将要进行的修改，不实际执行"
    echo "  --manual            显示手动配置说明（不自动修改项目）"
    echo "  --help, -h          显示帮助"
    echo ""
    echo "示例:"
    echo "  $0 /path/to/MyApp.xcworkspace"
    echo "  $0 /path/to/MyApp.xcodeproj --target MyApp"
    echo "  $0 /path/to/MyApp.xcodeproj --list-targets"
    echo "  $0 /path/to/MyApp.xcodeproj --remove"
    exit 0
}

show_manual() {
    local LINT_PATH="$PROJECT_ROOT"

    echo ""
    echo "=========================================="
    echo "     手动配置 Xcode Build Phase"
    echo "=========================================="
    echo ""
    echo "1. 打开 Xcode 项目"
    echo "2. 选择 Target → Build Phases"
    echo "3. 点击 '+' → New Run Script Phase"
    echo "4. 将此 Phase 拖动到 'Compile Sources' 之前"
    echo "5. 粘贴以下脚本:"
    echo ""
    echo "----------------------------------------"
    cat << SCRIPT
#!/bin/bash

# BiliObjCLint - Objective-C 代码规范检查

LINT_PATH="${LINT_PATH}"
CONFIG_PATH="\${SRCROOT}/.biliobjclint.yaml"
PYTHON_BIN="\${LINT_PATH}/.venv/bin/python3"

# Release 模式跳过
if [ "\${CONFIGURATION}" == "Release" ]; then
    echo "Release 模式，跳过 Lint 检查"
    exit 0
fi

# 检查 venv
if [ ! -f "\$PYTHON_BIN" ]; then
    echo "warning: BiliObjCLint venv 未初始化"
    exit 0
fi

# 创建临时文件存储 JSON 输出
VIOLATIONS_FILE=\$(mktemp)

# 执行 Lint 检查，输出 JSON 格式到临时文件
"\$PYTHON_BIN" "\${LINT_PATH}/scripts/biliobjclint.py" \\
    --config "\$CONFIG_PATH" \\
    --project-root "\${SRCROOT}" \\
    --incremental \\
    --json-output > "\$VIOLATIONS_FILE" 2>/dev/null

# 执行 Lint 检查，输出 Xcode 格式
"\$PYTHON_BIN" "\${LINT_PATH}/scripts/biliobjclint.py" \\
    --config "\$CONFIG_PATH" \\
    --project-root "\${SRCROOT}" \\
    --incremental \\
    --xcode-output

LINT_EXIT=\$?

# 如果有违规，调用 Claude 修复模块
if [ -s "\$VIOLATIONS_FILE" ] && [ \$LINT_EXIT -ne 0 ]; then
    "\$PYTHON_BIN" "\${LINT_PATH}/scripts/claude_fixer.py" \\
        --violations "\$VIOLATIONS_FILE" \\
        --config "\$CONFIG_PATH" \\
        --project-root "\${SRCROOT}" &
fi

# 清理临时文件
(sleep 5 && rm -f "\$VIOLATIONS_FILE") &

exit \$LINT_EXIT
SCRIPT
    echo "----------------------------------------"
    echo ""
    echo "6. 复制配置文件到项目根目录:"
    echo "   cp ${LINT_PATH}/config/default.yaml /你的项目路径/.biliobjclint.yaml"
    echo ""
    exit 0
}

# 解析参数
PROJECT_PATH=""
TARGET_NAME=""
ACTION="add"
DRY_RUN=""
OVERRIDE=""
MANUAL_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            show_help
            ;;
        --manual)
            MANUAL_MODE=true
            shift
            ;;
        --target|-t)
            TARGET_NAME="$2"
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
        --list-targets)
            ACTION="list"
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

# 手动模式
if [ "$MANUAL_MODE" = true ]; then
    show_manual
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
    echo "  $PROJECT_ROOT/scripts/bin/setup_env.sh"
    exit 1
fi

echo "=========================================="
echo "     BiliObjCLint Xcode 集成"
echo "=========================================="
echo ""

# 构建命令参数
CMD_ARGS=("$PROJECT_PATH")

if [ -n "$TARGET_NAME" ]; then
    CMD_ARGS+=("--target" "$TARGET_NAME")
fi

if [ "$ACTION" = "remove" ]; then
    CMD_ARGS+=("--remove")
elif [ "$ACTION" = "list" ]; then
    CMD_ARGS+=("--list-targets")
fi

if [ -n "$DRY_RUN" ]; then
    CMD_ARGS+=("$DRY_RUN")
fi

if [ -n "$OVERRIDE" ]; then
    CMD_ARGS+=("$OVERRIDE")
fi

# 执行 Python 脚本
"$PYTHON_BIN" "$PROJECT_ROOT/scripts/xcode_integrator.py" "${CMD_ARGS[@]}"

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
