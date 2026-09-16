#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GRPC_VERSION="v1.51.3"
SOURCE_DIR="${ROOT_DIR}/.deps/src/grpc"
HOST_PREFIX="${ROOT_DIR}/.deps/host"
TARGET_PREFIX="${ROOT_DIR}/.deps/target"
JOBS="${JOBS:-$(nproc)}"

if [[ -z "${LUCKFOX_SDK_PATH:-}" ]]; then
    echo "LUCKFOX_SDK_PATH is required" >&2
    exit 2
fi

mkdir -p "${ROOT_DIR}/.deps/src"
if [[ ! -d "${SOURCE_DIR}/.git" ]]; then
    rm -rf "${SOURCE_DIR}"
    GIT_CONFIG_GLOBAL=/dev/null git -c http.version=HTTP/1.1 clone --branch "${GRPC_VERSION}" --depth 1 \
        https://github.com/grpc/grpc.git "${SOURCE_DIR}"
fi

GIT_CONFIG_GLOBAL=/dev/null git -c http.version=HTTP/1.1 -C "${SOURCE_DIR}" submodule update --init --depth 1 \
    third_party/abseil-cpp \
    third_party/boringssl-with-bazel \
    third_party/cares/cares \
    third_party/protobuf \
    third_party/re2 \
    third_party/zlib

if [[ ! -x "${HOST_PREFIX}/bin/grpc_cpp_plugin" ]]; then
    cmake -S "${SOURCE_DIR}" -B "${ROOT_DIR}/.deps/build-host" \
        -DCMAKE_BUILD_TYPE=Release \
        -DgRPC_BUILD_TESTS=OFF \
        -DBUILD_SHARED_LIBS=OFF
    cmake --build "${ROOT_DIR}/.deps/build-host" --target protoc grpc_cpp_plugin --parallel "${JOBS}"
    mkdir -p "${HOST_PREFIX}/bin"
    cp "${ROOT_DIR}/.deps/build-host/third_party/protobuf/protoc" "${HOST_PREFIX}/bin/protoc"
    cp "${ROOT_DIR}/.deps/build-host/grpc_cpp_plugin" "${HOST_PREFIX}/bin/grpc_cpp_plugin"
fi

if [[ ! -f "${TARGET_PREFIX}/lib/cmake/grpc/gRPCConfig.cmake" ]]; then
    cmake -S "${SOURCE_DIR}" -B "${ROOT_DIR}/.deps/build-target" \
        -DCMAKE_TOOLCHAIN_FILE="${ROOT_DIR}/cmake/rv1106-uclibc.cmake" \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_FLAGS="-Dstatic_assert=_Static_assert" \
        -DCMAKE_INSTALL_PREFIX="${TARGET_PREFIX}" \
        -DgRPC_INSTALL=ON \
        -DgRPC_BUILD_TESTS=OFF \
        -DgRPC_BUILD_CODEGEN=OFF \
        -Dprotobuf_BUILD_PROTOC_BINARIES=OFF \
        -DProtobuf_PROTOC_EXECUTABLE="${HOST_PREFIX}/bin/protoc" \
        -DBUILD_SHARED_LIBS=OFF
    cmake --build "${ROOT_DIR}/.deps/build-target" --parallel "${JOBS}"
    cmake --install "${ROOT_DIR}/.deps/build-target"
fi

echo "Host tools: ${HOST_PREFIX}"
echo "Target libraries: ${TARGET_PREFIX}"