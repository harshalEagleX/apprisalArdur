"""
Image Preprocessing Module for OCR Enhancement

This module provides image preprocessing functions to improve OCR accuracy by:
1. Converting PDFs to high-resolution images
2. Applying grayscale conversion
3. Denoising images to remove artifacts
4. Binary thresholding for text clarity
5. Removing table lines and borders
6. Deskewing rotated images

Usage:
    preprocessor = ImagePreprocessor()
    images = preprocessor.pdf_to_images('document.pdf')
    clean_images = [preprocessor.preprocess_image(img) for img in images]
"""

import logging
from typing import List, Optional, Tuple
from pathlib import Path
import numpy as np

# Optional imports with graceful degradation
try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    logging.info("pdf2image not available. Install with: pip install pdf2image")

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logging.info("OpenCV not available. Install with: pip install opencv-python")

from PIL import Image

logger = logging.getLogger(__name__)


class ImagePreprocessor:
    """
    Handles image preprocessing for OCR quality improvement.
    """
    
    # Default DPI for PDF to image conversion
    DEFAULT_DPI = 300
    
    # Denoising parameters
    DENOISE_H = 10  # Filter strength
    DENOISE_TEMPLATE_WINDOW = 7
    DENOISE_SEARCH_WINDOW = 21
    
    def __init__(self, dpi: int = DEFAULT_DPI, enable_table_removal: bool = True):
        """
        Initialize image preprocessor.
        
        Args:
            dpi: Resolution for PDF to image conversion (higher = better quality)
            enable_table_removal: Whether to remove table lines during preprocessing
        """
        self.dpi = dpi
        self.enable_table_removal = enable_table_removal
        
        if not PDF2IMAGE_AVAILABLE:
            logger.error("pdf2image not available. PDF to image conversion will fail.")
        if not CV2_AVAILABLE:
            logger.error("OpenCV not available. Image preprocessing will be limited.")
    
    def pdf_to_images(self, pdf_path: str) -> List[np.ndarray]:
        """
        Convert PDF pages to high-resolution images.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of images as numpy arrays (one per page)
        """
        if not PDF2IMAGE_AVAILABLE:
            raise ImportError("pdf2image is required. Install with: pip install pdf2image")
        
        logger.info(f"Converting PDF to images: {pdf_path} at {self.dpi} DPI")
        
        try:
            # Convert PDF to PIL Images
            pil_images = convert_from_path(pdf_path, dpi=self.dpi)
            
            # Convert PIL Images to numpy arrays
            np_images = []
            for i, pil_img in enumerate(pil_images):
                # Convert PIL Image to numpy array (RGB)
                np_img = np.array(pil_img)
                np_images.append(np_img)
                logger.debug(f"Converted page {i+1} to image: shape={np_img.shape}")
            
            logger.info(f"Successfully converted {len(np_images)} pages to images")
            return np_images
            
        except Exception as e:
            logger.error(f"Failed to convert PDF to images: {e}")
            raise
    
    def preprocess_image(self, image: np.ndarray, debug: bool = False) -> np.ndarray:
        """
        Apply full preprocessing pipeline to an image.
        
        Pipeline:
        1. Grayscale conversion
        2. Denoising
        3. Binary thresholding
        4. Table line removal (optional)
        5. Deskewing (optional)
        
        Args:
            image: Input image as numpy array
            debug: If True, save intermediate steps for debugging
            
        Returns:
            Preprocessed image ready for OCR
        """
        if not CV2_AVAILABLE:
            logger.info("OpenCV not available. Returning original image.")
            return image
        
        logger.debug(f"Preprocessing image: shape={image.shape}")
        
        # Step 1: Grayscale conversion
        gray = self.grayscale_convert(image)
        
        # Step 2: Denoising
        denoised = self.denoise_image(gray)
        
        # Step 3: Adaptive binary thresholding
        thresholded = self.apply_threshold(denoised)
        
        # Step 4: Table line removal (if enabled)
        if self.enable_table_removal:
            clean = self.remove_table_lines(thresholded)
        else:
            clean = thresholded
        
        # Step 5: Deskewing (optional - only if significant rotation detected)
        angle = self.detect_skew(clean)
        if abs(angle) > 0.5:  # Only deskew if angle > 0.5 degrees
            logger.debug(f"Detected skew angle: {angle:.2f}°")
            deskewed = self.deskew_image(clean, angle)
        else:
            deskewed = clean
        
        logger.debug(f"Preprocessing complete: input_shape={image.shape}, output_shape={deskewed.shape}")
        return deskewed
    
    def grayscale_convert(self, image: np.ndarray) -> np.ndarray:
        """
        Convert RGB image to grayscale.
        
        Args:
            image: Input image (RGB or BGR)
            
        Returns:
            Grayscale image
        """
        if not CV2_AVAILABLE:
            return image
        
        if len(image.shape) == 2:
            # Already grayscale
            return image
        
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        logger.debug("Converted to grayscale")
        return gray
    
    def denoise_image(self, image: np.ndarray) -> np.ndarray:
        """
        Remove noise from image using Non-local Means Denoising.
        
        Args:
            image: Grayscale input image
            
        Returns:
            Denoised image
        """
        if not CV2_AVAILABLE:
            return image
        
        denoised = cv2.fastNlMeansDenoising(
            image,
            h=self.DENOISE_H,
            templateWindowSize=self.DENOISE_TEMPLATE_WINDOW,
            searchWindowSize=self.DENOISE_SEARCH_WINDOW
        )
        logger.debug("Applied denoising")
        return denoised
    
    def apply_threshold(self, image: np.ndarray) -> np.ndarray:
        """
        Apply adaptive binary thresholding.

        Converts image to pure black text on white background.
        Adaptive thresholding handles mixed lighting and scanned pages better
        than a single global Otsu cutoff.
        
        Args:
            image: Grayscale input image
            
        Returns:
            Binary thresholded image
        """
        if not CV2_AVAILABLE:
            return image
        
        thresh = cv2.adaptiveThreshold(
            image,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            35,
            11,
        )
        logger.debug("Applied adaptive binary thresholding")
        return thresh
    
    def remove_table_lines(self, image: np.ndarray) -> np.ndarray:
        """
        Remove horizontal and vertical table lines while preserving text.
        
        Process:
        1. Detect horizontal lines using morphological operations
        2. Detect vertical lines
        3. Create mask of all lines
        4. Remove lines from original image
        
        Args:
            image: Binary thresholded image
            
        Returns:
            Image with table lines removed
        """
        if not CV2_AVAILABLE:
            return image
        
        # Create copy to avoid modifying original
        result = image.copy()
        
        # Invert image (black text on white -> white text on black)
        inverted = cv2.bitwise_not(result)
        
        # Detect horizontal lines
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        horizontal_lines = cv2.morphologyEx(inverted, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
        
        # Detect vertical lines
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
        vertical_lines = cv2.morphologyEx(inverted, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
        
        # Combine horizontal and vertical lines
        table_lines = cv2.add(horizontal_lines, vertical_lines)
        
        # Remove lines from original image
        # Invert table_lines mask and apply
        result = cv2.subtract(inverted, table_lines)
        
        # Invert back to black text on white
        result = cv2.bitwise_not(result)
        
        logger.debug("Removed table lines")
        return result
    
    def detect_skew(self, image: np.ndarray) -> float:
        """
        Detect rotation angle of scanned document.
        
        Args:
            image: Binary thresholded image
            
        Returns:
            Skew angle in degrees
        """
        if not CV2_AVAILABLE:
            return 0.0
        
        try:
            # Find all contours
            contours, _ = cv2.findContours(
                cv2.bitwise_not(image), 
                cv2.RETR_EXTERNAL, 
                cv2.CHAIN_APPROX_SIMPLE
            )
            
            if not contours:
                return 0.0
            
            # Find the largest contour (likely the document)
            largest_contour = max(contours, key=cv2.contourArea)
            
            # Get minimum area rectangle
            rect = cv2.minAreaRect(largest_contour)
            angle = rect[-1]
            
            # Normalize angle to [-45, 45] range
            if angle < -45:
                angle = 90 + angle
            
            return angle
            
        except Exception as e:
            logger.info(f"Failed to detect skew: {e}")
            return 0.0
    
    def deskew_image(self, image: np.ndarray, angle: float) -> np.ndarray:
        """
        Rotate image to correct skew.
        
        Args:
            image: Input image
            angle: Rotation angle in degrees
            
        Returns:
            Deskewed image
        """
        if not CV2_AVAILABLE:
            return image
        
        # Get image dimensions
        (h, w) = image.shape[:2]
        
        # Calculate rotation matrix
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        
        # Perform rotation
        rotated = cv2.warpAffine(
            image, 
            M, 
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )
        
        logger.debug(f"Deskewed image by {angle:.2f}°")
        return rotated
    
    def save_image(self, image: np.ndarray, output_path: str):
        """
        Save preprocessed image to file.
        
        Args:
            image: Image to save
            output_path: Output file path
        """
        if not CV2_AVAILABLE:
            logger.info("OpenCV not available. Cannot save image.")
            return
        
        cv2.imwrite(output_path, image)
        logger.info(f"Saved preprocessed image to: {output_path}")


# Convenience function
def preprocess_pdf_for_ocr(pdf_path: str, dpi: int = 300) -> List[np.ndarray]:
    """
    Convenience function to convert PDF to preprocessed images ready for OCR.
    
    Args:
        pdf_path: Path to PDF file
        dpi: Resolution for conversion
        
    Returns:
        List of preprocessed images
    """
    preprocessor = ImagePreprocessor(dpi=dpi)
    raw_images = preprocessor.pdf_to_images(pdf_path)
    clean_images = [preprocessor.preprocess_image(img) for img in raw_images]
    return clean_images
