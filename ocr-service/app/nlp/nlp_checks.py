"""
CPU-Friendly NLP Checks for Appraisal QC

Provides:
- Canned/generic commentary detection
- Reasoning presence validation
- Market trend keyword extraction

Uses rule-based approaches and lightweight models suitable for CPU inference.
"""

import re
import logging
from typing import List, Tuple, Dict, Set, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Try to import optional NLP libraries
try:
    from sentence_transformers import SentenceTransformer, util
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.info("sentence-transformers not available. Using rule-based fallback.")


@dataclass
class CommentaryAnalysis:
    """Result of commentary analysis."""
    is_canned: bool
    confidence: float  # 0.0 to 1.0
    matched_templates: List[str] = None
    reasoning_score: float = 0.0
    has_specific_details: bool = False


# Known canned/generic phrases commonly found in appraisals
CANNED_TEMPLATES = [
    "the subject property is located in a",
    "the neighborhood is characterized by",
    "the subject is typical for the neighborhood",
    "see attached addendum for additional comments",
    "refer to the addendum for further analysis",
    "no adverse conditions were noted",
    "the property appears to be in average condition",
    "the improvements are typical for the area",
    "the subject is compatible with the neighborhood",
    "see 1004mc",
    "refer to market conditions addendum",
    "this is a stable neighborhood",
    "the market appears balanced",
    "see comparable sales grid",
    "adjustments reflect market reactions",
    "comparable sales were selected based on",
    "the cost approach was not developed",
    "the income approach was not developed",
    "equal weight was given to",
    "weighted average",
]

# Words/phrases that indicate reasoning and analysis
REASONING_INDICATORS = [
    "because", "therefore", "as a result", "due to", "since",
    "based on", "indicates", "suggests", "reflects", "demonstrates",
    "specifically", "particularly", "notably", "considering",
    "analysis shows", "data indicates", "evidence suggests",
    "in comparison to", "relative to", "when compared",
    "taking into account", "given that", "as evidenced by",
    "this is supported by", "consistent with",
]

# Causal connectors
CAUSAL_PATTERNS = [
    r'\bbecause\b',
    r'\btherefore\b',
    r'\bas a result\b',
    r'\bdue to\b',
    r'\bsince\b',
    r'\bthis (is|was|reflects|indicates|suggests)\b',
    r'\bconsequently\b',
    r'\baccordingly\b',
]

# Market trend keywords
MARKET_TREND_KEYWORDS = {
    "increasing": ["increasing", "appreciating", "rising", "growing", "upward", "stronger", "improving"],
    "decreasing": ["declining", "decreasing", "falling", "dropping", "downward", "weakening", "softening"],
    "stable": ["stable", "steady", "balanced", "consistent", "unchanged", "flat", "equilibrium"],
    "shortage": ["shortage", "undersupply", "limited inventory", "low supply", "high demand"],
    "oversupply": ["oversupply", "surplus", "excess inventory", "high supply", "low demand"],
}

# Specific detail indicators
SPECIFICITY_PATTERNS = [
    r'\$[\d,]+',  # Dollar amounts
    r'\d+\s*(?:sf|sq\.?\s*ft|square feet)',  # Square footage
    r'\d+\s*(?:bedrooms?|beds?|bdrms?)',  # Bedroom counts
    r'\d+(?:\.\d+)?\s*(?:baths?|bathrooms?)',  # Bathroom counts
    r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d+',  # Dates
    r'\d+/\d+/\d+',  # Date patterns
    r'\b(?:MLS|mls)\s*#?\s*[\d\w]+',  # MLS numbers
    r'\b[A-Z]{2,5}MLS',  # MLS abbreviations
    r'DOM\s*\d+',  # Days on market
    r'\d+%',  # Percentages
    r'\d{4}\s*(?:built|constructed)',  # Year built
]


