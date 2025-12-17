# Document Intelligence Engine for OCR Post-Processing
# Handles checkbox resolution, validation, normalization, and accuracy metrics

import re
from typing import Dict, List, Tuple, Optional, Any

class CheckboxResolver:
    """Resolves checkbox detections into semantic boolean values"""
    
    def __init__(self, checkbox_groups: Dict):
        self.groups = checkbox_groups
    
    def resolve_group(self, group_name: str, detections: List[Dict]) -> Optional[str]:
        """Resolve mutually exclusive checkbox group to single value"""
        if group_name not in self.groups:
            return None
        
        group = self.groups[group_name]
        options = group['options']
        
        # Find which option has highest confidence
        best_match = None
        best_conf = 0
        
        for det in detections:
            for opt in options:
                if opt.lower() in det.get('label', '').lower():
                    if det.get('checked', False) and det.get('confidence', 0) > best_conf:
                        best_match = opt
                        best_conf = det['confidence']
        
        # Validate mutually exclusive constraint
        if group['mutually_exclusive']:
            checked_count = sum(1 for d in detections if d.get('checked', False))
            if checked_count > 1:
                # Multiple checked - use highest confidence only
                return best_match
        
        return best_match
    
    def detect_checkbox_state(self, roi_image, x: int, y: int, w: int, h: int) -> Tuple[bool, float]:
        """Determine if checkbox is checked based on pixel analysis"""
        import cv2
        import numpy as np
        
        # Extract checkbox region
        checkbox = roi_image[y:y+h, x:x+w]
        
        # Calculate fill ratio
        if len(checkbox.shape) == 3:
            checkbox = cv2.cvtColor(checkbox, cv2.COLOR_BGR2GRAY)
        
        _, binary = cv2.threshold(checkbox, 128, 255, cv2.THRESH_BINARY_INV)
        fill_ratio = np.sum(binary > 0) / (w * h)
        
        # Checked if >15% filled (X or checkmark present)
        is_checked = fill_ratio > 0.15
        confidence = min(fill_ratio * 2, 1.0) if is_checked else 1.0 - fill_ratio
        
        return is_checked, confidence


class FieldValidator:
    """Validates extracted fields against business rules"""
    
    def __init__(self, rules: Dict):
        self.rules = rules
    
    def validate(self, field_name: str, value: Any) -> Tuple[bool, str, Any]:
        """Validate field value, return (is_valid, error_msg, corrected_value)"""
        if field_name not in self.rules:
            return True, "", value
        
        rule = self.rules[field_name]
        field_type = rule.get('type', 'text')
        
        # Type-specific validation
        if field_type == 'currency':
            return self._validate_currency(value, rule)
        elif field_type == 'number':
            return self._validate_number(value, rule)
        elif field_type == 'year':
            return self._validate_year(value, rule)
        elif field_type == 'date':
            return self._validate_date(value, rule)
        elif field_type == 'enum':
            return self._validate_enum(value, rule)
        
        return True, "", value
    
    def _validate_currency(self, value: Any, rule: Dict) -> Tuple[bool, str, Any]:
        """Validate and clean currency value"""
        # Clean currency string
        if isinstance(value, str):
            clean = re.sub(r'[,$\s]', '', value)
            try:
                value = float(clean)
            except ValueError:
                return False, f"Invalid currency: {value}", None
        
        # Range check
        if 'min' in rule and value < rule['min']:
            return False, f"Below minimum {rule['min']}", value
        if 'max' in rule and value > rule['max']:
            return False, f"Above maximum {rule['max']}", value
        
        return True, "", value
    
    def _validate_number(self, value: Any, rule: Dict) -> Tuple[bool, str, Any]:
        """Validate numeric value"""
        if isinstance(value, str):
            clean = re.sub(r'[,\s]', '', value)
            try:
                value = float(clean)
            except ValueError:
                return False, f"Invalid number: {value}", None
        
        if 'min' in rule and value < rule['min']:
            return False, f"Below minimum {rule['min']}", value
        if 'max' in rule and value > rule['max']:
            return False, f"Above maximum {rule['max']}", value
        
        return True, "", value
    
    def _validate_year(self, value: Any, rule: Dict) -> Tuple[bool, str, Any]:
        """Validate year value"""
        try:
            year = int(str(value).strip())
        except ValueError:
            return False, f"Invalid year: {value}", None
        
        if year < rule.get('min', 1800) or year > rule.get('max', 2030):
            return False, f"Year out of range: {year}", None
        
        return True, "", year
    
    def _validate_date(self, value: Any, rule: Dict) -> Tuple[bool, str, Any]:
        """Validate date format"""
        date_patterns = [
            r'\d{2}/\d{2}/\d{4}',
            r'\d{1,2}/\d{1,2}/\d{4}',
            r'\d{4}-\d{2}-\d{2}'
        ]
        
        value_str = str(value).strip()
        for pattern in date_patterns:
            if re.match(pattern, value_str):
                return True, "", value_str
        
        return False, f"Invalid date format: {value}", None
    
    def _validate_enum(self, value: Any, rule: Dict) -> Tuple[bool, str, Any]:
        """Validate against allowed values"""
        allowed = rule.get('values', [])
        value_str = str(value).strip().upper()
        
        for valid in allowed:
            if value_str == valid.upper():
                return True, "", valid
        
        return False, f"Value '{value}' not in allowed list", None


