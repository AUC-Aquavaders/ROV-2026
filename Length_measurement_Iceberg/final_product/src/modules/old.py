import numpy as np
import depthai as dai
import cv2
import threading
import time
import logging
import os
import json
import torch
from enum import Enum
from typing import Optional, Tuple, List, Dict, Any
from pathlib import Path
from datetime import datetime


class MeasurementState(Enum):
    LIVE = 'live'
    CAPTURING = 'capturing'
    BURST_ANNOTATING = 'burst_annotating'
    BURST_DONE = 'burst_done'


class MeasurementMode(Enum):
    LIVE_CONTINUOUS = 'live_continuous'
    BURST_CAPTURE = 'burst_capture'


class PipeLengthMeasurement:
    """Handles camera pipeline, frame capture, and measurement logic."""

    def __init__(self, num_frames: int = 30):
        self.logger = logging.getLogger(__name__)
        self.num_frames = num_frames

        self.state = MeasurementState.LIVE
        self.measurement_mode = MeasurementMode.BURST_CAPTURE

        self.device_type = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            self.logger.info(f"Using Device: cuda ({device_name})")
        else:
            self.logger.info(f"Using Device: cpu")

        self.pipeline = None
        self.device = None
        self.color_queue = None
        self.depth_queue = None
        self.frame_count = 0
        self.fps = 0.0
        self.current_fps = 0.0
        self.last_frame_time = time.time()
        self.last_fps_update = time.time()
        self.frames_since_last_update = 0

        self.latest_color = None
        self.latest_depth_raw = None
        self.last_valid_color = None
        self.last_valid_depth_raw = None
        self.capture_thread = None
        self.running = True

        self.live_points = []
        self.live_pipe_length = None
        self.live_measurements = []
        self.live_is_measuring = False

        self.burst_color_frames: List[np.ndarray] = []
        self.burst_depth_frames: List[np.ndarray] = []
        self.burst_results: List[Dict] = []
        self.burst_current_index = 0
        self.burst_pending_points = []
        self.burst_carry_over_points = []
        self.frozen_color_frame = None
        self.frozen_depth_frame = None

        self.width = 1280
        self.height = 720

        self.fx = None
        self.fy = None
        self.cx = None
        self.cy = None

        self._init_camera()

    def _init_camera(self):
        """Initialize OAK-D PoE camera with MJPEG color + raw depth."""
        try:
            self.pipeline = dai.Pipeline()

            cam = self.pipeline.createColorCamera()
            cam.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
            cam.setIspScale(2, 3)
            cam.setPreviewSize(1280, 720)
            cam.setInterleaved(False)
            cam.setFps(30)
            cam.initialControl.setAutoExposureLimit(33000)

            mono_left = self.pipeline.createMonoCamera()
            mono_left.setBoardSocket(dai.CameraBoardSocket.CAM_B)
            mono_left.setResolution(dai.MonoCameraProperties.SensorResolution.THE_720_P)
            mono_left.setFps(30)
            mono_left.initialControl.setAutoExposureLimit(33000)

            mono_right = self.pipeline.createMonoCamera()
            mono_right.setBoardSocket(dai.CameraBoardSocket.CAM_C)
            mono_right.setResolution(dai.MonoCameraProperties.SensorResolution.THE_720_P)
            mono_right.setFps(30)
            mono_right.initialControl.setAutoExposureLimit(33000)

            stereo = self.pipeline.createStereoDepth()
            stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.HIGH_DENSITY)
            stereo.setDepthAlign(dai.CameraBoardSocket.RGB)
            stereo.initialConfig.setMedianFilter(dai.MedianFilter.KERNEL_7x7)
            stereo.setLeftRightCheck(True)

            mono_left.out.link(stereo.left)
            mono_right.out.link(stereo.right)

            jpeg = self.pipeline.createVideoEncoder()
            jpeg.setDefaultProfilePreset(30, dai.VideoEncoderProperties.Profile.MJPEG)
            jpeg.setQuality(95)
            cam.video.link(jpeg.input)

            xout_color = self.pipeline.createXLinkOut()
            xout_color.setStreamName("color")
            xout_color.input.setBlocking(False)
            jpeg.bitstream.link(xout_color.input)
            
            xout_depth = self.pipeline.createXLinkOut()
            xout_depth.setStreamName("depth")
            xout_depth.input.setBlocking(False)
            stereo.depth.link(xout_depth.input)

            self.device = dai.Device(self.pipeline)

            calibData = self.device.readCalibration()
            intrinsics = calibData.getCameraIntrinsics(dai.CameraBoardSocket.CAM_A, 1280, 720)
            self.fx = intrinsics[0][0]
            self.fy = intrinsics[1][1]
            self.cx = intrinsics[0][2]
            self.cy = intrinsics[1][2]
            self.logger.info(f"True 720p Intrinsics: fx={self.fx:.2f}, fy={self.fy:.2f}, cx={self.cx:.2f}, cy={self.cy:.2f}")

            self.logger.info("Warming up camera sensors for 2 seconds (AE/AWB convergence)...")
            time.sleep(2.0)

            self.color_queue = self.device.getOutputQueue(name="color", maxSize=4, blocking=False)
            self.depth_queue = self.device.getOutputQueue(name="depth", maxSize=4, blocking=False)

            self.color_queue.tryGetAll()
            self.depth_queue.tryGetAll()
            self.logger.info("Warmup complete. Queues flushed.")

            self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.capture_thread.start()

            self.logger.info("Camera initialized: MJPEG color + raw depth")
        except Exception as e:
            self.logger.error(f"Camera initialization failed: {e}")
            raise

    def _capture_loop(self):
        """Background daemon thread - decode MJPEG, keep depth raw."""
        while self.running:
            try:
                c_msg = self.color_queue.tryGet()
                d_msg = self.depth_queue.tryGet()

                if c_msg:
                    frame_data = np.array(c_msg.getData())
                    self.latest_color = cv2.imdecode(frame_data, cv2.IMREAD_COLOR)
                    if self.latest_color is not None:
                        self.last_valid_color = self.latest_color

                if d_msg:
                    self.latest_depth_raw = d_msg.getFrame()
                    if self.latest_depth_raw is not None:
                        self.last_valid_depth_raw = self.latest_depth_raw

                if c_msg and d_msg:
                    self.frame_count += 1
                    now = time.time()
                    dt = now - self.last_frame_time
                    self.last_frame_time = now
                    if dt > 0:
                        instant_fps = 1.0 / dt
                        self.current_fps = (0.1 * instant_fps) + (0.9 * self.current_fps)
                else:
                    time.sleep(0.001)

            except Exception:
                time.sleep(0.001)

    def get_frames(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Get current or last valid color and raw depth frames."""
        color = self.latest_color if self.latest_color is not None else self.last_valid_color
        depth = self.latest_depth_raw if self.latest_depth_raw is not None else self.last_valid_depth_raw
        return color, depth

    def get_fps(self) -> float:
        """Get current FPS from hardware capture loop."""
        return self.current_fps

    def get_depth_colormap(self, depth_frame: np.ndarray) -> np.ndarray:
        """Ultra-fast colormap with fixed range (0.2m - 3.0m)."""
        if depth_frame is None or depth_frame.size == 0:
            return np.zeros((self.height, self.width, 3), dtype=np.uint8)

        dh, dw = depth_frame.shape[:2]
        depth_m = depth_frame.astype(np.float32) / 1000.0

        MIN_DEPTH = 0.2
        MAX_DEPTH = 3.0
        depth_scaled = np.clip((depth_m - MIN_DEPTH) / (MAX_DEPTH - MIN_DEPTH) * 255.0, 0, 255).astype(np.uint8)

        colormap = cv2.applyColorMap(depth_scaled, cv2.COLORMAP_TURBO)

        colormap[depth_m <= 0] = [0, 0, 0]

        if dh != self.height or dw != self.width:
            colormap = cv2.resize(colormap, (self.width, self.height), interpolation=cv2.INTER_NEAREST)

        return colormap

    def toggle_measurement_mode(self) -> Dict[str, Any]:
        """Toggle between Live Continuous and Burst Capture modes."""
        if self.measurement_mode == MeasurementMode.LIVE_CONTINUOUS:
            self.measurement_mode = MeasurementMode.BURST_CAPTURE
            self.state = MeasurementState.LIVE
            self.reset_live_continuous()
            return {'success': True, 'message': 'Switched to BURST CAPTURE mode'}
        else:
            self.measurement_mode = MeasurementMode.LIVE_CONTINUOUS
            self.state = MeasurementState.LIVE
            self.reset_live_continuous()
            return {'success': True, 'message': 'Switched to LIVE CONTINUOUS mode'}

    def mark_point_live_continuous(self, x: int, y: int) -> Dict[str, Any]:
        """Mark point in live continuous mode."""
        if self.measurement_mode != MeasurementMode.LIVE_CONTINUOUS:
            return {'success': False, 'message': 'Not in live continuous mode'}

        if len(self.live_points) >= 2:
            self.live_points = [(x, y)]
            self.live_measurements = []
            self.live_is_measuring = True
            return {'success': True, 'message': f'P1 reset at ({x}, {y})', 'measuring': False}

        self.live_points.append((x, y))

        if len(self.live_points) == 1:
            return {'success': True, 'message': f'P1 set at ({x}, {y})', 'measuring': False}

        self.live_is_measuring = True
        return {'success': True, 'message': f'P2 set at ({x}, {y})', 'measuring': True}

    def process_live_continuous_measurement(self, depth_frame: np.ndarray) -> Dict[str, Any]:
        """Process live continuous measurement with depth values."""
        if not self.live_is_measuring or len(self.live_points) < 2:
            return {'invalid': True}

        if depth_frame is None:
            return {'invalid': True}

        x1, y1 = self.live_points[0]
        x2, y2 = self.live_points[1]

        h, w = depth_frame.shape[:2]
        if x1 >= w or x2 >= w or y1 >= h or y2 >= h:
            return {'invalid': True}

        z1 = depth_frame[y1, x1] if not np.isnan(depth_frame[y1, x1]) else 0
        z2 = depth_frame[y2, x2] if not np.isnan(depth_frame[y2, x2]) else 0

        if z1 <= 0 or z2 <= 0:
            return {'invalid': True}

        x1_mm = (x1 - self.cx) * z1 / self.fx
        y1_mm = (y1 - self.cy) * z1 / self.fy
        x2_mm = (x2 - self.cx) * z2 / self.fx
        y2_mm = (y2 - self.cy) * z2 / self.fy

        distance = self._calculate_distance_meters(x1_mm, y1_mm, z1, x2_mm, y2_mm, z2)

        self.live_pipe_length = distance
        self.live_measurements.append(distance)

        return {
            'invalid': False,
            'pipe_length': distance,
            'point1': (x1, y1, z1),
            'point2': (x2, y2, z2)
        }

    def finalize_live_measurement(self) -> Dict[str, Any]:
        """Finalize live measurement."""
        if not self.live_measurements:
            return {'success': False, 'message': 'No measurements taken'}

        avg = np.mean(self.live_measurements)
        std = np.std(self.live_measurements)

        return {
            'success': True,
            'message': f'Final: {avg:.4f}m ± {std:.4f}m',
            'average': avg,
            'std': std,
            'count': len(self.live_measurements)
        }

    def reset_live_continuous(self):
        """Reset live continuous measurement."""
        self.live_points = []
        self.live_pipe_length = None
        self.live_measurements = []
        self.live_is_measuring = False

    def start_burst_capture(self) -> Dict[str, Any]:
        """Start burst capture mode."""
        if self.state != MeasurementState.LIVE:
            return {'success': False, 'message': 'Not in live state'}

        self.burst_color_frames = []
        self.burst_depth_frames = []
        self.burst_results = []
        self.burst_current_index = 0
        self.burst_pending_points = []
        self.burst_carry_over_points = []
        self.state = MeasurementState.CAPTURING

        return {'success': True, 'message': f'Capturing {self.num_frames} frames...'}

    def capture_burst_frame(self, color_frame: np.ndarray, depth_frame: np.ndarray):
        """Capture single frame during burst mode."""
        if self.state != MeasurementState.CAPTURING:
            return

        if len(self.burst_color_frames) >= self.num_frames:
            self.state = MeasurementState.BURST_ANNOTATING
            self.frozen_color_frame = self.burst_color_frames[0].copy()
            self.frozen_depth_frame = self.burst_depth_frames[0].copy()
            return

        if color_frame is not None:
            self.burst_color_frames.append(color_frame.copy())
        if depth_frame is not None:
            self.burst_depth_frames.append(depth_frame.copy())

    def mark_burst_point(self, x: int, y: int) -> Dict[str, Any]:
        """Mark first point in burst annotation."""
        if self.state != MeasurementState.BURST_ANNOTATING:
            return {'success': False, 'message': 'Not in annotation state'}

        if not self.burst_color_frames:
            return {'success': False, 'message': 'No frames captured'}

        depth = self.frozen_depth_frame
        h, w = depth.shape[:2] if depth is not None else (0, 0)

        if x >= w or y >= h:
            return {'success': False, 'message': 'Point outside frame'}

        z = depth[y, x] if depth is not None and not np.isnan(depth[y, x]) else 0

        self.burst_pending_points = [(x, y, z)]
        self.burst_carry_over_points = []

        return {'success': True, 'message': f'P1 set at ({x}, {y})'}

    def mark_burst_second_point(self, x: int, y: int) -> Dict[str, Any]:
        """Mark second point in burst annotation."""
        if self.state != MeasurementState.BURST_ANNOTATING:
            return {'success': False, 'message': 'Not in annotation state'}

        if len(self.burst_pending_points) != 1:
            return {'success': False, 'message': 'P1 not set'}

        depth = self.frozen_depth_frame
        h, w = depth.shape[:2] if depth is not None else (0, 0)

        if x >= w or y >= h:
            return {'success': False, 'message': 'Point outside frame'}

        z = depth[y, x] if depth is not None and not np.isnan(depth[y, x]) else 0

        self.burst_pending_points.append((x, y, z))

        return {'success': True, 'message': f'P2 set at ({x}, {y})'}

    def clear_burst_points(self):
        """Clear pending points."""
        self.burst_pending_points = []

    def accept_burst_points(self) -> Dict[str, Any]:
        """Accept pending points and record measurement."""
        if len(self.burst_pending_points) != 2:
            return {'success': False, 'message': 'Need 2 points'}

        p1, p2 = self.burst_pending_points
        
        if p1[2] <= 0 or p2[2] <= 0:
            return {'success': False, 'message': 'Invalid depth at one or both points'}

        x1_mm = (p1[0] - self.cx) * p1[2] / self.fx
        y1_mm = (p1[1] - self.cy) * p1[2] / self.fy
        x2_mm = (p2[0] - self.cx) * p2[2] / self.fx
        y2_mm = (p2[1] - self.cy) * p2[2] / self.fy

        distance = self._calculate_distance_meters(x1_mm, y1_mm, p1[2], x2_mm, y2_mm, p2[2])

        self.burst_results.append({
            'frame_index': self.burst_current_index,
            'point1': p1,
            'point2': p2,
            'distance': distance
        })

        self.burst_carry_over_points = self.burst_pending_points.copy()
        self.burst_pending_points = []

        next_frame = self.burst_current_index + 1

        if next_frame >= len(self.burst_color_frames):
            self.state = MeasurementState.BURST_DONE
            return {'success': True, 'complete': True, 'total': len(self.burst_results)}

        self.burst_current_index = next_frame
        self.frozen_color_frame = self.burst_color_frames[next_frame].copy()
        self.frozen_depth_frame = self.burst_depth_frames[next_frame].copy()

        return {'success': True, 'complete': False, 'frame_index': self.burst_current_index}

    def accept_carry_over(self) -> Dict[str, Any]:
        """Accept carry-over points from previous frame."""
        if len(self.burst_carry_over_points) != 2:
            return {'success': False, 'message': 'No carry-over points'}

        if self.burst_current_index == 0:
            return {'success': False, 'message': 'Already at frame 0'}

        self.burst_pending_points = self.burst_carry_over_points.copy()
        return self.accept_burst_points()

    def skip_frame(self) -> Dict[str, Any]:
        """Skip current frame."""
        if self.state != MeasurementState.BURST_ANNOTATING:
            return {'success': False, 'message': 'Not annotating'}

        self.burst_results.append({
            'frame_index': self.burst_current_index,
            'point1': None,
            'point2': None,
            'distance': None,
            'skipped': True
        })

        self.burst_carry_over_points = []
        self.burst_pending_points = []

        next_frame = self.burst_current_index + 1

        if next_frame >= len(self.burst_color_frames):
            self.state = MeasurementState.BURST_DONE
            return {'success': True, 'complete': True, 'frame_index': self.burst_current_index}

        self.burst_current_index = next_frame
        self.frozen_color_frame = self.burst_color_frames[next_frame].copy()
        self.frozen_depth_frame = self.burst_depth_frames[next_frame].copy()

        return {'success': True, 'complete': False, 'frame_index': self.burst_current_index}

    def go_back(self) -> Dict[str, Any]:
        """Go back to previous frame."""
        if self.state != MeasurementState.BURST_ANNOTATING:
            return {'success': False, 'message': 'Not annotating'}

        if self.burst_current_index == 0:
            return {'success': False, 'message': 'Already at first frame'}

        if self.burst_results:
            self.burst_results.pop()

        prev_frame = self.burst_current_index - 1
        self.burst_current_index = prev_frame
        self.frozen_color_frame = self.burst_color_frames[prev_frame].copy()
        self.frozen_depth_frame = self.burst_depth_frames[prev_frame].copy()
        self.burst_pending_points = []
        self.burst_carry_over_points = []

        return {'success': True, 'frame_index': prev_frame}

    def get_burst_summary(self) -> Dict[str, Any]:
        """Get summary statistics of burst measurements."""
        valid_distances = [r['distance'] for r in self.burst_results
                         if r.get('distance') is not None and not r.get('skipped')]

        if not valid_distances:
            return {'success': False, 'message': 'No valid measurements'}

        return {
            'success': True,
            'num_measurements': len(valid_distances),
            'average_distance': float(np.mean(valid_distances)),
            'std_distance': float(np.std(valid_distances)),
            'min_distance': float(np.min(valid_distances)),
            'max_distance': float(np.max(valid_distances)),
            'distances': [float(d) for d in valid_distances]
        }

    def reset_to_live(self):
        """Reset burst mode and return to live state."""
        self.state = MeasurementState.LIVE
        self.burst_color_frames = []
        self.burst_depth_frames = []
        self.burst_results = []
        self.burst_current_index = 0
        self.burst_pending_points = []
        self.burst_carry_over_points = []
        self.frozen_color_frame = None
        self.frozen_depth_frame = None

    def _calculate_distance_meters(self, x1: float, y1: float, z1: float,
                                   x2: float, y2: float, z2: float) -> float:
        """Calculate 3D Euclidean distance from real-world XYZ points in millimeters."""
        p1_mm = np.array([x1, y1, z1], dtype=np.float64)
        p2_mm = np.array([x2, y2, z2], dtype=np.float64)
        return float(np.linalg.norm(p1_mm - p2_mm) * 0.001)

    def cleanup(self):
        """Cleanup camera resources."""
        self.running = False
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=1)
        if self.device:
            self.device.close()
