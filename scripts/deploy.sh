#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOARD="${1:-root@192.168.0.108}"
PACKAGE_DIR="${ROOT_DIR}/dist/luckfox_rknn_grpc"

if [[ ! -x "${PACKAGE_DIR}/rknn_grpc_server" ]]; then
    echo "Build the server first: bash scripts/build_server.sh" >&2
    exit 2
fi

ssh "${BOARD}" 'if [ -x /root/luckfox_rknn_grpc/start_server.sh ]; then /root/luckfox_rknn_grpc/start_server.sh stop; fi; rm -rf /root/luckfox_rknn_grpc; mkdir -p /root/luckfox_rknn_grpc'
scp -r "${PACKAGE_DIR}"/* "${BOARD}:/root/luckfox_rknn_grpc/"
ssh "${BOARD}" 'cd /root/luckfox_rknn_grpc && ./start_server.sh start'

echo "Deployed to ${BOARD}:/root/luckfox_rknn_grpc"