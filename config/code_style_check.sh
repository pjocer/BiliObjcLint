#!/bin/bash
#
# BiliObjCLint - Code Style Check
# 代码规范审查脚本
#
# 在 Xcode Build Phase 中执行，检查 Objective-C 代码规范
# 通过 Homebrew 安装的 biliobjclint 执行检查
#
# Usage:
#   在 Xcode Build Phase 中：
#   "${SRCROOT}/../.biliobjclint/code_style_check.sh"
#
# 依赖的 Xcode 环境变量：
#   - SRCROOT: 项目根目录
#   - CONFIGURATION: 构建配置（Debug/Release）
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
error() { echo -e "${RED}[BiliObjCLint]${NC} $1"; }

# ==================== 环境检查 ====================

# 检查必要的环境变量
if [ -z "$SRCROOT" ]; then
    error "SRCROOT 环境变量未设置，请在 Xcode Build Phase 中运行"
    exit 1
fi

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 检查是否为调试模式
DEBUG_FILE="$SCRIPT_DIR/.debug"
DEBUG_MODE=false
if [ -f "$DEBUG_FILE" ]; then
    DEBUG_PATH=$(cat "$DEBUG_FILE")
    if [ -d "$DEBUG_PATH" ]; then
        DEBUG_MODE=true
        LINT_PATH="$DEBUG_PATH"
        PYTHON_BIN="$LINT_PATH/.venv/bin/python3"
        info "[DEBUG MODE] 使用本地目录: $LINT_PATH"
    else
        error "[DEBUG MODE] 本地目录不存在: $DEBUG_PATH"
        error "请删除 $DEBUG_FILE 或重新执行 --bootstrap --debug"
        exit 1
    fi
else
    # 正常模式：使用 Homebrew 安装
    LINT_PATH=$(brew --prefix biliobjclint 2>/dev/null)
    if [ -z "$LINT_PATH" ] || [ ! -d "$LINT_PATH" ]; then
        error "BiliObjCLint 未安装，请运行: brew install pjocer/biliobjclint/biliobjclint"
        exit 1
    fi
    PYTHON_BIN="${LINT_PATH}/libexec/.venv/bin/python3"
fi

# 项目根目录 = SCRIPT_DIR 的父目录（.biliobjclint/ 的上一级）
# bootstrap 时 .biliobjclint/ 创建在项目根目录下，因此 SCRIPT_DIR 的父目录就是项目根目录
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 配置文件搜索策略（优先级从高到低）：
# 1. PROJECT_ROOT/.biliobjclint.yaml（项目根目录，即 .biliobjclint/ 同级）
# 2. SRCROOT/.biliobjclint.yaml（子项目级覆盖）
CONFIG_PATH=""
if [ -f "${PROJECT_ROOT}/.biliobjclint.yaml" ]; then
    CONFIG_PATH="${PROJECT_ROOT}/.biliobjclint.yaml"
elif [ -f "${SRCROOT}/.biliobjclint.yaml" ]; then
    CONFIG_PATH="${SRCROOT}/.biliobjclint.yaml"
fi

if [ -z "$CONFIG_PATH" ]; then
    warn "未找到配置文件 .biliobjclint.yaml"
    exit 0
fi

# 加载日志库
if [ "$DEBUG_MODE" = true ]; then
    LOG_LIB_PATH="${LINT_PATH}/scripts/lib/logging.sh"
else
    LOG_LIB_PATH="${LINT_PATH}/libexec/scripts/lib/logging.sh"
fi

if [ -f "$LOG_LIB_PATH" ]; then
    source "$LOG_LIB_PATH"
    init_logging "xcode_build_phase"
    log_script_start "Build Phase Lint Check"
    log_info "Project: ${SRCROOT}"
    log_info "Configuration: ${CONFIGURATION}"
    [ "$DEBUG_MODE" = true ] && log_info "Debug mode: enabled"
    log_info "Config file: $CONFIG_PATH"
else
    # 如果日志库不存在，定义空函数
    log_info() { :; }
    log_debug() { :; }
    log_warn() { :; }
    log_error() { :; }
fi

# ==================== 构建检查 ====================

# Release 模式跳过
if [ "${CONFIGURATION}" == "Release" ]; then
    log_info "Release mode, skipping lint check"
    info "Release 模式，跳过 Lint 检查"
    exit 0