class NLPChecker:
    """
    CPU-friendly NLP checker for appraisal commentary analysis.
    
    Uses rule-based approaches with optional sentence-transformers for
    better canned commentary detection.
    """
    
    def __init__(self, use_embeddings: bool = False):
        """
        Initialize NLP checker.
        
        Args:
            use_embeddings: Whether to use sentence-transformers (slower but more accurate)
        """
        self.use_embeddings = use_embeddings and SENTENCE_TRANSFORMERS_AVAILABLE
        self._model = None
        self._template_embeddings = None
        
        if self.use_embeddings:
            self._init_embeddings()
    
    def _init_embeddings(self):
        """Initialize sentence transformer model."""
        try:
            # Use a small, CPU-friendly model
            self._model = SentenceTransformer('all-MiniLM-L6-v2')
            # Pre-compute template embeddings
            self._template_embeddings = self._model.encode(
                CANNED_TEMPLATES, 
                convert_to_tensor=True
            )
            logger.info("Sentence transformer initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize sentence transformer: {e}")
            self.use_embeddings = False
    
    def detect_canned_commentary(
        self, 
        text: str, 
        threshold: float = 0.75
    ) -> CommentaryAnalysis:
        """
        Detect if commentary appears to be generic/canned.
        
        Args:
            text: Commentary text to analyze
            threshold: Similarity threshold for embedding-based detection
            
        Returns:
            CommentaryAnalysis with detection results
        """
        if not text or len(text.strip()) < 20:
            return CommentaryAnalysis(
                is_canned=False, 
                confidence=0.0,
                has_specific_details=False
            )
        
        text_lower = text.lower()
        
        # Method 1: Direct template matching
        matched_templates = []
        for template in CANNED_TEMPLATES:
            if template in text_lower:
                matched_templates.append(template)
        
        # Method 2: Embedding similarity (if available)
        embedding_score = 0.0
        if self.use_embeddings and self._model:
            try:
                text_embedding = self._model.encode(text, convert_to_tensor=True)
                similarities = util.cos_sim(text_embedding, self._template_embeddings)
                embedding_score = float(similarities.max())
            except Exception as e:
                logger.warning(f"Embedding comparison failed: {e}")
        
        # Method 3: Check for specific details
        has_specific_details = self._has_specific_details(text)
        
        # Calculate final score
        template_score = min(1.0, len(matched_templates) * 0.3)
        
        if self.use_embeddings:
            combined_score = (template_score * 0.3 + embedding_score * 0.7)
        else:
            combined_score = template_score
        
        # Reduce score if specific details present
        if has_specific_details:
            combined_score *= 0.5
        
        # Check reasoning
        reasoning_score = self._check_reasoning_presence(text)
        
        return CommentaryAnalysis(
            is_canned=combined_score > 0.4,
            confidence=combined_score,
            matched_templates=matched_templates,
            reasoning_score=reasoning_score,
            has_specific_details=has_specific_details
        )
    
    def _has_specific_details(self, text: str) -> bool:
        """Check if text contains specific details like numbers, dates, MLS numbers."""
        for pattern in SPECIFICITY_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def _check_reasoning_presence(self, text: str) -> float:
        """
        Calculate a reasoning score for the text.
        
        Higher score indicates more analytical/reasoning content.
        
        Returns:
            Score from 0.0 to 1.0
        """
        if not text:
            return 0.0
        
        text_lower = text.lower()
        words = text_lower.split()
        
        if len(words) < 10:
            return 0.0
        
        # Count reasoning indicators
        indicator_count = 0
        for indicator in REASONING_INDICATORS:
            if indicator in text_lower:
                indicator_count += 1
        
        # Count causal patterns
        causal_count = 0
        for pattern in CAUSAL_PATTERNS:
            matches = re.findall(pattern, text_lower)
            causal_count += len(matches)
        
        # Calculate score based on density
        word_count = len(words)
        indicator_density = indicator_count / (word_count / 100)  # per 100 words
        causal_density = causal_count / (word_count / 100)
        
        # Combine scores
        score = min(1.0, (indicator_density * 0.3 + causal_density * 0.3))
        
        # Bonus for specific details
        if self._has_specific_details(text):
            score += 0.2
        
        return min(1.0, score)
    
    def check_reasoning_presence(self, text: str) -> Tuple[bool, float]:
        """
        Check if text contains adequate reasoning.
        
        Args:
            text: Text to analyze
            
        Returns:
            Tuple of (has_reasoning, score)
        """
        score = self._check_reasoning_presence(text)
        return (score >= 0.3, score)
    
    def extract_market_trends(self, text: str) -> Dict[str, List[str]]:
        """
        Extract market trend keywords from text.
        
        Returns:
            Dict mapping trend types to found keywords
        """
        if not text:
            return {}
        
        text_lower = text.lower()
        found_trends = {}
        
        for trend_type, keywords in MARKET_TREND_KEYWORDS.items():
            found = [kw for kw in keywords if kw in text_lower]
            if found:
                found_trends[trend_type] = found
        
        return found_trends
    
    def analyze_commentary(self, text: str) -> Dict[str, any]:
        """
        Comprehensive commentary analysis.
        
        Returns:
            Dict with all analysis results
        """
        canned_result = self.detect_canned_commentary(text)
        reasoning_present, reasoning_score = self.check_reasoning_presence(text)
        market_trends = self.extract_market_trends(text)
        
        return {
            "is_canned": canned_result.is_canned,
            "canned_confidence": canned_result.confidence,
            "matched_templates": canned_result.matched_templates,
            "has_reasoning": reasoning_present,
            "reasoning_score": reasoning_score,
            "has_specific_details": canned_result.has_specific_details,
            "market_trends": market_trends,
            "word_count": len(text.split()) if text else 0,
        }


def detect_canned_commentary(text: str) -> Tuple[bool, float]:
    """
    Simple function to detect canned commentary.
    
    Returns:
        Tuple of (is_canned, confidence)
    """
    checker = NLPChecker(use_embeddings=False)
    result = checker.detect_canned_commentary(text)
    return (result.is_canned, result.confidence)


def check_reasoning_presence(text: str) -> bool:
    """
    Check if text contains adequate reasoning.
    
    Uses rule-based detection of causal words and analytical phrases.
    """
    checker = NLPChecker(use_embeddings=False)
    has_reasoning, _ = checker.check_reasoning_presence(text)
    return has_reasoning


def extract_market_trends(text: str) -> List[str]:
    """
    Extract market trend keywords from text.
    
    Returns list of found trend keywords.
    """
    checker = NLPChecker(use_embeddings=False)
    trends = checker.extract_market_trends(text)
    
    # Flatten to list
    all_keywords = []
    for keywords in trends.values():
        all_keywords.extend(keywords)
    
    return all_keywords
