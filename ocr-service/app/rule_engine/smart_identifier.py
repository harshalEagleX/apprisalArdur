import logging
import traceback
from enum import Enum
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field

# Configure logging - STREAM ONLY (Stateless / No PII on disk)
# We do NOT write to a file to comply with data privacy requirements (No permanent storage).
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("SmartIdentifier")

class RuleStatus(str, Enum):
    PASS         = "pass"
    FAIL         = "fail"
    VERIFY       = "verify"        # field missing or too low confidence — human must check


class RuleSeverity(str, Enum):
    BLOCKING = "BLOCKING"   # FAIL = stop delivery, return to appraiser
    STANDARD = "STANDARD"   # FAIL = correction needed before delivery
    ADVISORY = "ADVISORY"   # non-blocking VERIFY-style finding


class RuleResult(BaseModel):
    rule_id: str
    rule_name: str
    status: RuleStatus
    message: str
    details: Optional[Dict[str, Any]] = None
    action_item: Optional[str] = None
    # Comparison fields for reviewer UI
    appraisal_value: Optional[str] = None
    engagement_value: Optional[str] = None
    confidence: Optional[float] = None
    extracted_value: Optional[Any] = None
    expected_value: Optional[Any] = None
    verify_question: Optional[str] = None
    rejection_text: Optional[str] = None
    evidence: List[str] = Field(default_factory=list)
    review_required: bool = False
    # Phase 3 additions
    severity: RuleSeverity = RuleSeverity.STANDARD
    source_page: Optional[int] = None          # PDF page where the triggering field was found
    bbox_x: Optional[float] = None             # Normalized 0-1 coordinates; currently null until OCR blocks expose boxes
    bbox_y: Optional[float] = None
    bbox_w: Optional[float] = None
    bbox_h: Optional[float] = None
    field_confidence: Optional[float] = None   # Confidence of extracted value(s) used
    auto_correctable: bool = False             # True if system can fix without human
    rule_version: str = "1.0"

class SmartLogger:
    """
    A smart logging system that tracks rule execution and identifies
    areas where the rule engine needs improvement (e.g. missing data).
    """
    
    def __init__(self):
        self.results: List[RuleResult] = []
        self.missing_data_log: Dict[str, int] = {} # Field name -> count

    def log_result(self, result: RuleResult):
        self.results.append(result)
        
        if result.status == RuleStatus.VERIFY:
            logger.info(f"Rule {result.rule_id} VERIFY: {result.message}")
            # Track missing fields for improvement suggestions
            if result.details and "field" in result.details:
                field = result.details["field"]
                self.missing_data_log[field] = self.missing_data_log.get(field, 0) + 1
        elif result.status == RuleStatus.FAIL:
            logger.info(f"Rule {result.rule_id} FAIL: {result.message}")

    def get_summary(self) -> Dict[str, Any]:
        params = {
            "total_rules": len(self.results),
            "passed": len([r for r in self.results if r.status == RuleStatus.PASS]),
            "failed": len([r for r in self.results if r.status == RuleStatus.FAIL]),
            "verify": len([r for r in self.results if r.status == RuleStatus.VERIFY]),
            "missing_data_hotspots": self.missing_data_log
        }
        return params

    def analyze_improvements(self) -> List[str]:
        """
        Returns a list of suggested improvements for the rule engine 
        based on the errors encountered.
        """
        improvements = []
        if self.missing_data_log:
            top_missing = sorted(self.missing_data_log.items(), key=lambda x: x[1], reverse=True)
            for field, count in top_missing:
                improvements.append(f"Improve OCR/Extraction for field '{field}' - caused {count} rule errors.")
        
        return improvements

# Exceptions
class RuleException(Exception):
    """Base exception for rule execution"""
    pass

class DataMissingException(RuleException):
    """Raised when a rule cannot run due to missing data"""
    def __init__(self, field_name: str):
        self.field_name = field_name
        super().__init__(f"Missing required field: {field_name}")

class ComparisonException(RuleException):
    """Raised when comparison logic fails (e.g. type mismatch)"""
    pass
