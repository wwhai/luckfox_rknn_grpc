#!/usr/bin/env bash
#
# package_tar.sh
#
# Pack the built dist/luckfox_rknn_grpc package into a versioned, device-side
# distributable tar. Uses an uncompressed POSIX tar so that BuildRoot boards
# (BusyBox tar, no gzip/unzip guarantees) can always extract it.
#
# The artifact is written to dist/ as:
#   luckfox_rknn_grpc-<VERSION>_<YYYYMMDD>_<HHMMSS>.tar
#
# Usage:
#   bash scripts/package_tar.sh                 # auto version + timestamp
#   VERSION=v0.3.0 bash scripts/package_tar.sh  # explicit version
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_DIR="${ROOT_DIR}/dist/luckfox_rknn_grpc"
DIST_DIR="${ROOT_DIR}/dist"
VERSION="${VERSION:-}"
STAMP="$(date +%Y%m%d_%H%M%S)"

if [ ! -x "${PACKAGE_DIR}/rknn_grpc_server" ]; then
    echo "Package not built. Run: bash scripts/build_server.sh" >&2
    exit 2
fi

if [ -z "${VERSION}" ]; then
    if command -v git >/dev/null 2>&1 && VERSION="$(git -C "${ROOT_DIR}" describe --tags --always 2>/dev/null)"; then
        : # use git describe result
    else
        VERSION="dev"
    fi
fi
# keep the filename friendly for cross-platform disks
VERSION_CLEAN="${VERSION//\//-}"

TAR_NAME="luckfox_rknn_grpc-${VERSION_CLEAN}_${STAMP}.tar"
TAR_PATH="${DIST_DIR}/${TAR_NAME}"

# Uncompressed POSIX tar: universally extractable by BusyBox tar -xf.
tar --format=posix -cf "${TAR_PATH}" -C "${DIST_DIR}" luckfox_rknn_grpc

echo "Created: ${TAR_PATH}"
echo "SHA256:  $(sha256sum "${TAR_PATH}" | awk '{print $1}')"
echo
echo "On the board, extract with:"
echo "  cd / && tar -xf /tmp/${TAR_NAME}"
echo "Then install the service (once):"
echo "  sh /root/luckfox_rknn_grpc/deploy/install_service.sh"