class SemanticNormalizer:
    """Normalizes OCR output to canonical values"""
    
    def __init__(self, normalization_map: Dict):
        self.map = normalization_map
        self._build_index()
    
    def _build_index(self):
        """Build case-insensitive lookup index"""
        self.index = {k.upper(): v for k, v in self.map.items()}
    
    def normalize(self, value: str) -> str:
        """Normalize value to canonical form"""
        if not value:
            return value
        
        # Try exact match first
        upper = value.upper().strip()
        if upper in self.index:
            return self.index[upper]
        
        # Try fuzzy matching for common OCR errors
        for key, canonical in self.index.items():
            # Allow 1-2 character difference
            if self._similar(upper, key):
                return canonical
        
        return value
    
    def _similar(self, a: str, b: str) -> bool:
        """Check if strings are similar (allow OCR drift)"""
        if len(a) != len(b):
            return False
        diff = sum(1 for i in range(len(a)) if a[i] != b[i])
        return diff <= 2


class AccuracyTracker:
    """Tracks field-level accuracy metrics"""
    
    def __init__(self):
        self.results = {
            'total_fields': 0,
            'valid_fields': 0,
            'corrected_fields': 0,
            'invalid_fields': 0,
            'critical_accuracy': 0.0,
            'overall_accuracy': 0.0,
            'field_details': {}
        }
        self.critical_fields = ['contract_price', 'gla_sqft', 'property_address', 
                                'borrower', 'date_of_contract', 'year_built']
    
    def record(self, field_name: str, is_valid: bool, was_corrected: bool = False):
        """Record field extraction result"""
        self.results['total_fields'] += 1
        
        if is_valid:
            self.results['valid_fields'] += 1
            if was_corrected:
                self.results['corrected_fields'] += 1
        else:
            self.results['invalid_fields'] += 1
        
        self.results['field_details'][field_name] = {
            'valid': is_valid,
            'corrected': was_corrected,
            'critical': field_name in self.critical_fields
        }
    
    def calculate_accuracy(self) -> Dict:
        """Calculate final accuracy metrics"""
        total = self.results['total_fields']
        if total == 0:
            return self.results
        
        self.results['overall_accuracy'] = (
            self.results['valid_fields'] / total * 100
        )
        
        # Calculate critical field accuracy
        critical_total = sum(1 for f, d in self.results['field_details'].items() 
                            if d['critical'])
        critical_valid = sum(1 for f, d in self.results['field_details'].items() 
                            if d['critical'] and d['valid'])
        
        if critical_total > 0:
            self.results['critical_accuracy'] = critical_valid / critical_total * 100
        
        return self.results
    
    def get_report(self) -> str:
        """Generate accuracy report"""
        self.calculate_accuracy()
        
        report = [
            "=" * 60,
            "ACCURACY METRICS REPORT",
            "=" * 60,
            f"Total Fields Processed: {self.results['total_fields']}",
            f"Valid Fields: {self.results['valid_fields']}",
            f"Auto-Corrected: {self.results['corrected_fields']}",
            f"Invalid/Failed: {self.results['invalid_fields']}",
            "",
            f"Overall Accuracy: {self.results['overall_accuracy']:.1f}%",
            f"Critical Field Accuracy: {self.results['critical_accuracy']:.1f}%",
            "=" * 60
        ]
        
        return "\n".join(report)


print("✅ Document Intelligence Engine loaded")
print("   - CheckboxResolver: Semantic checkbox resolution")
print("   - FieldValidator: Business rule validation")
print("   - SemanticNormalizer: OCR drift correction")
print("   - AccuracyTracker: Field-level metrics")
