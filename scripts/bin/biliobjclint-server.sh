#!/bin/bash
#
# BiliObjCLint Local Server - Shell Wrapper
#
# 用法:
#   biliobjclint-server.sh start|stop|restart|status|run|clear
#   biliobjclint-server.sh --start/--stop/--restart/--status/--run/--clear
#   biliobjclint-server.sh clear -y  # 跳过确认直接清空
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

PYTHON_SCRIPT="$PROJECT_ROOT/scripts/core/server/cli.py"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python3"

if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Error: server cli not found: $PYTHON_SCRIPT" >&2
    exit 1
fi

if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: Python virtual environment not found" >&2
    echo "Please run: $PROJECT_ROOT/setup_env.sh" >&2
    exit 1
fi

if [ $# -eq 0 ]; then
    echo "Usage: $0 start|stop|restart|status|run|clear"
    echo "       $0 --start/--stop/--restart/--status/--run/--clear"
    echo "       $0 clear -y  (skip confirmation)"
    exit 1
fi

"$VENV_PYTHON" "$PYTHON_SCRIPT" "$@"
EXIT_CODE=$?

ACTION="$1"
if [[ "$ACTION" == "--start" || "$ACTION" == "start" || "$ACTION" == "--restart" || "$ACTION" == "restart" ]]; then
    if [ $EXIT_CODE -eq 0 ]; then
        echo ""
        echo "BiliObjCLint Server 已启动"
        echo "  Dashboard: http://127.0.0.1:18080/login"
        echo "  配置文件: ~/.biliobjclint/biliobjclint_server_config.json"
        echo "  日志文件: ~/.biliobjclint/lintserver.log"
        echo "  查看状态: $0 --status"
        echo ""
    else
        echo "BiliObjCLint Server 启动失败，请查看日志: ~/.biliobjclint/lintserver.log" >&2
    fi
fi

exit $EXIT_CODE
