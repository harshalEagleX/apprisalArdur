import logging
import traceback
from enum import Enum
from typing import Optional, Dict, List, Any
from pydantic import BaseModel

# Configure logging - STREAM ONLY (Stateless / No PII on disk)
# We do NOT write to a file to comply with data privacy requirements (No permanent storage).
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("SmartIdentifier")

class RuleStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    VERIFY = "VERIFY"  # OCR uncertain/missing field - needs human review
    WARNING = "WARNING"  # Soft issue, can be accepted
    SKIPPED = "SKIPPED"  # Rule not applicable
    SYSTEM_ERROR = "SYSTEM_ERROR"  # Engine crash, unreadable PDF only

class RuleResult(BaseModel):
    rule_id: str
    rule_name: str
    status: RuleStatus
    message: str
    details: Optional[Dict[str, Any]] = None
    action_item: Optional[str] = None  # Suggestion for the developer/user
    # Comparison fields for reviewer UI
    appraisal_value: Optional[str] = None  # Value extracted from appraisal document
    engagement_value: Optional[str] = None  # Expected value from engagement letter
    review_required: bool = False  # True if human review is needed

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
        
        if result.status == RuleStatus.SYSTEM_ERROR:
            logger.error(f"Rule {result.rule_id} SYSTEM_ERROR: {result.message} | Action: {result.action_item}")
        elif result.status == RuleStatus.VERIFY:
            logger.warning(f"Rule {result.rule_id} VERIFY: {result.message}")
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
            "verify": len([r for r in self.results if r.status in [RuleStatus.VERIFY, RuleStatus.WARNING]]),
            "system_errors": len([r for r in self.results if r.status == RuleStatus.SYSTEM_ERROR]),
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
