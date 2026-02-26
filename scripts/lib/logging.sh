#!/bin/bash
#
# BiliObjCLint Shell Logging Library
#
# 用法:
#   source /path/to/logging.sh
#   init_logging "module_name"
#   log_info "message"
#   log_error "message"
#
# 日志文件统一存储在 ~/.biliobjclint/logs/ 目录下
#

# 获取脚本所在目录（调用时确定）
_LOGGING_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_BILIOBJCLINT_ROOT="$(dirname "$(dirname "$_LOGGING_LIB_DIR")")"
_LOGS_DIR="$HOME/.biliobjclint/logs"

# 日志级别
LOG_LEVEL_DEBUG=0
LOG_LEVEL_INFO=1
LOG_LEVEL_WARN=2
LOG_LEVEL_ERROR=3

# 当前日志级别（默认 INFO）
CURRENT_LOG_LEVEL=${CURRENT_LOG_LEVEL:-$LOG_LEVEL_INFO}

# 日志文件路径
LOG_FILE=""
LOG_MODULE_NAME=""

# 颜色定义
_COLOR_DEBUG='\033[0;36m'   # Cyan
_COLOR_INFO='\033[0;32m'    # Green
_COLOR_WARN='\033[1;33m'    # Yellow
_COLOR_ERROR='\033[0;31m'   # Red
_COLOR_NC='\033[0m'         # No Color

# 初始化日志
# 参数: module_name
init_logging() {
    local module_name="${1:-shell}"
    LOG_MODULE_NAME="$module_name"

    # 创建日志目录
    mkdir -p "$_LOGS_DIR"

    # 生成日志文件名
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    LOG_FILE="$_LOGS_DIR/${module_name}_${timestamp}.log"

    # 写入日志头
    echo "========================================" >> "$LOG_FILE"
    echo "BiliObjCLint Log - $module_name" >> "$LOG_FILE"
    echo "Started: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
    echo "========================================" >> "$LOG_FILE"
}

# 获取当前日志文件路径
get_log_file() {
    echo "$LOG_FILE"
}

# 内部日志函数
_log() {
    local level="$1"
    local level_num="$2"
    local color="$3"
    local message="$4"

    # 检查日志级别
    if [ $level_num -lt $CURRENT_LOG_LEVEL ]; then
        return
    fi

    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local log_line="$timestamp [$level] [$LOG_MODULE_NAME] $message"

    # 写入文件
    if [ -n "$LOG_FILE" ]; then
        echo "$log_line" >> "$LOG_FILE"
    fi

    # 输出到控制台（如果设置了 BILIOBJCLINT_VERBOSE 或级别 >= WARN）
    if [ -n "$BILIOBJCLINT_VERBOSE" ] || [ $level_num -ge $LOG_LEVEL_WARN ]; then
        echo -e "${color}[$level]${_COLOR_NC} $message" >&2
    fi
}

# 日志函数
log_debug() {
    _log "DEBUG" $LOG_LEVEL_DEBUG "$_COLOR_DEBUG" "$1"
}

log_info() {
    _log "INFO" $LOG_LEVEL_INFO "$_COLOR_INFO" "$1"
}

log_warn() {
    _log "WARN" $LOG_LEVEL_WARN "$_COLOR_WARN" "$1"
}

log_error() {
    _log "ERROR" $LOG_LEVEL_ERROR "$_COLOR_ERROR" "$1"
}

# 记录命令执行
# 参数: command description
log_cmd() {
    local cmd="$1"
    local desc="${2:-Executing command}"
    log_debug "$desc: $cmd"
}

# 记录命令结果
# 参数: exit_code description
log_cmd_result() {
    local exit_code="$1"
    local desc="${2:-Command}"
    if [ $exit_code -eq 0 ]; then
        log_debug "$desc completed successfully"
    else
        log_error "$desc failed with exit code $exit_code"
    fi
}

# 记录分隔线
log_separator() {
    local title="${1:-}"
    if [ -n "$title" ]; then
        _log "INFO" $LOG_LEVEL_INFO "$_COLOR_NC" "==================== $title ===================="
    else
        _log "INFO" $LOG_LEVEL_INFO "$_COLOR_NC" "============================================================"
    fi
}

# 记录环境信息
log_environment() {
    log_debug "Environment Info:"
    log_debug "  PWD: $(pwd)"
    log_debug "  USER: $USER"
    log_debug "  HOME: $HOME"
    log_debug "  SHELL: $SHELL"
    log_debug "  PATH: $PATH"
}

# 记录脚本开始
log_script_start() {
    local script_name="${1:-$(basename "$0")}"
    log_separator "Script Start: $script_name"
    log_info "Script: $script_name"
    log_info "Arguments: $*"
    log_debug "Working directory: $(pwd)"
}

# 记录脚本结束
log_script_end() {
    local exit_code="${1:-0}"
    local script_name="${2:-$(basename "$0")}"
    if [ $exit_code -eq 0 ]; then
        log_info "Script $script_name completed successfully"
    else
        log_error "Script $script_name failed with exit code $exit_code"
    fi
    log_separator "Script End: $script_name"
}

# 清理旧日志
# 参数: max_days (默认 7)
cleanup_old_logs() {
    local max_days="${1:-7}"
    log_debug "Cleaning up logs older than $max_days days"

    if [ -d "$_LOGS_DIR" ]; then
        find "$_LOGS_DIR" -name "*.log" -type f -mtime +$max_days -delete 2>/dev/null
        log_debug "Old logs cleaned up"
    fi
}
