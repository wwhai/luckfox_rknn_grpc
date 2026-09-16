#!/bin/sh
set -eu

APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PID_FILE="$APP_DIR/server.pid"
LOG_FILE="$APP_DIR/server.log"
PASSWORD_FILE="$APP_DIR/password"

start_server() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "server already running with PID $(cat "$PID_FILE")"
        return 0
    fi
    cd "$APP_DIR"
    export LD_LIBRARY_PATH="$APP_DIR/lib:${LD_LIBRARY_PATH:-}"
    PASSWORD="19940724"
    if [ -f "$PASSWORD_FILE" ]; then
        PASSWORD="$(cat "$PASSWORD_FILE")"
    fi
    nohup ./rknn_grpc_server --listen 0.0.0.0:50051 \
        --model ./model/yolov5.rknn --password "$PASSWORD" >>"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    echo "server started with PID $(cat "$PID_FILE")"
}

stop_server() {
    if [ ! -f "$PID_FILE" ]; then
        echo "server is not running"
        return 0
    fi
    PID="$(cat "$PID_FILE")"
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        while kill -0 "$PID" 2>/dev/null; do
            sleep 1
        done
    fi
    rm -f "$PID_FILE"
    echo "server stopped"
}

case "${1:-start}" in
    start) start_server ;;
    stop) stop_server ;;
    restart) stop_server; start_server ;;
    status)
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "running PID $(cat "$PID_FILE")"
        else
            echo "stopped"
            exit 1
        fi
        ;;
    logs) tail -n 100 "$LOG_FILE" ;;
    *) echo "Usage: $0 {start|stop|restart|status|logs}" >&2; exit 2 ;;
esac