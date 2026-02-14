"""
Vision Processing Module
=========================
Handles number detection and OCR for iceberg survey.
Detects numbers on iceberg corners (15cm below surface) and keel.
"""

import cv2
import numpy as np
from typing import Tuple, List, Optional, Dict
import logging

# Try to import OCR libraries (install separately)
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    logging.warning("EasyOCR not available. Install with: pip install easyocr")

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logging.warning("Tesseract not available. Install with: pip install pytesseract")


class VisionProcessor:
    """Processes camera frames to detect and recognize numbers."""
    
    def __init__(self, ocr_engine='easyocr', confidence_threshold=0.6, gpu=True):
        """
        Initialize the vision processor.
        
        Args:
            ocr_engine (str): 'easyocr' or 'tesseract'
            confidence_threshold (float): Minimum confidence for number detection
            gpu (bool): Use GPU acceleration if available (default: True)
        """
        self.ocr_engine = ocr_engine
        self.confidence_threshold = confidence_threshold
        self.reader = None
        
        if ocr_engine == 'easyocr' and EASYOCR_AVAILABLE:
            # Auto-detect GPU availability
            use_gpu = gpu and self._check_gpu_available()
            
            if gpu and not use_gpu:
                logging.warning("GPU requested but not available. Using CPU (slower).")
                logging.info("To enable GPU: Install CUDA toolkit and pytorch with CUDA support")
            
            self.reader = easyocr.Reader(['en'], gpu=use_gpu)
            
            if use_gpu:
                logging.info("EasyOCR initialized with GPU acceleration")
            else:
                logging.info("EasyOCR initialized with CPU (consider GPU for faster processing)")
                
        elif ocr_engine == 'tesseract' and not TESSERACT_AVAILABLE:
            logging.error("Tesseract not installed")
        
        logging.info(f"VisionProcessor initialized with {ocr_engine}")
    
    def _check_gpu_available(self) -> bool:
        """
        Check if GPU (CUDA) is available for PyTorch.
        
        Returns:
            bool: True if CUDA-capable GPU is available
        """
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
    
    def enhance_underwater_image(self, frame: np.ndarray) -> np.ndarray:
        """
        Enhance underwater image for better OCR performance.
        
        Applies:
        - White balance correction
        - Contrast enhancement (CLAHE)
        - Denoising
        
        Args:
            frame: Input BGR image
            
        Returns:
            Enhanced BGR image
        """
        # Convert to LAB color space
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        
        # Apply CLAHE to L channel for contrast enhancement
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        
        # Merge channels
        enhanced_lab = cv2.merge([l, a, b])
        enhanced = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
        
        # Denoise
        enhanced = cv2.fastNlMeansDenoisingColored(enhanced, None, 10, 10, 7, 21)
        
        return enhanced
    
    def detect_numbers(self, frame: np.ndarray, enhance: bool = True) -> List[Dict]:
        """
        Detect numbers in the given frame using OCR.
        
        Args:
            frame: Input BGR image
            enhance: Whether to apply image enhancement
            
        Returns:
            List of detected numbers with format:
            [{'number': '5', 'confidence': 0.95, 'bbox': (x, y, w, h)}, ...]
        """
        if enhance:
            frame = self.enhance_underwater_image(frame)
        
        detections = []
        
        if self.ocr_engine == 'easyocr' and self.reader:
            detections = self._detect_with_easyocr(frame)
        elif self.ocr_engine == 'tesseract' and TESSERACT_AVAILABLE:
            detections = self._detect_with_tesseract(frame)
        
        # Filter to single digits 0-9 only
        valid_detections = []
        for det in detections:
            if det['number'].isdigit() and len(det['number']) == 1:
                if det['confidence'] >= self.confidence_threshold:
                    valid_detections.append(det)
        
        return valid_detections
    
    def _detect_with_easyocr(self, frame: np.ndarray) -> List[Dict]:
        """Detect numbers using EasyOCR."""
        results = self.reader.readtext(frame)
        
        detections = []
        for (bbox, text, confidence) in results:
            # Convert bbox to x, y, w, h format
            pts = np.array(bbox, dtype=np.int32)
            x = int(pts[:, 0].min())
            y = int(pts[:, 1].min())
            w = int(pts[:, 0].max() - x)
            h = int(pts[:, 1].max() - y)
            
            detections.append({
                'number': text.strip(),
                'confidence': confidence,
                'bbox': (x, y, w, h)
            })
        
        return detections
    
    def _detect_with_tesseract(self, frame: np.ndarray) -> List[Dict]:
        """Detect numbers using Tesseract OCR."""
        # Configure Tesseract for single digit detection
        config = '--psm 6 -c tessedit_char_whitelist=0123456789'
        
        # Get detailed data from Tesseract
        data = pytesseract.image_to_data(frame, config=config, output_type=pytesseract.Output.DICT)
        
        detections = []
        for i in range(len(data['text'])):
            text = data['text'][i].strip()
            conf = int(data['conf'][i])
            
            if text and conf > 0:
                x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                detections.append({
                    'number': text,
                    'confidence': conf / 100.0,  # Normalize to 0-1
                    'bbox': (x, y, w, h)
                })
        
        return detections
    
    def validate_sequence(self, numbers: List[int]) -> Tuple[bool, str]:
        """
        Validate that detected numbers form a valid sequence (0-4 or 5-9).
        
        Args:
            numbers: List of detected numbers
            
        Returns:
            (is_valid, sequence_type) where sequence_type is '0-4', '5-9', or 'invalid'
        """
        if not numbers or len(numbers) != 5:
            return False, 'invalid'
        
        numbers_set = set(numbers)
        
        # Check if it's 0-4 sequence
        if numbers_set == {0, 1, 2, 3, 4}:
            return True, '0-4'
        
        # Check if it's 5-9 sequence
        if numbers_set == {5, 6, 7, 8, 9}:
            return True, '5-9'
        
        return False, 'invalid'
    
    def highlight_detection(self, frame: np.ndarray, number: str, 
                          bbox: Tuple[int, int, int, int], 
                          confidence: float) -> np.ndarray:
        """
        Draw bounding box and label on detected number.
        
        Args:
            frame: Input BGR image
            number: Detected number as string
            bbox: Bounding box (x, y, w, h)
            confidence: Detection confidence
            
        Returns:
            Frame with overlay drawn
        """
        frame_copy = frame.copy()
        x, y, w, h = bbox
        
        # Choose color based on confidence
        if confidence >= 0.8:
            color = (0, 255, 0)  # Green - high confidence
        elif confidence >= 0.6:
            color = (0, 255, 255)  # Yellow - medium confidence
        else:
            color = (0, 165, 255)  # Orange - low confidence
        
        # Draw bounding box
        cv2.rectangle(frame_copy, (x, y), (x + w, y + h), color, 2)
        
        # Draw label background
        label = f"{number} ({confidence:.2f})"
        label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(frame_copy, (x, y - label_size[1] - 10), 
                     (x + label_size[0], y), color, -1)
        
        # Draw label text
        cv2.putText(frame_copy, label, (x, y - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        
        return frame_copy
    
    def preprocess_for_ocr(self, frame: np.ndarray, roi: Optional[Tuple[int, int, int, int]] = None) -> np.ndarray:
        """
        Advanced preprocessing for OCR.
        
        Args:
            frame: Input BGR image
            roi: Optional region of interest (x, y, w, h)
            
        Returns:
            Preprocessed grayscale image
        """
        # Extract ROI if specified
        if roi:
            x, y, w, h = roi
            frame = frame[y:y+h, x:x+w]
        
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Apply bilateral filter to reduce noise while keeping edges
        filtered = cv2.bilateralFilter(gray, 9, 75, 75)
        
        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(filtered, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                      cv2.THRESH_BINARY, 11, 2)
        
        # Morphological operations to clean up
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        
        return morph


# Example usage
if __name__ == "__main__":
    # Initialize vision processor
    vp = VisionProcessor(ocr_engine='easyocr')
    
    # Example with webcam or test image
    cap = cv2.VideoCapture(0)
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Detect numbers
        detections = vp.detect_numbers(frame)
        
        # Draw detections
        for det in detections:
            frame = vp.highlight_detection(frame, det['number'], 
                                          det['bbox'], det['confidence'])
        
        cv2.imshow('Number Detection', frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()
