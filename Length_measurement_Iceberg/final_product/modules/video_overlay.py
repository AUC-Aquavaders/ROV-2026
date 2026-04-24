import cv2
import numpy as np
from typing import Dict, Any


class VideoOverlay:
    """Handles UI overlays and alerts."""
    
    def __init__(self):
        self.alert_colors = {
            'info': (255, 255, 255),
            'success': (0, 255, 0),
            'warning': (0, 165, 255),
            'error': (0, 0, 255)
        }
    
    def draw_alert(self, frame: np.ndarray, message: str, alert_type: str = 'info') -> np.ndarray:
        """Draw an alert message on the frame."""
        display = frame.copy()
        h, w = frame.shape[:2]
        
        color = self.alert_colors.get(alert_type, (255, 255, 255))
        
        cv2.rectangle(display, (0, h - 40), (w, h), (0, 0, 0), -1)
        
        text_size = cv2.getTextSize(message, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
        x_pos = (w - text_size[0]) // 2
        
        cv2.putText(display, message, (x_pos, h - 12),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        return display
    
    def draw_measurement_box(self, frame: np.ndarray, measurement: float, 
                            position: tuple = None) -> np.ndarray:
        """Draw measurement result box."""
        display = frame.copy()
        h, w = frame.shape[:2]
        
        if position is None:
            position = (w // 2 - 100, h // 2 - 50)
        
        x, y = position
        
        cv2.rectangle(display, (x, y), (x + 200, y + 100), (0, 0, 0), -1)
        cv2.rectangle(display, (x, y), (x + 200, y + 100), (0, 255, 0), 2)
        
        cv2.putText(display, f"{measurement:.4f}m", (x + 20, y + 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        
        return display
