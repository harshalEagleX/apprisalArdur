"""
Parallel OCR Pipeline for Appraisal Document Processing

Strategy (Phase 1):
  - Render all pages to PIL Images in main thread (fitz is NOT thread-safe)
  - OCR pages in parallel via ThreadPoolExecutor(max_workers=4)
  - Smart threshold: ≥100 words embedded → skip Tesseract entirely
                     30–99 words → run both, pick best
                     <30 words   → Tesseract required (image/photo pages)
  - Force mode (force_image_ocr=True): always Tesseract, but still parallelized
"""

import re
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum

import fitz  # PyMuPDF

# Optional imports - graceful degradation if not available
try:
    import pytesseract
    from PIL import Image
    from PIL import Image as PILImage  # Alias for use in preprocessed image handling
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logging.warning("pytesseract not available. Install with: pip install pytesseract pillow")

# Import image preprocessor
try:
    from app.ocr.image_preprocessor import ImagePreprocessor
    PREPROCESSOR_AVAILABLE = True
except ImportError:
    PREPROCESSOR_AVAILABLE = False
    logging.warning("ImagePreprocessor not available. Image preprocessing will be disabled.")

logger = logging.getLogger(__name__)


class ExtractionMethod(str, Enum):
    """Method used to extract text from a page."""
    EMBEDDED = "embedded"  # PyMuPDF embedded text
    TESSERACT = "tesseract"  # Tesseract OCR
    CLOUD = "cloud"  # Cloud OCR (Google Vision, etc.)


@dataclass
class PageText:
    """Extracted text from a single page with metadata."""
    page_number: int
    text: str
    method: ExtractionMethod
    confidence: float = 1.0  # 0.0 to 1.0
    word_count: int = 0
    has_tables: bool = False


@dataclass
class ExtractionResult:
    """Result of OCR extraction for an entire document."""
    page_index: Dict[int, str] = field(default_factory=dict)
    page_details: List[PageText] = field(default_factory=list)
    total_pages: int = 0
    images: List[Tuple[int, bytes]] = field(default_factory=list)  # (page_num, image_bytes)
    extraction_time_ms: int = 0
    warnings: List[str] = field(default_factory=list)
    # PIL Images per page — used for moondream checkbox detection (Phase 2 Step 2)
    # Stored as grayscale PIL.Image objects, keyed by 1-indexed page number
    page_images: Dict[int, "Image.Image"] = field(default_factory=dict)


