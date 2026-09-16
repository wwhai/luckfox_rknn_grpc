# API Integration Guide

## Lifecycle

### LAN Discovery

Send the exact ASCII payload `LUCKFOX_RKNN_DISCOVER` as a UDP broadcast to port `50052`. Each accelerator responds to the sender with one JSON object containing its hostname, board/SoC, architecture, gRPC port, model/task, busy state and password requirement. Use the response source IP with `grpc_port` to form the endpoint.

Discovery does not open or consume the exclusive inference session.

### Transport Connect

Create a gRPC channel to `IP:Port` and wait for channel readiness with a deadline. A transport failure is reported by the client SDK as `Connect` with `DEADLINE_EXCEEDED` or `UNAVAILABLE`.

### Discover

Call `GetServerInfo` to read models and request limits. Call `Health` before opening a session and for periodic monitoring.

`GetServerInfo` also returns structured board identity, OS/architecture, model input layout, quantization and model size. `exclusive_access=true` means only one active inference session is permitted.

### Performance

Call `GetPerformance` to read current CPU usage and core count, 1/5/15 minute load averages, memory capacity/availability/usage, system uptime and board temperature when exposed by thermal sysfs. This monitoring call does not consume the exclusive inference session.

### OpenSession

Call `OpenSession` with `model_name`, a descriptive `client_name`, and `password`. The default server password is `19940724`. Keep the returned `session_id`; it is required by every inference request. Sessions expire after the returned idle timeout.

The accelerator uses exclusive ownership. If another session is active, `OpenSession` returns `RESOURCE_EXHAUSTED`. Discovery and health calls remain available so monitoring tools can inspect the busy accelerator.

### Infer

`Infer` accepts one encoded JPEG or PNG. Always provide a unique `request_id` so logs and responses can be correlated. Zero option values select server defaults.

The response boxes use pixel coordinates in the original image:

- left/top are inclusive origins.
- right/bottom are the detected extent.
- score is in `[0, 1]`.
- sequence number starts at `1` and matches the visual marker/order returned by the server.
- timing values are microseconds measured on the server.

`StreamInfer` uses the same request and response messages. Responses preserve stream order because one stream is processed sequentially. Use separate streams to overlap network transfer; NPU execution remains serialized.

### Close

Call `CloseSession`, then close the gRPC channel. `CloseSession` is idempotent: an already closed or expired session returns `closed=false` with gRPC `OK`.

## Error Contract

| gRPC code | Meaning | Client action |
| --- | --- | --- |
| `INVALID_ARGUMENT` | Empty, unsupported, or undecodable image | Fix request; do not retry unchanged |
| `UNAUTHENTICATED` | Password rejected | Correct the password |
| `NOT_FOUND` | Model missing, or session expired | Open a new session |
| `RESOURCE_EXHAUSTED` | Session/image limit exceeded | Back off or reduce request |
| `FAILED_PRECONDITION` | Session model unavailable | Rediscover models and reconnect |
| `DEADLINE_EXCEEDED` | Client deadline elapsed | Retry with bounded backoff if appropriate |
| `UNAVAILABLE` | Server/channel unavailable | Reconnect with exponential backoff |
| `INTERNAL` | Decode-independent server/NPU failure | Log request ID and retry once |

Recommended retry policy: retry only idempotent discovery calls and an `Infer` whose response was not received. Use the same request ID, exponential backoff, and a small retry limit. The current server does not deduplicate request IDs.

## Python SDK

```python
from rknn_client import RknnClient

with RknnClient(timeout_seconds=10) as client:
    devices = client.discover()
    info = client.connect(devices[0].endpoint, model_name="yolov5", password="19940724")
    response = client.infer("bus.jpg", score_threshold=0.25)
    for item in response.detections:
        print(item.label, item.score, item.box)
```

Other languages should generate code from the schema using their standard protobuf and gRPC plugins. No JSON translation layer is required.

## Defaults And Limits

| Setting | Default |
| --- | --- |
| Discovery | UDP `50052` |
| gRPC | TCP `50051` |
| Password | `19940724` |
| Max encoded image | 8 MiB |
| Max active sessions | 1 (exclusive) |
| Session idle timeout | 300 seconds |
| Score threshold | 0.25 |
| NMS threshold | 0.45 |
| Max detections | 128 server hard limit |