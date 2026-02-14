"""
Image Processing Utilities
===========================
Common computer vision utilities for underwater image processing.
"""

import cv2
import numpy as np
from typing import Tuple, Optional


def enhance_underwater(image: np.ndarray) -> np.ndarray:
    """
    Enhance underwater image quality.
    
    Args:
        image: Input BGR image
        
    Returns:
        Enhanced BGR image
    """
    # Convert to LAB color space
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    
    # Apply CLAHE to luminance channel
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    
    # Merge and convert back
    lab = cv2.merge([l, a, b])
    enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    
    return enhanced


def white_balance(image: np.ndarray, method='gray_world') -> np.ndarray:
    """
    Apply white balance correction.
    
    Args:
        image: Input BGR image
        method: 'gray_world' or 'white_patch'
        
    Returns:
        White balanced BGR image
    """
    result = image.copy()
    
    if method == 'gray_world':
        # Gray world assumption
        avg_b = np.mean(result[:, :, 0])
        avg_g = np.mean(result[:, :, 1])
        avg_r = np.mean(result[:, :, 2])
        avg = (avg_b + avg_g + avg_r) / 3
        
        result[:, :, 0] = np.clip(result[:, :, 0] * (avg / avg_b), 0, 255)
        result[:, :, 1] = np.clip(result[:, :, 1] * (avg / avg_g), 0, 255)
        result[:, :, 2] = np.clip(result[:, :, 2] * (avg / avg_r), 0, 255)
    
    return result.astype(np.uint8)


def denoise_image(image: np.ndarray, strength: int = 10) -> np.ndarray:
    """
    Denoise image while preserving edges.
    
    Args:
        image: Input image
        strength: Denoising strength (higher = more smoothing)
        
    Returns:
        Denoised image
    """
    if len(image.shape) == 3:
        # Color image
        return cv2.fastNlMeansDenoisingColored(image, None, strength, strength, 7, 21)
    else:
        # Grayscale
        return cv2.fastNlMeansDenoising(image, None, strength, 7, 21)


def sharpen_image(image: np.ndarray, strength: float = 1.0) -> np.ndarray:
    """
    Sharpen image using unsharp masking.
    
    Args:
        image: Input image
        strength: Sharpening strength (0-2, where 1 is normal)
        
    Returns:
        Sharpened image
    """
    # Create Gaussian blur
    blurred = cv2.GaussianBlur(image, (0, 0), 3)
    
    # Unsharp mask
    sharpened = cv2.addWeighted(image, 1 + strength, blurred, -strength, 0)
    
    return sharpened


def adaptive_threshold(image: np.ndarray, block_size: int = 11, c: int = 2) -> np.ndarray:
    """
    Apply adaptive thresholding for better text/number detection.
    
    Args:
        image: Input grayscale image
        block_size: Size of neighborhood area
        c: Constant subtracted from mean
        
    Returns:
        Binary image
    """
    if len(image.shape) == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    return cv2.adaptiveThreshold(image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY, block_size, c)


def detect_roi_by_color(image: np.ndarray, 
                        lower_hsv: Tuple[int, int, int],
                        upper_hsv: Tuple[int, int, int]) -> Optional[Tuple[int, int, int, int]]:
    """
    Detect region of interest by color range in HSV.
    
    Args:
        image: Input BGR image
        lower_hsv: Lower HSV threshold (H: 0-180, S: 0-255, V: 0-255)
        upper_hsv: Upper HSV threshold
        
    Returns:
        Bounding box (x, y, w, h) or None
    """
    # Convert to HSV
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    
    # Create mask
    mask = cv2.inRange(hsv, np.array(lower_hsv), np.array(upper_hsv))
    
    # Find contours
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None
    
    # Get largest contour
    largest_contour = max(contours, key=cv2.contourArea)
    
    # Get bounding box
    x, y, w, h = cv2.boundingRect(largest_contour)
    
    return (x, y, w, h)


def calculate_sharpness(image: np.ndarray) -> float:
    """
    Calculate image sharpness using Laplacian variance.
    
    Args:
        image: Input image (color or grayscale)
        
    Returns:
        Sharpness score (higher = sharper)
    """
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    
    # Compute Laplacian
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    
    # Return variance
    return laplacian.var()


def auto_canny(image: np.ndarray, sigma: float = 0.33) -> np.ndarray:
    """
    Automatic Canny edge detection with computed thresholds.
    
    Args:
        image: Input grayscale image
        sigma: Determines threshold range
        
    Returns:
        Edge map
    """
    if len(image.shape) == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Compute median
    median = np.median(image)
    
    # Compute thresholds
    lower = int(max(0, (1.0 - sigma) * median))
    upper = int(min(255, (1.0 + sigma) * median))
    
    # Apply Canny
    edges = cv2.Canny(image, lower, upper)
    
    return edges


def perspective_correction(image: np.ndarray, 
                          corners: np.ndarray,
                          target_width: int,
                          target_height: int) -> np.ndarray:
    """
    Apply perspective transformation to correct angled view.
    
    Args:
        image: Input image
        corners: 4 corner points in image [[x,y], ...] (top-left, top-right, bottom-right, bottom-left)
        target_width: Output width
        target_height: Output height
        
    Returns:
        Warped image with corrected perspective
    """
    # Define destination points (rectangle)
    dst_points = np.array([
        [0, 0],
        [target_width - 1, 0],
        [target_width - 1, target_height - 1],
        [0, target_height - 1]
    ], dtype=np.float32)
    
    # Calculate perspective transform matrix
    matrix = cv2.getPerspectiveTransform(corners.astype(np.float32), dst_points)
    
    # Apply transformation
    warped = cv2.warpPerspective(image, matrix, (target_width, target_height))
    
    return warped


# Example usage
if __name__ == "__main__":
    # Test with sample image
    import sys
    
    if len(sys.argv) > 1:
        image = cv2.imread(sys.argv[1])
        
        # Test enhancements
        enhanced = enhance_underwater(image)
        balanced = white_balance(enhanced)
        denoised = denoise_image(balanced)
        sharpened = sharpen_image(denoised, 0.5)
        
        # Calculate sharpness
        sharpness = calculate_sharpness(sharpened)
        print(f"Image sharpness: {sharpness:.2f}")
        
        # Display
        cv2.imshow('Original', image)
        cv2.imshow('Enhanced', sharpened)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    else:
        print("Usage: python image_processing.py <image_path>")
