from __future__ import annotations

import queue
import threading
import tkinter as tk
import time
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Optional

import cv2
from PIL import Image, ImageDraw, ImageTk

from rknn_client import AcceleratorError, RknnClient


class ImageViewer:
    def __init__(self, parent: tk.Tk, image: Image.Image, title: str) -> None:
        self.window = tk.Toplevel(parent)
        self.window.title(title)
        self.window.geometry("1000x760")
        self.window.minsize(640, 480)
        self.image = image.copy()
        self.preview = None
        self.zoom_factor = 1.0

        toolbar = ttk.Frame(self.window, padding=8)
        toolbar.pack(fill=tk.X)
        ttk.Button(toolbar, text="-", width=3, command=lambda: self._change_zoom(1 / 1.2)).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="+", width=3, command=lambda: self._change_zoom(1.2)).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Fit", command=self._fit).pack(side=tk.LEFT)
        ttk.Label(toolbar, text="Mouse wheel to zoom; drag to move", style="Muted.TLabel").pack(side=tk.RIGHT)

        viewport = ttk.Frame(self.window)
        viewport.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(viewport, background="#17212b", highlightthickness=0, cursor="fleur")
        horizontal_scroll = ttk.Scrollbar(viewport, orient=tk.HORIZONTAL, command=self.canvas.xview)
        vertical_scroll = ttk.Scrollbar(viewport, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=horizontal_scroll.set, yscrollcommand=vertical_scroll.set)
        self.canvas.grid(row=0, column=0, sticky=tk.NSEW)
        vertical_scroll.grid(row=0, column=1, sticky=tk.NS)
        horizontal_scroll.grid(row=1, column=0, sticky=tk.EW)
        viewport.rowconfigure(0, weight=1)
        viewport.columnconfigure(0, weight=1)

        self.canvas.bind("<MouseWheel>", self._zoom)
        self.canvas.bind("<Button-4>", self._zoom)
        self.canvas.bind("<Button-5>", self._zoom)
        self.canvas.bind("<ButtonPress-1>", self._start_pan)
        self.canvas.bind("<B1-Motion>", self._pan)
        self.window.after_idle(self._display)

    def _fit(self) -> None:
        self.zoom_factor = 1.0
        self._display()

    def _change_zoom(self, factor: float) -> None:
        self.zoom_factor = min(8.0, max(0.25, self.zoom_factor * factor))
        self._display()

    def _zoom(self, event) -> str:
        zoom_in = event.num == 4 or getattr(event, "delta", 0) > 0
        self._change_zoom(1.15 if zoom_in else 1 / 1.15)
        return "break"

    def _start_pan(self, event) -> None:
        self.canvas.scan_mark(event.x, event.y)

    def _pan(self, event) -> None:
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _display(self) -> None:
        self.window.update_idletasks()
        viewport_width = max(1, self.canvas.winfo_width() - 12)
        viewport_height = max(1, self.canvas.winfo_height() - 12)
        fit_scale = min(viewport_width / self.image.width, viewport_height / self.image.height, 1.0)
        scale = fit_scale * self.zoom_factor
        width = max(1, round(self.image.width * scale))
        height = max(1, round(self.image.height * scale))
        display = self.image.resize((width, height), Image.Resampling.LANCZOS)
        self.preview = ImageTk.PhotoImage(display)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.preview, anchor=tk.NW)
        self.canvas.configure(scrollregion=(0, 0, width, height))


class AcceleratorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Luckfox RKNN Accelerator")
        self.root.geometry("1120x720")
        self.root.minsize(900, 600)
        self.client = RknnClient(timeout_seconds=10.0)
        self.events: queue.Queue = queue.Queue()
        self.video_frames: queue.Queue = queue.Queue(maxsize=1)
        self.inference_frames: queue.Queue = queue.Queue(maxsize=1)
        self.image_path: Optional[Path] = None
        self.source_image: Optional[Image.Image] = None
        self.last_response = None
        self.rendered_image: Optional[Image.Image] = None
        self.preview = None
        self.box_color = "#00a878"
        self.zoom_factor = 1.0
        self.scan_dialog: Optional[tk.Toplevel] = None
        self.scan_results = ()
        self.stream_dialog: Optional[tk.Toplevel] = None
        self.video_stop_event = threading.Event()
        self.video_thread: Optional[threading.Thread] = None
        self.inference_thread: Optional[threading.Thread] = None
        self.video_generation = 0
        self.video_running = False
        self.video_source_label = ""
        self.video_playback_fps = 0.0
        self.video_inference_fps = 0.0

        self.endpoint = tk.StringVar(value="192.168.0.108:50051")
        self.password = tk.StringVar(value="19940724")
        self.model = tk.StringVar(value="yolov5")
        self.score = tk.DoubleVar(value=0.25)
        self.nms = tk.DoubleVar(value=0.45)
        self.status = tk.StringVar(value="Disconnected")
        self.detail = tk.StringVar(value="Select a server endpoint and connect")
        self.timing = tk.StringVar(value="No inference yet")
        self.board_info = tk.StringVar(value="Board: not connected")
        self.model_info = tk.StringVar(value="Model: unavailable")
        self.service_info = tk.StringVar(value="Service: unavailable")
        self.performance_info = tk.StringVar(value="Performance: connect to view")

        self._configure_style()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_exit)
        self.root.after(16, self._poll_events)

    def _configure_style(self) -> None:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 17), foreground="#17212b")
        style.configure("Status.TLabel", font=("Segoe UI Semibold", 10), foreground="#146c43")
        style.configure("Muted.TLabel", foreground="#5b6570")
        style.configure("Treeview", rowheight=28)
        style.configure("TButton", padding=(12, 7))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(outer)
        header.pack(fill=tk.X, pady=(0, 14))
        ttk.Label(header, text="RKNN Network Accelerator", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, textvariable=self.status, style="Status.TLabel").pack(side=tk.RIGHT)

        connection = ttk.LabelFrame(outer, text="Connection", padding=12)
        connection.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(connection, text="IP:Port").grid(row=0, column=0, sticky=tk.W)
        self.endpoint_combo = ttk.Combobox(connection, textvariable=self.endpoint, width=28)
        self.endpoint_combo.grid(row=1, column=0, sticky=tk.EW, padx=(0, 10))
        ttk.Label(connection, text="Model").grid(row=0, column=1, sticky=tk.W)
        ttk.Combobox(connection, textvariable=self.model, values=("yolov5",), state="readonly", width=13).grid(row=1, column=1, padx=(0, 10))
        ttk.Label(connection, text="Password").grid(row=0, column=2, sticky=tk.W)
        ttk.Entry(connection, textvariable=self.password, show="*", width=24).grid(row=1, column=2, sticky=tk.EW, padx=(0, 10))
        self.scan_button = ttk.Button(connection, text="Scan", command=self._scan)
        self.scan_button.grid(row=1, column=3, padx=(0, 8))
        self.connect_button = ttk.Button(connection, text="Connect", command=self._connect)
        self.connect_button.grid(row=1, column=4, padx=(0, 8))
        self.close_button = ttk.Button(connection, text="Close", command=self._close, state=tk.DISABLED)
        self.close_button.grid(row=1, column=5)
        connection.columnconfigure(0, weight=1)
        connection.columnconfigure(2, weight=1)

        information = ttk.LabelFrame(outer, text="Accelerator Information", padding=10)
        information.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(information, textvariable=self.board_info, wraplength=360, justify=tk.LEFT).grid(row=0, column=0, sticky=tk.W, padx=(0, 14))
        ttk.Label(information, textvariable=self.model_info, wraplength=360, justify=tk.LEFT).grid(row=0, column=1, sticky=tk.W, padx=(0, 14))
        ttk.Label(information, textvariable=self.service_info, wraplength=280, justify=tk.LEFT).grid(row=0, column=2, sticky=tk.W)
        ttk.Label(information, textvariable=self.performance_info, justify=tk.LEFT).grid(
            row=1, column=0, columnspan=2, sticky=tk.W, pady=(10, 0)
        )
        self.performance_button = ttk.Button(
            information,
            text="Refresh",
            command=self._refresh_performance,
            state=tk.DISABLED,
        )
        self.performance_button.grid(row=1, column=2, sticky=tk.E, pady=(10, 0))
        information.columnconfigure(0, weight=1)
        information.columnconfigure(1, weight=1)
        information.columnconfigure(2, weight=1)

        body = ttk.Panedwindow(outer, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)
        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=3)
        body.add(right, weight=2)

        preview_frame = ttk.LabelFrame(left, text="Image", padding=10)
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=(0, 8))
        self.canvas = tk.Canvas(preview_frame, background="#eef1f4", highlightthickness=0)
        horizontal_scroll = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        vertical_scroll = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=horizontal_scroll.set, yscrollcommand=vertical_scroll.set)
        self.canvas.grid(row=0, column=0, sticky=tk.NSEW)
        vertical_scroll.grid(row=0, column=1, sticky=tk.NS)
        horizontal_scroll.grid(row=1, column=0, sticky=tk.EW)
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        self.canvas.bind("<MouseWheel>", self._zoom_image)
        self.canvas.bind("<Button-4>", self._zoom_image)
        self.canvas.bind("<Button-5>", self._zoom_image)
        self.canvas.bind("<ButtonPress-1>", self._start_image_pan)
        self.canvas.bind("<B1-Motion>", self._pan_image)
        self.canvas.bind("<Double-1>", self._open_image_viewer)
        self.canvas.configure(cursor="fleur")
        self.canvas.create_text(300, 220, text="Choose a JPEG or PNG image", fill="#68737d", tags="placeholder")

        controls = ttk.Frame(left, padding=(0, 10, 8, 0))
        controls.pack(fill=tk.X)
        self.choose_button = ttk.Button(controls, text="Choose Image", command=self._choose_image)
        self.choose_button.grid(row=0, column=0, padx=(0, 8), sticky=tk.W)
        self.viewer_button = ttk.Button(
            controls,
            text="Open Viewer",
            command=self._open_image_viewer,
            state=tk.DISABLED,
        )
        self.viewer_button.grid(row=0, column=1, sticky=tk.W)
        self.infer_button = ttk.Button(controls, text="Infer", width=12, command=self._infer, state=tk.DISABLED)
        self.infer_button.grid(row=0, column=3, padx=(12, 0), sticky=tk.E)
        controls.columnconfigure(2, weight=1)

        settings = ttk.Frame(controls)
        settings.grid(row=1, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))
        ttk.Label(settings, text="Score").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Spinbox(settings, from_=0.01, to=1.0, increment=0.05, textvariable=self.score, width=6).pack(side=tk.LEFT)
        ttk.Label(settings, text="NMS").pack(side=tk.LEFT, padx=(12, 5))
        ttk.Spinbox(settings, from_=0.01, to=1.0, increment=0.05, textvariable=self.nms, width=6).pack(side=tk.LEFT)
        ttk.Label(settings, text="Box Color").pack(side=tk.LEFT, padx=(12, 5))
        self.color_button = tk.Button(
            settings,
            background=self.box_color,
            activebackground=self.box_color,
            width=3,
            relief=tk.SOLID,
            borderwidth=1,
            command=self._choose_box_color,
        )
        self.color_button.pack(side=tk.LEFT)

        video_controls = ttk.Frame(controls)
        video_controls.grid(row=2, column=0, columnspan=4, sticky=tk.EW, pady=(8, 0))
        self.video_file_button = ttk.Button(
            video_controls, text="Local Video", command=self._choose_video, state=tk.DISABLED
        )
        self.video_file_button.pack(side=tk.LEFT)
        self.camera_button = ttk.Button(
            video_controls, text="Camera", command=self._start_camera, state=tk.DISABLED
        )
        self.camera_button.pack(side=tk.LEFT, padx=(8, 0))
        self.stream_button = ttk.Button(
            video_controls, text="RTSP / Stream", command=self._open_stream_dialog, state=tk.DISABLED
        )
        self.stream_button.pack(side=tk.LEFT, padx=(8, 0))
        self.stop_video_button = ttk.Button(
            video_controls, text="Stop", command=self._stop_video, state=tk.DISABLED
        )
        self.stop_video_button.pack(side=tk.RIGHT)

        result_frame = ttk.LabelFrame(right, text="Detections", padding=10)
        result_frame.pack(fill=tk.BOTH, expand=True)
        columns = ("number", "label", "score", "box")
        self.results = ttk.Treeview(result_frame, columns=columns, show="headings", height=12)
        self.results.heading("number", text="#")
        self.results.heading("label", text="Label")
        self.results.heading("score", text="Score")
        self.results.heading("box", text="Box")
        self.results.column("number", width=42, anchor=tk.CENTER, stretch=False)
        self.results.column("label", width=110)
        self.results.column("score", width=70, anchor=tk.CENTER)
        self.results.column("box", width=170)
        self.results.pack(fill=tk.BOTH, expand=True)
        self.results.bind("<<TreeviewSelect>>", self._select_detection)

        ttk.Label(right, textvariable=self.timing, style="Muted.TLabel").pack(fill=tk.X, pady=(9, 4))
        ttk.Label(right, textvariable=self.detail, wraplength=400, justify=tk.LEFT).pack(fill=tk.X, pady=(0, 8))
        log_frame = ttk.LabelFrame(right, text="Activity", padding=8)
        log_frame.pack(fill=tk.X)
        self.log = tk.Text(log_frame, height=7, state=tk.DISABLED, background="#17212b", foreground="#d7e0e8", insertbackground="white")
        self.log.pack(fill=tk.X)

    def _run_async(self, operation: str, function) -> None:
        def worker() -> None:
            try:
                self.events.put((operation, True, function()))
            except Exception as exc:
                self.events.put((operation, False, exc))

        threading.Thread(target=worker, daemon=True).start()

    def _scan(self) -> None:
        self._open_scan_dialog()
        self._set_busy(True, "Scanning")
        self._write_log("Discover -> UDP broadcast :50052")
        self._run_async("scan", self.client.discover)

    def _open_scan_dialog(self) -> None:
        if self.scan_dialog is not None and self.scan_dialog.winfo_exists():
            self.scan_dialog.destroy()
        dialog = tk.Toplevel(self.root)
        dialog.title("Select RKNN Accelerator")
        dialog.geometry("760x360")
        dialog.minsize(640, 300)
        dialog.transient(self.root)
        dialog.protocol("WM_DELETE_WINDOW", self._close_scan_dialog)
        self.scan_dialog = dialog

        content = ttk.Frame(dialog, padding=14)
        content.pack(fill=tk.BOTH, expand=True)
        self.scan_status = ttk.Label(content, text="Scanning UDP port 50052...")
        self.scan_status.pack(fill=tk.X, pady=(0, 10))
        columns = ("endpoint", "device", "model", "status")
        self.scan_tree = ttk.Treeview(content, columns=columns, show="headings", selectmode="browse")
        self.scan_tree.heading("endpoint", text="Endpoint")
        self.scan_tree.heading("device", text="Device")
        self.scan_tree.heading("model", text="Model")
        self.scan_tree.heading("status", text="Status")
        self.scan_tree.column("endpoint", width=150, stretch=False)
        self.scan_tree.column("device", width=220)
        self.scan_tree.column("model", width=150)
        self.scan_tree.column("status", width=90, anchor=tk.CENTER, stretch=False)
        self.scan_tree.pack(fill=tk.BOTH, expand=True)
        self.scan_tree.bind("<<TreeviewSelect>>", self._update_scan_selection)
        self.scan_tree.bind("<Double-1>", self._connect_selected_accelerator)

        actions = ttk.Frame(content, padding=(0, 10, 0, 0))
        actions.pack(fill=tk.X)
        ttk.Button(actions, text="Cancel", command=self._close_scan_dialog).pack(side=tk.RIGHT)
        self.scan_connect_button = ttk.Button(
            actions,
            text="Connect",
            command=self._connect_selected_accelerator,
            state=tk.DISABLED,
        )
        self.scan_connect_button.pack(side=tk.RIGHT, padx=(0, 8))

    def _close_scan_dialog(self) -> None:
        if self.scan_dialog is not None:
            self.scan_dialog.destroy()
            self.scan_dialog = None

    def _update_scan_selection(self, _event=None) -> None:
        state = tk.NORMAL if self.scan_tree.selection() else tk.DISABLED
        self.scan_connect_button.configure(state=state)

    def _connect_selected_accelerator(self, _event=None) -> None:
        selected_rows = self.scan_tree.selection()
        if not selected_rows:
            return
        selected = self.scan_results[int(selected_rows[0])]
        self.endpoint.set(selected.endpoint)
        if selected.model_name:
            self.model.set(selected.model_name)
        self.board_info.set(
            f"Board: {selected.board_model}\nHost: {selected.hostname} | {selected.soc}\nArchitecture: {selected.architecture}"
        )
        self.model_info.set(f"Model: {selected.model_name} | {selected.task}")
        self.service_info.set(
            f"Endpoint: {selected.endpoint}\nStatus: {'Busy' if selected.busy else 'Available'}\nPassword: required"
        )
        self._close_scan_dialog()
        self._connect()

    def _connect(self) -> None:
        self._set_busy(True, "Connecting")
        endpoint = self.endpoint.get()
        password = self.password.get()
        model = self.model.get()
        self._write_log(f"Connect -> {endpoint}")
        self._run_async("connect", lambda: self.client.connect(endpoint, model, password, "tk-demo"))

    def _close(self) -> None:
        self._stop_video(update_status=False)
        self._set_busy(True, "Closing")
        self._write_log("CloseSession")
        self._run_async("close", self.client.close)

    def _refresh_performance(self) -> None:
        if not self.client.connected:
            return
        self.performance_button.configure(state=tk.DISABLED)
        self.performance_info.set("Performance: loading...")
        self._run_async("performance", self.client.performance)

    def _choose_image(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choose image", filetypes=(("Images", "*.jpg *.jpeg *.png"), ("All files", "*.*"))
        )
        if not selected:
            return
        self._stop_video(update_status=False)
        self.image_path = Path(selected)
        self.source_image = Image.open(self.image_path).convert("RGB")
        self.last_response = None
        for row in self.results.get_children():
            self.results.delete(row)
        self.detail.set(str(self.image_path))
        self._show_image(self.source_image, reset_zoom=True)
        self._update_controls()

    def _choose_video(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choose video",
            filetypes=(
                ("Videos", "*.mp4 *.avi *.mkv *.mov *.m4v *.wmv *.webm"),
                ("All files", "*.*"),
            ),
        )
        if selected:
            self._start_video(selected, Path(selected).name)

    def _start_camera(self) -> None:
        self._start_video(0, "Camera 0")

    def _open_stream_dialog(self) -> None:
        if self.stream_dialog is not None and self.stream_dialog.winfo_exists():
            self.stream_dialog.focus_set()
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Open Network Stream")
        dialog.geometry("620x150")
        dialog.resizable(True, False)
        dialog.transient(self.root)
        self.stream_dialog = dialog
        content = ttk.Frame(dialog, padding=14)
        content.pack(fill=tk.BOTH, expand=True)
        ttk.Label(content, text="RTSP / HTTP URL").pack(anchor=tk.W)
        stream_url = tk.StringVar(value="rtsp://")
        entry = ttk.Entry(content, textvariable=stream_url)
        entry.pack(fill=tk.X, pady=(5, 12))
        entry.focus_set()

        def start_stream() -> None:
            url = stream_url.get().strip()
            if not url or "://" not in url:
                messagebox.showerror("Invalid stream", "Enter a valid RTSP or HTTP URL.", parent=dialog)
                return
            dialog.destroy()
            self.stream_dialog = None
            self._start_video(url, url)

        ttk.Button(content, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)
        ttk.Button(content, text="Open", command=start_stream).pack(side=tk.RIGHT, padx=(0, 8))
        entry.bind("<Return>", lambda _event: start_stream())
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)

    def _start_video(self, source, label: str) -> None:
        if not self.client.connected:
            messagebox.showerror("Not connected", "Connect to an accelerator first.", parent=self.root)
            return
        self._stop_video(update_status=False)
        self.video_generation += 1
        generation = self.video_generation
        stop_event = threading.Event()
        self.video_stop_event = stop_event
        self.video_running = True
        self.video_source_label = label
        self.video_playback_fps = 0.0
        self.video_inference_fps = 0.0
        self._clear_queue(self.video_frames)
        self._clear_queue(self.inference_frames)
        self.image_path = None
        self.source_image = None
        self.last_response = None
        self.zoom_factor = 1.0
        self.status.set("Video")
        self.detail.set(f"Opening {label}")
        self._write_log(f"Video -> {label}")
        self._update_controls()
        score = self.score.get()
        nms = self.nms.get()
        self.video_thread = threading.Thread(
            target=self._video_capture_worker,
            args=(source, label, stop_event, generation),
            daemon=True,
        )
        self.inference_thread = threading.Thread(
            target=self._video_inference_worker,
            args=(label, stop_event, generation, score, nms),
            daemon=True,
        )
        self.video_thread.start()
        self.inference_thread.start()

    def _video_capture_worker(
        self,
        source,
        label: str,
        stop_event: threading.Event,
        generation: int,
    ) -> None:
        capture = None
        try:
            live_source = isinstance(source, int) or (isinstance(source, str) and "://" in source)
            if isinstance(source, str) and "://" in source:
                capture = cv2.VideoCapture(
                    source,
                    cv2.CAP_FFMPEG,
                    [
                        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                        5000,
                        cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                        3000,
                    ],
                )
            else:
                capture = cv2.VideoCapture(source)
            if not capture.isOpened():
                raise RuntimeError(f"cannot open video source: {label}")
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            source_fps = capture.get(cv2.CAP_PROP_FPS)
            if source_fps <= 0 or source_fps > 240:
                source_fps = 30.0
            frame_interval = 1.0 / source_fps
            frame_number = 0
            started_at = time.perf_counter()
            next_frame_at = started_at
            while not stop_event.is_set():
                available, frame = capture.read()
                if not available:
                    break
                if not live_source:
                    delay = next_frame_at - time.perf_counter()
                    if delay > 0 and stop_event.wait(delay):
                        break
                    next_frame_at += frame_interval
                frame_number += 1
                elapsed = max(time.perf_counter() - started_at, 0.001)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self._put_latest(
                    self.video_frames,
                    (generation, Image.fromarray(rgb_frame), frame_number, frame_number / elapsed, label),
                )
                self._put_latest(self.inference_frames, (generation, frame_number, frame))
            if not stop_event.is_set():
                self.events.put(("video_end", True, (generation, label)))
                stop_event.set()
        except Exception as exc:
            if not stop_event.is_set():
                self.events.put(("video_error", False, (generation, exc)))
                stop_event.set()
        finally:
            if capture is not None:
                capture.release()

    def _video_inference_worker(
        self,
        label: str,
        stop_event: threading.Event,
        generation: int,
        score: float,
        nms: float,
    ) -> None:
        inference_count = 0
        started_at = time.perf_counter()
        while not stop_event.is_set():
            try:
                item_generation, frame_number, frame = self.inference_frames.get(timeout=0.1)
            except queue.Empty:
                continue
            if item_generation != generation:
                continue
            try:
                encoded, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if not encoded:
                    continue
                response = self.client.infer_bytes(
                    jpeg.tobytes(),
                    image_encoding="jpeg",
                    score_threshold=score,
                    nms_threshold=nms,
                    timeout_seconds=5.0,
                )
                inference_count += 1
                elapsed = max(time.perf_counter() - started_at, 0.001)
                self.events.put(
                    (
                        "video_inference",
                        True,
                        (generation, response, frame_number, inference_count / elapsed, label),
                    )
                )
            except Exception as exc:
                if not stop_event.is_set():
                    self.events.put(("video_error", False, (generation, exc)))
                return

    @staticmethod
    def _put_latest(target_queue: queue.Queue, item) -> None:
        try:
            target_queue.put_nowait(item)
        except queue.Full:
            try:
                target_queue.get_nowait()
            except queue.Empty:
                pass
            target_queue.put_nowait(item)

    @staticmethod
    def _clear_queue(target_queue: queue.Queue) -> None:
        while True:
            try:
                target_queue.get_nowait()
            except queue.Empty:
                return

    def _stop_video(self, update_status: bool = True) -> None:
        if not self.video_running:
            return
        self.video_stop_event.set()
        self.video_generation += 1
        self.video_running = False
        if update_status:
            self.status.set("Connected" if self.client.connected else "Disconnected")
            self.detail.set("Video stopped")
            self._write_log("Video <- stopped")
        self._update_controls()

    def _choose_box_color(self) -> None:
        _, selected = colorchooser.askcolor(
            color=self.box_color,
            title="Choose detection box color",
            parent=self.root,
        )
        if selected is None:
            return
        self.box_color = selected
        self.color_button.configure(background=selected, activebackground=selected)
        self._redraw_detections()

    def _select_detection(self, _event=None) -> None:
        self._redraw_detections()

    def _open_image_viewer(self, _event=None) -> None:
        if self.rendered_image is None:
            return
        title = self.image_path.name if self.image_path is not None else "Detection Result"
        ImageViewer(self.root, self.rendered_image, title)

    def _infer(self) -> None:
        if self.image_path is None:
            return
        self._set_busy(True, "Inferencing")
        self._write_log(f"Infer -> {self.image_path.name}")
        path = self.image_path
        score = self.score.get()
        nms = self.nms.get()
        self._run_async("infer", lambda: self.client.infer(path, score, nms))

    def _poll_events(self) -> None:
        try:
            latest_frame = self.video_frames.get_nowait()
            self._handle_video_frame(latest_frame)
        except queue.Empty:
            pass
        try:
            while True:
                operation, success, value = self.events.get_nowait()
                self._handle_event(operation, success, value)
        except queue.Empty:
            pass
        self.root.after(16, self._poll_events)

    def _handle_event(self, operation: str, success: bool, value) -> None:
        if operation == "video_error":
            generation, error = value
            if generation != self.video_generation:
                return
            self.video_running = False
            self.status.set("Error")
            self.detail.set(str(error))
            self._write_log(f"Video <- {error}")
            self._update_controls()
            return
        if operation == "video_end":
            generation, label = value
            if generation != self.video_generation:
                return
            self.video_running = False
            self.status.set("Connected")
            self.detail.set(f"Video finished: {label}")
            self._write_log("Video <- finished")
            self._update_controls()
            return
        if operation == "video_inference":
            generation, response, frame_number, inference_fps, label = value
            if generation != self.video_generation or not self.video_running:
                return
            self.video_inference_fps = inference_fps
            self._render_response(response)
            self._update_video_detail(label, frame_number)
            return
        if not success:
            code = value.code if isinstance(value, AcceleratorError) else "CLIENT"
            if operation == "performance":
                self.performance_info.set(f"Performance unavailable: {value}")
                self.performance_button.configure(
                    state=tk.NORMAL if self.client.connected else tk.DISABLED
                )
                self._write_log(f"performance <- {code}: {value}")
                return
            self.status.set("Error")
            self.detail.set(str(value))
            self._write_log(f"{operation} <- {code}: {value}")
            if operation == "scan" and self.scan_dialog is not None:
                self.scan_status.configure(text=f"Scan failed: {value}")
            self._set_busy(False)
            self._update_controls()
            return

        if operation == "scan":
            self.scan_results = value
            self.endpoint_combo.configure(values=tuple(item.endpoint for item in value))
            if not value:
                self.status.set("Disconnected")
                self.detail.set("No accelerator found. Check UDP 50052 and Windows firewall.")
                self._write_log("Discover <- no accelerators")
                if self.scan_dialog is not None:
                    self.scan_status.configure(text="No accelerator found. Check UDP 50052 and Windows firewall.")
            else:
                self.status.set("Discovered")
                self.detail.set(f"Found {len(value)} accelerator(s)")
                self._write_log(f"Discover <- {len(value)} accelerator(s)")
                if self.scan_dialog is not None:
                    self.scan_status.configure(text=f"Found {len(value)} accelerator(s). Select one to connect.")
                    for index, accelerator in enumerate(value):
                        self.scan_tree.insert(
                            "",
                            tk.END,
                            iid=str(index),
                            values=(
                                accelerator.endpoint,
                                f"{accelerator.hostname} | {accelerator.board_model}",
                                accelerator.model_name,
                                "Busy" if accelerator.busy else "Available",
                            ),
                        )
                    self.scan_tree.selection_set("0")
                    self.scan_tree.focus("0")
        elif operation == "connect":
            self.status.set("Connected")
            model = value.models[0] if value.models else None
            self.board_info.set(
                f"Board: {value.board_model}\nHost: {value.hostname} | {value.soc}\nSystem: {value.operating_system} ({value.architecture})"
            )
            if model is not None:
                self.model_info.set(
                    f"Model: {model.name} | {model.task}\nInput: {model.input_width} x {model.input_height} {model.tensor_layout}\nQuantization: {model.quantization} | {model.file_size_bytes / (1024 * 1024):.1f} MiB"
                )
            self.service_info.set(
                f"Endpoint: {value.endpoint}\nAccess: {'Exclusive (1 client)' if value.exclusive_access else 'Shared'}"
            )
            self.detail.set(f"Session timeout {value.idle_timeout_seconds}s | Max image {value.max_image_bytes / (1024 * 1024):.1f} MiB")
            self._write_log(f"Connect <- session {value.session_id[:12]}...")
            self._run_async("performance", self.client.performance)
        elif operation == "close":
            self.status.set("Disconnected")
            self.detail.set("Session closed")
            self.service_info.set("Service: disconnected")
            self.performance_info.set("Performance: connect to view")
            self._write_log(f"CloseSession <- closed={value}")
        elif operation == "performance":
            used_memory = value.memory_total_bytes - value.memory_available_bytes
            temperature = (
                f"{value.temperature_celsius:.1f} C"
                if value.temperature_celsius is not None else "unavailable"
            )
            self.performance_info.set(
                f"CPU: {value.cpu_usage_percent:.1f}% ({value.cpu_core_count} cores)  |  "
                f"Load: {value.load_average_1m:.2f} / {value.load_average_5m:.2f} / {value.load_average_15m:.2f}\n"
                f"Memory: {used_memory / (1024 * 1024):.1f} / {value.memory_total_bytes / (1024 * 1024):.1f} MiB "
                f"({value.memory_usage_percent:.1f}%)  |  Temperature: {temperature}  |  "
                f"Uptime: {self._format_uptime(value.uptime_seconds)}"
            )
            self._write_log("Performance <- updated")
        elif operation == "infer":
            self.status.set("Connected")
            self._render_response(value)
            self._write_log(f"Infer <- {len(value.detections)} detections, {value.timing.total_us / 1000:.1f} ms")
        self._set_busy(False)
        self._update_controls()

    def _handle_video_frame(self, item) -> None:
        generation, frame, frame_number, playback_fps, label = item
        if generation != self.video_generation or not self.video_running:
            return
        self.status.set("Video")
        self.video_playback_fps = playback_fps
        self.source_image = frame
        if self.last_response is None:
            self._show_image(frame)
        else:
            self._redraw_detections()
        self._update_video_detail(label, frame_number)

    def _update_video_detail(self, label: str, frame_number: int) -> None:
        self.detail.set(
            f"{label} | Frame {frame_number} | Playback {self.video_playback_fps:.1f} FPS | "
            f"Inference {self.video_inference_fps:.1f} FPS | "
            f"{len(self.last_response.detections) if self.last_response is not None else 0} detections"
        )

    def _render_response(self, response, source_image: Optional[Image.Image] = None) -> None:
        if source_image is not None:
            self.source_image = source_image
        if self.source_image is None:
            return
        self.last_response = response
        for row in self.results.get_children():
            self.results.delete(row)
        for fallback_number, detection in enumerate(response.detections, start=1):
            number = detection.sequence_number or fallback_number
            box = detection.box
            self.results.insert("", tk.END, iid=str(number), values=(
                number,
                detection.label,
                f"{detection.score:.3f}",
                f"{box.left},{box.top} - {box.right},{box.bottom}",
            ))
        self._redraw_detections()
        timing = response.timing
        self.timing.set(
            f"Total {timing.total_us / 1000:.1f} ms | NPU {timing.inference_us / 1000:.1f} ms | Queue {timing.queue_us / 1000:.1f} ms"
        )
        self.detail.set(f"Request {response.request_id} | {response.image_width} x {response.image_height}")

    def _redraw_detections(self) -> None:
        if self.source_image is None or self.last_response is None:
            return
        selected_rows = self.results.selection()
        selected_number = int(selected_rows[0]) if selected_rows else None
        image = self.source_image.copy()
        draw = ImageDraw.Draw(image)
        for fallback_number, detection in enumerate(self.last_response.detections, start=1):
            number = detection.sequence_number or fallback_number
            box = detection.box
            selected = number == selected_number
            outline_color = "#e53935" if selected else self.box_color
            width = 7 if selected else 3
            draw.rectangle(
                (box.left, box.top, box.right, box.bottom),
                outline=outline_color,
                width=width,
            )
            label = f"#{number} {detection.label} {detection.score:.2f}"
            label_left = box.left
            label_top = box.top - 16 if box.top >= 16 else box.top
            text_bounds = draw.textbbox((label_left + 3, label_top + 2), label)
            draw.rectangle(
                (label_left, label_top, text_bounds[2] + 3, text_bounds[3] + 2),
                fill=outline_color,
            )
            draw.text(
                (label_left + 3, label_top + 2),
                label,
                fill=self._contrast_color(outline_color),
            )
        self._show_image(image)

    @staticmethod
    def _contrast_color(color: str) -> str:
        red = int(color[1:3], 16)
        green = int(color[3:5], 16)
        blue = int(color[5:7], 16)
        return "#17212b" if red * 299 + green * 587 + blue * 114 > 150000 else "#ffffff"

    @staticmethod
    def _format_uptime(seconds: int) -> str:
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes = remainder // 60
        return f"{days}d {hours:02d}h {minutes:02d}m"

    def _show_image(self, image: Image.Image, reset_zoom: bool = False) -> None:
        self.rendered_image = image
        if reset_zoom:
            self.zoom_factor = 1.0
        self._display_canvas_image()

    def _display_canvas_image(self) -> None:
        if self.rendered_image is None:
            return
        self.root.update_idletasks()
        viewport_width = max(1, self.canvas.winfo_width() - 12)
        viewport_height = max(1, self.canvas.winfo_height() - 12)
        base_scale = min(
            viewport_width / self.rendered_image.width,
            viewport_height / self.rendered_image.height,
            1.0,
        )
        scale = base_scale * self.zoom_factor
        width = max(1, round(self.rendered_image.width * scale))
        height = max(1, round(self.rendered_image.height * scale))
        display = self.rendered_image.resize((width, height), Image.Resampling.LANCZOS)
        self.preview = ImageTk.PhotoImage(display)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.preview, anchor=tk.NW)
        self.canvas.configure(scrollregion=(0, 0, width, height))

    def _zoom_image(self, event) -> str:
        if self.rendered_image is None:
            return "break"
        zoom_in = event.num == 4 or getattr(event, "delta", 0) > 0
        factor = 1.15 if zoom_in else 1 / 1.15
        new_zoom = min(6.0, max(0.5, self.zoom_factor * factor))
        if new_zoom == self.zoom_factor:
            return "break"

        old_width = max(1, int(self.canvas.cget("scrollregion").split()[2]))
        old_height = max(1, int(self.canvas.cget("scrollregion").split()[3]))
        image_x = self.canvas.canvasx(event.x) / old_width
        image_y = self.canvas.canvasy(event.y) / old_height
        self.zoom_factor = new_zoom
        self._display_canvas_image()
        new_region = self.canvas.cget("scrollregion").split()
        new_width = max(1, int(new_region[2]))
        new_height = max(1, int(new_region[3]))
        self.canvas.xview_moveto(max(0.0, (image_x * new_width - event.x) / new_width))
        self.canvas.yview_moveto(max(0.0, (image_y * new_height - event.y) / new_height))
        return "break"

    def _start_image_pan(self, event) -> None:
        self.canvas.scan_mark(event.x, event.y)

    def _pan_image(self, event) -> None:
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _set_busy(self, busy: bool, label: str = "") -> None:
        if busy:
            self.status.set(label)
            self.scan_button.configure(state=tk.DISABLED)
            self.connect_button.configure(state=tk.DISABLED)
            self.close_button.configure(state=tk.DISABLED)
            self.infer_button.configure(state=tk.DISABLED)
        else:
            self._update_controls()

    def _update_controls(self) -> None:
        connected = self.client.connected
        self.scan_button.configure(state=tk.DISABLED if connected else tk.NORMAL)
        self.connect_button.configure(state=tk.DISABLED if connected else tk.NORMAL)
        self.close_button.configure(state=tk.NORMAL if connected else tk.DISABLED)
        self.infer_button.configure(
            state=tk.NORMAL if connected and self.image_path is not None and not self.video_running else tk.DISABLED
        )
        self.viewer_button.configure(state=tk.NORMAL if self.rendered_image is not None else tk.DISABLED)
        self.performance_button.configure(state=tk.NORMAL if connected else tk.DISABLED)
        video_state = tk.NORMAL if connected and not self.video_running else tk.DISABLED
        self.video_file_button.configure(state=video_state)
        self.camera_button.configure(state=video_state)
        self.stream_button.configure(state=video_state)
        self.stop_video_button.configure(state=tk.NORMAL if self.video_running else tk.DISABLED)

    def _write_log(self, message: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, message + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _on_exit(self) -> None:
        self._stop_video(update_status=False)
        self.client.close()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    AcceleratorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()