fi

# 检查 venv
if [ ! -f "$PYTHON_BIN" ]; then
    log_warn "BiliObjCLint venv not initialized"
    warn "BiliObjCLint venv 未初始化，请重新安装: brew reinstall biliobjclint"
    exit 0
fi

log_info "Python binary: $PYTHON_BIN"

# ==================== 执行 Lint 检查 ====================

# 根据模式设置脚本路径
if [ "$DEBUG_MODE" = true ]; then
    SCRIPTS_PATH="${LINT_PATH}/scripts"
else
    SCRIPTS_PATH="${LINT_PATH}/libexec/scripts"
fi

# 创建临时文件存储 JSON 输出（用于 Claude fixer）
VIOLATIONS_FILE=$(mktemp)
log_debug "Violations temp file: $VIOLATIONS_FILE"

# 记录开始时间
LINT_START_TIME=$("$PYTHON_BIN" -c "import time; print(time.time())")

# 执行 Lint 检查（单次执行，同时输出 Xcode 格式和 JSON 文件）
# --xcode-output: 输出 Xcode 兼容格式到 stdout（用于 Xcode 显示警告/错误）
# --json-file: 同时输出 JSON 格式到文件（用于 Claude fixer）
# 临时禁用 set -e，因为 lint 检查可能返回非零退出码（有 error 级别违规时）
log_info "Running lint check..."
set +e
"$PYTHON_BIN" "${SCRIPTS_PATH}/wrapper/lint/cli.py" \
    --config "$CONFIG_PATH" \
    --project-root "${SRCROOT}" \
    --incremental \
    --xcode-output \
    --json-file "$VIOLATIONS_FILE"
LINT_EXIT=$?
set -e

# 记录结束时间并计算耗时
LINT_END_TIME=$("$PYTHON_BIN" -c "import time; print(time.time())")
LINT_DURATION=$("$PYTHON_BIN" -c "print(f'{$LINT_END_TIME - $LINT_START_TIME:.2f}')")
info "=========================================="
info "Lint 检查耗时: ${LINT_DURATION} 秒"
info "=========================================="
log_info "Lint exit code: $LINT_EXIT, duration: ${LINT_DURATION}s"

# ==================== Claude 自动修复 ====================

# 如果有违规，调用 Claude 修复模块
# claude_fixer.py 会根据配置文件中的 claude_autofix.trigger 决定是否显示对话框：
#   - trigger: "any" → 任何违规都弹窗
#   - trigger: "error" → 只有 error 级别违规才弹窗
#   - trigger: "disable" → 禁用自动弹窗
if [ -s "$VIOLATIONS_FILE" ]; then
    # 保存违规信息到固定位置
    VIOLATIONS_COPY="/tmp/biliobjclint_violations_$$.json"
    cp "$VIOLATIONS_FILE" "$VIOLATIONS_COPY"
    log_debug "Violations copied to: $VIOLATIONS_COPY"

    # 在进入后台子进程前，先保存所有需要的变量值
    # 因为 Xcode 环境变量在后台子进程中可能不可用
    _PYTHON_BIN="$PYTHON_BIN"
    _SCRIPTS_PATH="$SCRIPTS_PATH"
    _CONFIG_PATH="$CONFIG_PATH"
    _PROJECT_ROOT="${PROJECT_ROOT}"
    _VIOLATIONS_COPY="$VIOLATIONS_COPY"

    log_info "Launching Claude fixer in background..."

    # 在后台调用 claude_fixer.py，它会：
    # 1. 根据 trigger 配置决定是否触发
    # 2. 显示对话框询问用户
    # 3. 执行修复（如果用户同意）
    (
        "$_PYTHON_BIN" "$_SCRIPTS_PATH/claude/cli.py" \
            --violations "$_VIOLATIONS_COPY" \
            --config "$_CONFIG_PATH" \
            --project-root "$_PROJECT_ROOT"

        rm -f "$_VIOLATIONS_COPY"
    ) &
fi

# 清理临时文件
rm -f "$VIOLATIONS_FILE"
log_debug "Temp file cleaned up"

log_info "Build phase completed with exit code: $LINT_EXIT"
exit $LINT_EXIT
