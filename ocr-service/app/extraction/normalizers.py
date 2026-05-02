"""
Value Normalization Utilities for Appraisal Data

Handles normalization of:
- Addresses (parsing, standardization)
- Money values ($435k → 435000)
- Dates (various formats → ISO)
- Census tracts (validation)
"""

import re
import logging
from typing import Optional, Dict, Tuple, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class NormalizedAddress:
    """Standardized address components."""
    full_address: str
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    zip_plus4: Optional[str] = None
    unit: Optional[str] = None
    confidence: float = 1.0


@dataclass
class MoneyValue:
    """Normalized monetary value."""
    raw: str
    value: float
    currency: str = "USD"
    confidence: float = 1.0


# Common US state abbreviations and names
US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia"
}

# Reverse mapping: state name to abbreviation
STATE_TO_ABBREV = {v.upper(): k for k, v in US_STATES.items()}


def normalize_address(raw: str) -> NormalizedAddress:
    """
    Parse and normalize a US address string.
    
    This is a CPU-friendly implementation using regex.
    For production, consider libpostal or USPS API.
    
    Args:
        raw: Raw address string
        
    Returns:
        NormalizedAddress with parsed components
    """
    if not raw:
        return NormalizedAddress(full_address="", confidence=0.0)
    
    # Clean up the raw address
    cleaned = re.sub(r'\s+', ' ', raw.strip())
    
    result = NormalizedAddress(full_address=cleaned)
    
    # Try to extract ZIP code (5 or 9 digit)
    zip_match = re.search(r'\b(\d{5})(?:-(\d{4}))?\b', cleaned)
    if zip_match:
        result.zip_code = zip_match.group(1)
        result.zip_plus4 = zip_match.group(2)
    
    # Try to extract state (abbreviation or full name)
    state_abbrev_match = re.search(r'\b([A-Z]{2})\s*(?:\d{5}|$)', cleaned)
    if state_abbrev_match:
        potential_state = state_abbrev_match.group(1)
        if potential_state in US_STATES:
            result.state = potential_state
    else:
        # Try full state names
        for state_name, abbrev in STATE_TO_ABBREV.items():
            if state_name in cleaned.upper():
                result.state = abbrev
                break
    
    # Try to extract city (word(s) before state)
    if result.state:
        city_match = re.search(
            rf'([A-Za-z\s]+?)\s*,?\s*{result.state}',
            cleaned,
            re.IGNORECASE
        )
        if city_match:
            result.city = city_match.group(1).strip().rstrip(',')
    
    # Try to extract street address (everything before city)
    if result.city:
        street_match = re.search(
            rf'^(.+?)\s*,?\s*{re.escape(result.city)}',
            cleaned,
            re.IGNORECASE
        )
        if street_match:
            result.street = street_match.group(1).strip().rstrip(',')
    
    # Extract unit/apt number if present
    unit_match = re.search(
        r'\b(?:apt|unit|suite|ste|#)\s*([A-Za-z0-9-]+)\b',
        cleaned,
        re.IGNORECASE
    )
    if unit_match:
        result.unit = unit_match.group(1)
    
    # Calculate confidence based on components found
    components = [result.street, result.city, result.state, result.zip_code]
    found_count = sum(1 for c in components if c)
    result.confidence = found_count / 4.0
    
    return result


def normalize_money(raw: str) -> MoneyValue:
    """
    Parse monetary values to float.
    
    Handles formats like:
    - $435,000
    - $435k
    - $1.5M
    - 435000
    - $435,000.00
    
    Args:
        raw: Raw money string
        
    Returns:
        MoneyValue with parsed amount
    """
    if not raw:
        return MoneyValue(raw="", value=0.0, confidence=0.0)
    
    cleaned = raw.strip()
    
    # Remove currency symbols and whitespace
    cleaned = re.sub(r'[$€£\s]', '', cleaned)
    
    # Handle suffixes (K, M, B)
    multiplier = 1
    suffix_match = re.search(r'([kKmMbB])$', cleaned)
    if suffix_match:
        suffix = suffix_match.group(1).upper()
        multiplier = {"K": 1000, "M": 1000000, "B": 1000000000}.get(suffix, 1)
        cleaned = cleaned[:-1]
    
    # Remove commas
    cleaned = cleaned.replace(',', '')
    
    try:
        value = float(cleaned) * multiplier
        return MoneyValue(raw=raw, value=value, confidence=1.0)
    except ValueError:
        logger.info(f"Could not parse money value: {raw}")
        return MoneyValue(raw=raw, value=0.0, confidence=0.0)


