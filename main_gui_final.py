"""
Camera UI Application  –  Marine Vision System
================================================
Hardware : Intel OAK-D (via DepthAI)
Left panel : Control buttons
              • Record Video
              • Length Measurement  → Length_measurement_Iceberg/final_product/main.py
              • Crab Detection      → DISABLED (commented out, OAK-D port pending)
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


# ─────────────────────────────────────────────────────────────────────────────
class CameraUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Marine Vision System")
        self.root.configure(bg="#1a1a2e")
        self.root.resizable(True, True)

        # ── State ──────────────────────────────────────────────────────────
        self.pipeline      = None   # DepthAI pipeline
        self.device        = None   # DepthAI device
        self.q_rgb         = None   # output queue from OAK-D

        # Fallback OpenCV cap (used when OAK-D is not available)
        self.cap           = None

        self.is_running    = False
        self.is_recording  = False
        self.video_writer  = None
        self.current_frame = None
        self.camera_thread = None

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

        # ── CRAB DETECTION  (DISABLED – OAK-D port pending) ───────────────
        # self._make_button(
        #     parent=left, icon="🦀", label="Crab Detection",
        #     sublabel="YOLO detection module",
        #     color="#533483", hover="#6a44a8",
        #     command=self._run_crab_detection, attr="crab_btn"
        # )
        # Placeholder label so the panel doesn't feel empty
        disabled_frame = tk.Frame(left, bg="#2d2d3a", relief=tk.FLAT)
        disabled_frame.pack(fill=tk.X, padx=16, pady=6)
        inner_d = tk.Frame(disabled_frame, bg="#2d2d3a", padx=12, pady=10)
        inner_d.pack(fill=tk.X)
        top_d = tk.Frame(inner_d, bg="#2d2d3a")
        top_d.pack(fill=tk.X)
        tk.Label(top_d, text="🦀", font=("Helvetica", 16),
                 bg="#2d2d3a", fg="#555577").pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(top_d, text="Crab Detection",
                 font=("Helvetica", 11, "bold"),
                 bg="#2d2d3a", fg="#555577").pack(side=tk.LEFT)
        tk.Label(inner_d, text="OAK-D port in progress…",
                 font=("Helvetica", 8),
                 bg="#2d2d3a", fg="#444455").pack(anchor=tk.W)

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
        self._show_placeholder()

    # ──────────────────────────────────────────────────────────────────────────
    def _make_button(self, parent, icon, label, sublabel,
                     color, hover, command, attr):
        """Styled card-button with hover effect."""
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
    #  CAMERA – OAK-D via DepthAI (falls back to OpenCV webcam)
    # ══════════════════════════════════════════════════════════════════════════

    def _start_camera(self):
        if DEPTHAI_AVAILABLE:
            self._start_oakd()
        else:
            self._start_opencv_fallback()

    # ── OAK-D ────────────────────────────────────────────────────────────────
    def _start_oakd(self):
        try:
            self.pipeline = dai.Pipeline()

            cam_rgb = self.pipeline.create(dai.node.ColorCamera)
            cam_rgb.setPreviewSize(640, 480)
            cam_rgb.setInterleaved(False)
            cam_rgb.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
            cam_rgb.setFps(30)

            xout = self.pipeline.create(dai.node.XLinkOut)
            xout.setStreamName("rgb")
            cam_rgb.preview.link(xout.input)

            self.device = dai.Device(self.pipeline)
            self.q_rgb  = self.device.getOutputQueue(name="rgb",
                                                     maxSize=4,
                                                     blocking=False)
            self.is_running = True
            self.status_dot.config(fg="#00ff88")
            self.status_label.config(text=" OAK-D Live")
            self.camera_thread = threading.Thread(
                target=self._feed_loop_oakd, daemon=True)
            self.camera_thread.start()
        except Exception as exc:
            self._show_placeholder(f"⚠  OAK-D error: {exc}")

    def _feed_loop_oakd(self):
        while self.is_running:
            try:
                in_rgb = self.q_rgb.get()
                frame  = in_rgb.getCvFrame()          # BGR numpy array
                self._process_frame(frame)
            except Exception:
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

        if self.is_recording and self.video_writer:
            self.video_writer.write(frame)

        rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img   = Image.fromarray(rgb)
        cw    = max(self.canvas.winfo_width(), 640)
        ch    = max(self.canvas.winfo_height(), 480)
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
            if self.device:                          # OAK-D fixed resolution
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
        script_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "Length_measurement_Iceberg", "final_product", "main.py"
        )
        self._launch_script(script_path, "Length Measurement")

    # ── Crab Detection  ── DISABLED (OAK-D port pending) ─────────────────────
    # def _run_crab_detection(self):
    #     script_path = os.path.join(
    #         os.path.dirname(os.path.abspath(__file__)),
    #         "crab_detecting", "Real_Senses.py"
    #     )
    #     self._launch_script(script_path, "Crab Detection")

    # ── Frequency Analysis ────────────────────────────────────────────────────
    def _run_frequency_analysis(self):
        script_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "Frequency_measurements", "frequency_measurement.py"
        )
        self._launch_script(script_path, "Frequency Analysis")

    # ── Iceberg Tracker (embedded HTML via pywebview) ─────────────────────────
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
            # Graceful fallback: open in default browser
            import webbrowser
            webbrowser.open(f"file://{html_path}")
            messagebox.showinfo(
                "Iceberg Tracker",
                "pywebview not installed — opened in your default browser.\n"
                "Install it with:  pip install pywebview"
            )
            return

        # ── pywebview MUST run on the main thread on macOS.
        # Strategy: hide the Tkinter window, run webview (blocking), then
        # restore Tkinter when the webview window is closed.
        def _run_webview():
            self.root.withdraw()          # hide Tk window while webview is open
            try:
                win = webview.create_window(
                    title="Iceberg Threat Tracker",
                    url=f"file://{html_path}",
                    width=1200,
                    height=750,
                    resizable=True,
                )
                webview.start()           # blocks until all webview windows close
            except Exception as exc:
                messagebox.showerror("Iceberg Tracker Error", str(exc))
            finally:
                self.root.deiconify()     # restore Tk window afterwards

        # Schedule on the main thread via after() so any pending Tk events
        # flush first, then we hand control to webview.
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
        # Release OAK-D device
        if self.device:
            try:
                self.device.close()
            except Exception:
                pass
        # Release fallback OpenCV capture
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