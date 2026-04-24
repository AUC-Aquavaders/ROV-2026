import numpy as np
import cv2
import threading
import time
import logging
from enum import Enum
from typing import Optional, Tuple, List, Dict, Any

# ── DepthAI import with version detection ────────────────────────────────────
try:
    import depthai as dai
    _DAI_AVAILABLE = True
    # New API (depthai >= 2.20 / 3.x) exposes dai.node.*
    # Old API (depthai < 2.20)        uses pipeline.createXxx()
    _DAI_NEW_API = hasattr(dai, "node")
except ImportError:
    _DAI_AVAILABLE = False
    _DAI_NEW_API   = False


class MeasurementState(Enum):
    LIVE             = 'live'
    CAPTURING        = 'capturing'
    BURST_ANNOTATING = 'burst_annotating'
    BURST_DONE       = 'burst_done'


class MeasurementMode(Enum):
    LIVE_CONTINUOUS = 'live_continuous'
    BURST_CAPTURE   = 'burst_capture'


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _create_node(pipeline, node_type_str: str):
    """
    Create a pipeline node that works with both DepthAI API generations.
      Old (< 2.20) : pipeline.createColorCamera()
      New (>= 2.20): pipeline.create(dai.node.ColorCamera)
    """
    if _DAI_NEW_API:
        return pipeline.create(getattr(dai.node, node_type_str))
    else:
        return getattr(pipeline, f"create{node_type_str}")()