class OCRPipeline:
    """
    Parallel OCR pipeline for appraisal PDFs.

    Pages are rendered to images in the main thread (fitz thread-safety),
    then OCR'd in parallel with ThreadPoolExecutor(max_workers=4).
    """

    # ≥ this many embedded words → use embedded text, skip Tesseract
    MIN_WORDS_THRESHOLD = 100

    # < this many embedded words → must OCR (image/photo pages)
    HYBRID_OCR_THRESHOLD = 30

    # Confidence threshold for re-extraction
    LOW_CONFIDENCE_THRESHOLD = 0.5

    # Max parallel Tesseract workers
    MAX_WORKERS = 4
    
    def __init__(self, use_tesseract: bool = True, use_cloud: bool = False, force_image_ocr: bool = False, use_preprocessing: bool = False):
        self.use_tesseract = use_tesseract and TESSERACT_AVAILABLE
        self.use_cloud = use_cloud
        self.force_image_ocr = force_image_ocr and TESSERACT_AVAILABLE
        self.use_preprocessing = use_preprocessing and PREPROCESSOR_AVAILABLE and TESSERACT_AVAILABLE
        
        # Initialize preprocessor if available
        if self.use_preprocessing:
            self.preprocessor = ImagePreprocessor(dpi=300, enable_table_removal=True)
            logger.info("Image preprocessing enabled for OCR")
        else:
            self.preprocessor = None
            if use_preprocessing and not (PREPROCESSOR_AVAILABLE and TESSERACT_AVAILABLE):
                logger.warning("Image preprocessing requested but dependencies not available. Falling back to standard mode.")
        
        if force_image_ocr and not TESSERACT_AVAILABLE:
            logger.warning("Force Image OCR requested but Tesseract not available. Falling back to hybrid mode.")

    def extract_all_pages(self, pdf_path: str, force_ocr: bool = None) -> ExtractionResult:
        """
        Extract text from all pages of a PDF using parallel Tesseract workers.

        Phase 1 (main thread): Render each page to a PIL Image via fitz.
            fitz Page objects are NOT thread-safe — all fitz calls happen here.
        Phase 2 (ThreadPoolExecutor): Run Tesseract in parallel on pre-rendered images.
            pytesseract operating on PIL Images IS thread-safe.

        Smart decision per page:
            embedded words ≥ MIN_WORDS_THRESHOLD (100) → use embedded, no OCR
            embedded words 30–99 (HYBRID zone)         → run both, pick best
            embedded words < HYBRID_OCR_THRESHOLD (30) → OCR required
            force_image_ocr=True                       → always OCR (parallelised)
        """
        import time
        start_time = time.time()

        result = ExtractionResult()
        use_force = force_ocr if force_ocr is not None else self.force_image_ocr

        try:
            doc = fitz.open(pdf_path)
            result.total_pages = len(doc)

            # ── Phase 1: render in main thread (fitz is not thread-safe) ──────
            page_jobs = []
            for i in range(len(doc)):
                page = doc[i]
                page_num = i + 1

                embedded_text = page.get_text("text")
                embedded_wc = len(embedded_text.split())
                has_tables = self._detect_tables(page)

                # Decide whether OCR render is needed
                needs_render = (
                    use_force
                    or embedded_wc < self.MIN_WORDS_THRESHOLD
                ) and self.use_tesseract

                pil_img = None
                if needs_render:
                    # Higher DPI for low-text pages (photos, signatures, maps)
                    dpi = 300 if (use_force or embedded_wc < self.HYBRID_OCR_THRESHOLD) else 200
                    mat = fitz.Matrix(dpi / 72, dpi / 72)
                    pix = page.get_pixmap(matrix=mat)
                    # Convert to greyscale PIL Image — safe to pass to other threads
                    pil_img = Image.frombytes(
                        "RGB", [pix.width, pix.height], pix.samples
                    ).convert("L")

                page_jobs.append({
                    "page_num":      page_num,
                    "embedded_text": embedded_text,
                    "embedded_wc":   embedded_wc,
                    "has_tables":    has_tables,
                    "pil_img":       pil_img,
                    "force":         use_force,
                })

                # Store page image for moondream checkbox detection
                # Only keep first 10 pages (form pages) to manage memory
                if pil_img is not None and page_num <= 10:
                    result.page_images[page_num] = pil_img

            doc.close()

            # ── Phase 2: OCR in parallel (PIL + pytesseract is thread-safe) ───
            def _ocr_job(job: dict) -> PageText:
                pn       = job["page_num"]
                emb_text = job["embedded_text"]
                emb_wc   = job["embedded_wc"]
                htables  = job["has_tables"]
                img      = job["pil_img"]
                force    = job["force"]

                def _tess(image) -> Tuple[str, int]:
                    text = pytesseract.image_to_string(image, config="--psm 6")
                    return text, len(text.split())

                # Force path: always Tesseract
                if force and img is not None:
                    try:
                        text, wc = _tess(img)
                        return PageText(pn, text, ExtractionMethod.TESSERACT,
                                        self._estimate_confidence(text), wc, htables)
                    except Exception as e:
                        logger.warning("Forced Tesseract failed page %d: %s", pn, e)
                        # Fall through to embedded

                # Embedded text good enough
                if emb_wc >= self.MIN_WORDS_THRESHOLD:
                    return PageText(pn, emb_text, ExtractionMethod.EMBEDDED,
                                    self._estimate_confidence(emb_text), emb_wc, htables)

                # Hybrid zone or OCR-required zone
                if img is not None:
                    try:
                        text, wc = _tess(img)
                        if wc > emb_wc:
                            return PageText(pn, text, ExtractionMethod.TESSERACT,
                                            self._estimate_confidence(text), wc, htables)
                    except Exception as e:
                        logger.warning("Tesseract fallback failed page %d: %s", pn, e)

                # Last resort: return whatever embedded gave us
                conf = 0.5 if emb_wc < 10 else 0.7
                return PageText(pn, emb_text, ExtractionMethod.EMBEDDED, conf, emb_wc, htables)

            workers = min(self.MAX_WORKERS, len(page_jobs))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                # executor.map preserves input order → no need to sort
                page_results = list(pool.map(_ocr_job, page_jobs))

            for pt in page_results:
                result.page_index[pt.page_number] = pt.text
                result.page_details.append(pt)

        except Exception as e:
            logger.error("Failed to process PDF: %s", e)
            result.warnings.append(f"PDF processing error: {str(e)}")

        result.extraction_time_ms = int((time.time() - start_time) * 1000)
        return result
    
    def _extract_page(self, page: fitz.Page, page_number: int, force_image: bool = False) -> PageText:
        """
        Extract text from a single page using multi-pass approach.
        """
        # Pass 0: Forced Image OCR (High Quality for Forms)
        if force_image and self.use_tesseract:
            try:
                # Use --psm 6 for uniform block of text (preserves layout) 
                tesseract_text = self._tesseract_extract(page, dpi=300, config='--psm 6')
                word_count = len(tesseract_text.split())
                
                return PageText(
                    page_number=page_number,
                    text=tesseract_text,
                    method=ExtractionMethod.TESSERACT,
                    confidence=self._estimate_confidence(tesseract_text),
                    word_count=word_count,
                    has_tables=self._detect_tables(page)
                )
            except Exception as e:
                logger.warning(f"Forced Tesseract extraction failed for page {page_number}: {e}")
                # Fallback to embedded
        
        # Pass 1: Try embedded text extraction (fastest)
        embedded_text = page.get_text("text")
        word_count = len(embedded_text.split())
        
        if word_count >= self.MIN_WORDS_THRESHOLD:
            return PageText(
                page_number=page_number,
                text=embedded_text,
                method=ExtractionMethod.EMBEDDED,
                confidence=self._estimate_confidence(embedded_text),
                word_count=word_count,
                has_tables=self._detect_tables(page)
            )
        
        # Pass 2: Try Tesseract if enabled and embedded text is poor
        if self.use_tesseract:
            try:
                tesseract_text = self._tesseract_extract(page)
                tesseract_words = len(tesseract_text.split())
                
                # Use Tesseract if it gives better results
                if tesseract_words > word_count:
                    return PageText(
                        page_number=page_number,
                        text=tesseract_text,
                        method=ExtractionMethod.TESSERACT,
                        confidence=self._estimate_confidence(tesseract_text),
                        word_count=tesseract_words,
                        has_tables=self._detect_tables(page)
                    )
            except Exception as e:
                logger.warning(f"Tesseract extraction failed for page {page_number}: {e}")
        
        # Return whatever we got from embedded extraction
        return PageText(
            page_number=page_number,
            text=embedded_text,
            method=ExtractionMethod.EMBEDDED,
            confidence=0.5 if word_count < 10 else 0.7,
            word_count=word_count,
            has_tables=self._detect_tables(page)
        )
    
    def _tesseract_extract(self, page: fitz.Page = None, image=None, dpi: int = 200, config: str = '') -> str:
        """
        Extract text using Tesseract OCR with preprocessing.
        
        Args:
            page: PyMuPDF page object (if extracting from PDF directly)
            image: Preprocessed numpy array image (if using preprocessor)
            dpi: DPI for rendering (only used if page is provided)
            config: Tesseract configuration string
            
        Returns:
            Extracted text
        """
        if not TESSERACT_AVAILABLE:
            return ""
        
        # If preprocessed image is provided, use it directly
        if image is not None:
            # Convert numpy array to PIL Image
            if len(image.shape) == 2:
                # Grayscale
                pil_img = PILImage.fromarray(image, mode='L')
            else:
                # RGB
                pil_img = PILImage.fromarray(image)
            
            # Run Tesseract
            text = pytesseract.image_to_string(pil_img, config=config)
            return text
        
        # Otherwise, render PDF page to image
        if page is None:
            return ""
            
        # Render page to image at high DPI
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Preprocessing: Convert to Grayscale
        img = img.convert('L')
        
        # Run Tesseract with config
        # --psm 6: Assume a single uniform block of text.
        text = pytesseract.image_to_string(img, config=config)
        return text
    
    def _estimate_confidence(self, text: str) -> float:
        """
        Estimate extraction confidence based on text quality indicators.
        """
        if not text or len(text) < 20:
            return 0.1
            
        # Check for common quality indicators
        score = 0.5
        
        # Good signs: contains common appraisal terms
        appraisal_terms = [
            "property", "address", "borrower", "value", "appraisal",
            "comparable", "sales", "neighborhood", "condition"
        ]
        text_lower = text.lower()
        terms_found = sum(1 for term in appraisal_terms if term in text_lower)
        score += min(0.3, terms_found * 0.05)
        
        # Bad signs: too many special characters (OCR artifacts)
        special_ratio = len(re.findall(r'[^\w\s.,;:$%()-]', text)) / max(len(text), 1)
        if special_ratio > 0.1:
            score -= 0.2
            
        # Bad signs: too many numbers stuck together (OCR issues)
        long_numbers = len(re.findall(r'\d{10,}', text))
        if long_numbers > 3:
            score -= 0.1
            
        return max(0.1, min(1.0, score))
    
    def _detect_tables(self, page: fitz.Page) -> bool:
        """
        Detect if page likely contains tables.
        """
        # Check for table-like structures using text blocks
        blocks = page.get_text("blocks")
        if len(blocks) > 10:  # Many text blocks might indicate table
            return True
            
        # Check for grid lines
        drawings = page.get_drawings()
        if len(drawings) > 20:  # Many lines might indicate table
            return True
            
        return False
    
    def extract_images(self, pdf_path: str) -> List[Tuple[int, bytes, str]]:
        """
        Extract all images from PDF for storage (not processing).
        
        Returns:
            List of (page_number, image_bytes, image_ext)
        """
        images = []
        
        try:
            doc = fitz.open(pdf_path)
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images()
                
                for img_idx, img in enumerate(image_list):
                    xref = img[0]
                    try:
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]
                        images.append((page_num + 1, image_bytes, image_ext))
                    except Exception as e:
                        logger.warning(f"Failed to extract image {img_idx} from page {page_num + 1}: {e}")
                        
            doc.close()
            
        except Exception as e:
            logger.error(f"Failed to extract images: {e}")
            
        return images
    
    def extract_with_preprocessing(self, pdf_path: str) -> ExtractionResult:
        """
        Extract text using image preprocessing pipeline for maximum quality.
        
        Process:
        1. Convert PDF to high-resolution images
        2. Preprocess each image (grayscale, denoise, threshold, table removal)
        3. Run Tesseract OCR on clean images
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            ExtractionResult with preprocessed extraction
        """
        import time
        start_time = time.time()
        
        if not self.use_preprocessing or not self.preprocessor:
            logger.warning("Preprocessing not available. Falling back to standard extraction.")
            return self.extract_all_pages(pdf_path)
        
        logger.info(f"Extracting with image preprocessing: {pdf_path}")
        
        result = ExtractionResult()
        
        try:
            # Step 1: Convert PDF to images
            logger.info("Converting PDF to images...")
            raw_images = self.preprocessor.pdf_to_images(pdf_path)
            result.total_pages = len(raw_images)
            logger.info(f"Converted {len(raw_images)} pages to images")
            
            # Step 2 & 3: Preprocess and OCR each image
            for page_num, raw_image in enumerate(raw_images, start=1):
                logger.debug(f"Processing page {page_num}/{len(raw_images)}")
                
                # Preprocess image
                clean_image = self.preprocessor.preprocess_image(raw_image)
                
                # Run Tesseract on preprocessed image
                text = self._tesseract_extract(image=clean_image, config='--psm 6')
                word_count = len(text.split())
                
                # Store results
                result.page_index[page_num] = text
                result.page_details.append(PageText(
                    page_number=page_num,
                    text=text,
                    method=ExtractionMethod.TESSERACT,
                    confidence=self._estimate_confidence(text),
                    word_count=word_count,
                    has_tables=True  # Assume tables since we're preprocessing
                ))
                
                logger.debug(f"Page {page_num}: extracted {word_count} words")
            
            logger.info(f"Preprocessing extraction complete: {len(raw_images)} pages processed")
            
        except Exception as e:
            logger.error(f"Preprocessing extraction failed: {e}")
            result.warnings.append(f"Preprocessing error: {str(e)}")
            # Fallback to standard extraction
            logger.info("Falling back to standard extraction...")
            return self.extract_all_pages(pdf_path)
        
        result.extraction_time_ms = int((time.time() - start_time) * 1000)
        return result
    
    def get_full_text(self, page_index: Dict[int, str]) -> str:
        """Combine all page texts into a single string."""
        return "\n\n".join(
            page_index.get(i, "") 
            for i in sorted(page_index.keys())
        )


