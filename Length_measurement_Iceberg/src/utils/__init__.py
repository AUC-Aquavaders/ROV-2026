"""
Utility Functions Package
==========================
Helper utilities for the iceberg tracking system.
"""

from .realsense_camera import RealSenseCamera
from .navigation import (
    haversine_distance,
    bearing,
    destination_point,
    cross_track_distance,
    latitude_to_nm,
    longitude_to_nm
)
from .image_processing import (
    enhance_underwater,
    white_balance,
    denoise_image,
    sharpen_image,
    adaptive_threshold,
    detect_roi_by_color,
    calculate_sharpness,
    auto_canny,
    perspective_correction
)

__all__ = [
    'RealSenseCamera',
    'haversine_distance',
    'bearing',
    'destination_point',
    'cross_track_distance',
    'latitude_to_nm',
    'longitude_to_nm',
    'enhance_underwater',
    'white_balance',
    'denoise_image',
    'sharpen_image',
    'adaptive_threshold',
    'detect_roi_by_color',
    'calculate_sharpness',
    'auto_canny',
    'perspective_correction'
]
