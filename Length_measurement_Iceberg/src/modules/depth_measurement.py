"""
Depth Measurement Module
========================
Measures keel depth using Intel RealSense D415 stereo depth camera.
Provides accurate depth measurements for the iceberg keel (0.5m - 1.5m range).
"""

import numpy as np
import cv2
from typing import Tuple, Optional, Dict
import logging
from collections import deque
import time

try:
    import pyrealsense2 as rs
    REALSENSE_AVAILABLE = True
except ImportError:
    REALSENSE_AVAILABLE = False
    logging.warning("pyrealsense2 not available. Install with: pip install pyrealsense2")


class DepthMeasurement:
    """Handles depth measurement for keel depth calculation."""
    
    def __init__(self, width=1280, height=720, fps=30, 
                 measurement_samples=20, filter_outliers=True):
        """
        Initialize depth measurement system.
        
        Args:
            width: Camera resolution width
            height: Camera resolution height
            fps: Frame rate
            measurement_samples: Number of samples to average for accuracy
            filter_outliers: Whether to filter outlier measurements
        """
        self.width = width
        self.height = height
        self.fps = fps
        self.measurement_samples = measurement_samples
        self.filter_outliers = filter_outliers
        
        # Measurement buffer for averaging
        self.depth_buffer = deque(maxlen=measurement_samples)
        
        # RealSense pipeline and config
        self.pipeline = None
        self.config = None
        self.align = None
        
        if REALSENSE_AVAILABLE:
            self._initialize_camera()
        
        logging.info("DepthMeasurement initialized")
    
    def _initialize_camera(self):
        """Initialize RealSense camera pipeline."""
        try:
            self.pipeline = rs.pipeline()
            self.config = rs.config()
            
            # Configure streams
            self.config.enable_stream(rs.stream.depth, self.width, self.height, 
                                     rs.format.z16, self.fps)
            self.config.enable_stream(rs.stream.color, self.width, self.height, 
                                     rs.format.bgr8, self.fps)
            
            # Start pipeline
            profile = self.pipeline.start(self.config)
            
            # Get depth sensor and configure settings for underwater
            depth_sensor = profile.get_device().first_depth_sensor()
            
            # Set preset for better underwater performance
            # Preset 4 = High Accuracy, good for static measurements
            depth_sensor.set_option(rs.option.visual_preset, 4)
            
            # Align depth frame to color frame
            self.align = rs.align(rs.stream.color)
            
            logging.info("RealSense camera initialized successfully")
            
        except Exception as e:
            logging.error(f"Failed to initialize RealSense camera: {e}")
            raise
    
    def get_frames(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Get aligned color and depth frames from camera.
        
        Returns:
            (color_frame, depth_frame) as numpy arrays
            color_frame: BGR image (H, W, 3)
            depth_frame: Depth in millimeters (H, W)
        """
        if not self.pipeline:
            logging.error("Camera not initialized")
            return None, None
        
        try:
            # Wait for frames
            frames = self.pipeline.wait_for_frames()
            
            # Align depth to color
            aligned_frames = self.align.process(frames)
            
            # Get aligned frames
            color_frame = aligned_frames.get_color_frame()
            depth_frame = aligned_frames.get_depth_frame()
            
            if not color_frame or not depth_frame:
                return None, None
            
            # Convert to numpy arrays
            color_image = np.asanyarray(color_frame.get_data())
            depth_image = np.asanyarray(depth_frame.get_data())
            
            return color_image, depth_image
            
        except Exception as e:
            logging.error(f"Error getting frames: {e}")
            return None, None
    
    def measure_depth_at_point(self, depth_frame: np.ndarray, 
                               x: int, y: int, 
                               roi_size: int = 20) -> Optional[float]:
        """
        Measure depth at a specific point with averaging over ROI.
        
        Args:
            depth_frame: Depth frame from camera (in mm)
            x: X coordinate of point
            y: Y coordinate of point
            roi_size: Size of region around point to average
            
        Returns:
            Depth in meters, or None if invalid
        """
        h, w = depth_frame.shape
        
        # Define ROI bounds
        x1 = max(0, x - roi_size // 2)
        x2 = min(w, x + roi_size // 2)
        y1 = max(0, y - roi_size // 2)
        y2 = min(h, y + roi_size // 2)
        
        # Extract ROI
        roi = depth_frame[y1:y2, x1:x2]
        
        # Filter out zeros (invalid depth)
        valid_depths = roi[roi > 0]
        
        if len(valid_depths) == 0:
            return None
        
        # Use median to reduce noise and outliers
        depth_mm = np.median(valid_depths)
        
        # Convert to meters
        depth_m = depth_mm / 1000.0
        
        return depth_m
    
    def measure_keel_depth(self, depth_frame: np.ndarray, 
                          roi: Optional[Tuple[int, int, int, int]] = None,
                          surface_depth: Optional[float] = None) -> Dict:
        """
        Measure the depth of the iceberg keel.
        
        Args:
            depth_frame: Depth frame from camera (in mm)
            roi: Region of interest for keel (x, y, w, h). If None, uses center
            surface_depth: Known depth to surface (for calculating keel length)
            
        Returns:
            Dictionary with measurement results:
            {
                'keel_depth': float (meters from surface),
                'raw_depth': float (meters from camera),
                'confidence': float (0-1),
                'valid': bool
            }
        """
        # Use center of frame if no ROI specified
        if roi is None:
            h, w = depth_frame.shape
            roi = (w//2 - 50, h//2 - 50, 100, 100)
        
        x, y, w, h = roi
        
        # Get center point of ROI
        center_x = x + w // 2
        center_y = y + h // 2
        
        # Measure depth at keel
        keel_raw_depth = self.measure_depth_at_point(depth_frame, center_x, center_y, 
                                                     roi_size=min(w, h))
        
        if keel_raw_depth is None:
            return {
                'keel_depth': None,
                'raw_depth': None,
                'confidence': 0.0,
                'valid': False
            }
        
        # Add to buffer for averaging
        self.depth_buffer.append(keel_raw_depth)
        
        # Calculate averaged depth
        if self.filter_outliers:
            averaged_depth = self._calculate_filtered_average()
        else:
            averaged_depth = np.mean(list(self.depth_buffer))
        
        # Calculate confidence based on stability
        confidence = self._calculate_confidence()
        
        # If we know surface depth, calculate keel depth from surface
        if surface_depth is not None:
            keel_depth = averaged_depth - surface_depth
        else:
            # Assume surface is at minimum stable depth in field of view
            keel_depth = averaged_depth
        
        return {
            'keel_depth': keel_depth,
            'raw_depth': averaged_depth,
            'confidence': confidence,
            'valid': True
        }
    
    def _calculate_filtered_average(self) -> float:
        """Calculate average depth with outlier filtering (IQR method)."""
        if len(self.depth_buffer) < 3:
            return np.mean(list(self.depth_buffer))
        
        depths = np.array(list(self.depth_buffer))
        
        # Calculate quartiles
        q1 = np.percentile(depths, 25)
        q3 = np.percentile(depths, 75)
        iqr = q3 - q1
        
        # Filter outliers
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        filtered = depths[(depths >= lower_bound) & (depths <= upper_bound)]
        
        if len(filtered) == 0:
            return np.mean(depths)
        
        return np.mean(filtered)
    
    def _calculate_confidence(self) -> float:
        """
        Calculate measurement confidence based on stability.
        
        Returns:
            Confidence score 0-1, where 1 is most confident
        """
        if len(self.depth_buffer) < 5:
            return 0.5  # Medium confidence with few samples
        
        depths = np.array(list(self.depth_buffer))
        
        # Calculate coefficient of variation (std / mean)
        std = np.std(depths)
        mean = np.mean(depths)
        
        if mean == 0:
            return 0.0
        
        cv = std / mean
        
        # Convert CV to confidence (lower CV = higher confidence)
        # CV < 0.01 = very stable = 1.0 confidence
        # CV > 0.05 = unstable = 0.0 confidence
        confidence = 1.0 - min(cv / 0.05, 1.0)
        
        return confidence
    
    def reset_measurement(self):
        """Clear measurement buffer for new measurement."""
        self.depth_buffer.clear()
        logging.info("Measurement buffer reset")
    
    def get_depth_colormap(self, depth_frame: np.ndarray) -> np.ndarray:
        """
        Create colorized depth visualization.
        
        Args:
            depth_frame: Depth frame in millimeters
            
        Returns:
            Colorized depth image (BGR)
        """
        # Normalize depth for visualization (0-3000mm range typical for this task)
        depth_normalized = np.clip(depth_frame, 0, 3000) / 3000.0 * 255
        depth_normalized = depth_normalized.astype(np.uint8)
        
        # Apply colormap
        depth_colormap = cv2.applyColorMap(depth_normalized, cv2.COLORMAP_JET)
        
        return depth_colormap
    
    def validate_accuracy(self, measured_depth: float, 
                         true_depth: Optional[float] = None) -> Dict:
        """
        Validate measurement accuracy against requirements.
        
        Competition requirements:
        - Within ±5cm: 10 points
        - Within ±5.01-10cm: 5 points
        - Beyond ±10cm: 0 points
        
        Args:
            measured_depth: Measured keel depth in meters
            true_depth: Known true depth (for validation/testing)
            
        Returns:
            {
                'points': int (10, 5, or 0),
                'error': float (in meters),
                'within_tolerance': bool
            }
        """
        result = {
            'points': 0,
            'error': None,
            'within_tolerance': False
        }
        
        if true_depth is None:
            logging.warning("No true depth provided for validation")
            return result
        
        # Calculate error in meters
        error = abs(measured_depth - true_depth)
        result['error'] = error
        
        # Determine points based on accuracy
        if error <= 0.05:  # Within 5cm
            result['points'] = 10
            result['within_tolerance'] = True
        elif error <= 0.10:  # Within 5.01-10cm
            result['points'] = 5
            result['within_tolerance'] = True
        else:  # Beyond 10cm
            result['points'] = 0
            result['within_tolerance'] = False
        
        logging.info(f"Validation: Error={error*100:.2f}cm, Points={result['points']}")
        
        return result
    
    def stop(self):
        """Stop the camera pipeline."""
        if self.pipeline:
            self.pipeline.stop()
            logging.info("Camera pipeline stopped")


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Initialize depth measurement
    dm = DepthMeasurement()
    
    try:
        # Continuous measurement
        print("Measuring depth... Press 'q' to quit, 'r' to reset, 's' to save")
        
        while True:
            color_frame, depth_frame = dm.get_frames()
            
            if color_frame is None or depth_frame is None:
                continue
            
            # Measure keel depth at center
            result = dm.measure_keel_depth(depth_frame)
            
            # Create visualization
            depth_colormap = dm.get_depth_colormap(depth_frame)
            
            # Draw measurement info on color frame
            if result['valid']:
                text = f"Depth: {result['keel_depth']:.3f}m | Conf: {result['confidence']:.2f}"
                color = (0, 255, 0) if result['confidence'] > 0.8 else (0, 165, 255)
                cv2.putText(color_frame, text, (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            
            # Draw crosshair at center
            h, w = color_frame.shape[:2]
            cv2.drawMarker(color_frame, (w//2, h//2), (0, 255, 0), 
                          cv2.MARKER_CROSS, 20, 2)
            
            # Display
            combined = np.hstack((color_frame, depth_colormap))
            cv2.imshow('Keel Depth Measurement', combined)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('r'):
                dm.reset_measurement()
                print("Measurement reset")
            elif key == ord('s'):
                if result['valid']:
                    print(f"Saved: {result['keel_depth']:.3f}m (confidence: {result['confidence']:.2f})")
    
    finally:
        dm.stop()
        cv2.destroyAllWindows()