def normalize_date(raw: str) -> str:
    """
    Parse date strings to ISO format (YYYY-MM-DD).
    
    Handles formats like:
    - MM/DD/YYYY
    - MM-DD-YYYY
    - Month DD, YYYY
    - YYYY-MM-DD
    
    Args:
        raw: Raw date string
        
    Returns:
        ISO formatted date string or empty string if parsing fails
    """
    if not raw:
        return ""
    
    cleaned = raw.strip()
    
    # Common date formats to try
    formats = [
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%Y-%m-%d",
        "%m/%d/%y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
        "%d %b %Y",
        "%Y%m%d",
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    
    # Try regex extraction for common patterns
    date_match = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', cleaned)
    if date_match:
        month, day, year = date_match.groups()
        if len(year) == 2:
            year = "20" + year if int(year) < 50 else "19" + year
        try:
            return f"{year}-{int(month):02d}-{int(day):02d}"
        except ValueError:
            pass
    
    logger.info(f"Could not parse date: {raw}")
    return ""


def normalize_census_tract(raw: str) -> Tuple[str, bool]:
    """
    Validate and normalize census tract format.
    
    Expected format: XXXX.XX (4 digits, decimal, 2 digits)
    
    Args:
        raw: Raw census tract string
        
    Returns:
        Tuple of (normalized_value, is_valid)
    """
    if not raw:
        return ("", False)
    
    cleaned = raw.strip()
    
    # Already in correct format
    if re.match(r'^\d{4}\.\d{2}$', cleaned):
        return (cleaned, True)
    
    # Try to extract and normalize
    digits_only = re.sub(r'[^\d]', '', cleaned)
    
    if len(digits_only) == 6:
        # Insert decimal point
        return (f"{digits_only[:4]}.{digits_only[4:]}", True)
    elif len(digits_only) >= 4:
        # Assume first 4 are tract, pad rest
        tract = digits_only[:4]
        suffix = digits_only[4:6].ljust(2, '0') if len(digits_only) > 4 else "00"
        return (f"{tract}.{suffix}", True)
    
    return (cleaned, False)


def normalize_apn(raw: str) -> str:
    """
    Normalize Assessor's Parcel Number.
    
    Different counties have different formats, so we just clean it up.
    
    Args:
        raw: Raw APN string
        
    Returns:
        Cleaned APN string
    """
    if not raw:
        return ""
    
    # Remove extra whitespace, preserve hyphens and dots
    cleaned = re.sub(r'\s+', ' ', raw.strip())
    return cleaned


def normalize_area(raw: str) -> Tuple[float, str]:
    """
    Parse site area into value and unit.
    
    Args:
        raw: Raw area string (e.g., "7500 sf", "1.5 acres")
        
    Returns:
        Tuple of (value, unit) where unit is "sf" or "ac"
    """
    if not raw:
        return (0.0, "sf")
    
    cleaned = raw.strip().lower()
    
    # Extract numeric value
    num_match = re.search(r'([\d,]+(?:\.\d+)?)', cleaned)
    if not num_match:
        return (0.0, "sf")
    
    value = float(num_match.group(1).replace(',', ''))
    
    # Determine unit
    if any(u in cleaned for u in ['acre', 'ac']):
        unit = "ac"
    else:
        unit = "sf"
    
    return (value, unit)


def area_to_sf(value: float, unit: str) -> float:
    """Convert area to square feet."""
    if unit == "ac":
        return value * 43560
    return value


def sf_to_acres(sf: float) -> float:
    """Convert square feet to acres."""
    return sf / 43560
