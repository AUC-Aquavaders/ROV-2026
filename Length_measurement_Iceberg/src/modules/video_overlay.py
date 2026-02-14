"""
Video Overlay Module
====================
Provides HUD (Heads-Up Display) overlays for operator and judge.
Displays survey progress, depth measurements, and detected numbers.
"""

import cv2
import numpy as np
from typing import Tuple, List, Optional, Dict
from datetime import datetime


class VideoOverlay:
    """Create video overlays and HUD elements."""
    
    def __init__(self, frame_width: int = 1280, frame_height: int = 720):
        """
        Initialize video overlay.
        
        Args:
            frame_width: Video frame width
            frame_height: Video frame height
        """
        self.width = frame_width
        self.height = frame_height
        
        # Colors (BGR format)
        self.COLOR_GREEN = (0, 255, 0)
        self.COLOR_YELLOW = (0, 255, 255)
        self.COLOR_RED = (0, 0, 255)
        self.COLOR_ORANGE = (0, 165, 255)
        self.COLOR_WHITE = (255, 255, 255)
        self.COLOR_BLACK = (0, 0, 0)
        self.COLOR_BLUE = (255, 0, 0)
        
        # Font settings
        self.FONT = cv2.FONT_HERSHEY_SIMPLEX
        self.FONT_SCALE_LARGE = 0.8
        self.FONT_SCALE_MEDIUM = 0.6
        self.FONT_SCALE_SMALL = 0.5
        self.FONT_THICKNESS = 2
    
    def draw_hud(self, frame: np.ndarray, survey_status: Dict,
                depth_measurement: Optional[Dict] = None) -> np.ndarray:
        """
        Draw main HUD overlay with survey progress.
        
        Args:
            frame: Input video frame
            survey_status: Status from SurveyTracker.get_status()
            depth_measurement: Optional depth measurement data
            
        Returns:
            Frame with HUD overlay
        """
        overlay = frame.copy()
        
        # Draw semi-transparent background for HUD
        hud_height = 180
        cv2.rectangle(overlay, (0, 0), (self.width, hud_height), 
                     self.COLOR_BLACK, -1)
        
        # Blend with original
        alpha = 0.6
        frame = cv2.addWeighted(frame, 1, overlay, alpha, 0)
        
        # Title
        cv2.putText(frame, "ICEBERG SURVEY", (10, 30),
                   self.FONT, self.FONT_SCALE_LARGE, self.COLOR_WHITE, 
                   self.FONT_THICKNESS)
        
        # Timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")
        cv2.putText(frame, timestamp, (self.width - 120, 30),
                   self.FONT, self.FONT_SCALE_MEDIUM, self.COLOR_WHITE, 1)
        
        # Progress bar
        progress_text = f"Progress: {survey_status['corners_found']}/5 corners"
        cv2.putText(frame, progress_text, (10, 65),
                   self.FONT, self.FONT_SCALE_MEDIUM, self.COLOR_GREEN, 2)
        
        # Draw progress bar
        bar_x, bar_y = 10, 80
        bar_width = 300
        bar_height = 20
        progress_ratio = survey_status['corners_found'] / 5
        
        # Background
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height),
                     self.COLOR_WHITE, 2)
        
        # Fill
        fill_width = int(bar_width * progress_ratio)
        if fill_width > 0:
            color = self.COLOR_GREEN if survey_status['corners_found'] == 5 else self.COLOR_YELLOW
            cv2.rectangle(frame, (bar_x, bar_y), 
                         (bar_x + fill_width, bar_y + bar_height),
                         color, -1)
        
        # Numbers found
        numbers_text = f"Numbers: {survey_status['numbers']}"
        cv2.putText(frame, numbers_text, (10, 125),
                   self.FONT, self.FONT_SCALE_SMALL, self.COLOR_WHITE, 1)
        
        # Sequence validation
        if survey_status['sequence_valid']:
            seq_text = f"Sequence: {survey_status['sequence_type']} ✓"
            seq_color = self.COLOR_GREEN
        elif survey_status['sequence_type']:
            seq_text = f"Sequence: {survey_status['sequence_type']} ✗"
            seq_color = self.COLOR_RED
        else:
            seq_text = "Sequence: Detecting..."
            seq_color = self.COLOR_YELLOW
        
        cv2.putText(frame, seq_text, (10, 150),
                   self.FONT, self.FONT_SCALE_SMALL, seq_color, 2)
        
        # Keel depth
        if survey_status['keel_depth']:
            keel_text = f"Keel Depth: {survey_status['keel_depth']:.3f}m"
            keel_conf = survey_status.get('keel_confidence', 0)
            keel_color = self.COLOR_GREEN if keel_conf > 0.8 else self.COLOR_YELLOW
        else:
            keel_text = "Keel Depth: Not measured"
            keel_color = self.COLOR_ORANGE
        
        cv2.putText(frame, keel_text, (350, 65),
                   self.FONT, self.FONT_SCALE_MEDIUM, keel_color, 2)
        
        # Points
        points_text = f"Points: {survey_status['points_earned']}/35"
        cv2.putText(frame, points_text, (350, 100),
                   self.FONT, self.FONT_SCALE_MEDIUM, self.COLOR_WHITE, 2)
        
        # Status indicator
        if survey_status['complete']:
            status_text = "COMPLETE ✓"
            status_color = self.COLOR_GREEN
        else:
            status_text = "IN PROGRESS"
            status_color = self.COLOR_YELLOW
        
        cv2.putText(frame, status_text, (350, 135),
                   self.FONT, self.FONT_SCALE_MEDIUM, status_color, 2)
        
        return frame
    
    def draw_crosshair(self, frame: np.ndarray, size: int = 30,
                      color: Tuple[int, int, int] = None) -> np.ndarray:
        """
        Draw crosshair at center of frame.
        
        Args:
            frame: Input frame
            size: Crosshair size
            color: Color (BGR), defaults to green
            
        Returns:
            Frame with crosshair
        """
        if color is None:
            color = self.COLOR_GREEN
        
        center_x = self.width // 2
        center_y = self.height // 2
        
        # Draw crosshair lines
        cv2.line(frame, (center_x - size, center_y), 
                (center_x + size, center_y), color, 2)
        cv2.line(frame, (center_x, center_y - size), 
                (center_x, center_y + size), color, 2)
        
        # Draw center circle
        cv2.circle(frame, (center_x, center_y), 5, color, 2)
        
        return frame
    
    def draw_number_detection(self, frame: np.ndarray, number: str,
                             bbox: Tuple[int, int, int, int],
                             confidence: float) -> np.ndarray:
        """
        Highlight detected number with bounding box.
        
        Args:
            frame: Input frame
            number: Detected number
            bbox: Bounding box (x, y, w, h)
            confidence: Detection confidence
            
        Returns:
            Frame with detection overlay
        """
        x, y, w, h = bbox
        
        # Choose color based on confidence
        if confidence >= 0.9:
            color = self.COLOR_GREEN
        elif confidence >= 0.7:
            color = self.COLOR_YELLOW
        else:
            color = self.COLOR_ORANGE
        
        # Draw bounding box
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 3)
        
        # Draw label
        label = f"Number: {number}"
        conf_text = f"Conf: {confidence:.0%}"
        
        # Background for text
        text_size_1, _ = cv2.getTextSize(label, self.FONT, 
                                        self.FONT_SCALE_MEDIUM, 2)
        text_size_2, _ = cv2.getTextSize(conf_text, self.FONT, 
                                        self.FONT_SCALE_SMALL, 1)
        
        bg_y = max(y - 60, 0)
        cv2.rectangle(frame, (x, bg_y), 
                     (x + max(text_size_1[0], text_size_2[0]) + 10, y),
                     color, -1)
        
        # Draw text
        cv2.putText(frame, label, (x + 5, bg_y + 25),
                   self.FONT, self.FONT_SCALE_MEDIUM, self.COLOR_BLACK, 2)
        cv2.putText(frame, conf_text, (x + 5, bg_y + 50),
                   self.FONT, self.FONT_SCALE_SMALL, self.COLOR_BLACK, 1)
        
        return frame
    
    def draw_depth_measurement(self, frame: np.ndarray, 
                              depth: float, 
                              confidence: float,
                              roi: Optional[Tuple[int, int, int, int]] = None) -> np.ndarray:
        """
        Draw depth measurement overlay.
        
        Args:
            frame: Input frame
            depth: Measured depth in meters
            confidence: Measurement confidence
            roi: Optional region of interest for measurement
            
        Returns:
            Frame with depth overlay
        """
        # Draw ROI if provided
        if roi:
            x, y, w, h = roi
            color = self.COLOR_GREEN if confidence > 0.8 else self.COLOR_YELLOW
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            
            # Draw center point
            center_x = x + w // 2
            center_y = y + h // 2
            cv2.circle(frame, (center_x, center_y), 8, color, -1)
        
        # Draw measurement panel
        panel_x = self.width - 300
        panel_y = self.height - 150
        panel_w = 290
        panel_h = 140
        
        # Semi-transparent background
        overlay = frame.copy()
        cv2.rectangle(overlay, (panel_x, panel_y), 
                     (panel_x + panel_w, panel_y + panel_h),
                     self.COLOR_BLACK, -1)
        frame = cv2.addWeighted(frame, 0.6, overlay, 0.4, 0)
        
        # Border
        cv2.rectangle(frame, (panel_x, panel_y), 
                     (panel_x + panel_w, panel_y + panel_h),
                     self.COLOR_WHITE, 2)
        
        # Title
        cv2.putText(frame, "KEEL DEPTH", (panel_x + 10, panel_y + 30),
                   self.FONT, self.FONT_SCALE_MEDIUM, self.COLOR_WHITE, 2)
        
        # Depth value (large)
        depth_text = f"{depth:.3f} m"
        cv2.putText(frame, depth_text, (panel_x + 10, panel_y + 75),
                   self.FONT, self.FONT_SCALE_LARGE, self.COLOR_GREEN, 2)
        
        # Confidence
        conf_text = f"Confidence: {confidence:.0%}"
        conf_color = self.COLOR_GREEN if confidence > 0.8 else self.COLOR_YELLOW
        cv2.putText(frame, conf_text, (panel_x + 10, panel_y + 105),
                   self.FONT, self.FONT_SCALE_SMALL, conf_color, 1)
        
        # Accuracy indicator
        if confidence >= 0.9:
            acc_text = "HIGH ACCURACY"
            acc_color = self.COLOR_GREEN
        elif confidence >= 0.7:
            acc_text = "MEDIUM ACCURACY"
            acc_color = self.COLOR_YELLOW
        else:
            acc_text = "LOW ACCURACY"
            acc_color = self.COLOR_RED
        
        cv2.putText(frame, acc_text, (panel_x + 10, panel_y + 130),
                   self.FONT, self.FONT_SCALE_SMALL, acc_color, 1)
        
        return frame
    
    def draw_alert(self, frame: np.ndarray, message: str, 
                  alert_type: str = 'info') -> np.ndarray:
        """
        Draw alert message banner.
        
        Args:
            frame: Input frame
            message: Alert message
            alert_type: 'info', 'warning', 'error', 'success'
            
        Returns:
            Frame with alert
        """
        # Choose color based on type
        colors = {
            'info': self.COLOR_BLUE,
            'warning': self.COLOR_YELLOW,
            'error': self.COLOR_RED,
            'success': self.COLOR_GREEN
        }
        color = colors.get(alert_type, self.COLOR_WHITE)
        
        # Alert banner
        banner_y = self.height - 80
        banner_height = 70
        
        # Background
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, banner_y), 
                     (self.width, banner_y + banner_height),
                     color, -1)
        frame = cv2.addWeighted(frame, 0.7, overlay, 0.3, 0)
        
        # Border
        cv2.rectangle(frame, (0, banner_y), 
                     (self.width, banner_y + banner_height),
                     color, 3)
        
        # Message
        text_size, _ = cv2.getTextSize(message, self.FONT, 
                                       self.FONT_SCALE_LARGE, 2)
        text_x = (self.width - text_size[0]) // 2
        text_y = banner_y + 45
        
        cv2.putText(frame, message, (text_x, text_y),
                   self.FONT, self.FONT_SCALE_LARGE, self.COLOR_BLACK, 3)
        
        return frame
    
    def draw_grid(self, frame: np.ndarray, spacing: int = 50,
                 color: Tuple[int, int, int] = None) -> np.ndarray:
        """
        Draw measurement grid overlay.
        
        Args:
            frame: Input frame
            spacing: Grid spacing in pixels
            color: Grid color
            
        Returns:
            Frame with grid
        """
        if color is None:
            color = (100, 100, 100)  # Gray
        
        # Vertical lines
        for x in range(0, self.width, spacing):
            cv2.line(frame, (x, 0), (x, self.height), color, 1)
        
        # Horizontal lines
        for y in range(0, self.height, spacing):
            cv2.line(frame, (0, y), (self.width, y), color, 1)
        
        return frame
    
    def create_split_screen(self, frame1: np.ndarray, 
                           frame2: np.ndarray,
                           labels: Tuple[str, str] = ('Camera', 'Depth')) -> np.ndarray:
        """
        Create side-by-side split screen view.
        
        Args:
            frame1: First frame (e.g., RGB)
            frame2: Second frame (e.g., depth colormap)
            labels: Labels for each view
            
        Returns:
            Combined frame
        """
        # Resize to half width
        half_width = self.width // 2
        frame1_resized = cv2.resize(frame1, (half_width, self.height))
        frame2_resized = cv2.resize(frame2, (half_width, self.height))
        
        # Add labels
        cv2.putText(frame1_resized, labels[0], (10, 30),
                   self.FONT, self.FONT_SCALE_MEDIUM, self.COLOR_WHITE, 2)
        cv2.putText(frame2_resized, labels[1], (10, 30),
                   self.FONT, self.FONT_SCALE_MEDIUM, self.COLOR_WHITE, 2)
        
        # Combine horizontally
        combined = np.hstack([frame1_resized, frame2_resized])
        
        # Draw divider
        cv2.line(combined, (half_width, 0), (half_width, self.height),
                self.COLOR_WHITE, 2)
        
        return combined


# Example usage
if __name__ == "__main__":
    # Create sample frames
    width, height = 1280, 720
    
    # Initialize overlay
    overlay = VideoOverlay(width, height)
    
    # Create test frame
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    
    # Sample survey status
    survey_status = {
        'corners_found': 3,
        'corners_needed': 5,
        'numbers': [5, 6, 7],
        'sequence_type': '5-9',
        'sequence_valid': False,
        'keel_depth': None,
        'keel_confidence': None,
        'complete': False,
        'points_earned': 5
    }
    
    # Draw HUD
    frame = overlay.draw_hud(frame, survey_status)
    frame = overlay.draw_crosshair(frame)
    frame = overlay.draw_alert(frame, "Survey in progress...", 'info')
    
    # Display
    cv2.imshow('Video Overlay Demo', frame)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
