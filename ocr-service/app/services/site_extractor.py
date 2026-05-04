import re
from typing import Dict, Any, Optional

def extract_advanced_fields(text: str) -> Dict[str, Any]:
    """
    Extracts detailed appraisal fields using robust regex patterns 
    that look for common 1004 form labels.
    """
    data = {}
    
    # 1. Subject Section
    # Address (often improved regex needed)
    addr_match = re.search(r"(?:Property Address|Subject Property)[\s:.]+(.*?)(?:City|State|Zip|Borrower)", text, re.IGNORECASE | re.DOTALL)
    if addr_match:
        data["propertyAddress"] = addr_match.group(1).strip().replace('\n', ' ')

    borrower_match = re.search(r"Borrower[\s:.]+(.*?)(?:Owner|Occupant|Map Ref)", text, re.IGNORECASE)
    if borrower_match:
        data["borrowerName"] = borrower_match.group(1).strip()

    # 2. Site Section
    # Dimensions (Look for digit x digit pattern or specific label)
    # Often "Dimensions" is followed by text.
    dim_match = re.search(r"Dimensions\s*[:\.]?\s*([\d\.]+\s*[xX]\s*[\d\.]+)", text)
    if not dim_match:
         dim_match = re.search(r"Dimensions\s*[:\.]?\s*([^\n]{5,30})", text, re.IGNORECASE)
    if dim_match:
        data["siteDimensions"] = dim_match.group(1).strip()
        
    # Site Area
    # Look for "Site Area" or "Area" followed by number
    area_match = re.search(r"(?:Site Area|Area)\s*[:\.]?\s*([\d,]+(?:\.\d+)?)\s*(sf|sq\.?\s*ft|ac|acres)", text, re.IGNORECASE)
    if area_match:
        area_raw = (area_match.group(1) or "").replace(',', '').strip()
        try:
            data["siteArea"] = float(area_raw)
            data["siteAreaUnit"] = area_match.group(2).lower()
        except ValueError:
            pass

    # Zoning Compliance
    # The form usually has "Specific Zoning Classification ... Zoning Compliance [ ] Legal ..."
    # We search for "Zoning Compliance" and grab the next ~50 chars.
    z_start = text.find("Zoning Compliance")
    if z_start != -1:
        z_chunk = text[z_start:z_start+200] # Grab enough text
        if "Legal" in z_chunk and not "Non-Conforming" in z_chunk: # Primitive check
            data["zoningCompliance"] = "Legal"
        elif "Legal Non-Conforming" in z_chunk:
             data["zoningCompliance"] = "Legal Non-Conforming"
        elif "No Zoning" in z_chunk:
             data["zoningCompliance"] = "No Zoning"
        elif "Illegal" in z_chunk:
             data["zoningCompliance"] = "Illegal"

    # Highest and Best Use
    # "Is the subject property's existing use its highest and best use?"
    # It might appear as "Highest and Best Use ... Yes"
    h_start = text.lower().find("highest and best use")
    if h_start != -1:
        h_chunk = text[h_start:h_start+200]
        if "Yes" in h_chunk or "[x] Yes" in h_chunk:
             data["highestAndBestUse"] = True

    # 3. Improvements
    # Design Style
    # "Design (Style)" ...
    ds_match = re.search(r"Design\s*\(Style\)\s*[:\.]?\s*([^\n\d]+)", text, re.IGNORECASE)
    if ds_match:
        data["designStyle"] = ds_match.group(1).strip()

    # Year Built
    yr_match = re.search(r"Year Built[\s:.]+(\d{4})", text, re.IGNORECASE)
    if yr_match:
        data["yearBuilt"] = int(yr_match.group(1))

    # Room Counts (Total/Bed/Bath)
    # "Above Grade ... Rooms Bedrooms Baths"
    # This usually appears in a grid row.
    # Regex for "Total Bdrms Baths ... 6 3 2.0"
    # Finding this robustly in raw text is hard without layout analysis.
    # We'll look for pattern "Above Grade" ... digits
    # Attempt to capture the line with the counts
    
    # 4. Sales Comparison
    # Count sales
    # Look for "There are X comparable sales" or counting columns in grid (hard in text)
    # We might look for "Comparable Sale # 1", "# 2", "# 3"
    comps = re.findall(r"Comparable Sale #\s*\d", text)
    data["comparableCount"] = len(comps)

    # 5. Market Conditions
    # Look for implicit text sections using headers
    if "Market Conditions" in text:
        # Check if there is text following it
        pass

    return data
