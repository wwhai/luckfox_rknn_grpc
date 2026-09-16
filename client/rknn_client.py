from __future__ import annotations

import json
import pathlib
import socket
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Optional, Tuple

import grpc

GENERATED_DIR = pathlib.Path(__file__).resolve().parent / "generated"
if str(GENERATED_DIR) not in sys.path:
    sys.path.insert(0, str(GENERATED_DIR))

try:
    import rknn_accelerator_pb2 as messages
    import rknn_accelerator_pb2_grpc as services
except ImportError as exc:
    raise RuntimeError(
        "gRPC stubs are missing. Run: python scripts/generate_python.py"
    ) from exc


class AcceleratorError(RuntimeError):
    def __init__(self, operation: str, detail: str, code: str = "CLIENT") -> None:
        super().__init__(f"{operation}: {detail}")
        self.operation = operation
        self.detail = detail
        self.code = code


@dataclass(frozen=True)
class ModelSummary:
    name: str
    task: str
    input_width: int
    input_height: int
    quantization: str
    tensor_layout: str
    file_size_bytes: int


@dataclass(frozen=True)
class DiscoveredAccelerator:
    endpoint: str
    hostname: str
    board_model: str
    soc: str
    architecture: str
    model_name: str
    task: str
    busy: bool
    password_required: bool


@dataclass(frozen=True)
class ConnectionInfo:
    endpoint: str
    session_id: str
    device: str
    hostname: str
    board_model: str
    soc: str
    operating_system: str
    architecture: str
    models: Tuple[ModelSummary, ...]
    max_image_bytes: int
    exclusive_access: bool
    idle_timeout_seconds: int


@dataclass(frozen=True)
class PerformanceInfo:
    cpu_core_count: int
    cpu_usage_percent: float
    load_average_1m: float
    load_average_5m: float
    load_average_15m: float
    memory_total_bytes: int
    memory_available_bytes: int
    memory_usage_percent: float
    uptime_seconds: int
    temperature_celsius: Optional[float]


