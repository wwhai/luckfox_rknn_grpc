import queue
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "client"))

from tk_app import AcceleratorApp


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    def infer_bytes(self, image: bytes, **_options):
        assert image.startswith(b"\xff\xd8")
        time.sleep(0.2)
        self.calls += 1
        return SimpleNamespace(detections=())


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_directory:
        video_path = str(Path(temp_directory) / "input.avi")
        writer = cv2.VideoWriter(
            video_path,
            cv2.VideoWriter_fourcc(*"MJPG"),
            20.0,
            (64, 48),
        )
        assert writer.isOpened()
        for value in range(20):
            writer.write(np.full((48, 64, 3), value, dtype=np.uint8))
        writer.release()

        app = object.__new__(AcceleratorApp)
        app.client = FakeClient()
        app.video_frames = queue.Queue(maxsize=1)
        app.inference_frames = queue.Queue(maxsize=1)
        app.events = queue.Queue()
        stop_event = threading.Event()
        capture_thread = threading.Thread(
            target=app._video_capture_worker,
            args=(video_path, "input.avi", stop_event, 7),
        )
        inference_thread = threading.Thread(
            target=app._video_inference_worker,
            args=("input.avi", stop_event, 7, 0.25, 0.45),
        )
        capture_thread.start()
        inference_thread.start()
        capture_thread.join(timeout=3.0)
        inference_thread.join(timeout=3.0)
        assert not capture_thread.is_alive()
        assert not inference_thread.is_alive()

        generation, frame, frame_number, fps, label = app.video_frames.get_nowait()
        assert generation == 7
        assert frame.size == (64, 48)
        assert frame_number == 20
        assert fps >= 15
        assert label == "input.avi"
        assert 2 <= app.client.calls < 10
        events = []
        while not app.events.empty():
            events.append(app.events.get_nowait())
        assert any(operation == "video_inference" for operation, _success, _value in events)
        assert ("video_end", True, (7, "input.avi")) in events
    print("client_video_test passed")


if __name__ == "__main__":
    main()