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
        # 读取配置获取端口
        CONFIG_FILE="$HOME/.biliobjclint/biliobjclint_server_config.json"
        PORT=18080
        HOST="0.0.0.0"
        if [ -f "$CONFIG_FILE" ]; then
            PORT=$(grep -o '"port"[[:space:]]*:[[:space:]]*[0-9]*' "$CONFIG_FILE" | grep -o '[0-9]*' | head -1)
            HOST=$(grep -o '"host"[[:space:]]*:[[:space:]]*"[^"]*"' "$CONFIG_FILE" | sed 's/.*"\([^"]*\)"$/\1/' | head -1)
            [ -z "$PORT" ] && PORT=18080
            [ -z "$HOST" ] && HOST="0.0.0.0"
        fi

        echo ""
        echo "BiliObjCLint Server 已后台启动"
        echo ""
        if [ "$HOST" = "0.0.0.0" ]; then
            # 获取本机 IP
            LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "")
            echo "  Dashboard:"
            echo "    - http://127.0.0.1:$PORT/login (本机)"
            [ -n "$LOCAL_IP" ] && echo "    - http://$LOCAL_IP:$PORT/login (局域网)"
            echo ""
            echo "  客户端配置 (.biliobjclint/config.yaml):"
            echo "    metrics:"
            echo "      enabled: true"
            [ -n "$LOCAL_IP" ] && echo "      endpoint: \"http://$LOCAL_IP:$PORT\""
            [ -z "$LOCAL_IP" ] && echo "      endpoint: \"http://<服务器IP>:$PORT\""
        else
            echo "  Dashboard: http://$HOST:$PORT/login"
        fi
        echo ""
        echo "  配置文件: $CONFIG_FILE"
        echo "  日志文件: ~/.biliobjclint/lintserver.log"
        echo "  查看状态: $0 --status"
        echo ""
        echo "  提示: 如需开机自启动，请使用 brew services:"
        echo "    brew services start biliobjclint"
        echo ""
    else
        echo "BiliObjCLint Server 启动失败，请查看日志: ~/.biliobjclint/lintserver.log" >&2
    fi
fi

exit $EXIT_CODE
