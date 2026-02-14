"""
Iceberg Tracking System - Modules Package
==========================================
All core modules for the ROV iceberg tracking task.
"""

__version__ = "1.0.0"
__author__ = "ROV Team"

from .vision_processor import VisionProcessor
from .depth_measurement import DepthMeasurement
from .survey_tracker import SurveyTracker
from .threat_calculator import ThreatCalculator, IcebergData
from .data_manager import DataManager
from .video_overlay import VideoOverlay

__all__ = [
    'VisionProcessor',
    'DepthMeasurement',
    'SurveyTracker',
    'ThreatCalculator',
    'IcebergData',
    'DataManager',
    'VideoOverlay'
]
