#!/bin/sh
#
# update_server.sh
#
# Update the RKNN gRPC accelerator on the target board without touching the
# SysVinit service definition. Reuses the init script to perform a graceful
# restart after the package files have been replaced, preserving the custom
# password and log history across the upgrade.
#
# Run from the host (after a successful build):
#     sh deploy/update_server.sh ssh root@192.168.0.108
#
# Run directly on the board to refresh from a local package directory:
#     sh deploy/update_server.sh local /tmp/luckfox_rknn_grpc
#
# Environment overrides:
#   BOARD       ssh target (default root@192.168.0.108; ignored for local mode)
#   APP_DIR     remote install directory (default /root/luckfox_rknn_grpc)
#   STAGE_DIR   remote staging directory (default $APP_DIR.new)
#   SERVICE_API   path to init script; if set and executable, it is used to
#                 stop/start the server, otherwise the legacy start_server.sh.
#

BOARD="${BOARD:-root@192.168.0.108}"
APP_DIR="${APP_DIR:-/root/luckfox_rknn_grpc}"
STAGE_DIR="${STAGE_DIR:-$APP_DIR.new}"
SERVICE_PATH="${SERVICE_PATH:-/etc/init.d/luckfox-rknn-grpc}"
LEGACY_PATH="$APP_DIR/start_server.sh"

log() { printf '[update_server] %s\n' "$*"; }
fail() { log "ERROR: $*" >&2; exit 1; }

stop_server_remote() {
    ssh "$BOARD" "if [ -x '$SERVICE_PATH' ]; then '$SERVICE_PATH' stop; elif [ -x '$LEGACY_PATH' ]; then '$LEGACY_PATH' stop; fi"
}

start_server_remote() {
    ssh "$BOARD" "if [ -x '$SERVICE_PATH' ]; then '$SERVICE_PATH' start; elif [ -x '$LEGACY_PATH' ]; then '$LEGACY_PATH' start; else echo 'no starter found' >&2; exit 1; fi"
}

# Backup current APP_DIR to "$1" on the board.
backup_remote() {
    local backup_path="$1"
    ssh "$BOARD" "rm -rf '$backup_path' && mv '$APP_DIR' '$backup_path'"
}

update_shared() {
    local dir="$1"
    [ -d "$dir" ] || fail "package directory $dir not found"
    # ensure the package carries the deployment helpers
    [ -f "$dir/deploy/initd/luckfox-rknn-grpc" ] || fail "package lacks deploy/initd/luckfox-rknn-grpc (rebuild with scripts/build_server.sh)"
    [ -f "$dir/deploy/install_service.sh" ] || fail "package lacks deploy/install_service.sh"
}

update_remote() {
    log "syncing package to ${BOARD}:${APP_DIR}"
    stop_server_remote || true

    # Stage the new package.
    ssh "$BOARD" "rm -rf '$STAGE_DIR' && mkdir -p '$STAGE_DIR'"
    scp -r "$PKG"/* "${BOARD}:${STAGE_DIR}/"

    # Preserve custom password, run state and logs across the upgrade.
    ssh "$BOARD" "cd '$APP_DIR' && if [ -f password ]; then cp password '$STAGE_DIR/password'; fi && if [ -f server.log ]; then cp server.log '$STAGE_DIR/server.log'; fi" 2>/dev/null || true

    backup_remote "$APP_DIR.old" || fail "failed to back up old package"
    ssh "$BOARD" "mv '$STAGE_DIR' '$APP_DIR'" || fail "failed to promote new package"

    start_server_remote
    log "update complete; previous tree preserved at ${BOARD}:${APP_DIR}.old"
}

update_local() {
    local new_dir="$PKG"
    update_shared "$new_dir"

    if [ -x "$SERVICE_PATH" ]; then
        "$SERVICE_PATH" stop || true
    elif [ -x "$LEGACY_PATH" ]; then
        "$LEGACY_PATH" stop || true
    fi

    log "swapping $APP_DIR with $new_dir"
    rm -rf "$APP_DIR.old"
    mv "$APP_DIR" "$APP_DIR.old"

    if [ -d "$APP_DIR.old" ]; then
        if [ -f "$APP_DIR.old/password" ]; then
            cp "$APP_DIR.old/password" "$new_dir/password"
        fi
        if [ -f "$APP_DIR.old/server.log" ]; then
            cp "$APP_DIR.old/server.log" "$new_dir/server.log"
        fi
    fi
    mv "$new_dir" "$APP_DIR"

    if [ -x "$SERVICE_PATH" ]; then
        "$SERVICE_PATH" start
    elif [ -x "$LEGACY_PATH" ]; then
        "$LEGACY_PATH" start
    fi
    log "update complete; previous tree preserved at $APP_DIR.old"
}

mode="$1"
if [ "$mode" = "local" ]; then
    PKG="${2:-}"
    [ -n "$PKG" ] || fail "usage: $0 local /path/to/new/package"
    update_shared "$PKG"
    update_local
else
    # default / explicit "ssh" mode: first arg is target, second is package dir
    if [ "$mode" = "ssh" ] || [ "$mode" = "remote" ]; then
        shift
    fi
    [ -n "$1" ] && BOARD="$1"
    PKG="${2:-dist/luckfox_rknn_grpc}"
    update_shared "$PKG"
    update_remote
fi