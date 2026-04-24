"""
Camera UI Application  –  Marine Vision System
================================================
Hardware : Intel OAK-D (via DepthAI)
Left panel : Control buttons
              • Record Video
              • Length Measurement  → Length_measurement_Iceberg/final_product/main.py
              • Crab Detection      → SIFT-based live detection
              • Frequency Analysis  → Frequency_measurements/frequency_measurement.py
              • Iceberg Tracker     → Iceberg.html embedded via pywebview
Right panel : Live OAK-D RGB feed
"""

import tkinter as tk
from tkinter import ttk, messagebox
import cv2
from PIL import Image, ImageTk
import threading
import datetime
import os
import subprocess
import sys
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

# ── Length Measurement (Full Version) ────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent / "Length_measurement_Iceberg" / "final_product"))
try:
    from modules.pipe_length_measurement import PipeLengthMeasurement, MeasurementState, MeasurementMode
    PIPE_MEASUREMENT_AVAILABLE = True
except ImportError:
    PIPE_MEASUREMENT_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
class CameraUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Marine Vision System")
        self.root.configure(bg="#1a1a2e")
        self.root.resizable(True, True)

        # ── State ──────────────────────────────────────────────────────────
        self.pipeline      = None   # DepthAI pipeline
        self.q_rgb         = None   # output queue from OAK-D
        self.q_depth       = None   # ✅ depth queue from OAK-D
        self.latest_depth  = None   # ✅ latest depth frame

        # Fallback OpenCV cap (used when OAK-D is not available)
        self.cap           = None

        self.is_running    = False
        self.is_recording  = False
        self.video_writer  = None
        self.current_frame = None
        self.camera_thread = None

        # ── Crab Detection ─────────────────────────────────────────────────
        self.crab_detection_enabled = False
        self.sift = cv2.SIFT_create()
        self.flann = cv2.FlannBasedMatcher(
            dict(algorithm=1, trees=5),
            dict(checks=50)
        )
        self.ref_features = self._load_reference_images()
        self.detected_crabs = []

        # ── Length Measurement (FULL VERSION - Burst + Live) ──────────────
        self.pipe_measurement = None
        if PIPE_MEASUREMENT_AVAILABLE:
            try:
                self.pipe_measurement = PipeLengthMeasurement(num_frames=30)
                if not self.pipe_measurement.camera_available:
                    print("⚠ Measurement camera initialization failed (will use main camera)")
            except Exception as e:
                print(f"✗ Failed to initialize PipeLengthMeasurement: {e}")
                self.pipe_measurement = None

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
        left = tk.Frame(main, bg="#16213e", width=220, relief=tk.FLAT, bd=0)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        left.pack_propagate(False)

        tk.Label(left, text="🦀 Marine Vision",
                 font=("Helvetica", 15, "bold"),
                 bg="#16213e", fg="#e94560").pack(pady=(20, 4))
        tk.Label(left, text="Control Panel",
                 font=("Helvetica", 10),
                 bg="#16213e", fg="#a8a8b3").pack(pady=(0, 24))

        ttk.Separator(left, orient="horizontal").pack(fill=tk.X, padx=16, pady=4)

        # Camera status indicator
        self.status_frame = tk.Frame(left, bg="#16213e")
        self.status_frame.pack(pady=(12, 4))
        self.status_dot = tk.Label(self.status_frame, text="●",
                                   font=("Helvetica", 12),
                                   bg="#16213e", fg="#ff4444")
        self.status_dot.pack(side=tk.LEFT)
        self.status_label = tk.Label(self.status_frame, text=" Camera Off",
                                     font=("Helvetica", 9),
                                     bg="#16213e", fg="#a8a8b3")
        self.status_label.pack(side=tk.LEFT)

        # OAK-D badge
        oak_color = "#00b894" if DEPTHAI_AVAILABLE else "#636e72"
        oak_text  = "OAK-D Connected" if DEPTHAI_AVAILABLE else "OAK-D Not Found"
        tk.Label(left, text=f"  {oak_text}  ",
                 font=("Helvetica", 8, "bold"),
                 bg=oak_color, fg="white").pack(pady=(4, 0))

        ttk.Separator(left, orient="horizontal").pack(fill=tk.X, padx=16, pady=12)

        # ── RECORD BUTTON ─────────────────────────────────────────────────
        self._make_button(
            parent=left, icon="⏺", label="Record Video",
            sublabel="Start / Stop recording",
            color="#e94560", hover="#c73652",
            command=self._toggle_record, attr="record_btn"
        )

        # ── LENGTH MEASUREMENT ────────────────────────────────────────────
        self._make_button(
            parent=left, icon="📏", label="Length Measurement",
            sublabel="Iceberg measurement (OAK-D)",
            color="#0f3460", hover="#1a5276",
            command=self._run_length_measurement, attr="length_btn"
        )

        # ── CRAB DETECTION ────────────────────────────────────────────────
        self._make_button(
            parent=left, icon="🦀", label="Crab Detection",
            sublabel="Toggle SIFT detection (live)",
            color="#533483", hover="#6a44a8",
            command=self._toggle_crab_detection, attr="crab_btn"
        )

        # ── FREQUENCY ANALYSIS ────────────────────────────────────────────
        self._make_button(
            parent=left, icon="📊", label="Frequency Analysis",
            sublabel="Species % frequency calculator",
            color="#1a6b4a", hover="#22895f",
            command=self._run_frequency_analysis, attr="freq_btn"
        )

        # ── ICEBERG TRACKER ───────────────────────────────────────────────
        self._make_button(
            parent=left, icon="🧊", label="Iceberg Tracker",
            sublabel="Threat assessment (HTML)",
            color="#1a3a5c", hover="#1e4d7a",
            command=self._open_iceberg, attr="iceberg_btn"
        )

        ttk.Separator(left, orient="horizontal").pack(fill=tk.X, padx=16, pady=16)

        # Recording timer
        self.timer_label = tk.Label(left, text="",
                                    font=("Courier", 11, "bold"),
                                    bg="#16213e", fg="#e94560")
        self.timer_label.pack()

        # ── RIGHT PANEL (camera feed) ──────────────────────────────────────
        right = tk.Frame(main, bg="#0f0f1a", relief=tk.FLAT)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        cam_header = tk.Frame(right, bg="#16213e", height=36)
        cam_header.pack(fill=tk.X)
        cam_header.pack_propagate(False)
        hw_tag = "OAK-D" if DEPTHAI_AVAILABLE else "Webcam (fallback)"
        tk.Label(cam_header, text=f"  📷  Live Camera Feed  [{hw_tag}]",
                 font=("Helvetica", 10, "bold"),
                 bg="#16213e", fg="#e2e2e2").pack(side=tk.LEFT, pady=6)

        self.rec_badge = tk.Label(cam_header, text="  ● REC  ",
                                  font=("Helvetica", 9, "bold"),
                                  bg="#e94560", fg="white")

        self.canvas = tk.Canvas(right, bg="#0a0a14", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.canvas.bind("<Button-1>", self._on_canvas_click)  # ✅ Add measurement point clicking
        self._show_placeholder()

    # ──────────────────────────────────────────────────────────────────────────
    def _make_button(self, parent, icon, label, sublabel,
                     color, hover, command, attr):
        frame = tk.Frame(parent, bg=color, cursor="hand2")
        frame.pack(fill=tk.X, padx=16, pady=6)
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
    #  CAMERA – OAK-D via DepthAI v3 (falls back to OpenCV webcam)
    # ══════════════════════════════════════════════════════════════════════════

    def _start_camera(self):
        if DEPTHAI_AVAILABLE:
            self._start_oakd()
        else:
            self._start_opencv_fallback()

    # ── OAK-D (DepthAI v3 API) ───────────────────────────────────────────────
    def _start_oakd(self):
        try:
            self.pipeline = dai.Pipeline()

            cam = self.pipeline.create(dai.node.Camera)
            cam.build()  # ✅ required before requestOutput in v3
            preview_out = cam.requestOutput((640, 480), dai.ImgFrame.Type.BGR888p)

            # ✅ v3: queue created on the output object, no XLinkOut node needed
            self.q_rgb = preview_out.createOutputQueue(maxSize=4, blocking=False)

            # ✅ Add stereo depth for measurement
            try:
                stereo = self.pipeline.create(dai.node.StereoDepth)
                stereo.build(autoCreateCameras=True, size=(640, 480))
                depth_out = stereo.depth
                if depth_out:
                    self.q_depth = depth_out.createOutputQueue(maxSize=4, blocking=False)
                    print("✓ Depth stream enabled for measurements")
            except Exception as e:
                print(f"⚠ Depth not available: {e} (measurements will be in pixels)")
                self.q_depth = None

            self.pipeline.start()
            self.is_running = True
            self.status_dot.config(fg="#00ff88")
            self.status_label.config(text=" OAK-D Live")
            self.camera_thread = threading.Thread(
                target=self._feed_loop_oakd, daemon=True)
            self.camera_thread.start()
        except Exception as exc:
            print(f"OAK-D failed: {exc}, falling back to webcam...")
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
                
                # ✅ Get depth if available
                depth_frame = None
                if self.q_depth:
                    try:
                        in_depth = self.q_depth.get()
                        if in_depth is not None:
                            depth_frame = in_depth.getFrame().astype(np.float32) / 1000.0
                            self.latest_depth = depth_frame.copy()
                    except:
                        pass
                
                # Feed frames to PipeLengthMeasurement engine if available
                if self.pipe_measurement and self.pipe_measurement.camera_available:
                    if self.pipe_measurement.measurement_mode == MeasurementMode.LIVE_CONTINUOUS:
                        # Update engine's latest frames
                        self.pipe_measurement.latest_color = frame.copy()
                        self.pipe_measurement.latest_depth = depth_frame
                        
                        # Process live measurement if enabled
                        if self.pipe_measurement.live_is_measuring and depth_frame is not None:
                            result = self.pipe_measurement.process_live_continuous_measurement(depth_frame)
                            if not result.get('invalid', False):
                                print(f"✓ Measurement: {result['pipe_length']*100:.2f} cm")
                    
                    elif self.pipe_measurement.measurement_mode == MeasurementMode.BURST_CAPTURE:
                        # Store frames during burst capture
                        if self.pipe_measurement.state == MeasurementState.CAPTURING:
                            self.pipe_measurement.capture_burst_frame(frame, depth_frame)
                
                self._process_frame(frame)
            except Exception as e:
                print(f"OAK-D feed error: {e}")
                break

    # ── OpenCV fallback ───────────────────────────────────────────────────────
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
            self._process_frame(frame)

    # ── Shared frame handler ──────────────────────────────────────────────────
    def _process_frame(self, frame):
        self.current_frame = frame.copy()

        if self.crab_detection_enabled:
            frame, self.detected_crabs = self._detect_crabs(frame)

        # ✅ Apply measurement overlay if enabled
        if self.measurement_enabled:
            frame = self._apply_measurement_overlay(frame)

        if self.is_recording and self.video_writer:
            self.video_writer.write(frame)

        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img   = Image.fromarray(rgb)
        cw    = max(self.canvas.winfo_width(), 640)
        ch    = max(self.canvas.winfo_height(), 480)
        self.canvas_width = cw  # ✅ Store for click coordinate mapping
        self.canvas_height = ch
        img   = img.resize((cw, ch), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        self.canvas.after(0, self._update_canvas, photo)

    def _update_canvas(self, photo):
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=photo)
        self.canvas._photo = photo

    def _show_placeholder(self, msg="Initializing camera…"):
        self.canvas.delete("all")
        self.canvas.create_text(320, 240, text=msg,
                                fill="#444466", font=("Helvetica", 16))

    # ══════════════════════════════════════════════════════════════════════════
    #  BUTTON CALLBACKS
    # ══════════════════════════════════════════════════════════════════════════

    # ── Record ────────────────────────────────────────────────────────────────
    def _toggle_record(self):
        if not self.is_running:
            messagebox.showwarning("No Camera", "Camera is not active.")
            return

        if not self.is_recording:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename  = f"recording_{timestamp}.avi"
            fourcc    = cv2.VideoWriter_fourcc(*"XVID")
            if self.pipeline:                        # ✅ OAK-D fixed resolution
                h, w = 480, 640
                fps  = 30
            else:
                h   = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                w   = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
            self.video_writer  = cv2.VideoWriter(filename, fourcc, fps, (w, h))
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
            messagebox.showinfo("Recording Saved",
                                "Video saved to current directory.")

    def _update_timer(self):
        if self.is_recording:
            elapsed = datetime.datetime.now() - self.record_start
            s = int(elapsed.total_seconds())
            self.timer_label.config(
                text=f"⏱ {s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}")
            self.root.after(1000, self._update_timer)

    # ── Length Measurement ────────────────────────────────────────────────────
    def _run_length_measurement(self):
        """Toggle length measurement mode (Full: Burst + Live Continuous)"""
        if not self.pipe_measurement or not self.pipe_measurement.camera_available:
            messagebox.showerror("Error", 
                                "❌ Measurement system not initialized.\n"
                                "Please ensure OAK-D camera is connected.")
            return
        
        if self.pipe_measurement.measurement_mode == MeasurementMode.LIVE_CONTINUOUS:
            # Switch to BURST mode
            result = self.pipe_measurement.toggle_measurement_mode()
            msg = "✓ BURST CAPTURE MODE ON\n\nControls:\n  C - Capture frames\n  Click P1, P2 on frozen frame\n  SPACE - Accept\n  N - Skip | B - Back | R - Reset"
            color = "#ff6b9d"
        else:
            # Switch to LIVE mode
            result = self.pipe_measurement.toggle_measurement_mode()
            msg = "✓ LIVE CONTINUOUS MODE ON\n\nClick P1, P2 on camera feed to measure.\nResults accumulate for statistics."
            color = "#1e90ff"
        
        self.length_btn.config(bg=color)
        messagebox.showinfo("Length Measurement Mode", msg)
        print(f"Mode switched: {result.get('message', 'OK')}")

    # ── Crab Detection ────────────────────────────────────────────────────────
    def _toggle_crab_detection(self):
        self.crab_detection_enabled = not self.crab_detection_enabled
        status = "ON (live in feed)" if self.crab_detection_enabled else "OFF"
        color  = "#a755c8" if self.crab_detection_enabled else "#533483"
        self.crab_btn.config(bg=color)
        messagebox.showinfo("Crab Detection", f"Crab detection: {status}")

    def _load_reference_images(self):
        ref_features = {}
        script_dir = os.path.dirname(os.path.abspath(__file__))
        img_path = os.path.join(script_dir, "carcinus-maenas.jpeg")
        try:
            img_ref = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
            if img_ref is None:
                print(f"Warning: Could not load reference image: {img_path}")
                return ref_features
            kp_ref, des_ref = self.sift.detectAndCompute(img_ref, None)
            ref_features["Crab"] = (kp_ref, des_ref, img_ref.shape)
            print(f"Loaded crab reference: {len(kp_ref)} keypoints")
        except Exception as e:
            print(f"Error loading reference image: {e}")
        return ref_features

    def _detect_crabs(self, frame):
        if not self.crab_detection_enabled or not self.ref_features:
            return frame, []
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            kp_target, des_target = self.sift.detectAndCompute(gray, None)
            detected_centers = []

            if des_target is not None and len(des_target) > 2:
                for crab_name, (kp_ref, des_ref, (h_ref, w_ref)) in self.ref_features.items():
                    matches = self.flann.knnMatch(des_ref, des_target, k=2)
                    good = [m for m, n in matches if m.distance < 0.75 * n.distance]

                    if len(good) < 6:
                        continue

                    used_mask = np.zeros(len(kp_target), dtype=bool)

                    for attempt in range(5):
                        available_good = [m for m in good if not used_mask[m.trainIdx]]
                        if len(available_good) < 6:
                            break

                        src_pts = np.float32([kp_ref[m.queryIdx].pt for m in available_good]).reshape(-1, 1, 2)
                        dst_pts = np.float32([kp_target[m.trainIdx].pt for m in available_good]).reshape(-1, 1, 2)

                        M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
                        if M is not None:
                            pts = np.float32([[0, 0], [0, h_ref-1], [w_ref-1, h_ref-1], [w_ref-1, 0]]).reshape(-1, 1, 2)
                            dst = cv2.perspectiveTransform(pts, M)
                            area = cv2.contourArea(np.int32(dst))
                            if 200 < area < 500000:
                                cv2.polylines(frame, [np.int32(dst)], True, (0, 255, 0), 2, cv2.LINE_AA)
                                center_x = int(np.mean(dst[:, 0, 0]))
                                center_y = int(np.mean(dst[:, 0, 1]))
                                detected_centers.append((center_x, center_y))
                                cv2.circle(frame, (center_x, center_y), 5, (0, 0, 255), -1)
                                inlier_indices = np.where(mask.ravel())[0]
                                for idx in inlier_indices:
                                    used_mask[available_good[idx].trainIdx] = True

            if len(detected_centers) > 1:
                proximity_threshold = 150
                for i in range(len(detected_centers)):
                    for j in range(i + 1, len(detected_centers)):
                        p1, p2 = detected_centers[i], detected_centers[j]
                        dist = math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)
                        if dist < proximity_threshold:
                            cv2.line(frame, p1, p2, (255, 255, 0), 2)

            cv2.putText(frame, f"Crabs detected: {len(detected_centers)}",
                        (10, frame.shape[0] - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            return frame, detected_centers

        except Exception as e:
            print(f"Crab detection error: {e}")
            return frame, []

    # ── Length Measurement Overlay ─────────────────────────────────────────────
    def _apply_measurement_overlay(self, frame):
        """Draw measurement overlay using full PipeLengthMeasurement engine"""
        if not self.pipe_measurement or not self.pipe_measurement.camera_available:
            return frame
        
        overlay = frame.copy()
        h, w = frame.shape[:2]
        
        # LIVE CONTINUOUS mode
        if self.pipe_measurement.measurement_mode == MeasurementMode.LIVE_CONTINUOUS:
            if self.pipe_measurement.state == MeasurementState.LIVE:
                points = self.pipe_measurement.live_points
                
                # Draw points
                for i, (x, y) in enumerate(points):
                    cv2.circle(overlay, (x, y), 6, (0, 255, 0), -1)
                    cv2.circle(overlay, (x, y), 9, (255, 255, 255), 2)
                    cv2.putText(overlay, f"P{i+1}", (x+10, y-5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                
                # Draw line and measurement if both points set
                if len(points) == 2:
                    cv2.line(overlay, points[0], points[1], (0, 255, 255), 2)
                    mid_x = (points[0][0] + points[1][0]) // 2
                    mid_y = (points[0][1] + points[1][1]) // 2
                    
                    if self.pipe_measurement.live_pipe_length:
                        dist_m = self.pipe_measurement.live_pipe_length
                        cv2.putText(overlay, f"{dist_m*100:.2f} cm", 
                                   (mid_x - 50, mid_y - 15),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 3)
                
                # Status
                status = f"LIVE MODE | Points: {len(points)}/2 | Measurements: {len(self.pipe_measurement.live_measurements)}"
                cv2.putText(overlay, status, (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
                
                if len(self.pipe_measurement.live_measurements) > 1:
                    avg = np.mean(self.pipe_measurement.live_measurements) * 100
                    std = np.std(self.pipe_measurement.live_measurements) * 100
                    cv2.putText(overlay, f"Avg: {avg:.2f}±{std:.2f} cm", (10, 60),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 200, 100), 2)
        
        # BURST CAPTURE mode
        elif self.pipe_measurement.measurement_mode == MeasurementMode.BURST_CAPTURE:
            if self.pipe_measurement.state == MeasurementState.BURST_ANNOTATING:
                frozen = self.pipe_measurement.frozen_color_frame
                if frozen is not None:
                    overlay = frozen.copy()
                    points = self.pipe_measurement.burst_pending_points
                    
                    for i, (x, y, z) in enumerate(points):
                        cv2.circle(overlay, (x, y), 6, (0, 255, 0), -1)
                        cv2.circle(overlay, (x, y), 9, (255, 255, 255), 2)
                        cv2.putText(overlay, f"P{i+1}", (x+10, y-5),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    
                    if len(points) == 2:
                        cv2.line(overlay, (points[0][0], points[0][1]), 
                                (points[1][0], points[1][1]), (0, 255, 255), 2)
                        mid_x = (points[0][0] + points[1][0]) // 2
                        mid_y = (points[0][1] + points[1][1]) // 2
                        dist = self.pipe_measurement._calculate_distance_between_points(
                            points[0][0], points[0][1], points[0][2],
                            points[1][0], points[1][1], points[1][2]
                        )
                        cv2.putText(overlay, f"{dist*100:.2f} cm", (mid_x - 50, mid_y - 15),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 3)
                    
                    idx = self.pipe_measurement.burst_current_index
                    total = len(self.pipe_measurement.burst_color_frames)
                    cv2.putText(overlay, f"BURST: Frame {idx+1}/{total}", (10, 30),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
        
        return overlay

    def _on_canvas_click(self, event):
        """Handle canvas clicks for measurement point marking"""
        if not self.pipe_measurement or not self.pipe_measurement.camera_available:
            return
        
        x = int(event.x * 640 / self.canvas.winfo_width())
        y = int(event.y * 480 / self.canvas.winfo_height())
        
        pm = self.pipe_measurement
        mode = pm.measurement_mode
        state = pm.state
        
        # LIVE CONTINUOUS mode
        if mode == MeasurementMode.LIVE_CONTINUOUS and state == MeasurementState.LIVE:
            result = pm.mark_point_live_continuous(x, y)
            if result['success']:
                print(f"✓ {result['message']}")
            else:
                print(f"✗ {result}")
        
        # BURST CAPTURE mode - annotation phase
        elif mode == MeasurementMode.BURST_CAPTURE and state == MeasurementState.BURST_ANNOTATING:
            pending = pm.burst_pending_points
            
            if len(pending) == 0:
                result = pm.mark_burst_point(x, y)
                print(f"✓ P1: {result['message']}")
            elif len(pending) == 1:
                result = pm.mark_burst_second_point(x, y)
                print(f"✓ P2: {result['message']}")

    def _calculate_distance_cm(self, x1, y1, x2, y2):
        """Fallback distance calculation (not used with full PipeLengthMeasurement)"""
        pass

    # ── Frequency Analysis ────────────────────────────────────────────────────
    def _run_frequency_analysis(self):
        script_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "Frequency_measurements", "frequency_measurement.py"
        )
        self._launch_script(script_path, "Frequency Analysis")

    # ── Iceberg Tracker ───────────────────────────────────────────────────────
    def _open_iceberg(self):
        html_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "Iceberg.html"
        )
        if not os.path.exists(html_path):
            messagebox.showerror(
                "Iceberg Tracker – Not Found",
                f"Could not locate:\n{html_path}\n\nPlease check the path."
            )
            return

        if not WEBVIEW_AVAILABLE:
            import webbrowser
            webbrowser.open(f"file://{html_path}")
            messagebox.showinfo(
                "Iceberg Tracker",
                "pywebview not installed — opened in your default browser.\n"
                "Install it with:  pip install pywebview"
            )
            return

        def _run_webview():
            self.root.withdraw()
            try:
                win = webview.create_window(
                    title="Iceberg Threat Tracker",
                    url=f"file://{html_path}",
                    width=1200,
                    height=750,
                    resizable=True,
                )
                webview.start()
            except Exception as exc:
                messagebox.showerror("Iceberg Tracker Error", str(exc))
            finally:
                self.root.deiconify()

        self.root.after(50, _run_webview)

    # ── Generic script launcher ───────────────────────────────────────────────
    def _launch_script(self, path, name):
        if not os.path.exists(path):
            messagebox.showerror(
                f"{name} – Not Found",
                f"Could not locate:\n{path}\n\nPlease check the path."
            )
            return
        try:
            subprocess.Popen([sys.executable, path])
            messagebox.showinfo(name, f"{name} module launched!")
        except Exception as exc:
            messagebox.showerror(f"{name} Error", str(exc))

    # ══════════════════════════════════════════════════════════════════════════
    #  CLEANUP
    # ══════════════════════════════════════════════════════════════════════════

    def _on_close(self):
        self.is_running   = False
        self.is_recording = False
        if self.video_writer:
            self.video_writer.release()
        # ✅ v3: stop pipeline instead of device.close()
        if self.pipeline:
            try:
                self.pipeline.stop()
            except Exception:
                pass
        if self.cap:
            self.cap.release()
        self.root.destroy()


# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1000x640")
    root.minsize(780, 520)
    app = CameraUI(root)
    root.mainloop()
    