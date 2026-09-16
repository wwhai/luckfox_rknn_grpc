#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${ROOT_DIR}/build/tests"
mkdir -p "${BUILD_DIR}"

g++ -std=c++14 -Wall -Wextra -Werror -pthread \
    -I"${ROOT_DIR}/server/include" \
    "${ROOT_DIR}/server/src/session_store.cc" \
    "${ROOT_DIR}/tests/session_store_test.cc" \
    -o "${BUILD_DIR}/session_store_test"
"${BUILD_DIR}/session_store_test"

g++ -std=c++14 -Wall -Wextra -Werror -pthread \
    -I"${ROOT_DIR}/server/include" \
    "${ROOT_DIR}/server/src/discovery_service.cc" \
    "${ROOT_DIR}/tests/discovery_service_test.cc" \
    -o "${BUILD_DIR}/discovery_service_test"
"${BUILD_DIR}/discovery_service_test"

g++ -std=c++14 -Wall -Wextra -Werror -pthread \
    -I"${ROOT_DIR}/server/include" \
    "${ROOT_DIR}/server/src/system_metrics.cc" \
    "${ROOT_DIR}/tests/system_metrics_test.cc" \
    -o "${BUILD_DIR}/system_metrics_test"
"${BUILD_DIR}/system_metrics_test"
protoc --proto_path="${ROOT_DIR}/proto" \
    --descriptor_set_out="${BUILD_DIR}/rknn_accelerator.pb" \
    "${ROOT_DIR}/proto/rknn_accelerator.proto"

python3 -m py_compile \
    "${ROOT_DIR}/client/rknn_client.py" \
    "${ROOT_DIR}/client/tk_app.py" \
    "${ROOT_DIR}/scripts/generate_python.py"

echo "host checks passed"