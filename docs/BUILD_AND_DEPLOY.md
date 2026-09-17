# Build And Deploy

## Prerequisites

- Ubuntu/WSL with CMake, Git, GCC/G++, Make and Python 3.
- Luckfox SDK at `/home/ubuntu/workspace/luckfox-pico-SDK-main` or another path exported as `LUCKFOX_SDK_PATH`.
- `luckfox_pico_rknn_example` adjacent to this project, or exported as `RKNN_EXAMPLE_ROOT`.
- Internet access for the first gRPC source checkout.
- Several gigabytes of disk space for native and target gRPC builds.

## Dependency Build

`scripts/build_grpc_deps.sh` pins gRPC to `v1.51.3` and creates:

- `.deps/host`: native `protoc` and `grpc_cpp_plugin`.
- `.deps/target`: ARM/uClibc static protobuf, gRPC, abseil and support libraries.

```bash
export LUCKFOX_SDK_PATH=/home/ubuntu/workspace/luckfox-pico-SDK-main
JOBS=4 bash scripts/build_grpc_deps.sh
```

Use a conservative `JOBS` value if WSL runs out of memory.

## Server Build

```bash
export LUCKFOX_SDK_PATH=/home/ubuntu/workspace/luckfox-pico-SDK-main
export RKNN_EXAMPLE_ROOT=/home/ubuntu/workspace/luckfox_pico_rknn_example
bash scripts/build_server.sh
```

The package contains the executable, model, label file, RKNN runtime and process script. gRPC/protobuf are statically linked to reduce board deployment complexity.

## Packaging For Distribution

`scripts/package_tar.sh` packs `dist/luckfox_rknn_grpc/` into a single **uncompressed POSIX tar** (`luckfox_rknn_grpc-<version>_<timestamp>.tar`), so BuildRoot boards can extract it with BusyBox `tar -xf` without needing `zip` or `gzip`:

```bash
bash scripts/package_tar.sh
# Created: dist/luckfox_rknn_grpc-7f5ddba_20260917_174445.tar
# SHA256:  ...
```

## Board Operations

The package ships a SysVinit service (BuildRoot + BusyBox init). Install once after placing the package:

```bash
cd / && tar -xf /tmp/luckfox_rknn_grpc-*.tar     # extracts to /root/luckfox_rknn_grpc/
sh /root/luckfox_rknn_grpc/deploy/install_service.sh
```

This copies `deploy/luckfox-rknn-grpc` to `/etc/init.d/`, creates `/etc/rc.d/S90luckfox-rknn-grpc` and `K10luckfox-rknn-grpc` symlinks for boot auto-start, writes a default `password` file if absent, and starts the server.

Control with:

```bash
/etc/init.d/luckfox-rknn-grpc {start|stop|restart|reload|status}
tail -f /root/luckfox_rknn_grpc/server.log
```

A legacy process script `start_server.sh` remains for compatibility:

```bash
cd /root/luckfox_rknn_grpc
./start_server.sh start|stop|restart|status|logs
```

The service writes `server.pid` and `server.log` in its own directory. It sets `LD_LIBRARY_PATH` only for the server process and does not modify the system image.

The server requires a password and uses `19940724` by default. To change it:

```bash
printf '%s' 'replace-with-a-long-random-password' > /root/luckfox_rknn_grpc/password
chmod 600 /root/luckfox_rknn_grpc/password
/etc/init.d/luckfox-rknn-grpc restart
```

## Updating The Board

`deploy/update_server.sh` swaps the package while preserving `password` and `server.log`, and keeps the previous tree at `$APP_DIR.old`:

```bash
# from the host (default target root@192.168.0.108)
sh deploy/update_server.sh ssh root@192.168.0.108
# or on the board, from a local package directory
sh /root/luckfox_rknn_grpc/deploy/update_server.sh local /tmp/luckfox_rknn_grpc_new
```

## Network And Security

Allow UDP port `50052` for LAN discovery and TCP port `50051` for gRPC. Do not expose the endpoint directly to the Internet: the password is application authentication, not transport encryption. Use a private LAN, WireGuard/Tailscale, or a TLS-capable proxy.

## Troubleshooting

Check architecture and dynamic dependencies:

```bash
file rknn_grpc_server
LD_LIBRARY_PATH=./lib ldd ./rknn_grpc_server
```

If startup reports `librknnmrt.so` missing, verify `lib/librknnmrt.so` exists and always launch through `start_server.sh`. If model initialization fails, verify the working directory contains `model/yolov5.rknn` and `model/coco_80_labels_list.txt`.