def _reset_crashed_device(logger) -> bool:
    """
    If a previous run crashed the OAK-D and left it in a bad state, opening it
    briefly with an empty pipeline forces a clean reboot so the next real
    connection succeeds.
    """
    if not _DAI_AVAILABLE:
        return False
    try:
        devices = dai.Device.getAllAvailableDevices()
        if not devices:
            logger.warning("[RESET] No OAK-D devices visible on the bus.")
            return False
        logger.info(f"[RESET] {len(devices)} device(s) found – attempting soft reset …")
        for dev_info in devices:
            try:
                with dai.Device(dev_info):   # empty-pipeline open → reboot
                    pass
                logger.info(f"[RESET] Device {dev_info.getMxId()} reset OK")
            except Exception as e:
                logger.warning(f"[RESET] Could not reset {dev_info.getMxId()}: {e}")
        time.sleep(2)          # wait for USB re-enumeration
        return True
    except Exception as e:
        logger.warning(f"[RESET] Reset procedure error: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Main class
# ─────────────────────────────────────────────────────────────────────────────

class PipeLengthMeasurement:
    """OAK-D camera + pipe-length measurement logic."""

    def __init__(self, num_frames: int = 30):
        self.logger    = logging.getLogger(__name__)
        self.num_frames = num_frames

        self.state            = MeasurementState.LIVE
        self.measurement_mode = MeasurementMode.LIVE_CONTINUOUS

        self.pipeline    = None
        self.color_queue = None
        self.depth_queue = None

        self.frame_count    = 0
        self.fps            = 0.0
        self.fps_start_time = time.time()

        self.latest_color = None
        self.latest_depth = None
        self.capture_thread = None
        self.running = True

        # Live-continuous state
        self.live_points       = []
        self.live_pipe_length  = None
        self.live_measurements = []
        self.live_is_measuring = False

        # Burst state
        self.burst_color_frames      = []
        self.burst_depth_frames      = []
        self.burst_results           = []
        self.burst_current_index     = 0
        self.burst_pending_points    = []
        self.burst_carry_over_points = []
        self.frozen_color_frame      = None
        self.frozen_depth_frame      = None

        self.width  = 640
        self.height = 480

        # Camera intrinsics for OAK-D 640x480 resolution
        # These are typical values; can be calibrated for specific device
        self.fx = 430.0  # focal length x (pixels)
        self.fy = 430.0  # focal length y (pixels)
        self.cx = 320.0  # principal point x (center of image)
        self.cy = 240.0  # principal point y (center of image)

        # Set to False if camera fails; callers can check this flag
        self.camera_available = False

        self._init_camera()

    # ── Camera initialisation ────────────────────────────────────────────────

    def _init_camera(self):
        """
        Initialize OAK-D camera with color + stereo depth.
        Gracefully handles missing camera.
        """
        if not _DAI_AVAILABLE:
            self.logger.warning("depthai not installed – running without camera.")
            return

        try:
            self.pipeline = dai.Pipeline()
            
            # Create camera node
            cam = self.pipeline.create(dai.node.Camera)
            cam.build()
            
            # Request color output at 640x480
            preview_out = cam.requestOutput((640, 480), dai.ImgFrame.Type.BGR888p)
            self.color_queue = preview_out.createOutputQueue(maxSize=4, blocking=False)
            
            # Create stereo depth with auto-camera creation
            stereo = self.pipeline.create(dai.node.StereoDepth)
            stereo.build(autoCreateCameras=True, size=(640, 480))
            
            # Get depth output - use .depth property of the stereo node
            depth_out_link = stereo.depth
            if depth_out_link:
                self.depth_queue = depth_out_link.createOutputQueue(maxSize=4, blocking=False)
            
            # Start pipeline
            self.pipeline.start()
            
            self.camera_available = True
            self.logger.info("Camera initialized successfully – OAK-D connected with depth")
            
            # Start capture thread
            self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.capture_thread.start()

        except Exception as e:
            self.logger.warning(f"Camera initialization failed: {e}. Running in simulation mode.")
            self.camera_available = False
            self._safe_close()

    def _safe_close(self):
        try:
            if self.pipeline:
                self.pipeline.stop()
                self.pipeline = None
        except Exception:
            pass

    # ── Frame capture ────────────────────────────────────────────────────────

    def _capture_loop(self):
        """Capture frames from camera queue"""
        while self.running:
            try:
                if self.color_queue:
                    in_video = self.color_queue.get()
                    if in_video is not None:
                        self.latest_color = in_video.getCvFrame()
                
                if self.depth_queue:
                    in_depth = self.depth_queue.get()
                    if in_depth is not None:
                        raw_depth = in_depth.getFrame()
                        if raw_depth is not None:
                            # Convert to meters (depth is in mm from device)
                            self.latest_depth = raw_depth.astype(np.float32) / 1000.0
                
                # Update FPS
                self.frame_count += 1
                elapsed = time.time() - self.fps_start_time
                if elapsed > 0:
                    self.fps = self.frame_count / elapsed
                    
            except Exception as e:
                self.logger.debug(f"Capture error: {e}")
                time.sleep(0.01)

    # ── Public frame API ─────────────────────────────────────────────────────

    def get_frames(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        return self.latest_color, self.latest_depth

    def get_fps(self) -> float:
        return self.fps

    def get_depth_colormap(self, depth_frame: np.ndarray) -> np.ndarray:
        blank = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        if depth_frame is None or depth_frame.size == 0:
            return blank

        h, w  = depth_frame.shape[:2]
        valid = (depth_frame > 0) & np.isfinite(depth_frame)
        if not np.any(valid):
            return np.zeros((h, w, 3), dtype=np.uint8)

        vd  = depth_frame[valid]
        p5  = np.percentile(vd, 5)
        p95 = np.percentile(vd, 95)
        if p95 <= p5:
            return np.zeros((h, w, 3), dtype=np.uint8)

        scaled = np.clip((depth_frame - p5) / (p95 - p5) * 255, 0, 255).astype(np.uint8)
        return cv2.applyColorMap(scaled, cv2.COLORMAP_TURBO)

    # ── Mode toggle ──────────────────────────────────────────────────────────

    def toggle_measurement_mode(self) -> Dict[str, Any]:
        if self.measurement_mode == MeasurementMode.LIVE_CONTINUOUS:
            self.measurement_mode = MeasurementMode.BURST_CAPTURE
            self.state = MeasurementState.LIVE
            return {'success': True, 'message': 'Switched to BURST CAPTURE'}
        else:
            self.measurement_mode = MeasurementMode.LIVE_CONTINUOUS
            self.state = MeasurementState.LIVE
            self.reset_live_continuous()
            return {'success': True, 'message': 'Switched to LIVE CONTINUOUS'}

    # ── Live-continuous ──────────────────────────────────────────────────────

    def mark_point_live_continuous(self, x: int, y: int) -> Dict[str, Any]:
        if self.measurement_mode != MeasurementMode.LIVE_CONTINUOUS:
            return {'success': False, 'message': 'Not in live continuous mode'}
        if len(self.live_points) >= 2:
            self.live_points = [(x, y)]
            self.live_measurements = []
            self.live_is_measuring = True
            return {'success': True, 'message': f'P1 reset at ({x},{y})', 'measuring': False}
        self.live_points.append((x, y))
        if len(self.live_points) == 1:
            return {'success': True, 'message': f'P1 set at ({x},{y})', 'measuring': False}
        self.live_is_measuring = True
        return {'success': True, 'message': f'P2 set at ({x},{y}) – Measuring', 'measuring': True}

    def process_live_continuous_measurement(self, depth_frame: np.ndarray) -> Dict[str, Any]:
        if not self.live_is_measuring or len(self.live_points) < 2 or depth_frame is None:
            return {'invalid': True}
        x1, y1 = self.live_points[0]
        x2, y2 = self.live_points[1]
        h, w   = depth_frame.shape[:2]
        if x1 >= w or x2 >= w or y1 >= h or y2 >= h:
            return {'invalid': True}
        z1 = float(depth_frame[y1, x1]) if np.isfinite(depth_frame[y1, x1]) else 0.0
        z2 = float(depth_frame[y2, x2]) if np.isfinite(depth_frame[y2, x2]) else 0.0
        if z1 <= 0 or z2 <= 0:
            return {'invalid': True}
        d = self._calculate_distance_between_points(x1, y1, z1, x2, y2, z2)
        self.live_pipe_length = d
        self.live_measurements.append(d)
        return {'invalid': False, 'pipe_length': d,
                'point1': (x1, y1, z1), 'point2': (x2, y2, z2)}

    def finalize_live_measurement(self) -> Dict[str, Any]:
        if not self.live_measurements:
            return {'success': False, 'message': 'No measurements taken'}
        avg = float(np.mean(self.live_measurements))
        std = float(np.std(self.live_measurements))
        return {'success': True, 'message': f'{avg:.4f}m ± {std:.4f}m',
                'average': avg, 'std': std, 'count': len(self.live_measurements)}

    def reset_live_continuous(self):
        self.live_points       = []
        self.live_pipe_length  = None
        self.live_measurements = []
        self.live_is_measuring = False

    # ── Burst capture ────────────────────────────────────────────────────────

    def start_burst_capture(self) -> Dict[str, Any]:
        if self.state != MeasurementState.LIVE:
            return {'success': False, 'message': 'Not in live state'}
        self.burst_color_frames      = []
        self.burst_depth_frames      = []
        self.burst_results           = []
        self.burst_current_index     = 0
        self.burst_pending_points    = []
        self.burst_carry_over_points = []
        self.state = MeasurementState.CAPTURING
        return {'success': True, 'message': f'Capturing {self.num_frames} frames …'}

    def capture_burst_frame(self, color_frame, depth_frame):
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

    def _burst_depth_z(self, x, y):
        d = self.frozen_depth_frame
        if d is None or y >= d.shape[0] or x >= d.shape[1]:
            return 0.0
        v = float(d[y, x])
        return v if np.isfinite(v) else 0.0

    def mark_burst_point(self, x: int, y: int) -> Dict[str, Any]:
        if self.state != MeasurementState.BURST_ANNOTATING:
            return {'success': False, 'message': 'Not annotating'}
        if not self.burst_color_frames:
            return {'success': False, 'message': 'No frames captured'}
        self.burst_pending_points    = [(x, y, self._burst_depth_z(x, y))]
        self.burst_carry_over_points = []
        return {'success': True, 'message': f'P1 at ({x},{y})'}

    def mark_burst_second_point(self, x: int, y: int) -> Dict[str, Any]:
        if self.state != MeasurementState.BURST_ANNOTATING:
            return {'success': False, 'message': 'Not annotating'}
        if len(self.burst_pending_points) != 1:
            return {'success': False, 'message': 'P1 not set'}
        self.burst_pending_points.append((x, y, self._burst_depth_z(x, y)))
        return {'success': True, 'message': f'P2 at ({x},{y})'}

    def clear_burst_points(self):
        self.burst_pending_points = []

    def accept_burst_points(self) -> Dict[str, Any]:
        if len(self.burst_pending_points) != 2:
            return {'success': False, 'message': 'Need 2 points'}
        p1, p2 = self.burst_pending_points
        d = self._calculate_distance_between_points(p1[0],p1[1],p1[2],p2[0],p2[1],p2[2])
        self.burst_results.append({'frame_index': self.burst_current_index,
                                   'point1': p1, 'point2': p2, 'distance': d})
        self.burst_carry_over_points = self.burst_pending_points.copy()
        self.burst_pending_points    = []
        nxt = self.burst_current_index + 1
        if nxt >= len(self.burst_color_frames):
            self.state = MeasurementState.BURST_DONE
            return {'success': True, 'complete': True, 'total': len(self.burst_results)}
        self.burst_current_index = nxt
        self.frozen_color_frame  = self.burst_color_frames[nxt].copy()
        self.frozen_depth_frame  = self.burst_depth_frames[nxt].copy()
        return {'success': True, 'complete': False, 'frame_index': nxt}

    def accept_carry_over(self) -> Dict[str, Any]:
        if len(self.burst_carry_over_points) != 2:
            return {'success': False, 'message': 'No carry-over'}
        if self.burst_current_index == 0:
            return {'success': False, 'message': 'At frame 0'}
        self.burst_pending_points = self.burst_carry_over_points.copy()
        return self.accept_burst_points()

    def skip_frame(self) -> Dict[str, Any]:
        if self.state != MeasurementState.BURST_ANNOTATING:
            return {'success': False, 'message': 'Not annotating'}
        self.burst_results.append({'frame_index': self.burst_current_index,
                                   'point1': None, 'point2': None,
                                   'distance': None, 'skipped': True})
        self.burst_carry_over_points = []
        self.burst_pending_points    = []
        nxt = self.burst_current_index + 1
        if nxt >= len(self.burst_color_frames):
            self.state = MeasurementState.BURST_DONE
            return {'success': True, 'complete': True}
        self.burst_current_index = nxt
        self.frozen_color_frame  = self.burst_color_frames[nxt].copy()
        self.frozen_depth_frame  = self.burst_depth_frames[nxt].copy()
        return {'success': True, 'complete': False, 'frame_index': nxt}

    def go_back(self) -> Dict[str, Any]:
        if self.state != MeasurementState.BURST_ANNOTATING:
            return {'success': False, 'message': 'Not annotating'}
        if self.burst_current_index == 0:
            return {'success': False, 'message': 'At first frame'}
        if self.burst_results:
            self.burst_results.pop()
        prev = self.burst_current_index - 1
        self.burst_current_index     = prev
        self.frozen_color_frame      = self.burst_color_frames[prev].copy()
        self.frozen_depth_frame      = self.burst_depth_frames[prev].copy()
        self.burst_pending_points    = []
        self.burst_carry_over_points = []
        return {'success': True, 'frame_index': prev}

    def get_burst_summary(self) -> Dict[str, Any]:
        valid = [r['distance'] for r in self.burst_results
                 if r.get('distance') is not None and not r.get('skipped')]
        if not valid:
            return {'success': False, 'message': 'No valid measurements'}
        return {'success': True, 'num_measurements': len(valid),
                'average_distance': float(np.mean(valid)),
                'std_distance':     float(np.std(valid)),
                'min_distance':     float(np.min(valid)),
                'max_distance':     float(np.max(valid)),
                'distances': valid}

    def reset_to_live(self):
        self.state = MeasurementState.LIVE
        self.burst_color_frames      = []
        self.burst_depth_frames      = []
        self.burst_results           = []
        self.burst_current_index     = 0
        self.burst_pending_points    = []
        self.burst_carry_over_points = []
        self.frozen_color_frame      = None
        self.frozen_depth_frame      = None

    # ── Distance math ────────────────────────────────────────────────────────

    def _deproject_to_3d(self, u: int, v: int, z: float) -> tuple:
        """
        Deproject 2D pixel coordinates + depth to 3D camera coordinates.
        Uses OAK-D camera intrinsics for accurate 3D reconstruction.
        
        Args:
            u, v: pixel coordinates (x, y)
            z: depth in meters
        Returns:
            (X, Y, Z) in meters, camera coordinate system
        """
        if z <= 0 or not np.isfinite(z):
            return (0.0, 0.0, 0.0)
        # Standard pinhole camera deprojection
        # X = (u - cx) * Z / fx
        # Y = (v - cy) * Z / fy
        # Z = depth
        X = (u - self.cx) * z / self.fx
        Y = (v - self.cy) * z / self.fy
        return (X, Y, z)

    def _calculate_distance_between_points(self, x1, y1, z1, x2, y2, z2) -> float:
        """
        Calculate 3D distance between two points using proper camera 3D coordinates.
        x1,y1,x2,y2: pixel coordinates
        z1,z2: depth in meters (from OAK-D depth frame)
        """
        # Deproject both points to 3D camera coordinates
        X1, Y1, Z1 = self._deproject_to_3d(x1, y1, z1)
        X2, Y2, Z2 = self._deproject_to_3d(x2, y2, z2)

        # Euclidean distance in 3D camera space
        dx = X1 - X2
        dy = Y1 - Y2
        dz = Z1 - Z2
        distance = np.sqrt(dx**2 + dy**2 + dz**2)
        return float(distance)

    # ── Cleanup ──────────────────────────────────────────────────────────────

    def cleanup(self):
        self.running = False
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2)
        self._safe_close()