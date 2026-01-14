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
        dims = dim_match.group(1).strip()
        low = dims.lower()
        if low not in {"listed)", "listed", ")"} and len(dims) >= 6:
            data["siteDimensions"] = dims
        
    # Site Area
    # Look for "Site Area" or "Area" followed by number
    area_match = re.search(r"(?:Site Area|Area)\s*[:\.]?\s*([\d,]+(?:\.\d+)?)\s*(sf|sq\.?\s*ft|ac|acres)", text, re.IGNORECASE)
    if area_match:
        data["siteArea"] = float(area_match.group(1).replace(',', ''))
        data["siteAreaUnit"] = area_match.group(2).lower()

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

    # Effective Age
    ea_match = re.search(r"Effective Age\s*\(?(?:Yrs|Years)\)?\s*[:\.]?\s*(\d{1,3})", text, re.IGNORECASE)
    if ea_match:
        data["effectiveAge"] = int(ea_match.group(1))

    # Units
    units_match = re.search(r"Units\s*(?:\W|\s)*((?:One|Two|Three|Four)|\d{1,2})", text, re.IGNORECASE)
    if units_match:
        raw = units_match.group(1).strip()
        word_map = {"one": 1, "two": 2, "three": 3, "four": 4}
        data["unitsCount"] = word_map.get(raw.lower(), int(raw) if raw.isdigit() else None)

    # Stories
    stories_match = re.search(r"#\s*of\s*Stories\s*[:\.]?\s*([^\n]{1,10})", text, re.IGNORECASE)
    if stories_match:
        data["stories"] = stories_match.group(1).strip()

    # Type
    type_match = re.search(r"\bType\b\s*[:\.]?\s*([^\n]{2,30})", text, re.IGNORECASE)
    if type_match:
        val = type_match.group(1).strip()
        val = re.sub(r"\s+(?:Det\.|Att\.|S-Det/End Unit).*", "", val, flags=re.IGNORECASE).strip() or val
        data["improvementType"] = val

    # Existing/Proposed/Under Construction
    status_chunk_match = re.search(r"(Existing|Proposed|Under\s+Const\.?|Under\s+Construction)", text, re.IGNORECASE)
    if status_chunk_match:
        raw = status_chunk_match.group(1).strip().lower()
        if "under" in raw:
            data["constructionStatus"] = "Under Construction"
        else:
            data["constructionStatus"] = raw.title()

    # Foundation (checkboxes listed)
    foundation_chunk_start = text.lower().find("foundation")
    if foundation_chunk_start != -1:
        chunk = text[foundation_chunk_start:foundation_chunk_start + 400]
        for key, label in [
            ("Concrete Slab", "Concrete Slab"),
            ("Crawl Space", "Crawl Space"),
            ("Full Basement", "Full Basement"),
            ("Partial Basement", "Partial Basement"),
        ]:
            if re.search(rf"\b{re.escape(key)}\b", chunk, re.IGNORECASE):
                data["foundation"] = label
                break

        sump_match = re.search(r"Sump\s*Pump", chunk, re.IGNORECASE)
        if sump_match:
            data["sumpPump"] = True

        # Evidence of (these are typically checkboxes near the field)
        if re.search(r"Evidence of\s*(?:Moisture|Dampness)", chunk, re.IGNORECASE):
            data["evidenceDampness"] = True
        if re.search(r"Evidence of\s*Settlement", chunk, re.IGNORECASE):
            data["evidenceSettlement"] = True
        if re.search(r"Evidence of\s*Infestation", chunk, re.IGNORECASE):
            data["evidenceInfestation"] = True

    # Exterior / Interior description (material/condition tokens)
    def _grab_field(label: str, max_len: int = 40) -> Optional[str]:
        m = re.search(rf"{label}\s*[:\.]?\s*([^\n]{{1,{max_len}}})", text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    data["foundationWalls"] = _grab_field(r"Foundation\s+Walls") or data.get("foundationWalls")
    data["exteriorWalls"] = _grab_field(r"Exterior\s+Walls") or data.get("exteriorWalls")
    data["roofSurface"] = _grab_field(r"Roof\s+Surface") or data.get("roofSurface")
    data["guttersDownspouts"] = _grab_field(r"Gutters\s*&\s*Downspouts") or data.get("guttersDownspouts")
    data["windowType"] = _grab_field(r"Window\s+Type") or data.get("windowType")
    data["stormSashScreens"] = _grab_field(r"Storm\s+Sash/(?:Insulated\s+)?Screens") or data.get("stormSashScreens")

    data["floors"] = _grab_field(r"Floors") or data.get("floors")
    data["walls"] = _grab_field(r"Walls") or data.get("walls")
    data["trimFinish"] = _grab_field(r"Trim/Finish") or data.get("trimFinish")
    data["bathFloor"] = _grab_field(r"Bath\s+Floor") or data.get("bathFloor")
    data["bathWainscot"] = _grab_field(r"Bath\s+Wainscot") or data.get("bathWainscot")

    # Car storage + driveway
    car_storage = _grab_field(r"Car\s+Storage", max_len=30)
    if car_storage:
        data["carStorage"] = car_storage
    driveway_surface = _grab_field(r"Driveway\s+Surface", max_len=30)
    if driveway_surface:
        data["drivewaySurface"] = driveway_surface

    # Condition rating + condition commentary (often in a sentence)
    cond_match = re.search(r"\b(C[1-6])\b", text)
    if cond_match:
        data["conditionRating"] = cond_match.group(1)

    # Condition commentary line
    cond_line = re.search(r"Describe the condition of the property.*?\n([^\n]{10,200})", text, re.IGNORECASE)
    if cond_line:
        data["conditionCommentary"] = cond_line.group(1).strip()

    # Adverse conditions affecting livability
    if re.search(r"adverse conditions.*\?\s*(?:Yes|No)", text, re.IGNORECASE):
        yes = re.search(r"adverse conditions.*\?[^\n]{0,80}(?:\[x\]|\[X\]|X|><|XX)\s*Yes", text, re.IGNORECASE)
        no = re.search(r"adverse conditions.*\?[^\n]{0,80}(?:\[x\]|\[X\]|X|><|XX)\s*No", text, re.IGNORECASE)
        if yes and not no:
            data["adverseConditionsAffectingLivability"] = True
        elif no and not yes:
            data["adverseConditionsAffectingLivability"] = False

    # Conforms to neighborhood
    conf_yes = re.search(r"conform to the neighborhood.*\?[^\n]{0,120}(?:\[x\]|\[X\]|X|><|XX)\s*Yes", text, re.IGNORECASE)
    conf_no = re.search(r"conform to the neighborhood.*\?[^\n]{0,120}(?:\[x\]|\[X\]|X|><|XX)\s*No", text, re.IGNORECASE)
    if conf_yes and not conf_no:
        data["conformsToNeighborhood"] = True
    elif conf_no and not conf_yes:
        data["conformsToNeighborhood"] = False

    # Room Counts (Total/Bed/Bath)
    # "Above Grade ... Rooms Bedrooms Baths"
    # This usually appears in a grid row.
    # Regex for "Total Bdrms Baths ... 6 3 2.0"
    # Finding this robustly in raw text is hard without layout analysis.
    # "Finished area above grade contains: <rooms> Rooms <beds> Bedrooms <baths> Bath(s) <gla> Square Feet ..."
    finished_area_match = re.search(
        r"(?is)Finished\s+area\s+above\s+grade\s+contains\s*:?\s*"
        r"(\d{1,2})\s*Rooms\s*"
        r"(\d{1,2})\s*Bedrooms\s*"
        r"(\d+(?:\.\d+)?)\s*Bath\(s\)\s*"
        r"([\d,]{3,6})\s*Square\s+Feet\s+of\s+Gross\s+Living\s+Area\s+Above\s+Grade",
        text,
        re.IGNORECASE,
    )
    if finished_area_match:
        try:
            data["totalRooms"] = int(finished_area_match.group(1))
            data["bedrooms"] = int(finished_area_match.group(2))
            data["baths"] = float(finished_area_match.group(3))
            data["gla"] = float(finished_area_match.group(4).replace(",", ""))
        except ValueError:
            pass

    # Utilities status (FHA-style wording often in addenda)
    util_stmt = None
    util_m = re.search(
        r"(?is)\butilities\b[\s\S]{0,180}?\b(?:were|are|was)\b[\s\S]{0,180}?\b(on|off)\b",
        text,
        re.IGNORECASE,
    )
    if util_m:
        util_stmt = re.sub(r"\s+", " ", util_m.group(0)).strip()
    else:
        util_m = re.search(r"(?is)\butilities\b[\s\S]{0,220}?\bnot\s+on\b", text, re.IGNORECASE)
        if util_m:
            util_stmt = re.sub(r"\s+", " ", util_m.group(0)).strip()
        else:
            util_m = re.search(r"(?is)\ball\s+utilities\b[\s\S]{0,240}?\b(off|on)\b", text, re.IGNORECASE)
            if util_m:
                util_stmt = re.sub(r"\s+", " ", util_m.group(0)).strip()
    if util_stmt:
        data["utilitiesStatus"] = util_stmt

    # N-4: Present Land Use - 'Other' description often appears in narrative/addenda.
    other_desc = None
    m = re.search(
        r"(?is)\bOther\s+Land\s+Use\b\s*[:\-]?\s*\n?\s*([\s\S]{10,240}?)(?=\n\s*(?:Neighborhood\s+Predominant\s+Age|Market\s+Conditions|Neighborhood\s+Boundaries|\Z))",
        text,
        re.IGNORECASE,
    )
    if m:
        other_desc = re.sub(r"\s+", " ", m.group(1)).strip()
    if not other_desc:
        m = re.search(
            r"(?is)\b\"?Other\"?\s+line\s+item\s+\d{1,3}%\s+refers\s+to\s*([\s\S]{10,220}?)(?:\.|\n|\Z)",
            text,
            re.IGNORECASE,
        )
        if m:
            other_desc = re.sub(r"\s+", " ", m.group(1)).strip(" .")
    if other_desc and "form 1004" not in other_desc.lower():
        data["landUseOtherDescription"] = other_desc[:240]

    # I-8: Additional features narrative sometimes appears as a standalone sentence.
    if "additionalFeatures" not in data:
        m = re.search(
            r"(?is)(?:No\s+additional\s+features\.|The\s+additional\s+features\s+include\s*[:;]\s*[^\n]{5,240})",
            text,
            re.IGNORECASE,
        )
        if m:
            val = re.sub(r"\s+", " ", m.group(0)).strip()
            if re.search(r"\bno\s+additional\s+features\b", val, re.IGNORECASE):
                data["additionalFeatures"] = "NONE"
            else:
                data["additionalFeatures"] = val[:240]

    # If the report explicitly states Energy Efficient Items, use it to satisfy I-8 wording expectations.
    ee_val = None
    ee_m = re.search(
        r"(?is)\bEnergy\s+Efficient\s+Items\b\s*(?:\n|\r|\s)+\s*([^\n\r]{2,120})",
        text,
        re.IGNORECASE,
    )
    if ee_m:
        ee_val = re.sub(r"\s+", " ", ee_m.group(1)).strip(" .")
        if re.search(r"\bnone\b", ee_val, re.IGNORECASE):
            ee_val = "None"

    if ee_val:
        cur = (data.get("additionalFeatures") or "").strip()
        if not cur:
            data["additionalFeatures"] = f"Energy Efficient Items: {ee_val}"[:240]
        else:
            low = cur.lower()
            if not any(k in low for k in ["energy", "efficient", "insulation", "solar", "low-e", "heat pump", "tankless"]):
                # Append a short, truthful note so the field references energy efficient items when the report has it.
                data["additionalFeatures"] = (cur + f"; Energy Efficient Items: {ee_val}")[:240]
    
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
