import numpy as np
import depthai as dai
import cv2
import threading
import time
import logging
from enum import Enum
from typing import Optional, Tuple, List, Dict, Any


class MeasurementState(Enum):
    LIVE = 'live'
    CAPTURING = 'capturing'
    BURST_ANNOTATING = 'burst_annotating'
    BURST_DONE = 'burst_done'


class MeasurementMode(Enum):
    LIVE_CONTINUOUS = 'live_continuous'
    BURST_CAPTURE = 'burst_capture'


class PipeLengthMeasurement:
    """Main measurement class handling camera and measurement logic."""
    
    def __init__(self, num_frames: int = 30):
        self.logger = logging.getLogger(__name__)
        self.num_frames = num_frames
        
        self.state = MeasurementState.LIVE
        self.measurement_mode = MeasurementMode.LIVE_CONTINUOUS
        
        self.pipeline = None
        self.device = None
        self.color_queue = None
        self.depth_queue = None
        self.frame_count = 0
        self.fps = 0
        self.fps_counter = 0
        self.fps_start_time = time.time()
        
        self.color_frame = None
        self.depth_frame = None
        self.latest_color = None
        self.latest_depth = None
        self.capture_thread = None
        self.running = True
        
        self.live_points = []
        self.live_pipe_length = None
        self.live_measurements = []
        self.live_is_measuring = False
        
        self.burst_color_frames = []
        self.burst_depth_frames = []
        self.burst_results = []
        self.burst_current_index = 0
        self.burst_pending_points = []
        self.burst_carry_over_points = []
        self.frozen_color_frame = None
        self.frozen_depth_frame = None
        
        self.width = 1280
        self.height = 720
        
        self._init_camera()
    
    def _init_camera(self):
        """Initialize the OAK-D PoE camera - MINIMAL PIPELINE FOR DIAGNOSTICS."""
        try:
            self.pipeline = dai.Pipeline()
            
            cam = self.pipeline.createColorCamera()
            cam.setPreviewSize(1280, 720)
            cam.setInterleaved(False)
            cam.setFps(30)
            
            mono_left = self.pipeline.createMonoCamera()
            mono_left.setBoardSocket(dai.CameraBoardSocket.LEFT)
            mono_left.setFps(30)
            
            mono_right = self.pipeline.createMonoCamera()
            mono_right.setBoardSocket(dai.CameraBoardSocket.RIGHT)
            mono_right.setFps(30)
            
            stereo = self.pipeline.createStereoDepth()
            stereo.setConfidenceThreshold(255)
            stereo.initialConfig.setMedianFilter(dai.MedianFilter.MEDIAN_OFF)
            stereo.setLeftRightCheck(False)
            stereo.setSubpixel(False)
            stereo.setExtendedDisparity(False)
            
            mono_left.out.link(stereo.left)
            mono_right.out.link(stereo.right)
            
            xout_color = self.pipeline.createXLinkOut()
            xout_color.setStreamName("color")
            xout_color.setBlocking(False)
            cam.preview.link(xout_color.input)
            
            xout_depth = self.pipeline.createXLinkOut()
            xout_depth.setStreamName("depth")
            xout_depth.setBlocking(False)
            stereo.depth.link(xout_depth.input)
            
            self.device = dai.Device(self.pipeline)
            self.device.startPipeline()
            
            self.color_queue = self.device.getOutputQueue(name="color", maxSize=8, blocking=False)
            self.depth_queue = self.device.getOutputQueue(name="depth", maxSize=8, blocking=False)
            
            self.diag_zero_count = 0
            self.diag_total_pixels = 0
            
            self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.capture_thread.start()
            
            self.logger.info("Camera initialized - MINIMAL PIPELINE (filters disabled)")
        except Exception as e:
            self.logger.error(f"Camera initialization failed: {e}")
            raise
    
    def _capture_loop(self):
        """Background thread for non-blocking frame capture WITH DIAGNOSTICS."""
        last_diag_time = time.time()
        while self.running:
            loop_start = time.time()
            
            try:
                color_msg = self.color_queue.tryGet()
                color_time = time.time()
                
                if color_msg:
                    self.latest_color = color_msg.getCvFrame()
                
                depth_msg = self.depth_queue.tryGet()
                depth_time = time.time()
                
                if depth_msg:
                    raw_depth = depth_msg.getFrame()
                    if raw_depth is not None:
                        self.latest_depth = raw_depth.astype(np.float32) / 1000.0
                        
                        if self.frame_count % 30 == 0:
                            total_pixels = raw_depth.size
                            zero_pixels = np.sum(raw_depth == 0)
                            pct_zero = (zero_pixels / total_pixels) * 100
                            raw_min = float(np.min(raw_depth))
                            raw_max = float(np.max(raw_depth))
                            
                            self.logger.info(
                                f"[DIAG DEPTH] frame={self.frame_count} "
                                f"dtype={raw_depth.dtype} shape={raw_depth.shape} "
                                f"raw_min={raw_min:.1f} raw_max={raw_max:.1f} "
                                f"zero_pct={pct_zero:.2f}%"
                            )
                            
                            if pct_zero > 95:
                                self.logger.warning(
                                    f"[CRITICAL] {pct_zero:.1f}% of depth pixels are 0! "
                                    f"Stereo matching is failing."
                                )
                
                self.frame_count += 1
                loop_time = (time.time() - loop_start) * 1000
                
                if self.frame_count % 30 == 0:
                    elapsed = time.time() - self.fps_start_time
                    self.fps = self.frame_count / elapsed if elapsed > 0 else 0
                    self.logger.info(
                        f"[DIAG FPS] current={self.fps:.1f} "
                        f"loop_ms={loop_time:.1f} color_queue_ms={(color_time - loop_start)*1000:.1f} "
                        f"depth_queue_ms={(depth_time - color_time)*1000:.1f}"
                    )
                
            except Exception as e:
                self.logger.debug(f"Capture loop error: {e}")
                time.sleep(0.01)
    
    def get_frames(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Get current color and depth frames."""
        return self.latest_color, self.latest_depth
    
    def get_fps(self) -> float:
        """Get current FPS."""
        return self.fps
    
    def get_depth_colormap(self, depth_frame: np.ndarray) -> np.ndarray:
        """Convert depth frame to colormap for display WITH DIAGNOSTICS."""
        if depth_frame is None:
            return np.zeros((480, 640, 3), dtype=np.uint8)
        
        if depth_frame.size == 0:
            return np.zeros((480, 640, 3), dtype=np.uint8)
        
        h, w = depth_frame.shape[:2]
        
        valid_mask = (depth_frame > 0) & ~np.isnan(depth_frame) & ~np.isinf(depth_frame)
        valid_count = np.sum(valid_mask)
        total_count = depth_frame.size
        valid_pct = (valid_count / total_count) * 100 if total_count > 0 else 0
        
        if valid_count == 0:
            self.logger.warning("[DIAG COLORMAP] No valid depth pixels - returning black frame")
            return np.zeros((h, w, 3), dtype=np.uint8)
        
        valid_depth = depth_frame[valid_mask]
        p5 = np.percentile(valid_depth, 5)
        p95 = np.percentile(valid_depth, 95)
        
        if p95 <= p5:
            self.logger.warning(f"[DIAG COLORMAP] p5={p5:.3f} >= p95={p95:.3f} - collapsing")
            return np.zeros((h, w, 3), dtype=np.uint8)
        
        depth_scaled = np.clip((depth_frame - p5) / (p95 - p5) * 255, 0, 255).astype(np.uint8)
        
        if self.frame_count % 30 == 0:
            self.logger.info(
                f"[DIAG COLORMAP] frame={self.frame_count} "
                f"valid_pct={valid_pct:.1f}% p5={p5:.3f}m p95={p95:.3f}m "
                f"depth_min={float(np.min(valid_depth)):.3f}m depth_max={float(np.max(valid_depth)):.3f}m"
            )
        
        return cv2.applyColorMap(depth_scaled, cv2.COLORMAP_TURBO)
    
    def toggle_measurement_mode(self) -> Dict[str, Any]:
        """Toggle between Live Continuous and Burst Capture modes."""
        if self.measurement_mode == MeasurementMode.LIVE_CONTINUOUS:
            self.measurement_mode = MeasurementMode.BURST_CAPTURE
            self.state = MeasurementState.LIVE
            return {'success': True, 'message': 'Switched to BURST CAPTURE mode'}
        else:
            self.measurement_mode = MeasurementMode.LIVE_CONTINUOUS
            self.state = MeasurementState.LIVE
            self.reset_live_continuous()
            return {'success': True, 'message': 'Switched to LIVE CONTINUOUS mode'}
    
    def mark_point_live_continuous(self, x: int, y: int) -> Dict[str, Any]:
        """Mark a point in live continuous mode."""
        if self.measurement_mode != MeasurementMode.LIVE_CONTINUOUS:
            return {'success': False, 'message': 'Not in live continuous mode'}
        
        if len(self.live_points) >= 2:
            self.live_points = [(x, y)]
            self.live_measurements = []
            self.live_is_measuring = True
            return {'success': True, 'message': f'P1 set at ({x}, {y}) - Reset', 'measuring': False}
        
        self.live_points.append((x, y))
        
        if len(self.live_points) == 1:
            return {'success': True, 'message': f'P1 set at ({x}, {y})', 'measuring': False}
        
        self.live_is_measuring = True
        return {'success': True, 'message': f'P2 set at ({x}, {y}) - Measuring', 'measuring': True}
    
    def process_live_continuous_measurement(self, depth_frame: np.ndarray) -> Dict[str, Any]:
        """Process live continuous measurement."""
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
        
        distance = self._calculate_distance_between_points(x1, y1, z1, x2, y2, z2)
        
        self.live_pipe_length = distance
        self.live_measurements.append(distance)
        
        return {
            'invalid': False,
            'pipe_length': distance,
            'point1': (x1, y1, z1),
            'point2': (x2, y2, z2)
        }
    
    def finalize_live_measurement(self) -> Dict[str, Any]:
        """Finalize live measurement and calculate statistics."""
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
        """Capture a single frame during burst mode."""
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
        distance = self._calculate_distance_between_points(
            p1[0], p1[1], p1[2], p2[0], p2[1], p2[2]
        )
        
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
            'average_distance': np.mean(valid_distances),
            'std_distance': np.std(valid_distances),
            'min_distance': np.min(valid_distances),
            'max_distance': np.max(valid_distances),
            'distances': valid_distances
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
    
    def _calculate_distance_between_points(self, x1: int, y1: int, z1: float, 
                                          x2: int, y2: int, z2: float) -> float:
        """Calculate 3D Euclidean distance between two points."""
        dx = x1 - x2
        dy = y1 - y2
        dz = z1 - z2
        
        pixel_distance = np.sqrt(dx**2 + dy**2)
        real_distance = np.sqrt(pixel_distance**2 * (z1 + z2)**2 / 4 + dz**2)
        
        return real_distance * 0.001
    
    def cleanup(self):
        """Cleanup camera resources."""
        self.running = False
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=1)
        if self.device:
            self.device.close()