class RknnClient:
    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.channel: Optional[grpc.Channel] = None
        self.stub: Optional[services.RknnAcceleratorStub] = None
        self.session_id = ""
        self.endpoint = ""

    @property
    def connected(self) -> bool:
        return bool(self.channel and self.stub and self.session_id)

    def connect(
        self,
        endpoint: str,
        model_name: str = "yolov5",
        password: str = "19940724",
        client_name: str = "python-client",
    ) -> ConnectionInfo:
        self.close()
        endpoint = endpoint.strip()
        if not endpoint or ":" not in endpoint:
            raise AcceleratorError("Connect", "endpoint must use IP:Port format")

        channel = grpc.insecure_channel(
            endpoint,
            options=[
                ("grpc.max_send_message_length", 8 * 1024 * 1024 + 4096),
                ("grpc.max_receive_message_length", 8 * 1024 * 1024 + 4096),
            ],
        )
        try:
            grpc.channel_ready_future(channel).result(timeout=self.timeout_seconds)
            stub = services.RknnAcceleratorStub(channel)
            server_info = stub.GetServerInfo(
                messages.ServerInfoRequest(), timeout=self.timeout_seconds
            )
            health = stub.Health(messages.HealthRequest(), timeout=self.timeout_seconds)
            if health.status != messages.SERVING_STATUS_SERVING:
                raise AcceleratorError("Connect", f"server is not ready: {health.message}")
            opened = stub.OpenSession(
                messages.OpenSessionRequest(
                    client_name=client_name,
                    model_name=model_name,
                    password=password,
                ),
                timeout=self.timeout_seconds,
            )
        except grpc.FutureTimeoutError as exc:
            channel.close()
            raise AcceleratorError("Connect", "connection timed out", "DEADLINE_EXCEEDED") from exc
        except grpc.RpcError as exc:
            channel.close()
            raise self._rpc_error("Connect", exc) from exc
        except Exception:
            channel.close()
            raise

        self.channel = channel
        self.stub = stub
        self.session_id = opened.session_id
        self.endpoint = endpoint
        models = tuple(
            ModelSummary(
                name=model.name,
                task=model.task,
                input_width=model.input_width,
                input_height=model.input_height,
                quantization=model.quantization,
                tensor_layout=model.tensor_layout,
                file_size_bytes=model.file_size_bytes,
            )
            for model in server_info.models
        )
        return ConnectionInfo(
            endpoint=endpoint,
            session_id=opened.session_id,
            device=server_info.device,
            hostname=server_info.board.hostname,
            board_model=server_info.board.board_model,
            soc=server_info.board.soc,
            operating_system=server_info.board.operating_system,
            architecture=server_info.board.architecture,
            models=models,
            max_image_bytes=server_info.max_image_bytes,
            exclusive_access=server_info.exclusive_access,
            idle_timeout_seconds=opened.idle_timeout_seconds,
        )

    @staticmethod
    def discover(
        timeout_seconds: float = 1.5,
        discovery_port: int = 50052,
        targets: Tuple[str, ...] = ("255.255.255.255",),
    ) -> Tuple[DiscoveredAccelerator, ...]:
        request = b"LUCKFOX_RKNN_DISCOVER"
        found = {}
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        client.bind(("", 0))
        try:
            for target in targets:
                client.sendto(request, (target, discovery_port))
            deadline = time.monotonic() + timeout_seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                client.settimeout(min(remaining, 0.25))
                try:
                    payload, address = client.recvfrom(4096)
                except socket.timeout:
                    continue
                try:
                    data = json.loads(payload.decode("utf-8"))
                    if data.get("service") != "luckfox-rknn":
                        continue
                    endpoint = f"{address[0]}:{int(data['grpc_port'])}"
                    found[endpoint] = DiscoveredAccelerator(
                        endpoint=endpoint,
                        hostname=str(data.get("hostname", "unknown")),
                        board_model=str(data.get("board_model", "Luckfox Pico")),
                        soc=str(data.get("soc", "Rockchip RV1106/RV1103")),
                        architecture=str(data.get("architecture", "arm32")),
                        model_name=str(data.get("model_name", "")),
                        task=str(data.get("task", "")),
                        busy=bool(data.get("busy", False)),
                        password_required=bool(data.get("password_required", True)),
                    )
                except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
                    continue
        finally:
            client.close()
        return tuple(found[key] for key in sorted(found))

    def infer(
        self,
        image_path: str | pathlib.Path,
        score_threshold: float = 0.25,
        nms_threshold: float = 0.45,
        max_detections: int = 100,
        timeout_seconds: Optional[float] = None,
    ):
        if not self.connected or self.stub is None:
            raise AcceleratorError("Infer", "client is not connected", "FAILED_PRECONDITION")

        path = pathlib.Path(image_path)
        try:
            image = path.read_bytes()
        except OSError as exc:
            raise AcceleratorError("Infer", f"cannot read image: {exc}") from exc
        suffix = path.suffix.lower()
        if suffix in (".jpg", ".jpeg"):
            encoding = messages.IMAGE_ENCODING_JPEG
        elif suffix == ".png":
            encoding = messages.IMAGE_ENCODING_PNG
        else:
            raise AcceleratorError("Infer", "only JPEG and PNG images are supported")

        return self.infer_bytes(
            image,
            image_encoding="jpeg" if encoding == messages.IMAGE_ENCODING_JPEG else "png",
            score_threshold=score_threshold,
            nms_threshold=nms_threshold,
            max_detections=max_detections,
            timeout_seconds=timeout_seconds,
        )

    def infer_bytes(
        self,
        image: bytes,
        image_encoding: str = "jpeg",
        score_threshold: float = 0.25,
        nms_threshold: float = 0.45,
        max_detections: int = 100,
        timeout_seconds: Optional[float] = None,
    ):
        if not self.connected or self.stub is None:
            raise AcceleratorError("Infer", "client is not connected", "FAILED_PRECONDITION")
        if not image:
            raise AcceleratorError("Infer", "image is empty")
        encodings = {
            "jpeg": messages.IMAGE_ENCODING_JPEG,
            "jpg": messages.IMAGE_ENCODING_JPEG,
            "png": messages.IMAGE_ENCODING_PNG,
        }
        encoding = encodings.get(image_encoding.lower())
        if encoding is None:
            raise AcceleratorError("Infer", "image encoding must be JPEG or PNG")

        request = messages.InferRequest(
            session_id=self.session_id,
            request_id=str(uuid.uuid4()),
            image=image,
            encoding=encoding,
            options=messages.InferOptions(
                score_threshold=score_threshold,
                nms_threshold=nms_threshold,
                max_detections=max_detections,
            ),
        )
        try:
            return self.stub.Infer(
                request,
                timeout=timeout_seconds if timeout_seconds is not None else self.timeout_seconds,
            )
        except grpc.RpcError as exc:
            raise self._rpc_error("Infer", exc) from exc

    def health(self):
        if not self.connected or self.stub is None:
            raise AcceleratorError("Health", "client is not connected", "FAILED_PRECONDITION")
        try:
            return self.stub.Health(messages.HealthRequest(), timeout=self.timeout_seconds)
        except grpc.RpcError as exc:
            raise self._rpc_error("Health", exc) from exc

    def performance(self) -> PerformanceInfo:
        if not self.connected or self.stub is None:
            raise AcceleratorError("Performance", "client is not connected", "FAILED_PRECONDITION")
        try:
            response = self.stub.GetPerformance(
                messages.PerformanceRequest(), timeout=self.timeout_seconds
            )
        except grpc.RpcError as exc:
            raise self._rpc_error("Performance", exc) from exc
        return PerformanceInfo(
            cpu_core_count=response.cpu_core_count,
            cpu_usage_percent=response.cpu_usage_percent,
            load_average_1m=response.load_average_1m,
            load_average_5m=response.load_average_5m,
            load_average_15m=response.load_average_15m,
            memory_total_bytes=response.memory_total_bytes,
            memory_available_bytes=response.memory_available_bytes,
            memory_usage_percent=response.memory_usage_percent,
            uptime_seconds=response.uptime_seconds,
            temperature_celsius=(
                response.temperature_celsius if response.temperature_available else None
            ),
        )

    def close(self) -> bool:
        closed = False
        if self.stub is not None and self.session_id:
            try:
                response = self.stub.CloseSession(
                    messages.CloseSessionRequest(session_id=self.session_id),
                    timeout=min(self.timeout_seconds, 3.0),
                )
                closed = response.closed
            except grpc.RpcError:
                pass
        if self.channel is not None:
            self.channel.close()
        self.channel = None
        self.stub = None
        self.session_id = ""
        self.endpoint = ""
        return closed

    def __enter__(self) -> "RknnClient":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    @staticmethod
    def _rpc_error(operation: str, error: grpc.RpcError) -> AcceleratorError:
        code = error.code().name if error.code() is not None else "UNKNOWN"
        detail = error.details() or str(error)
        return AcceleratorError(operation, detail, code)