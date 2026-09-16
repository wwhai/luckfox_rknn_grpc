#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RKNN_EXAMPLE_ROOT="${RKNN_EXAMPLE_ROOT:-${ROOT_DIR}/../luckfox_pico_rknn_example}"
BUILD_DIR="${ROOT_DIR}/build/target"
PACKAGE_DIR="${ROOT_DIR}/dist/luckfox_rknn_grpc"
JOBS="${JOBS:-$(nproc)}"

if [[ -z "${LUCKFOX_SDK_PATH:-}" ]]; then
    echo "LUCKFOX_SDK_PATH is required" >&2
    exit 2
fi

if [[ ! -f "${ROOT_DIR}/.deps/target/lib/cmake/grpc/gRPCConfig.cmake" ]]; then
    "${ROOT_DIR}/scripts/build_grpc_deps.sh"
fi

cmake -S "${ROOT_DIR}" -B "${BUILD_DIR}" \
    -DCMAKE_TOOLCHAIN_FILE="${ROOT_DIR}/cmake/rv1106-uclibc.cmake" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="${PACKAGE_DIR}" \
    -DRKNN_EXAMPLE_ROOT="${RKNN_EXAMPLE_ROOT}"
cmake --build "${BUILD_DIR}" --parallel "${JOBS}"
rm -rf "${PACKAGE_DIR}"
cmake --install "${BUILD_DIR}"

echo "Package created: ${PACKAGE_DIR}"