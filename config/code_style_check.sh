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
#   "${SRCROOT}/../scripts/code_style_check.sh"
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

# 获取 biliobjclint 的安装路径
LINT_PATH=$(brew --prefix biliobjclint 2>/dev/null)
if [ -z "$LINT_PATH" ] || [ ! -d "$LINT_PATH" ]; then
    error "BiliObjCLint 未安装，请运行: brew install pjocer/biliobjclint/biliobjclint"
    exit 1
fi

# 配置文件路径
CONFIG_PATH="${SRCROOT}/.biliobjclint.yaml"
PYTHON_BIN="${LINT_PATH}/libexec/.venv/bin/python3"

# 加载日志库
if [ -f "${LINT_PATH}/libexec/scripts/lib/logging.sh" ]; then
    source "${LINT_PATH}/libexec/scripts/lib/logging.sh"
    init_logging "xcode_build_phase"
    log_script_start "Build Phase Lint Check"
    log_info "Project: ${SRCROOT}"
    log_info "Configuration: ${CONFIGURATION}"
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

# 创建临时文件存储 JSON 输出
VIOLATIONS_FILE=$(mktemp)
log_debug "Violations temp file: $VIOLATIONS_FILE"

# 执行 Lint 检查，输出 JSON 格式到临时文件
log_info "Running lint check (JSON output)..."
"$PYTHON_BIN" "${LINT_PATH}/libexec/scripts/biliobjclint.py" \
    --config "$CONFIG_PATH" \
    --project-root "${SRCROOT}" \
    --incremental \
    --json-output > "$VIOLATIONS_FILE" 2>/dev/null

# 执行 Lint 检查，输出 Xcode 格式（用于在 Xcode 中显示警告/错误）
log_info "Running lint check (Xcode output)..."
"$PYTHON_BIN" "${LINT_PATH}/libexec/scripts/biliobjclint.py" \
    --config "$CONFIG_PATH" \
    --project-root "${SRCROOT}" \
    --incremental \
    --xcode-output

LINT_EXIT=$?
log_info "Lint exit code: $LINT_EXIT"

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
    _LINT_PATH="$LINT_PATH"
    _CONFIG_PATH="$CONFIG_PATH"
    _PROJECT_ROOT="${SRCROOT}"
    _VIOLATIONS_COPY="$VIOLATIONS_COPY"

    log_info "Launching Claude fixer in background..."

    # 在后台调用 claude_fixer.py，它会：
    # 1. 根据 trigger 配置决定是否触发
    # 2. 显示对话框询问用户
    # 3. 执行修复（如果用户同意）
    (
        "$_PYTHON_BIN" "$_LINT_PATH/libexec/scripts/claude_fixer.py" \
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