class PageSelector:
    """
    Candidate page selection for targeted extraction.
    
    For each field/question, identifies likely pages using:
    - Keyword search
    - Regex patterns
    - Section headers
    - Table-of-contents heuristics
    """
    
    # Known section headers and their associated fields
    SECTION_KEYWORDS = {
        "subject": ["subject", "property address", "borrower", "legal description", "assessor"],
        "contract": ["contract", "price", "sale date", "seller", "concessions"],
        "neighborhood": ["neighborhood", "location", "built-up", "growth", "land use"],
        "site": ["site", "dimensions", "area", "zoning", "utilities", "flood"],
        "improvements": ["improvements", "foundation", "exterior", "interior", "condition", "room"],
        "sales_comparison": ["sales comparison", "comparable", "adjustment", "grid"],
        "cost_approach": ["cost approach", "depreciation", "land value"],
        "income_approach": ["income approach", "rent", "gross rent multiplier"],
        "reconciliation": ["reconciliation", "indicated value", "final value"],
        "addendum": ["addendum", "comments", "additional"],
        "signature": ["appraiser", "signature", "license", "certification"],
        "photographs": ["photograph", "photo", "front", "rear", "street scene"],
        "maps": ["map", "location map", "flood map", "plat"],
        "1004mc": ["market conditions", "1004mc", "inventory analysis"],
    }
    
    def __init__(self, page_index: Dict[int, str]):
        """
        Initialize with page index from OCR extraction.
        
        Args:
            page_index: Dict mapping page numbers to extracted text
        """
        self.page_index = page_index
        self._page_text_lower = {
            p: text.lower() for p, text in page_index.items()
        }
        
    def find_pages_for_section(self, section: str, max_pages: int = 10) -> List[int]:
        """
        Find candidate pages for a document section.
        
        Args:
            section: Section name (e.g., "subject", "contract")
            max_pages: Maximum number of pages to return
            
        Returns:
            List of page numbers, sorted by relevance
        """
        keywords = self.SECTION_KEYWORDS.get(section.lower(), [section.lower()])
        return self.find_pages_by_keywords(keywords, max_pages)
    
    def find_pages_by_keywords(
        self, 
        keywords: List[str], 
        max_pages: int = 10,
        require_all: bool = False
    ) -> List[int]:
        """
        Find pages containing specified keywords.
        
        Args:
            keywords: List of keywords to search for
            max_pages: Maximum number of pages to return
            require_all: If True, page must contain ALL keywords
            
        Returns:
            List of page numbers sorted by keyword match count
        """
        page_scores: Dict[int, int] = {}
        
        for page_num, text in self._page_text_lower.items():
            matches = sum(1 for kw in keywords if kw.lower() in text)
            
            if require_all and matches < len(keywords):
                continue
                
            if matches > 0:
                page_scores[page_num] = matches
                
        # Sort by score descending, then by page number ascending
        sorted_pages = sorted(
            page_scores.keys(),
            key=lambda p: (-page_scores[p], p)
        )
        
        return sorted_pages[:max_pages]
    
    def find_pages_by_pattern(
        self, 
        pattern: str, 
        max_pages: int = 10,
        flags: int = re.IGNORECASE
    ) -> List[Tuple[int, List[str]]]:
        """
        Find pages matching a regex pattern.
        
        Args:
            pattern: Regex pattern to search for
            max_pages: Maximum number of pages to return
            flags: Regex flags
            
        Returns:
            List of (page_number, matches) tuples
        """
        results = []
        regex = re.compile(pattern, flags)
        
        for page_num, text in self.page_index.items():
            matches = regex.findall(text)
            if matches:
                results.append((page_num, matches))
                
        # Sort by number of matches descending
        results.sort(key=lambda x: -len(x[1]))
        return results[:max_pages]
    
    def get_text_for_pages(self, page_numbers: List[int]) -> str:
        """Get combined text for specific pages."""
        return "\n\n".join(
            self.page_index.get(p, "") 
            for p in sorted(page_numbers)
        )
