"""
RealSense Camera Wrapper
========================
Simplified interface for Intel RealSense D415 camera.
"""

import numpy as np
import cv2
import logging
from typing import Tuple, Optional

try:
    import pyrealsense2 as rs
    REALSENSE_AVAILABLE = True
except ImportError:
    REALSENSE_AVAILABLE = False
    logging.warning("pyrealsense2 not available")


class RealSenseCamera:
    """Wrapper for RealSense camera operations."""
    
    def __init__(self, width=1280, height=720, fps=30, enable_depth=True, enable_color=True):
        """
        Initialize RealSense camera.
        
        Args:
            width: Frame width
            height: Frame height
            fps: Frame rate
            enable_depth: Enable depth stream
            enable_color: Enable color stream
        """
        if not REALSENSE_AVAILABLE:
            raise ImportError("pyrealsense2 not installed")
        
        self.width = width
        self.height = height
        self.fps = fps
        
        self.pipeline = rs.pipeline()
        self.config = rs.config()
        self.align = None
        
        # Configure streams
        if enable_depth:
            self.config.enable_stream(rs.stream.depth, width, height, rs.format.z16, fps)
        if enable_color:
            self.config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, fps)
        
        self.profile = None
        self.depth_sensor = None
        
        logging.info(f"RealSenseCamera configured: {width}x{height}@{fps}fps")
    
    def start(self, preset='high_accuracy'):
        """
        Start the camera pipeline.
        
        Args:
            preset: Depth preset ('high_accuracy', 'high_density', 'medium_density')
        """
        self.profile = self.pipeline.start(self.config)
        
        # Get depth sensor
        device = self.profile.get_device()
        self.depth_sensor = device.first_depth_sensor()
        
        # Set preset for underwater performance
        presets = {
            'high_accuracy': 3,
            'high_density': 4,
            'medium_density': 5
        }
        preset_value = presets.get(preset, 3)
        self.depth_sensor.set_option(rs.option.visual_preset, preset_value)
        
        # Create alignment object
        self.align = rs.align(rs.stream.color)
        
        logging.info(f"Camera started with preset: {preset}")
    
    def get_frames(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Get aligned color and depth frames.
        
        Returns:
            (color_frame, depth_frame) as numpy arrays
        """
        try:
            frames = self.pipeline.wait_for_frames()
            aligned_frames = self.align.process(frames)
            
            color_frame = aligned_frames.get_color_frame()
            depth_frame = aligned_frames.get_depth_frame()
            
            if not color_frame or not depth_frame:
                return None, None
            
            color_image = np.asanyarray(color_frame.get_data())
            depth_image = np.asanyarray(depth_frame.get_data())
            
            return color_image, depth_image
        
        except Exception as e:
            logging.error(f"Error getting frames: {e}")
            return None, None
    
    def get_depth_scale(self) -> float:
        """Get depth scale (meters per unit)."""
        return self.depth_sensor.get_depth_scale()
    
    def stop(self):
        """Stop the camera pipeline."""
        if self.pipeline:
            self.pipeline.stop()
            logging.info("Camera stopped")


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    camera = RealSenseCamera()
    camera.start()
    
    try:
        while True:
            color, depth = camera.get_frames()
            if color is not None:
                cv2.imshow('Color', color)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        camera.stop()
        cv2.destroyAllWindows()
