import json
import socket
import sys
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "client"))

from rknn_client import RknnClient


def main() -> None:
    responder = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    responder.bind(("127.0.0.1", 0))
    port = responder.getsockname()[1]

    def respond() -> None:
        request, address = responder.recvfrom(1024)
        assert request == b"LUCKFOX_RKNN_DISCOVER"
        payload = {
            "service": "luckfox-rknn",
            "hostname": "test-pico",
            "board_model": "Luckfox Pico Pro Max",
            "soc": "Rockchip RV1106",
            "architecture": "armv7l",
            "grpc_port": 50051,
            "model_name": "yolov5",
            "task": "object_detection",
            "busy": True,
            "password_required": True,
        }
        response = json.dumps(payload).encode("utf-8")
        responder.sendto(response, address)
        responder.sendto(response, address)

    worker = threading.Thread(target=respond)
    worker.start()
    try:
        results = RknnClient.discover(
            timeout_seconds=0.5,
            discovery_port=port,
            targets=("127.0.0.1",),
        )
    finally:
        worker.join(timeout=1.0)
        responder.close()

    assert len(results) == 1
    accelerator = results[0]
    assert accelerator.endpoint == "127.0.0.1:50051"
    assert accelerator.hostname == "test-pico"
    assert accelerator.model_name == "yolov5"
    assert accelerator.busy is True
    assert accelerator.password_required is True
    print("client_discovery_test passed")


if __name__ == "__main__":
    main()