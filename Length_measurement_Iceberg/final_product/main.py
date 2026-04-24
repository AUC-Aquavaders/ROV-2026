"""
Main Application - ROV Pipe Length Measurement System
Dual-mode: Live Continuous + Burst Capture with carry-over annotation.
Requires: opencv-python, depthai==2.28.0.0, numpy, torch
"""

import cv2
cv2.setNumThreads(4)

import numpy as np
import logging
import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from modules.pipe_length_measurement import PipeLengthMeasurement, MeasurementState, MeasurementMode


class AppState:
    NORMAL = 'normal'
    BROWSING_SESSIONS = 'browsing_sessions'


class IcebergTrackingSystem:
    """Main application with dual measurement modes and session management."""

    def __init__(self, config_dir: str = "./config"):
        self.config_dir = Path(config_dir)

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

        self.logger.info("Initializing Pipe Length Measurement System...")

        try:
            self.pipe_measure = PipeLengthMeasurement()
            if self.pipe_measure.camera_available:
                self.logger.info("Measurement module initialized successfully")
            else:
                self.logger.warning("Camera not available - running in simulation mode")
        except Exception as e:
            self.logger.error(f"Failed to initialize modules: {e}")
            self.pipe_measure = None

        self.running = False
        self.app_state = AppState.NORMAL
        self.session_list = []
        self.session_browser_index = 0
        self.session_base_path = Path(__file__).parent / "data" / "sessions"
        self.session_base_path.mkdir(parents=True, exist_ok=True)
        self.save_notification_time = 0
        self.save_message = ""

    def mouse_callback(self, event: int, x: int, y: int, flags: int, param):
        """Handle mouse clicks based on current mode and state."""
        if event != cv2.EVENT_LBUTTONDOWN:
            return

        state = self.pipe_measure.state
        mode = self.pipe_measure.measurement_mode

        if mode == MeasurementMode.LIVE_CONTINUOUS and state == MeasurementState.LIVE:
            result = self.pipe_measure.mark_point_live_continuous(x, y)
            if result['success']:
                print(f"\u2713 {result['message']}")
                if result.get('measuring'):
                    print("Measuring continuously... Press S to finalize or R to reset")
            else:
                print(f"\u2717 {result['message']}")

        elif mode == MeasurementMode.BURST_CAPTURE:
            if state == MeasurementState.BURST_ANNOTATING:
                pending = self.pipe_measure.burst_pending_points

                if len(pending) >= 2:
                    print("\u2717 Already have P1 and P2. Press SPACE to accept.")
                    return

                if len(pending) == 1:
                    result = self.pipe_measure.mark_burst_second_point(x, y)
                else:
                    self.pipe_measure.clear_burst_points()
                    result = self.pipe_measure.mark_burst_point(x, y)

                if result['success']:
                    print(f"\u2713 {result['message']}")
                else:
                    print(f"\u2717 {result['message']}")

            elif state == MeasurementState.LIVE:
                print("\u2717 Press C to CAPTURE first")

    def _get_fallback_frame(self, width=640, height=480, message=""):
        """Generate a placeholder frame when camera is unavailable."""
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        # Add gradient background
        for i in range(height):
            frame[i, :] = [int(50 + i * 0.05), int(30 + i * 0.03), int(60 + i * 0.04)]
        
        # Add main status box
        cv2.rectangle(frame, (width//2 - 120, height//2 - 80), (width//2 + 120, height//2 + 80), (0, 200, 255), 3)
        
        # Title
        cv2.putText(frame, "CAMERA", (width//2 - 70, height//2 - 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        cv2.putText(frame, "UNAVAILABLE", (width//2 - 90, height//2 - 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
        # Message
        if message:
            cv2.putText(frame, message, (width//2 - 60, height//2 + 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        
        # Instructions
        cv2.putText(frame, "Press Q to Exit", (width//2 - 50, height//2 + 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
        
        return frame

    def run(self):
        """Main application loop."""
        if self.pipe_measure is None:
            self.logger.error("Cannot start - initialization failed")
            return
        
        self.logger.info("=== Starting Pipe Measurement System ===")
        self.running = True

        window_name = 'Pipe Length Measurement'
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 640, 480)
        cv2.setMouseCallback(window_name, self.mouse_callback)

        # Only create depth window if camera is available
        depth_window = None
        if self.pipe_measure.camera_available:
            depth_window = 'Depth Map'
            cv2.namedWindow(depth_window, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(depth_window, 640, 480)

        try:
            while self.running:
                state = self.pipe_measure.state
                mode = self.pipe_measure.measurement_mode

                color_frame, depth_frame = self.pipe_measure.get_frames()

                # If camera is not available, use fallback frame
                if not self.pipe_measure.camera_available:
                    color_frame = self._get_fallback_frame(640, 480, "Check camera connection")
                    depth_frame = None

                if depth_frame is not None and depth_window is not None:
                    depth_colormap = self.pipe_measure.get_depth_colormap(depth_frame)
                    if depth_colormap is not None and depth_colormap.size > 0:
                        # Resize to fit window
                        depth_colormap = cv2.resize(depth_colormap, (640, 480))
                        cv2.imshow(depth_window, depth_colormap)

                if color_frame is None or color_frame.size == 0:
                    # Display fallback if no frame
                    fallback = self._get_fallback_frame(640, 480, "Waiting for frames...")
                    cv2.imshow(window_name, fallback)
                    cv2.waitKey(1)
                    continue

                # Ensure frame is correct size
                if color_frame.shape[:2] != (480, 640):
                    color_frame = cv2.resize(color_frame, (640, 480))

                display_frame = None

                if self.app_state == AppState.BROWSING_SESSIONS:
                    display_frame = self._get_session_browser_display(color_frame)
                    if display_frame is not None and display_frame.size > 0:
                        display_frame = cv2.resize(display_frame, (640, 480))
                        cv2.imshow(window_name, display_frame)
                    key = cv2.waitKey(1) & 0xFF
                    self._handle_session_browser_key(key)
                    continue

                if mode == MeasurementMode.LIVE_CONTINUOUS:
                    display_frame = self._get_live_mode_display(color_frame, depth_frame)

                elif mode == MeasurementMode.BURST_CAPTURE:
                    if state == MeasurementState.CAPTURING:
                        self.pipe_measure.capture_burst_frame(color_frame, depth_frame)
                        display_frame = color_frame.copy()
                        progress = len(self.pipe_measure.burst_color_frames)
                        total = self.pipe_measure.num_frames
                        cv2.rectangle(display_frame, (10, 10), (350, 60), (0, 0, 0), -1)
                        cv2.putText(display_frame, f"CAPTURING: {progress}/{total}", (20, 45),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                        if progress >= total:
                            print(f"\n\u2713 Capture complete! {progress} frames saved.")

                    elif state == MeasurementState.LIVE:
                        display_frame = color_frame.copy()
                        fps = self.pipe_measure.get_fps()
                        cv2.putText(display_frame, f"FPS: {fps:.1f}", (self.pipe_measure.width - 100, 30),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        cv2.putText(display_frame, "MODE: BURST", (10, 30),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
                        self._draw_alert(display_frame, "Press C to CAPTURE | M for LIVE mode", (0, 200, 255))

                    elif state == MeasurementState.BURST_ANNOTATING:
                        display_frame = self._get_burst_annotation_display()

                    elif state == MeasurementState.BURST_DONE:
                        display_frame = self._get_burst_result_display()

                if display_frame is not None and display_frame.size > 0:
                    # Ensure correct size before display
                    if display_frame.shape[:2] != (480, 640):
                        display_frame = cv2.resize(display_frame, (640, 480))
                    self._draw_notification(display_frame)
                    cv2.imshow(window_name, display_frame)
                else:
                    color_copy = color_frame.copy() if color_frame is not None else np.zeros((480, 640, 3), dtype=np.uint8)
                    if color_copy.shape[:2] != (480, 640):
                        color_copy = cv2.resize(color_copy, (640, 480))
                    self._draw_notification(color_copy)
                    cv2.imshow(window_name, color_copy)

                key = cv2.waitKey(1) & 0xFF

                if key == ord('q'):
                    self.running = False

                elif key == ord('m'):
                    result = self.pipe_measure.toggle_measurement_mode()
                    print(f"\n{result['message']}")

                elif key == ord('o'):
                    if mode == MeasurementMode.BURST_CAPTURE and state == MeasurementState.LIVE:
                        self._open_session_browser()

                elif key == ord('c'):
                    if mode == MeasurementMode.BURST_CAPTURE and state == MeasurementState.LIVE:
                        result = self.pipe_measure.start_burst_capture()
                        if result['success']:
                            print(f"\n{result['message']}")

                elif key == ord(' '):
                    if state == MeasurementState.BURST_ANNOTATING:
                        self._handle_space()

                elif key == ord('n'):
                    if state == MeasurementState.BURST_ANNOTATING:
                        result = self.pipe_measure.skip_frame()
                        print(f"\u27A4 Frame {result.get('frame_index', '?') + 1}: Skipped")

                elif key == ord('b'):
                    if state == MeasurementState.BURST_ANNOTATING:
                        result = self.pipe_measure.go_back()
                        if result['success']:
                            print(f"\u2B05 Back to frame {result.get('frame_index', 0) + 1}")

                elif key == ord('s'):
                    if mode == MeasurementMode.LIVE_CONTINUOUS and len(self.pipe_measure.live_points) >= 2:
                        if self.pipe_measure.live_is_measuring:
                            result = self.pipe_measure.finalize_live_measurement()
                            if result['success']:
                                self._save_live_measurement()
                                self.save_notification_time = time.time() + 2.0
                                self.save_message = "MEASUREMENT SAVED!"
                        else:
                            self._save_live_measurement()
                            self.save_notification_time = time.time() + 2.0
                            self.save_message = "MEASUREMENT SAVED!"
                    elif state == MeasurementState.BURST_DONE:
                        self._save_burst_results()
                        self.save_notification_time = time.time() + 2.0
                        self.save_message = "SESSION SAVED!"

                elif key == ord('r'):
                    if mode == MeasurementMode.LIVE_CONTINUOUS:
                        self.pipe_measure.reset_live_continuous()
                    else:
                        self.pipe_measure.reset_to_live()
                    print("\n\u2713 Reset complete")

        finally:
            self.cleanup()

    def _handle_space(self):
        """Handle SPACE key for burst annotation."""
        pm = self.pipe_measure
        pending = pm.burst_pending_points
        carry = pm.burst_carry_over_points

        if len(pending) == 2:
            result = pm.accept_burst_points()
            if result['success']:
                if result.get('complete'):
                    print(f"\n\u2713 ALL FRAMES ANNOTATED!")
                    print(f"Measurements: {result.get('total', 0)}")
                    summary = pm.get_burst_summary()
                    if summary['success']:
                        print(f"Average: {summary['average_distance']:.4f}m \u00b1 {summary['std_distance']:.4f}m")
                else:
                    print(f"\u2713 Frame {result.get('frame_index', 0) + 1}: Accepted")

        elif len(pending) == 1:
            print("\u2717 Click P2 first")

        elif len(carry) == 2 and pm.burst_current_index > 0:
            result = pm.accept_carry_over()
            if result['success']:
                if result.get('complete'):
                    print(f"\n\u2713 ALL FRAMES ANNOTATED!")
                    print(f"Measurements: {result.get('total', 0)}")
                    summary = pm.get_burst_summary()
                    if summary['success']:
                        print(f"Average: {summary['average_distance']:.4f}m \u00b1 {summary['std_distance']:.4f}m")
                else:
                    print(f"\u2713 Frame {result.get('frame_index', 0) + 1}: Carry-over accepted")
            else:
                print(f"\u2717 {result.get('message', 'Invalid carry-over')}")

        else:
            print("\u2717 Mark P1 and P2 first (frame 0)")

    def _get_live_mode_display(self, color_frame: np.ndarray, depth_frame: np.ndarray) -> np.ndarray:
        """Get Live Mode display with stats panel - no text on line."""
        display = color_frame.copy()
        h, w = color_frame.shape[:2]

        fps = self.pipe_measure.get_fps()
        cv2.putText(display, f"FPS: {fps:.1f}", (w - 100, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if fps > 20 else (0, 165, 255), 2)

        cv2.putText(display, "MODE: LIVE", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        live_stats = None
        if self.pipe_measure.live_is_measuring and depth_frame is not None:
            live_stats = self.pipe_measure.process_live_continuous_measurement(depth_frame)

        overlay = display.copy()
        cv2.rectangle(overlay, (10, 50), (290, 280), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, display, 0.3, 0, display)
        cv2.rectangle(display, (10, 50), (290, 280), (0, 255, 0), 2)

        y_pos = 80
        cv2.putText(display, "MEASUREMENT STATS", (20, y_pos),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        y_pos += 35

        points = self.pipe_measure.live_points

        if len(points) >= 1:
            x1, y1 = points[0][0], points[0][1]
            cv2.circle(display, (x1, y1), 3, (0, 255, 0), -1)
            cv2.circle(display, (x1, y1), 5, (255, 255, 255), 1)

        if len(points) >= 2:
            x1, y1 = points[0][0], points[0][1]
            x2, y2 = points[1][0], points[1][1]

            cv2.circle(display, (x2, y2), 3, (0, 0, 255), -1)
            cv2.circle(display, (x2, y2), 5, (255, 255, 255), 1)
            cv2.line(display, (x1, y1), (x2, y2), (0, 255, 255), 2)

        if live_stats:
            if live_stats.get('invalid'):
                cv2.putText(display, "INVALID DEPTH!", (20, y_pos),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                y_pos += 30
            else:
                cv2.putText(display, f"Length: {live_stats.get('pipe_length', 0):.4f}m",
                           (20, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                y_pos += 25

        y_pos += 10
        cv2.putText(display, "-" * 15, (20, y_pos),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 100), 1)
        y_pos += 25

        measurements = self.pipe_measure.live_measurements
        num_frames = len(measurements) if measurements else 0
        cv2.putText(display, f"Frames: {num_frames}", (20, y_pos),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        y_pos += 22

        if num_frames > 0:
            avg = np.mean(measurements)
            std = np.std(measurements) if num_frames > 1 else 0
            cv2.putText(display, f"Avg: {avg:.4f}m", (20, y_pos),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            y_pos += 22
            cv2.putText(display, f"Std: \u00b1{std:.4f}m", (20, y_pos),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            y_pos += 22

            stability = 100.0 * (1.0 - min(std / avg, 1.0)) if avg > 0 else 0
            stab_text = f"Stability: {stability:.1f}%"
            stab_color = (0, 255, 0) if stability > 90 else (0, 165, 255)
            cv2.putText(display, stab_text, (20, y_pos),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, stab_color, 1)

        if len(points) == 0:
            msg = "Click 2 points | M for BURST mode"
        elif len(points) == 1:
            msg = "Click second point"
        elif self.pipe_measure.live_is_measuring:
            msg = "Measuring continuously... S to finalize | R to reset"
        else:
            msg = "Press S to SAVE | R to reset"

        self._draw_alert(display, msg, (255, 255, 255))

        return display

    def _get_burst_annotation_display(self) -> np.ndarray:
        """Get burst annotation display with carry-over support."""
        pm = self.pipe_measure
        frame = pm.frozen_color_frame

        if frame is None:
            return np.zeros((720, 1280, 3), dtype=np.uint8)

        display = frame.copy()
        h, w = frame.shape[:2]

        cv2.putText(display, "MODE: BURST", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)

        idx = pm.burst_current_index
        total = len(pm.burst_color_frames)

        cv2.rectangle(display, (w - 180, 10), (w - 10, 50), (0, 0, 0), -1)
        cv2.putText(display, f"Frame {idx + 1}/{total}", (w - 170, 40),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        cv2.rectangle(display, (10, 60), (150, 100), (0, 0, 0), -1)
        cv2.putText(display, f"Done: {len(pm.burst_results)}", (20, 85),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        pending = pm.burst_pending_points
        carry = pm.burst_carry_over_points

        if len(pending) >= 1:
            x1, y1 = int(pending[0][0]), int(pending[0][1])
            cv2.circle(display, (x1, y1), 3, (0, 255, 0), -1)
            cv2.circle(display, (x1, y1), 5, (255, 255, 255), 1)
            cv2.putText(display, "P1", (x1 + 8, y1 - 8),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        if len(pending) >= 2:
            x1, y1 = int(pending[0][0]), int(pending[0][1])
            x2, y2 = int(pending[1][0]), int(pending[1][1])
            cv2.circle(display, (x2, y2), 3, (0, 0, 255), -1)
            cv2.circle(display, (x2, y2), 5, (255, 255, 255), 1)
            cv2.putText(display, "P2", (x2 + 8, y2 - 8),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            cv2.line(display, (x1, y1), (x2, y2), (0, 255, 255), 2)

            dist = pm._calculate_distance_between_points(x1, y1, pending[0][2], x2, y2, pending[1][2])
            cv2.rectangle(display, (w//2 - 80, 60), (w//2 + 80, 100), (0, 0, 0), -1)
            cv2.putText(display, f"Dist: {dist:.4f}m", (w//2 - 70, 90),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        elif len(carry) >= 2 and idx > 0:
            x1, y1 = int(carry[0][0]), int(carry[0][1])
            x2, y2 = int(carry[1][0]), int(carry[1][1])

            cv2.circle(display, (x1, y1), 3, (0, 255, 0), -1)
            cv2.circle(display, (x1, y1), 5, (255, 255, 255), 1)
            cv2.circle(display, (x2, y2), 3, (0, 0, 255), -1)
            cv2.circle(display, (x2, y2), 5, (255, 255, 255), 1)
            cv2.line(display, (x1, y1), (x2, y2), (0, 255, 255), 2)

            cv2.rectangle(display, (10, 110), (200, 150), (0, 0, 0), -1)
            cv2.putText(display, "CARRY-OVER", (20, 140),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            z1, z2 = carry[0][2], carry[1][2]
            dist = pm._calculate_distance_between_points(x1, y1, z1, x2, y2, z2)
            cv2.rectangle(display, (w//2 - 80, 60), (w//2 + 80, 100), (0, 0, 0), -1)
            cv2.putText(display, f"Est: {dist:.4f}m", (w//2 - 70, 90),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)

        elif idx == 0:
            cv2.putText(display, "Click P1 to start", (w//2 - 120, h//2),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 3)

        cv2.rectangle(display, (0, h - 50), (w, h), (0, 0, 0), -1)

        if len(pending) >= 2:
            instructions = "SPACE=Accept | CLICK=Redraw"
        elif len(carry) >= 2 and idx > 0:
            instructions = "SPACE=Accept carry-over | CLICK=Redraw | N=Skip | B=Back"
        else:
            instructions = "N=Skip | B=Back"

        text_size = cv2.getTextSize(instructions, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
        cv2.putText(display, instructions, ((w - text_size[0]) // 2, h - 18),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        return display

    def _get_burst_result_display(self) -> np.ndarray:
        """Get burst result summary display."""
        pm = self.pipe_measure
        frame = pm.frozen_color_frame

        if frame is None:
            return np.zeros((720, 1280, 3), dtype=np.uint8)

        display = frame.copy()
        h, w = frame.shape[:2]

        summary = pm.get_burst_summary()

        cv2.rectangle(display, (w//2 - 200, h//2 - 100), (w//2 + 200, h//2 + 100), (0, 0, 0), -1)
        cv2.rectangle(display, (w//2 - 200, h//2 - 100), (w//2 + 200, h//2 + 100), (0, 255, 0), 3)

        cv2.putText(display, "BURST COMPLETE", (w//2 - 120, h//2 - 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        if summary['success']:
            cv2.putText(display, f"Measurements: {summary['num_measurements']}", (w//2 - 100, h//2 - 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(display, f"Avg: {summary['average_distance']:.4f}m", (w//2 - 100, h//2 + 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.putText(display, f"Std: \u00b1{summary['std_distance']:.4f}m", (w//2 - 100, h//2 + 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        cv2.putText(display, "S=SAVE | R=RESTART", (w//2 - 100, h//2 + 80),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        return display

    def _save_live_measurement(self):
        """Save single measurement with color frame and depth map."""
        pm = self.pipe_measure
        if len(pm.live_points) < 2:
            print("\u2717 Need 2 points first")
            return

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_dir = self.session_base_path / f"live_{timestamp}"
            session_dir.mkdir(parents=True, exist_ok=True)

            color_frame, depth_frame = pm.get_frames()

            if color_frame is not None:
                cv2.imwrite(str(session_dir / "color.jpg"), color_frame)
            if depth_frame is not None:
                np.save(str(session_dir / "depth.npy"), depth_frame)

            pipe_length = pm.live_pipe_length if pm.live_pipe_length else 0.0

            data = {
                'type': 'live_measurement',
                'pipe_length': float(pipe_length),
                'point1': {'x': pm.live_points[0][0], 'y': pm.live_points[0][1]},
                'point2': {'x': pm.live_points[1][0], 'y': pm.live_points[1][1]},
                'timestamp': datetime.now().isoformat()
            }

            with open(session_dir / "metadata.json", 'w') as f:
                json.dump(data, f, indent=2)

            print(f"\n\u2713 Saved to: {session_dir}")
            print(f"   Distance: {pipe_length:.4f}m")
        except Exception as e:
            print(f"\u2717 Save failed: {e}")

    def _save_burst_results(self):
        """Save burst measurement results with all frames to unique session folder."""
        pm = self.pipe_measure
        summary = pm.get_burst_summary()

        if not summary['success']:
            print("\u2717 No measurements to save")
            return

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_dir = self.session_base_path / f"session_{timestamp}"
            session_dir.mkdir(parents=True, exist_ok=True)

            color_dir = session_dir / "color"
            depth_dir = session_dir / "depth"
            color_dir.mkdir(exist_ok=True)
            depth_dir.mkdir(exist_ok=True)

            for i, (color_frame, depth_frame) in enumerate(zip(pm.burst_color_frames, pm.burst_depth_frames)):
                cv2.imwrite(str(color_dir / f"frame_{i:03d}.jpg"), color_frame)
                np.save(str(depth_dir / f"frame_{i:03d}.npy"), depth_frame)

            metadata = {
                'type': 'burst_session',
                'average_distance': summary['average_distance'],
                'std_distance': summary['std_distance'],
                'num_measurements': summary['num_measurements'],
                'num_frames': len(pm.burst_color_frames),
                'distances': summary['distances'],
                'results': [{'frame_index': r['frame_index'], 'distance': r['distance']}
                           for r in pm.burst_results if r.get('distance') is not None],
                'timestamp': datetime.now().isoformat(),
                'session_id': timestamp
            }

            with open(session_dir / "metadata.json", 'w') as f:
                json.dump(metadata, f, indent=2)

            print(f"\n\u2713 Session saved: {session_dir}")
            print(f"   Frames: {len(pm.burst_color_frames)} | Avg: {summary['average_distance']:.4f}m")
        except Exception as e:
            print(f"\u2717 Save failed: {e}")

    def _open_session_browser(self):
        """Open the session browser UI."""
        self.session_base_path.mkdir(parents=True, exist_ok=True)

        folders = [f for f in os.listdir(self.session_base_path)
                  if os.path.isdir(self.session_base_path / f) and f.startswith("session_")]
        folders.sort(reverse=True)
        self.session_list = folders[:9]

        if not self.session_list:
            print("\u2717 No saved sessions found")
            return

        self.app_state = AppState.BROWSING_SESSIONS
        self.session_browser_index = 0
        print(f"\nSession Browser - {len(self.session_list)} sessions found")
        for i, name in enumerate(self.session_list, 1):
            print(f"  [{i}] {name}")
        print("  [ESC/R] Cancel\n")

    def _get_session_browser_display(self, color_frame: np.ndarray) -> np.ndarray:
        """Draw the session browser overlay."""
        h, w = color_frame.shape[:2]
        display = color_frame.copy()

        overlay = np.zeros((h, w, 3), dtype=np.uint8)
        overlay[:] = (20, 20, 30)
        display = cv2.addWeighted(display, 0.3, overlay, 0.7, 0)

        title = "SESSION BROWSER"
        cv2.putText(display, title, (w//2 - 150, 80),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3)

        cv2.putText(display, "Press [1-9] to load session | [ESC/R] to cancel",
                   (w//2 - 250, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)

        y_start = 200
        if not self.session_list:
            cv2.putText(display, "No sessions found", (w//2 - 100, y_start + 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (150, 150, 150), 2)
        else:
            for i, name in enumerate(self.session_list, 1):
                folder_path = self.session_base_path / name
                metadata_path = folder_path / "metadata.json"
                info = name.replace("session_", "")

                if metadata_path.exists():
                    try:
                        with open(metadata_path, 'r') as f:
                            meta = json.load(f)
                        if 'average_distance' in meta:
                            info = f"{name} - Avg: {meta['average_distance']:.4f}m"
                    except:
                        pass

                is_selected = i - 1 == self.session_browser_index
                box_color = (50, 50, 100) if is_selected else (40, 40, 50)
                cv2.rectangle(display, (w//2 - 250, y_start + i * 50 - 20),
                            (w//2 + 250, y_start + i * 50 + 25), box_color, -1)
                text_color = (255, 255, 255) if is_selected else (0, 255, 255)
                cv2.putText(display, f"[{i}] {info}", (w//2 - 230, y_start + i * 50 + 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2)

        return display

    def _handle_session_browser_key(self, key: int):
        """Handle keyboard input in session browser."""
        if key == 27 or key == ord('r'):
            self.app_state = AppState.NORMAL
            print("Session browser closed")
            return

        if key >= ord('1') and key <= ord('9'):
            idx = key - ord('1')
            if idx < len(self.session_list):
                self._load_session(idx)

    def _load_session(self, index: int):
        """Load a session by index."""
        if index >= len(self.session_list):
            return

        session_name = self.session_list[index]
        session_path = self.session_base_path / session_name

        try:
            color_dir = session_path / "color"
            depth_dir = session_path / "depth"

            if not color_dir.exists() or not depth_dir.exists():
                print(f"\u2717 Invalid session structure")
                self.app_state = AppState.NORMAL
                return

            color_frames = sorted([f for f in os.listdir(color_dir) if f.endswith('.jpg')])
            depth_frames = sorted([f for f in os.listdir(depth_dir) if f.endswith('.npy')])

            if not color_frames or not depth_frames:
                print(f"\u2717 No frames found in session")
                self.app_state = AppState.NORMAL
                return

            pm = self.pipe_measure
            pm.burst_color_frames = []
            pm.burst_depth_frames = []

            for frame_file in color_frames:
                frame = cv2.imread(str(color_dir / frame_file))
                if frame is not None:
                    pm.burst_color_frames.append(frame)

            for frame_file in depth_frames:
                frame = np.load(str(depth_dir / frame_file))
                pm.burst_depth_frames.append(frame)

            pm.burst_current_index = 0
            pm.burst_results = []
            pm.burst_pending_points = []
            pm.burst_carry_over_points = []
            pm.frozen_color_frame = pm.burst_color_frames[0] if pm.burst_color_frames else None
            pm.frozen_depth_frame = pm.burst_depth_frames[0] if pm.burst_depth_frames else None
            pm.state = MeasurementState.BURST_ANNOTATING
            pm.measurement_mode = MeasurementMode.BURST_CAPTURE

            self.app_state = AppState.NORMAL

            print(f"\n\u2713 Loaded session: {session_name}")
            print(f"   {len(pm.burst_color_frames)} frames loaded. Annotating frame 1...")

        except Exception as e:
            print(f"\u2717 Failed to load session: {e}")
            self.app_state = AppState.NORMAL

    def _draw_alert(self, frame: np.ndarray, message: str, color: tuple = (255, 255, 255)):
        """Draw an alert message at the bottom of the frame."""
        h, w = frame.shape[:2]

        cv2.rectangle(frame, (0, h - 40), (w, h), (0, 0, 0), -1)

        text_size = cv2.getTextSize(message, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
        x_pos = (w - text_size[0]) // 2

        cv2.putText(frame, message, (x_pos, h - 12),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    def _draw_notification(self, frame: np.ndarray):
        """Draw save notification at top center."""
        if time.time() < self.save_notification_time and self.save_message:
            h, w = frame.shape[:2]
            box_w = 320
            x1 = (w - box_w) // 2
            x2 = x1 + box_w
            cv2.rectangle(frame, (x1, 10), (x2, 50), (0, 150, 0), -1)
            cv2.putText(frame, self.save_message, (x1 + 20, 40),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    def cleanup(self):
        """Cleanup resources."""
        self.logger.info("Cleaning up...")
        if self.pipe_measure:
            self.pipe_measure.cleanup()
        cv2.destroyAllWindows()


def main():
    """Main entry point."""
    import argparse
    parser = argparse.ArgumentParser(description='ROV Pipe Length Measurement System')
    parser.add_argument('--config', default='./config', help='Config directory')

    args = parser.parse_args()
    system = IcebergTrackingSystem(config_dir=args.config)

    print("\n" + "=" * 60)
    print("PIPE LENGTH MEASUREMENT SYSTEM - ROV COMPETITION")
    print("=" * 60)
    print("\nControls:")
    print("  M - Toggle LIVE / BURST mode")
    print("  O - Open session browser (Burst mode, before capture)")
    print("  LIVE Mode: Click 2 points | S to save | R to reset")
    print("  BURST Mode: C=capture | Click P1,P2 | SPACE=accept")
    print("  SPACE - Accept carry-over points (Burst)")
    print("  N - Skip frame | B - Go back | R - Reset")
    print("  Q - Quit")
    print("=" * 60 + "\n")

    try:
        system.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted")
    except Exception as e:
        print(f"\n\nError: {e}")
        logging.exception("Fatal error")
    finally:
        system.cleanup()


if __name__ == "__main__":
    main()
