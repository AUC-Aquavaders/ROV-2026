"""
Camera UI Application  –  Marine Vision System
================================================
Hardware : Intel OAK-D (via DepthAI)
Left panel : Control buttons
              • Record Video
              • Length Measurement  → full PipeLengthMeasurement (burst + live)
              • Crab Detection      → SIFT-based live detection
              • Frequency Analysis  → Frequency_measurements/frequency_measurement.py
              • Iceberg Tracker     → Iceberg.html embedded via pywebview
Right panel : Live OAK-D RGB feed with integrated measurement overlay

Key fix: The GUI owns the *only* OAK-D pipeline.  PipeLengthMeasurement is
imported for its *logic* (state machine, distance math, burst management,
session save) but its internal camera init is intentionally suppressed
(camera_available=False path).  Every captured frame is pushed from the GUI
feed-loop into the measurement engine, so there is no feed conflict.

All display logic that previously lived in main.py / IcebergTrackingSystem is
reproduced here so the full burst+live experience runs inside the Tk canvas.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import cv2
from PIL import Image, ImageTk
import threading
import datetime
import time
import os
import subprocess
import sys
import json
import math
import numpy as np
from pathlib import Path

# ── OAK-D / DepthAI ──────────────────────────────────────────────────────────
try:
    import depthai as dai
    DEPTHAI_AVAILABLE = True
except ImportError:
    DEPTHAI_AVAILABLE = False

# ── pywebview (for embedded Iceberg HTML) ─────────────────────────────────────
try:
    import webview
    WEBVIEW_AVAILABLE = True
except ImportError:
    WEBVIEW_AVAILABLE = False

# ── Length Measurement logic from main.py (no camera init – GUI owns the feed) ─
sys.path.insert(0, str(Path(__file__).parent / "Length_measurement_Iceberg" / "final_product"))
try:
    # Import IcebergTrackingSystem from main.py to use its full logic
    from main import IcebergTrackingSystem, AppState
    from modules.pipe_length_measurement import (
        PipeLengthMeasurement, MeasurementState, MeasurementMode
    )
    from modules.video_overlay import VideoOverlay
    PIPE_MEASUREMENT_AVAILABLE = True
except ImportError as _e:
    PIPE_MEASUREMENT_AVAILABLE = False
    print(f"⚠  Measurement modules not found – measurement disabled: {_e}")


# ─────────────────────────────────────────────────────────────────────────────
# Headless IcebergTrackingSystem - uses main.py logic but GUI provides frames
# ─────────────────────────────────────────────────────────────────────────────
class _GUIIcebergSystem(IcebergTrackingSystem if PIPE_MEASUREMENT_AVAILABLE else object):
    """
    Extended IcebergTrackingSystem that works with GUI-owned camera.
    Overrides camera initialization to work in 'headless' mode where
    the GUI feed-loop pushes frames via push_frames().
    """
    def __init__(self, gui_app, num_frames: int = 30):
        self._gui_app = gui_app  # Reference to CameraUI for frame pushing

        # Initialize parent but suppress its camera initialization
        # by temporarily disabling the camera init in PipeLengthMeasurement
        super().__init__(config_dir="./config")

        # Replace the pipe_measure with a headless version
        # that accepts frames from GUI instead of owning the camera
        self._init_headless_measurement(num_frames)

    def _init_headless_measurement(self, num_frames: int = 30):
        """Initialize measurement in headless mode (GUI provides frames)."""
        import logging, time as _time

        # Create a headless PipeLengthMeasurement instance
        class _HeadlessPipeMeasurement(PipeLengthMeasurement):
            def __init__(self, num_frames: int = 30):
                # Skip parent __init__ which tries to init camera
                self.logger = logging.getLogger(__name__)
                self.num_frames = num_frames
                self.state = MeasurementState.LIVE
                self.measurement_mode = MeasurementMode.LIVE_CONTINUOUS

                self.pipeline = None
                self.color_queue = None
                self.depth_queue = None

                self.frame_count = 0
                self.fps = 0.0
                self.fps_start_time = _time.time()

                self.latest_color = None
                self.latest_depth = None
                self.capture_thread = None
                self.running = True

                # Live-continuous state
                self.live_points = []
                self.live_pipe_length = None
                self.live_measurements = []
                self.live_is_measuring = False

                # Burst state
                self.burst_color_frames = []
                self.burst_depth_frames = []
                self.burst_results = []
                self.burst_current_index = 0
                self.burst_pending_points = []
                self.burst_carry_over_points = []
                self.frozen_color_frame = None
                self.frozen_depth_frame = None

                self.width = 640
                self.height = 480

                # Camera intrinsics for OAK-D 640x480 (must match pipe_length_measurement.py)
                self.fx = 430.0
                self.fy = 430.0
                self.cx = 320.0
                self.cy = 240.0

                # Mark as available so all logic branches run
                self.camera_available = True

            def push_frames(self, color: np.ndarray, depth):
                """Called by the GUI feed-loop every frame."""
                self.latest_color = color
                self.latest_depth = depth
                self.frame_count += 1
                elapsed = _time.time() - self.fps_start_time
                # Reset FPS calculation every 2 seconds for accurate current FPS
                if elapsed > 2.0:
                    self.fps = self.frame_count / elapsed
                    self.frame_count = 0
                    self.fps_start_time = _time.time()
                elif elapsed > 0:
                    self.fps = self.frame_count / elapsed

            def cleanup(self):
                self.running = False

        # Replace the pipe_measure with our headless version
        if self.pipe_measure:
            self.pipe_measure.cleanup()
        self.pipe_measure = _HeadlessPipeMeasurement(num_frames)
        self.logger.info("Headless measurement system initialized (GUI provides frames)")

    def push_frames(self, color: np.ndarray, depth):
        """Push frames from GUI feed-loop into the measurement system."""
        if self.pipe_measure:
            self.pipe_measure.push_frames(color, depth)

            # Auto-capture during burst
            if self.pipe_measure.state == MeasurementState.CAPTURING:
                self.pipe_measure.capture_burst_frame(color, depth)

    @property
    def pm(self):
        """Alias for pipe_measure for compatibility."""
        return self.pipe_measure

    def run(self):
        """Override to prevent main.py from starting its own event loop."""
        # The GUI owns the main loop, so this should not be called
        self.logger.warning("run() should not be called in GUI mode - GUI owns the event loop")

    def cleanup(self):
        """Override cleanup to avoid destroying windows (GUI manages them)."""
        self.logger.info("Cleaning up headless measurement system...")
        if self.pipe_measure:
            self.pipe_measure.cleanup()
        # Don't call cv2.destroyAllWindows() - GUI manages its own windows

def _all_children(widget):
    children = list(widget.winfo_children())
    for child in list(children):
        children.extend(_all_children(child))
    return children


def _recolor(widget, color):
    try:
        widget.config(bg=color)
    except tk.TclError:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Main application
# ─────────────────────────────────────────────────────────────────────────────

class CameraUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Marine Vision System")
        self.root.configure(bg="#1a1a2e")
        self.root.resizable(True, True)

        # ── Camera state ───────────────────────────────────────────────────
        self.pipeline      = None
        self.q_rgb         = None
        self.q_depth       = None
        self.cap           = None          # OpenCV fallback
        self.is_running    = False
        self.current_frame = None          # latest raw BGR frame
        self.latest_depth  = None          # latest depth (metres, float32)
        self.camera_thread = None
        self.frame_count   = 0             # Frame counter for debug logging

        # ── Recording ─────────────────────────────────────────────────────
        self.is_recording  = False
        self.video_writer  = None
        self.record_start  = None

        # ── Crab detection ─────────────────────────────────────────────────
        self.crab_detection_enabled = False
        self.sift  = cv2.SIFT_create()
        self.flann = cv2.FlannBasedMatcher(
            dict(algorithm=1, trees=5), dict(checks=50))
        self.ref_features   = self._load_reference_images()
        self.detected_crabs = []

        # ── Length Measurement (using main.py IcebergTrackingSystem) ─────
        self.measurement_active = False   # True while panel is open
        self.iceberg_system: _GUIIcebergSystem | None = None
        self.pm = None  # Alias to pipe_measure for compatibility

        if PIPE_MEASUREMENT_AVAILABLE:
            try:
                self.iceberg_system = _GUIIcebergSystem(self, num_frames=30)
                self.pm = self.iceberg_system.pm  # Alias for compatibility
                print("✓ IcebergTrackingSystem from main.py ready (GUI headless mode)")
            except Exception as exc:
                print(f"✗ Could not create measurement engine: {exc}")

        # VideoOverlay from main.py for consistent display logic
        self.video_overlay = VideoOverlay() if PIPE_MEASUREMENT_AVAILABLE else None

        # Notification banner (now managed by IcebergTrackingSystem)
        self.save_notification_time = 0.0
        self.save_message           = ""

        # Session persistence path (now from IcebergTrackingSystem)
        if self.iceberg_system:
            self.session_base_path = self.iceberg_system.session_base_path
        else:
            self.session_base_path = Path(__file__).parent / "data" / "sessions"
            self.session_base_path.mkdir(parents=True, exist_ok=True)

        # ── Build UI then start camera ─────────────────────────────────────
        self._build_ui()
        self._start_camera()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ══════════════════════════════════════════════════════════════════════════
    #  UI CONSTRUCTION
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        main = tk.Frame(self.root, bg="#1a1a2e")
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        # ── LEFT PANEL ────────────────────────────────────────────────────
        left = tk.Frame(main, bg="#16213e", width=235, relief=tk.FLAT, bd=0)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        left.pack_propagate(False)

        tk.Label(left, text="🦀 Marine Vision",
                 font=("Helvetica", 15, "bold"),
                 bg="#16213e", fg="#e94560").pack(pady=(20, 4))
        tk.Label(left, text="Control Panel",
                 font=("Helvetica", 10),
                 bg="#16213e", fg="#a8a8b3").pack(pady=(0, 20))

        ttk.Separator(left, orient="horizontal").pack(fill=tk.X, padx=16, pady=4)

        # Camera status
        sf = tk.Frame(left, bg="#16213e")
        sf.pack(pady=(12, 4))
        self.status_dot   = tk.Label(sf, text="●", font=("Helvetica", 12),
                                      bg="#16213e", fg="#ff4444")
        self.status_dot.pack(side=tk.LEFT)
        self.status_label = tk.Label(sf, text=" Camera Off", font=("Helvetica", 9),
                                      bg="#16213e", fg="#a8a8b3")
        self.status_label.pack(side=tk.LEFT)

        oak_color = "#00b894" if DEPTHAI_AVAILABLE else "#636e72"
        oak_text  = "OAK-D Connected" if DEPTHAI_AVAILABLE else "OAK-D Not Found"
        tk.Label(left, text=f"  {oak_text}  ",
                 font=("Helvetica", 8, "bold"),
                 bg=oak_color, fg="white").pack(pady=(4, 0))

        ttk.Separator(left, orient="horizontal").pack(fill=tk.X, padx=16, pady=12)

        # ── BUTTONS ───────────────────────────────────────────────────────
        self._make_button(left, "⏺", "Record Video",
                          "Start / Stop recording",
                          "#e94560", "#c73652",
                          self._toggle_record, "record_btn")

        self._make_button(left, "📏", "Length Measurement",
                          "Burst + Live mode (OAK-D)",
                          "#0f3460", "#1a5276",
                          self._toggle_measurement, "length_btn")

        self._make_button(left, "🦀", "Crab Detection",
                          "Toggle SIFT detection (live)",
                          "#533483", "#6a44a8",
                          self._toggle_crab_detection, "crab_btn")

        self._make_button(left, "📊", "Frequency Analysis",
                          "Species % frequency calculator",
                          "#1a6b4a", "#22895f",
                          self._run_frequency_analysis, "freq_btn")

        self._make_button(left, "🧊", "Iceberg Tracker",
                          "Threat assessment (HTML)",
                          "#1a3a5c", "#1e4d7a",
                          self._open_iceberg, "iceberg_btn")

        ttk.Separator(left, orient="horizontal").pack(fill=tk.X, padx=16, pady=14)

        # Measurement mode badge (shows current sub-mode)
        self.meas_mode_label = tk.Label(
            left, text="", font=("Helvetica", 8, "bold"),
            bg="#16213e", fg="#a8a8b3", wraplength=200, justify=tk.LEFT)
        self.meas_mode_label.pack(padx=12, pady=(0, 4))

        # Keyboard hint (shown when measurement active)
        self.key_hint_label = tk.Label(
            left, text="", font=("Courier", 7),
            bg="#16213e", fg="#555577", wraplength=200, justify=tk.LEFT)
        self.key_hint_label.pack(padx=12, pady=(0, 4))

        # Recording timer
        self.timer_label = tk.Label(left, text="",
                                    font=("Courier", 11, "bold"),
                                    bg="#16213e", fg="#e94560")
        self.timer_label.pack(pady=(6, 0))

        # ── RIGHT PANEL (camera feed) ─────────────────────────────────────
        right = tk.Frame(main, bg="#0f0f1a", relief=tk.FLAT)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        cam_header = tk.Frame(right, bg="#16213e", height=36)
        cam_header.pack(fill=tk.X)
        cam_header.pack_propagate(False)
        hw_tag = "OAK-D" if DEPTHAI_AVAILABLE else "Webcam (fallback)"
        tk.Label(cam_header,
                 text=f"  📷  Live Camera Feed  [{hw_tag}]",
                 font=("Helvetica", 10, "bold"),
                 bg="#16213e", fg="#e2e2e2").pack(side=tk.LEFT, pady=6)

        self.rec_badge = tk.Label(cam_header, text="  ● REC  ",
                                  font=("Helvetica", 9, "bold"),
                                  bg="#e94560", fg="white")

        self.canvas = tk.Canvas(right, bg="#0a0a14", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.canvas.bind("<Button-1>", self._on_canvas_click)

        # Keyboard bindings (measurement shortcuts)
        self.root.bind("<space>",   self._kb_space)
        self.root.bind("<KeyPress-n>", self._kb_n)
        self.root.bind("<KeyPress-b>", self._kb_b)
        self.root.bind("<KeyPress-r>", self._kb_r)
        self.root.bind("<KeyPress-s>", self._kb_s)
        self.root.bind("<KeyPress-c>", self._kb_c)
        self.root.bind("<KeyPress-m>", self._kb_m)

        self._show_placeholder()

    # ── Button factory ────────────────────────────────────────────────────────
    def _make_button(self, parent, icon, label, sublabel,
                     color, hover, command, attr):
        frame = tk.Frame(parent, bg=color, cursor="hand2")
        frame.pack(fill=tk.X, padx=16, pady=5)
        inner = tk.Frame(frame, bg=color, padx=12, pady=10)
        inner.pack(fill=tk.X)
        top = tk.Frame(inner, bg=color)
        top.pack(fill=tk.X)
        tk.Label(top, text=icon, font=("Helvetica", 16),
                 bg=color, fg="white").pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(top, text=label, font=("Helvetica", 11, "bold"),
                 bg=color, fg="white").pack(side=tk.LEFT)
        tk.Label(inner, text=sublabel, font=("Helvetica", 8),
                 bg=color, fg="#cccccc").pack(anchor=tk.W)
        setattr(self, attr, frame)

        def on_enter(e, f=frame, h=hover):
            f.config(bg=h)
            for w in f.winfo_children(): _recolor(w, h)

        def on_leave(e, f=frame, c=color):
            f.config(bg=c)
            for w in f.winfo_children(): _recolor(w, c)

        for widget in [frame] + _all_children(frame):
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
            widget.bind("<Button-1>", lambda e, cmd=command: cmd())

    # ══════════════════════════════════════════════════════════════════════════
    #  CAMERA – OAK-D (DepthAI v3) with OpenCV fallback
    # ══════════════════════════════════════════════════════════════════════════

    def _start_camera(self):
        if DEPTHAI_AVAILABLE:
            self._start_oakd()
        else:
            self._start_opencv_fallback()

    def _start_oakd(self):
        try:
            self.pipeline = dai.Pipeline()

            cam = self.pipeline.create(dai.node.Camera)
            cam.build()
            preview_out = cam.requestOutput((640, 480), dai.ImgFrame.Type.BGR888p)
            self.q_rgb  = preview_out.createOutputQueue(maxSize=4, blocking=False)

            try:
                stereo = self.pipeline.create(dai.node.StereoDepth)
                stereo.build(autoCreateCameras=True, size=(640, 480))
                depth_out = stereo.depth
                if depth_out:
                    self.q_depth = depth_out.createOutputQueue(maxSize=4, blocking=False)
                    print("✓ Depth stream enabled")
            except Exception as exc:
                print(f"⚠  Depth not available: {exc}")
                self.q_depth = None

            self.pipeline.start()
            self.is_running = True
            self.status_dot.config(fg="#00ff88")
            self.status_label.config(text=" OAK-D Live")
            self.camera_thread = threading.Thread(
                target=self._feed_loop_oakd, daemon=True)
            self.camera_thread.start()
        except Exception as exc:
            print(f"OAK-D failed ({exc}), falling back to webcam …")
            self._start_opencv_fallback()

    def _feed_loop_oakd(self):
        while self.is_running:
            try:
                if not self.pipeline.isRunning():
                    break
                in_rgb = self.q_rgb.get()
                if in_rgb is None:
                    continue
                frame = in_rgb.getCvFrame()

                depth_frame = None
                if self.q_depth:
                    try:
                        in_depth = self.q_depth.get()
                        if in_depth is not None:
                            raw_depth = in_depth.getFrame()
                            # DepthAI v3: depth is typically uint16 in mm, convert to float32 meters
                            if raw_depth is not None:
                                if raw_depth.dtype == np.uint16:
                                    depth_frame = raw_depth.astype(np.float32) / 1000.0
                                elif raw_depth.dtype == np.float32:
                                    # Already in meters or needs different scaling
                                    depth_frame = raw_depth
                                else:
                                    depth_frame = raw_depth.astype(np.float32)
                                self.latest_depth = depth_frame.copy()
                                # Debug: log depth reception (first few frames only)
                                if self.frame_count < 5:
                                    print(f"[Depth] Frame {self.frame_count}: shape={depth_frame.shape}, "
                                          f"dtype={raw_depth.dtype}, min={depth_frame.min():.2f}, "
                                          f"max={depth_frame.max():.2f}m")
                    except Exception as exc:
                        if self.frame_count < 5:
                            print(f"[Depth] Error: {exc}")
                self.frame_count += 1

                # ── Push into measurement engine ───────────────────────────
                if self.iceberg_system and self.measurement_active:
                    self.iceberg_system.push_frames(frame, depth_frame)

                self._process_frame(frame)
            except Exception as exc:
                print(f"OAK-D feed error: {exc}")
                break

    def _start_opencv_fallback(self):
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self._show_placeholder("⚠  No camera detected")
            return
        self.is_running = True
        self.status_dot.config(fg="#ffaa00")
        self.status_label.config(text=" Webcam (fallback)")
        self.camera_thread = threading.Thread(
            target=self._feed_loop_opencv, daemon=True)
        self.camera_thread.start()

    def _feed_loop_opencv(self):
        while self.is_running:
            ret, frame = self.cap.read()
            if not ret:
                break
            if self.pm and self.measurement_active:
                self.pm.push_frames(frame, None)
                if self.pm.state == MeasurementState.CAPTURING:
                    self.pm.capture_burst_frame(frame, None)
            self._process_frame(frame)

    # ── Shared frame handler ──────────────────────────────────────────────────
    def _process_frame(self, frame: np.ndarray):
        self.current_frame = frame.copy()

        if self.crab_detection_enabled:
            frame, self.detected_crabs = self._detect_crabs(frame)

        # ── Full measurement overlay (mirrors main.py display logic) ───────
        if self.measurement_active and self.pm:
            frame = self._build_measurement_display(frame)

        # ── Notification banner ────────────────────────────────────────────
        if time.time() < self.save_notification_time and self.save_message:
            h, w = frame.shape[:2]
            box_w = 320
            x1 = (w - box_w) // 2
            cv2.rectangle(frame, (x1, 10), (x1 + box_w, 50), (0, 150, 0), -1)
            cv2.putText(frame, self.save_message, (x1 + 20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        if self.is_recording and self.video_writer:
            self.video_writer.write(frame)

        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img   = Image.fromarray(rgb)
        cw    = max(self.canvas.winfo_width(),  640)
        ch    = max(self.canvas.winfo_height(), 480)
        img   = img.resize((cw, ch), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        self.canvas.after(0, self._update_canvas, photo)

    def _update_canvas(self, photo):
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=photo)
        self.canvas._photo = photo   # keep reference

    def _show_placeholder(self, msg="Initializing camera…"):
        self.canvas.delete("all")
        self.canvas.create_text(320, 240, text=msg,
                                fill="#444466", font=("Helvetica", 16))

    # ══════════════════════════════════════════════════════════════════════════
    #  MEASUREMENT DISPLAY  (full port of main.py rendering logic)
    # ══════════════════════════════════════════════════════════════════════════

    def _build_measurement_display(self, frame: np.ndarray) -> np.ndarray:
        """
        Route to the correct display builder depending on pm.state / pm.mode.
        Mirrors the display logic in IcebergTrackingSystem.run() from main.py.
        """
        pm = self.pm
        if frame is None:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Ensure 640×480
        if frame.shape[:2] != (480, 640):
            frame = cv2.resize(frame, (640, 480))

        state = pm.state
        mode  = pm.measurement_mode

        if mode == MeasurementMode.LIVE_CONTINUOUS:
            return self._display_live_continuous(frame)

        elif mode == MeasurementMode.BURST_CAPTURE:
            if state == MeasurementState.LIVE:
                return self._display_burst_ready(frame)
            elif state == MeasurementState.CAPTURING:
                return self._display_burst_capturing(frame)
            elif state == MeasurementState.BURST_ANNOTATING:
                return self._display_burst_annotating()
            elif state == MeasurementState.BURST_DONE:
                return self._display_burst_done()

        return frame

    # ── Live Continuous display (mirrors _get_live_mode_display) ─────────────
    def _display_live_continuous(self, frame: np.ndarray) -> np.ndarray:
        pm      = self.pm
        display = frame.copy()
        h, w    = display.shape[:2]
        depth   = pm.latest_depth

        fps = pm.get_fps()
        cv2.putText(display, f"FPS: {fps:.1f}", (w - 110, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 255, 0) if fps > 20 else (0, 165, 255), 2)
        cv2.putText(display, "MODE: LIVE", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        # Process live measurement every frame while both points are set
        live_stats = None
        if pm.live_is_measuring and depth is not None:
            live_stats = pm.process_live_continuous_measurement(depth)

        # Semi-transparent stats panel (top-left)
        overlay = display.copy()
        cv2.rectangle(overlay, (10, 50), (290, 285), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, display, 0.3, 0, display)
        cv2.rectangle(display, (10, 50), (290, 285), (0, 255, 0), 2)

        y = 80
        cv2.putText(display, "MEASUREMENT STATS", (20, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
        y += 32

        points = pm.live_points
        if len(points) >= 1:
            x1, y1 = points[0]
            cv2.circle(display, (x1, y1), 5, (0, 255, 0), -1)
            cv2.circle(display, (x1, y1), 8, (255, 255, 255), 1)

        if len(points) >= 2:
            x1, y1 = points[0]
            x2, y2 = points[1]
            cv2.circle(display, (x2, y2), 5, (0, 0, 255), -1)
            cv2.circle(display, (x2, y2), 8, (255, 255, 255), 1)
            cv2.line(display, (x1, y1), (x2, y2), (0, 255, 255), 2)

        if live_stats and not live_stats.get('invalid'):
            cv2.putText(display, f"Length: {live_stats['pipe_length']:.4f} m",
                        (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            y += 25
        elif live_stats and live_stats.get('invalid'):
            cv2.putText(display, "INVALID DEPTH!", (20, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            y += 28

        y += 8
        cv2.line(display, (20, y), (280, y), (80, 80, 80), 1)
        y += 18

        measurements = pm.live_measurements
        cv2.putText(display, f"Frames: {len(measurements)}", (20, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        y += 22

        if measurements:
            avg = np.mean(measurements)
            std = np.std(measurements) if len(measurements) > 1 else 0.0
            cv2.putText(display, f"Avg: {avg:.4f} m", (20, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            y += 22
            cv2.putText(display, f"Std: ±{std:.4f} m", (20, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            y += 22
            stab = 100.0 * (1.0 - min(std / avg, 1.0)) if avg > 0 else 0.0
            cv2.putText(display, f"Stability: {stab:.1f}%", (20, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (0, 255, 0) if stab > 90 else (0, 165, 255), 1)

        # Bottom hint bar
        if not points:
            hint = "Click 2 points to measure  |  M=BURST mode"
        elif len(points) == 1:
            hint = "Click second point"
        elif pm.live_is_measuring:
            hint = "S=Finalize & Save  |  R=Reset"
        else:
            hint = "S=Save  |  R=Reset"
        self._draw_hint(display, hint)

        return display

    # ── Burst ready (waiting for C to capture) ────────────────────────────────
    def _display_burst_ready(self, frame: np.ndarray) -> np.ndarray:
        display = frame.copy()
        fps = self.pm.get_fps()
        cv2.putText(display, f"FPS: {fps:.1f}", (display.shape[1] - 110, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(display, "MODE: BURST", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
        self._draw_hint(display, "C=Capture frames  |  M=Live mode  |  O=Load session")
        return display

    # ── Burst capturing (frame accumulation progress bar) ────────────────────
    def _display_burst_capturing(self, frame: np.ndarray) -> np.ndarray:
        display = frame.copy()
        pm = self.pm
        progress = len(pm.burst_color_frames)
        total    = pm.num_frames
        # Progress bar
        bar_x1, bar_y1 = 10, 10
        bar_w = int((display.shape[1] - 20) * progress / max(total, 1))
        cv2.rectangle(display, (bar_x1, bar_y1),
                      (display.shape[1] - 10, bar_y1 + 30), (40, 40, 40), -1)
        cv2.rectangle(display, (bar_x1, bar_y1),
                      (bar_x1 + bar_w, bar_y1 + 30), (0, 200, 100), -1)
        cv2.putText(display, f"CAPTURING  {progress}/{total}", (20, bar_y1 + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        if progress >= total:
            self._draw_hint(display, "Capture complete – entering annotation mode …")
        return display

    # ── Burst annotation display (mirrors _get_burst_annotation_display) ─────
    def _display_burst_annotating(self) -> np.ndarray:
        pm    = self.pm
        frame = pm.frozen_color_frame
        if frame is None:
            return np.zeros((480, 640, 3), dtype=np.uint8)
        display = frame.copy()
        h, w = display.shape[:2]

        cv2.putText(display, "MODE: BURST", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)

        idx   = pm.burst_current_index
        total = len(pm.burst_color_frames)
        cv2.rectangle(display, (w - 185, 8), (w - 8, 48), (0, 0, 0), -1)
        cv2.putText(display, f"Frame {idx + 1}/{total}", (w - 175, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        cv2.rectangle(display, (8, 58), (155, 98), (0, 0, 0), -1)
        cv2.putText(display, f"Done: {len(pm.burst_results)}", (18, 83),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        pending = pm.burst_pending_points
        carry   = pm.burst_carry_over_points

        if len(pending) >= 1:
            x1, y1 = int(pending[0][0]), int(pending[0][1])
            cv2.circle(display, (x1, y1), 5, (0, 255, 0), -1)
            cv2.circle(display, (x1, y1), 8, (255, 255, 255), 1)
            cv2.putText(display, "P1", (x1 + 10, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        if len(pending) >= 2:
            x1, y1 = int(pending[0][0]), int(pending[0][1])
            x2, y2 = int(pending[1][0]), int(pending[1][1])
            cv2.circle(display, (x2, y2), 5, (0, 0, 255), -1)
            cv2.circle(display, (x2, y2), 8, (255, 255, 255), 1)
            cv2.putText(display, "P2", (x2 + 10, y2 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            cv2.line(display, (x1, y1), (x2, y2), (0, 255, 255), 2)

            dist = pm._calculate_distance_between_points(
                x1, y1, pending[0][2], x2, y2, pending[1][2])
            cv2.rectangle(display, (w // 2 - 85, 58), (w // 2 + 85, 98), (0, 0, 0), -1)
            cv2.putText(display, f"Dist: {dist:.4f} m",
                        (w // 2 - 75, 88),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        elif len(carry) >= 2 and idx > 0:
            # Carry-over preview
            x1, y1 = int(carry[0][0]), int(carry[0][1])
            x2, y2 = int(carry[1][0]), int(carry[1][1])
            for px, py in [(x1, y1), (x2, y2)]:
                cv2.circle(display, (px, py), 5, (0, 200, 100), -1)
                cv2.circle(display, (px, py), 8, (255, 255, 255), 1)
            cv2.line(display, (x1, y1), (x2, y2), (0, 200, 100), 2)
            cv2.rectangle(display, (10, 108), (205, 148), (0, 0, 0), -1)
            cv2.putText(display, "CARRY-OVER READY", (18, 138),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 100), 2)
            dist = pm._calculate_distance_between_points(
                x1, y1, carry[0][2], x2, y2, carry[1][2])
            cv2.rectangle(display, (w // 2 - 85, 58), (w // 2 + 85, 98), (0, 0, 0), -1)
            cv2.putText(display, f"Est: {dist:.4f} m",
                        (w // 2 - 75, 88),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)

        elif idx == 0 and not pending:
            cv2.putText(display, "Click P1 to start", (w // 2 - 120, h // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        # Bottom hint
        if len(pending) >= 2:
            hint = "SPACE=Accept  |  Click=Redraw"
        elif len(carry) >= 2 and idx > 0:
            hint = "SPACE=Accept carry-over  |  Click=Redraw  |  N=Skip  |  B=Back"
        else:
            hint = "N=Skip  |  B=Back"
        self._draw_hint(display, hint, (255, 255, 255))

        return display

    # ── Burst done / summary (mirrors _get_burst_result_display) ─────────────
    def _display_burst_done(self) -> np.ndarray:
        pm    = self.pm
        frame = pm.frozen_color_frame
        if frame is None:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
        display = frame.copy()
        h, w = display.shape[:2]

        summary = pm.get_burst_summary()

        cv2.rectangle(display,
                      (w // 2 - 210, h // 2 - 110),
                      (w // 2 + 210, h // 2 + 110), (0, 0, 0), -1)
        cv2.rectangle(display,
                      (w // 2 - 210, h // 2 - 110),
                      (w // 2 + 210, h // 2 + 110), (0, 255, 0), 3)

        cv2.putText(display, "BURST COMPLETE",
                    (w // 2 - 130, h // 2 - 68),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 255, 0), 2)

        if summary['success']:
            lines = [
                f"Measurements : {summary['num_measurements']}",
                f"Average      : {summary['average_distance']:.4f} m",
                f"Std Dev      : ±{summary['std_distance']:.4f} m",
                f"Min / Max    : {summary['min_distance']:.4f} / {summary['max_distance']:.4f} m",
            ]
            for i, line in enumerate(lines):
                cv2.putText(display, line,
                            (w // 2 - 190, h // 2 - 28 + i * 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                            (0, 255, 255) if i == 1 else (220, 220, 220), 1)
        else:
            cv2.putText(display, "No valid measurements",
                        (w // 2 - 130, h // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        self._draw_hint(display, "S=Save session  |  R=Restart")
        return display

    # ── Shared hint bar ───────────────────────────────────────────────────────
    @staticmethod
    def _draw_hint(frame: np.ndarray, text: str,
                   color=(255, 255, 255)):
        h, w = frame.shape[:2]
        cv2.rectangle(frame, (0, h - 40), (w, h), (0, 0, 0), -1)
        tw = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0][0]
        cv2.putText(frame, text, ((w - tw) // 2, h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    # ══════════════════════════════════════════════════════════════════════════
    #  KEYBOARD BINDINGS
    # ══════════════════════════════════════════════════════════════════════════

    def _kb_space(self, _event=None):
        if not self.measurement_active or not self.pm:
            return
        pm = self.pm
        if pm.state != MeasurementState.BURST_ANNOTATING:
            return

        pending = pm.burst_pending_points
        carry   = pm.burst_carry_over_points

        if len(pending) == 2:
            result = pm.accept_burst_points()
            self._handle_accept_result(result)
        elif len(pending) == 1:
            print("✗ Click P2 first")
        elif len(carry) == 2 and pm.burst_current_index > 0:
            result = pm.accept_carry_over()
            self._handle_accept_result(result)
        else:
            print("✗ Mark P1 and P2 first")

    def _handle_accept_result(self, result):
        if result['success']:
            if result.get('complete'):
                summary = self.pm.get_burst_summary()
                msg = f"All frames annotated! Avg: {summary['average_distance']:.4f} m" \
                      if summary['success'] else "All frames annotated!"
                print(f"✓ {msg}")
                self._update_mode_label()
            else:
                print(f"✓ Frame {result.get('frame_index', 0) + 1} accepted")

    def _kb_n(self, _event=None):
        if not self.measurement_active or not self.pm:
            return
        if self.pm.state == MeasurementState.BURST_ANNOTATING:
            result = self.pm.skip_frame()
            if result.get('complete'):
                print("✓ All frames processed (with skips)")
            else:
                print(f"→ Skipped, frame {result.get('frame_index', 0) + 1}")

    def _kb_b(self, _event=None):
        if not self.measurement_active or not self.pm:
            return
        if self.pm.state == MeasurementState.BURST_ANNOTATING:
            result = self.pm.go_back()
            if result['success']:
                print(f"← Back to frame {result.get('frame_index', 0) + 1}")

    def _kb_r(self, _event=None):
        if not self.measurement_active or not self.pm:
            return
        pm = self.pm
        if pm.measurement_mode == MeasurementMode.LIVE_CONTINUOUS:
            pm.reset_live_continuous()
            print("✓ Live measurement reset")
        else:
            pm.reset_to_live()
            print("✓ Burst reset – back to live preview")
        self._update_mode_label()

    def _kb_s(self, _event=None):
        if not self.measurement_active or not self.pm:
            return
        pm = self.pm
        if pm.measurement_mode == MeasurementMode.LIVE_CONTINUOUS \
                and len(pm.live_points) >= 2:
            if pm.live_is_measuring:
                pm.finalize_live_measurement()
            self._save_live_measurement()
        elif pm.state == MeasurementState.BURST_DONE:
            self._save_burst_results()

    def _kb_c(self, _event=None):
        if not self.measurement_active or not self.pm:
            return
        pm = self.pm
        if pm.measurement_mode == MeasurementMode.BURST_CAPTURE \
                and pm.state == MeasurementState.LIVE:
            result = pm.start_burst_capture()
            if result['success']:
                print(f"📷 {result['message']}")
                self._update_mode_label()

    def _kb_m(self, _event=None):
        if not self.measurement_active or not self.pm:
            return
        result = self.pm.toggle_measurement_mode()
        print(f"↔ {result['message']}")
        self._update_mode_label()

    # ── Canvas click → measurement point ─────────────────────────────────────
    def _on_canvas_click(self, event):
        if not self.measurement_active or not self.pm:
            return

        # Map canvas pixels → 640×480 frame coordinates
        cw = max(self.canvas.winfo_width(),  1)
        ch = max(self.canvas.winfo_height(), 1)
        x  = int(event.x * 640 / cw)
        y  = int(event.y * 480 / ch)

        pm    = self.pm
        mode  = pm.measurement_mode
        state = pm.state

        if mode == MeasurementMode.LIVE_CONTINUOUS and state == MeasurementState.LIVE:
            result = pm.mark_point_live_continuous(x, y)
            if result['success']:
                print(f"✓ {result['message']}")
                if result.get('measuring'):
                    print("  Measuring continuously … S=finalize  R=reset")
            else:
                print(f"✗ {result['message']}")

        elif mode == MeasurementMode.BURST_CAPTURE \
                and state == MeasurementState.BURST_ANNOTATING:
            pending = pm.burst_pending_points
            if len(pending) >= 2:
                print("✗ Already have P1+P2.  Press SPACE to accept.")
                return
            if len(pending) == 1:
                result = pm.mark_burst_second_point(x, y)
            else:
                pm.clear_burst_points()
                result = pm.mark_burst_point(x, y)
            if result['success']:
                print(f"✓ {result['message']}")

    # ══════════════════════════════════════════════════════════════════════════
    #  BUTTON CALLBACKS
    # ══════════════════════════════════════════════════════════════════════════

    # ── Toggle measurement panel ───────────────────────────────────────────────
    def _toggle_measurement(self):
        if not self.pm:
            messagebox.showerror(
                "Measurement Unavailable",
                "PipeLengthMeasurement module not found.\n"
                "Check that Length_measurement_Iceberg/final_product/modules/ exists.")
            return

        # Stop other tasks before toggling measurement
        self._stop_all_tasks(keep_measurement=True)

        self.measurement_active = not self.measurement_active

        if self.measurement_active:
            # Start in LIVE_CONTINUOUS by default
            self.pm.measurement_mode = MeasurementMode.LIVE_CONTINUOUS
            self.pm.state = MeasurementState.LIVE
            self.length_btn.config(bg="#1e90ff")
            self._update_mode_label()
            print("✓ Measurement ACTIVE  –  click 2 points on the feed to measure")
            messagebox.showinfo(
                "Length Measurement",
                "Measurement mode ON.\n\n"
                "Keyboard shortcuts (when canvas focused):\n"
                "  M      – toggle Live ↔ Burst mode\n"
                "  C      – capture burst frames\n"
                "  SPACE  – accept annotation / carry-over\n"
                "  N      – skip frame\n"
                "  B      – go back\n"
                "  S      – save result\n"
                "  R      – reset\n\n"
                "Click on the video feed to mark P1 / P2.")
        else:
            self.pm.reset_live_continuous()
            self.pm.reset_to_live()
            self.length_btn.config(bg="#0f3460")
            self.meas_mode_label.config(text="")
            self.key_hint_label.config(text="")
            print("✓ Measurement OFF")

    def _update_mode_label(self):
        if not self.pm or not self.measurement_active:
            self.meas_mode_label.config(text="")
            self.key_hint_label.config(text="")
            return

        pm    = self.pm
        mode  = pm.measurement_mode
        state = pm.state

        if mode == MeasurementMode.LIVE_CONTINUOUS:
            badge = "● LIVE CONTINUOUS"
            hint  = "Click 2 pts → measure\nS=save  R=reset  M=burst"
        elif state == MeasurementState.LIVE:
            badge = "● BURST – ready"
            hint  = "C=capture  M=live  O=sessions"
        elif state == MeasurementState.CAPTURING:
            n = len(pm.burst_color_frames)
            badge = f"● BURST – capturing ({n}/{pm.num_frames})"
            hint  = "Wait for capture to finish …"
        elif state == MeasurementState.BURST_ANNOTATING:
            badge = f"● BURST – annotating {pm.burst_current_index+1}/{len(pm.burst_color_frames)}"
            hint  = "Click P1,P2  SPACE=accept\nN=skip  B=back"
        elif state == MeasurementState.BURST_DONE:
            badge = "● BURST – done"
            hint  = "S=save  R=restart"
        else:
            badge = ""
            hint  = ""

        self.meas_mode_label.config(text=badge, fg="#00d4ff")
        self.key_hint_label.config(text=hint)

    # ── Record ────────────────────────────────────────────────────────────────
    def _toggle_record(self):
        if not self.is_running:
            messagebox.showwarning("No Camera", "Camera is not active.")
            return

        if not self.is_recording:
            ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"recording_{ts}.avi"
            fourcc   = cv2.VideoWriter_fourcc(*"XVID")
            h, w     = (480, 640) if self.pipeline else (
                int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)))
            fps_val  = 30 if self.pipeline else (self.cap.get(cv2.CAP_PROP_FPS) or 30)
            self.video_writer = cv2.VideoWriter(filename, fourcc, fps_val, (w, h))
            self.is_recording  = True
            self.record_start  = datetime.datetime.now()
            self.rec_badge.pack(side=tk.RIGHT, padx=8, pady=4)
            self._update_timer()
            self.record_btn.config(bg="#c0392b")
        else:
            self.is_recording = False
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None
            self.rec_badge.pack_forget()
            self.timer_label.config(text="")
            self.record_btn.config(bg="#e94560")
            messagebox.showinfo("Recording Saved", "Video saved to current directory.")

    def _update_timer(self):
        if self.is_recording:
            s = int((datetime.datetime.now() - self.record_start).total_seconds())
            self.timer_label.config(
                text=f"⏱ {s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}")
            self.root.after(1000, self._update_timer)

    # ── Crab detection ────────────────────────────────────────────────────────
    def _toggle_crab_detection(self):
        # Stop other tasks before toggling crab detection
        self._stop_all_tasks(keep_crab=True)

        self.crab_detection_enabled = not self.crab_detection_enabled
        status = "ON" if self.crab_detection_enabled else "OFF"
        self.crab_btn.config(bg="#a755c8" if self.crab_detection_enabled else "#533483")
        messagebox.showinfo("Crab Detection", f"Crab detection: {status}")

    def _load_reference_images(self):
        ref = {}
        img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "carcinus-maenas.jpeg")
        try:
            img_ref = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
            if img_ref is None:
                print(f"⚠  Reference image not found: {img_path}")
                return ref
            kp, des = self.sift.detectAndCompute(img_ref, None)
            ref["Crab"] = (kp, des, img_ref.shape)
            print(f"✓ Crab reference loaded: {len(kp)} keypoints")
        except Exception as exc:
            print(f"✗ Reference load error: {exc}")
        return ref

    def _detect_crabs(self, frame):
        if not self.ref_features:
            return frame, []
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            kp_t, des_t = self.sift.detectAndCompute(gray, None)
            centers = []
            if des_t is not None and len(des_t) > 2:
                for name, (kp_r, des_r, (hr, wr)) in self.ref_features.items():
                    matches = self.flann.knnMatch(des_r, des_t, k=2)
                    good = [m for m, n in matches if m.distance < 0.75 * n.distance]
                    if len(good) < 6:
                        continue
                    used = np.zeros(len(kp_t), dtype=bool)
                    for _ in range(5):
                        avail = [m for m in good if not used[m.trainIdx]]
                        if len(avail) < 6:
                            break
                        src = np.float32([kp_r[m.queryIdx].pt for m in avail]).reshape(-1, 1, 2)
                        dst = np.float32([kp_t[m.trainIdx].pt for m in avail]).reshape(-1, 1, 2)
                        M, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
                        if M is not None:
                            pts = np.float32([[0,0],[0,hr-1],[wr-1,hr-1],[wr-1,0]]).reshape(-1,1,2)
                            d = cv2.perspectiveTransform(pts, M)
                            if 200 < cv2.contourArea(np.int32(d)) < 500_000:
                                cv2.polylines(frame, [np.int32(d)], True, (0,255,0), 2)
                                cx = int(np.mean(d[:,0,0]))
                                cy = int(np.mean(d[:,0,1]))
                                centers.append((cx, cy))
                                cv2.circle(frame, (cx, cy), 5, (0,0,255), -1)
                                for idx in np.where(mask.ravel())[0]:
                                    used[avail[idx].trainIdx] = True
            if len(centers) > 1:
                for i in range(len(centers)):
                    for j in range(i+1, len(centers)):
                        if math.hypot(centers[i][0]-centers[j][0],
                                      centers[i][1]-centers[j][1]) < 150:
                            cv2.line(frame, centers[i], centers[j], (255,255,0), 2)
            cv2.putText(frame, f"Crabs: {len(centers)}",
                        (10, frame.shape[0]-20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
            return frame, centers
        except Exception as exc:
            print(f"Crab detection error: {exc}")
            return frame, []

    # ── Frequency Analysis ────────────────────────────────────────────────────
    def _run_frequency_analysis(self):
        # Stop all camera-related tasks before launching external script
        self._stop_all_tasks()

        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "Frequency_measurements", "frequency_measurement.py")
        self._launch_script(path, "Frequency Analysis")

    # ── Iceberg Tracker ───────────────────────────────────────────────────────
    def _open_iceberg(self):
        # Stop all camera-related tasks before opening webview
        self._stop_all_tasks()

        html = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Iceberg.html")
        if not os.path.exists(html):
            messagebox.showerror("Iceberg Tracker – Not Found",
                                 f"Could not locate:\n{html}")
            return
        if not WEBVIEW_AVAILABLE:
            import webbrowser
            webbrowser.open(f"file://{html}")
            messagebox.showinfo("Iceberg Tracker",
                                "pywebview not installed — opened in browser.")
            return

        def _run():
            self.root.withdraw()
            try:
                win = webview.create_window("Iceberg Threat Tracker",
                                            url=f"file://{html}",
                                            width=1200, height=750, resizable=True)
                webview.start()
            except Exception as exc:
                messagebox.showerror("Iceberg Tracker Error", str(exc))
            finally:
                self.root.deiconify()

        self.root.after(50, _run)

    def _launch_script(self, path, name):
        if not os.path.exists(path):
            messagebox.showerror(f"{name} – Not Found",
                                 f"Could not locate:\n{path}")
            return
        try:
            subprocess.Popen([sys.executable, path])
        except Exception as exc:
            messagebox.showerror(f"{name} Error", str(exc))

    # ══════════════════════════════════════════════════════════════════════════
    #  SESSION SAVE / LOAD  (full port from main.py)
    # ══════════════════════════════════════════════════════════════════════════

    def _notify(self, msg: str, duration: float = 2.5):
        self.save_message           = msg
        self.save_notification_time = time.time() + duration

    def _save_live_measurement(self):
        pm = self.pm
        if len(pm.live_points) < 2:
            print("✗ Need 2 points first")
            return
        try:
            ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            d   = self.session_base_path / f"live_{ts}"
            d.mkdir(parents=True, exist_ok=True)
            color, depth = pm.latest_color, pm.latest_depth
            if color is not None:
                cv2.imwrite(str(d / "color.jpg"), color)
            if depth is not None:
                np.save(str(d / "depth.npy"), depth)
            length = pm.live_pipe_length or 0.0
            data = {
                'type': 'live_measurement',
                'pipe_length': float(length),
                'point1': {'x': pm.live_points[0][0], 'y': pm.live_points[0][1]},
                'point2': {'x': pm.live_points[1][0], 'y': pm.live_points[1][1]},
                'timestamp': datetime.datetime.now().isoformat(),
            }
            with open(d / "metadata.json", "w") as f:
                json.dump(data, f, indent=2)
            print(f"✓ Live measurement saved → {d}\n  Distance: {length:.4f} m")
            self._notify("MEASUREMENT SAVED!")
        except Exception as exc:
            print(f"✗ Save failed: {exc}")

    def _save_burst_results(self):
        pm      = self.pm
        summary = pm.get_burst_summary()
        if not summary['success']:
            print("✗ No valid measurements to save")
            return
        try:
            ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            d   = self.session_base_path / f"session_{ts}"
            cd  = d / "color";  cd.mkdir(parents=True, exist_ok=True)
            dd  = d / "depth";  dd.mkdir(parents=True, exist_ok=True)
            for i, (cf, df) in enumerate(
                    zip(pm.burst_color_frames, pm.burst_depth_frames)):
                cv2.imwrite(str(cd / f"frame_{i:03d}.jpg"), cf)
                np.save(str(dd / f"frame_{i:03d}.npy"), df)
            meta = {
                'type':             'burst_session',
                'average_distance': summary['average_distance'],
                'std_distance':     summary['std_distance'],
                'num_measurements': summary['num_measurements'],
                'num_frames':       len(pm.burst_color_frames),
                'distances':        summary['distances'],
                'results': [{'frame_index': r['frame_index'],
                             'distance':    r['distance']}
                            for r in pm.burst_results
                            if r.get('distance') is not None],
                'timestamp':  datetime.datetime.now().isoformat(),
                'session_id': ts,
            }
            with open(d / "metadata.json", "w") as f:
                json.dump(meta, f, indent=2)
            print(f"✓ Session saved → {d}")
            print(f"  Frames: {len(pm.burst_color_frames)} | "
                  f"Avg: {summary['average_distance']:.4f} m")
            self._notify("SESSION SAVED!")
        except Exception as exc:
            print(f"✗ Save failed: {exc}")

    def _load_session(self, session_name: str):
        """Load a saved burst session directly into the annotation state."""
        sp = self.session_base_path / session_name
        cd = sp / "color"
        dd = sp / "depth"
        if not cd.exists() or not dd.exists():
            messagebox.showerror("Load Session", "Invalid session structure.")
            return
        cfiles = sorted(f for f in os.listdir(cd) if f.endswith(".jpg"))
        dfiles = sorted(f for f in os.listdir(dd) if f.endswith(".npy"))
        if not cfiles:
            messagebox.showerror("Load Session", "No frames found.")
            return
        pm = self.pm
        pm.burst_color_frames = [cv2.imread(str(cd / f)) for f in cfiles]
        pm.burst_depth_frames = [np.load(str(dd / f)) for f in dfiles] if dfiles else [None] * len(cfiles)
        pm.burst_current_index     = 0
        pm.burst_results           = []
        pm.burst_pending_points    = []
        pm.burst_carry_over_points = []
        pm.frozen_color_frame = pm.burst_color_frames[0].copy()
        pm.frozen_depth_frame = pm.burst_depth_frames[0].copy() if pm.burst_depth_frames[0] is not None else None
        pm.state            = MeasurementState.BURST_ANNOTATING
        pm.measurement_mode = MeasurementMode.BURST_CAPTURE
        self.measurement_active = True
        self._update_mode_label()
        print(f"✓ Loaded {len(pm.burst_color_frames)} frames from {session_name}")

    # ── O key – session browser (opens a simple Tk dialog) ───────────────────
    def _open_session_browser(self):
        if not self.pm:
            return
        folders = sorted(
            [f for f in os.listdir(self.session_base_path)
             if (self.session_base_path / f).is_dir() and f.startswith("session_")],
            reverse=True)[:9]
        if not folders:
            messagebox.showinfo("Sessions", "No saved sessions found.")
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("Load Session")
        dlg.configure(bg="#16213e")
        dlg.resizable(False, False)
        tk.Label(dlg, text="Select a session to load:",
                 bg="#16213e", fg="white",
                 font=("Helvetica", 11, "bold")).pack(padx=20, pady=12)
        for name in folders:
            meta_p = self.session_base_path / name / "metadata.json"
            label  = name
            if meta_p.exists():
                try:
                    with open(meta_p) as f:
                        m = json.load(f)
                    if "average_distance" in m:
                        label = f"{name}  [avg {m['average_distance']:.4f} m]"
                except Exception:
                    pass
            btn = tk.Button(
                dlg, text=label,
                font=("Courier", 9),
                bg="#0f3460", fg="white", activebackground="#1a5276",
                bd=0, padx=10, pady=6,
                command=lambda n=name, d=dlg: (self._load_session(n), d.destroy()))
            btn.pack(fill=tk.X, padx=20, pady=3)
        tk.Button(dlg, text="Cancel", bg="#333", fg="white", bd=0,
                  command=dlg.destroy).pack(pady=10)

    # bind 'o' to open sessions when in burst mode
    def _maybe_open_sessions(self, _event=None):
        if self.pm and self.measurement_active \
                and self.pm.measurement_mode == MeasurementMode.BURST_CAPTURE \
                and self.pm.state == MeasurementState.LIVE:
            self._open_session_browser()

    # ══════════════════════════════════════════════════════════════════════════
    #  CLEANUP
    # ══════════════════════════════════════════════════════════════════════════

    def _stop_all_tasks(self, keep_measurement=False, keep_crab=False, keep_recording=False):
        """Stop all active tasks to prevent conflicts when starting a new task."""
        # Stop crab detection (unless explicitly keeping)
        if not keep_crab and self.crab_detection_enabled:
            self.crab_detection_enabled = False
            self.crab_btn.config(bg="#533483")

        # Stop measurement (unless explicitly keeping)
        if not keep_measurement and self.measurement_active:
            self.measurement_active = False
            if self.pm:
                self.pm.reset_live_continuous()
                self.pm.reset_to_live()
            self.length_btn.config(bg="#0f3460")
            self.meas_mode_label.config(text="")
            self.key_hint_label.config(text="")

        # Note: Recording is typically kept running as it's independent
        # But can be stopped if needed via keep_recording=False
        if not keep_recording and self.is_recording:
            self._toggle_record()  # Stop recording

    def _on_close(self):
        self.is_running   = False
        self.is_recording = False
        if self.video_writer:
            self.video_writer.release()
        if self.pipeline:
            try:
                self.pipeline.stop()
            except Exception:
                pass
        if self.cap:
            self.cap.release()
        if self.pm:
            self.pm.cleanup()
        self.root.destroy()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1040x660")
    root.minsize(800, 540)
    app = CameraUI(root)
    # Wire up 'o' key after root exists
    root.bind("<KeyPress-o>", app._maybe_open_sessions)
    root.mainloop()