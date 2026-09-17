#!/bin/sh
#
# install_service.sh
#
# Install /etc/init.d/luckfox-rknn-grpc on the target (BuildRoot + BusyBox
# init) and wire it into the default runlevel so the RKNN gRPC accelerator
# starts automatically after reboot.
#
# Usage on the board (after the package has been uploaded):
#     sh /root/luckfox_rknn_grpc/deploy/install_service.sh
#
# Optional environment overrides:
#     APP_DIR          install directory (default /root/luckfox_rknn_grpc)
#     INIT_DIR         init.d directory (default /etc/init.d)
#     RC_DIR           runlevel symlink dir (default /etc/rc.d)
#     START_PRIORITY   S-prefix priority (default 90)
#     STOP_PRIORITY    K-prefix priority (default 10)
#     DISABLE_OLD      if non-empty, disable legacy start_server.sh
#

APP_DIR="${APP_DIR:-/root/luckfox_rknn_grpc}"
INIT_DIR="${INIT_DIR:-/etc/init.d}"
RC_DIR="${RC_DIR:-/etc/rc.d}"
START_PRIORITY="${START_PRIORITY:-90}"
STOP_PRIORITY="${STOP_PRIORITY:-10}"

SERVICE_NAME="luckfox-rknn-grpc"
SERVICE_PATH="$INIT_DIR/$SERVICE_NAME"
RC_START="$RC_DIR/S${START_PRIORITY}$SERVICE_NAME"
RC_STOP="$RC_DIR/K${STOP_PRIORITY}$SERVICE_NAME"
LEGACY="$APP_DIR/start_server.sh"

log() {
    printf '[install_service] %s\n' "$*"
}

fail() {
    log "ERROR: $*" >&2
    exit 1
}

[ -x "$APP_DIR/rknn_grpc_server" ] || fail "server binary missing under $APP_DIR"
[ -f "$APP_DIR/model/yolov5.rknn" ] || fail "model file missing under $APP_DIR/model"

mkdir -p "$INIT_DIR" "$RC_DIR"

# The init script ships with the package under deploy/initd/.
INIT_SOURCE="$APP_DIR/deploy/initd/luckfox-rknn-grpc"
[ -f "$INIT_SOURCE" ] || fail "init script source not found at $INIT_SOURCE"

cp -f "$INIT_SOURCE" "$SERVICE_PATH" || fail "failed to copy init script to $SERVICE_PATH"
chmod 755 "$SERVICE_PATH"

ln -sf "$SERVICE_PATH" "$RC_START"
ln -sf "$SERVICE_PATH" "$RC_STOP"

if [ -n "${DISABLE_OLD:-}" ] && [ -e "$LEGACY" ]; then
    mv "$LEGACY" "$LEGACY.disabled"
    log "legacy start_server.sh renamed to start_server.sh.disabled"
fi

if [ ! -e "$APP_DIR/password" ]; then
    printf '%s' "19940724" >"$APP_DIR/password"
    chmod 600 "$APP_DIR/password"
    log "wrote default password to $APP_DIR/password"
fi

"$SERVICE_PATH" status || true

log "service installed; reboot or run '$SERVICE_PATH start' to launch"