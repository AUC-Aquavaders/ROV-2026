"""
Camera UI Application
Left panel: Control buttons (Record, Length Measurement, Crab Detection)
Right panel: Live camera feed
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


class CameraUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Marine Vision System")
        self.root.configure(bg="#1a1a2e")
        self.root.resizable(True, True)

        # State variables
        self.cap = None
        self.is_running = False
        self.is_recording = False
        self.video_writer = None
        self.current_frame = None
        self.camera_thread = None

        # Build UI
        self._build_ui()

        # Start camera
        self._start_camera()

        # Handle close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # ── Main container ──────────────────────────────────────────────────
        main = tk.Frame(self.root, bg="#1a1a2e")
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        # ── LEFT PANEL (buttons) ─────────────────────────────────────────────
        left = tk.Frame(main, bg="#16213e", width=220,
                        relief=tk.FLAT, bd=0)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        left.pack_propagate(False)

        # Title
        tk.Label(left, text="🦀 Marine Vision",
                 font=("Helvetica", 15, "bold"),
                 bg="#16213e", fg="#e94560").pack(pady=(20, 4))
        tk.Label(left, text="Control Panel",
                 font=("Helvetica", 10),
                 bg="#16213e", fg="#a8a8b3").pack(pady=(0, 24))

        ttk.Separator(left, orient="horizontal").pack(fill=tk.X, padx=16, pady=4)

        # ── Camera status indicator
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

        ttk.Separator(left, orient="horizontal").pack(fill=tk.X, padx=16, pady=12)

        # ── RECORD BUTTON
        self._make_button(
            parent=left,
            icon="⏺",
            label="Record Video",
            sublabel="Start / Stop recording",
            color="#e94560",
            hover="#c73652",
            command=self._toggle_record,
            attr="record_btn"
        )

        # ── LENGTH MEASUREMENT BUTTON
        self._make_button(
            parent=left,
            icon="📏",
            label="Length Measurement",
            sublabel="Iceberg measurement module",
            color="#0f3460",
            hover="#1a5276",
            command=self._run_length_measurement,
            attr="length_btn"
        )

        # ── CRAB DETECTION BUTTON
        self._make_button(
            parent=left,
            icon="🦀",
            label="Crab Detection",
            sublabel="YOLO detection module",
            color="#533483",
            hover="#6a44a8",
            command=self._run_crab_detection,
            attr="crab_btn"
        )

        ttk.Separator(left, orient="horizontal").pack(fill=tk.X, padx=16, pady=16)

        # Recording timer label
        self.timer_label = tk.Label(left, text="",
                                    font=("Courier", 11, "bold"),
                                    bg="#16213e", fg="#e94560")
        self.timer_label.pack()

        # ── RIGHT PANEL (camera feed) ────────────────────────────────────────
        right = tk.Frame(main, bg="#0f0f1a", relief=tk.FLAT)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Camera header
        cam_header = tk.Frame(right, bg="#16213e", height=36)
        cam_header.pack(fill=tk.X)
        cam_header.pack_propagate(False)
        tk.Label(cam_header, text="  📷  Live Camera Feed",
                 font=("Helvetica", 10, "bold"),
                 bg="#16213e", fg="#e2e2e2").pack(side=tk.LEFT, pady=6)

        self.rec_badge = tk.Label(cam_header, text="  ● REC  ",
                                  font=("Helvetica", 9, "bold"),
                                  bg="#e94560", fg="white")
        # (hidden until recording starts)

        # Camera canvas
        self.canvas = tk.Canvas(right, bg="#0a0a14",
                                highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Placeholder text on canvas
        self._show_placeholder()

    def _make_button(self, parent, icon, label, sublabel,
                     color, hover, command, attr):
        """Create a styled card-button."""
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

        # Store reference
        setattr(self, attr, frame)

        # Hover & click bindings for whole frame + children
        def on_enter(e, f=frame, c=color, h=hover):
            f.config(bg=h)
            for w in f.winfo_children():
                _recolor(w, h)

        def on_leave(e, f=frame, c=color):
            f.config(bg=c)
            for w in f.winfo_children():
                _recolor(w, c)

        for widget in [frame] + _all_children(frame):
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
            widget.bind("<Button-1>", lambda e, cmd=command: cmd())

    # ── Camera logic ──────────────────────────────────────────────────────────

    def _start_camera(self):
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self._show_placeholder("⚠  No camera detected")
            return
        self.is_running = True
        self.status_dot.config(fg="#00ff88")
        self.status_label.config(text=" Camera Live")
        self.camera_thread = threading.Thread(target=self._feed_loop, daemon=True)
        self.camera_thread.start()

    def _feed_loop(self):
        while self.is_running:
            ret, frame = self.cap.read()
            if not ret:
                break
            self.current_frame = frame.copy()

            # Write to video if recording
            if self.is_recording and self.video_writer:
                self.video_writer.write(frame)

            # Convert for Tkinter
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)

            # Fit to canvas size
            cw = max(self.canvas.winfo_width(), 640)
            ch = max(self.canvas.winfo_height(), 480)
            img = img.resize((cw, ch), Image.LANCZOS)

            photo = ImageTk.PhotoImage(img)
            self.canvas.after(0, self._update_canvas, photo)

    def _update_canvas(self, photo):
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=photo)
        self.canvas._photo = photo  # prevent GC

    def _show_placeholder(self, msg="Initializing camera…"):
        self.canvas.delete("all")
        self.canvas.create_text(320, 240, text=msg,
                                fill="#444466",
                                font=("Helvetica", 16))

    # ── Button callbacks ──────────────────────────────────────────────────────

    def _toggle_record(self):
        if not self.is_running:
            messagebox.showwarning("No Camera", "Camera is not active.")
            return

        if not self.is_recording:
            # Start recording
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"recording_{timestamp}.avi"
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
            h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
            self.video_writer = cv2.VideoWriter(filename, fourcc, fps, (w, h))
            self.is_recording = True
            self.record_start = datetime.datetime.now()
            self.rec_badge.pack(side=tk.RIGHT, padx=8, pady=4)
            self._update_timer()
            self.record_btn.config(bg="#c0392b")
        else:
            # Stop recording
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

    def _run_length_measurement(self):
        """Launch the Length_measurement_Iceberg module."""
        # Adjust path as needed
        script_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "Length_measurement_Iceberg", "src", "main.py"
        )
        self._launch_script(script_path, "Length Measurement")

    def _run_crab_detection(self):
        """Launch the crab_detecting module."""
        script_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "crab_detecting", "Real_Senses.py"
        )
        self._launch_script(script_path, "Crab Detection")

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
        except Exception as e:
            messagebox.showerror(f"{name} Error", str(e))

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def _on_close(self):
        self.is_running = False
        self.is_recording = False
        if self.video_writer:
            self.video_writer.release()
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
    root.geometry("960x600")
    root.minsize(760, 480)
    app = CameraUI(root)
    root.mainloop()