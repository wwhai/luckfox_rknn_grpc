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

## Board Operations

```bash
cd /root/luckfox_rknn_grpc
./start_server.sh start
./start_server.sh status
./start_server.sh logs
./start_server.sh restart
./start_server.sh stop
```

The service writes `server.pid` and `server.log` in its own directory. It sets `LD_LIBRARY_PATH` only for the server process and does not modify the system image.

The server requires a password and uses `19940724` by default. To change it:

```bash
printf '%s' 'replace-with-a-long-random-password' > /root/luckfox_rknn_grpc/password
chmod 600 /root/luckfox_rknn_grpc/password
/root/luckfox_rknn_grpc/start_server.sh restart
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