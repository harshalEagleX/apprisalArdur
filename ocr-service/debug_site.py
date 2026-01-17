import sys
import os
import json

# Add app to path
sys.path.append(os.getcwd())

from app.extraction.layout_extractor import extract_urar_layout_fields

# PDF Path (for layout)
pdf_path = "testFile/apprisal_002.pdf"
if not os.path.exists(pdf_path):
    print(f"File not found: {pdf_path}")
    sys.exit(1)

# Text Path (for text fields)
txt_path = "test_output/apprisal_002_appraisal.txt"
if not os.path.exists(txt_path):
    print(f"File not found: {txt_path}")
    # Try alternate location
    txt_path = "../test_output/apprisal_002_appraisal.txt" 
    if not os.path.exists(txt_path):
         print(f"File not found alternate: {txt_path}")
         sys.exit(1)

with open(txt_path, "r") as f:
    full_text = f.read()

print(f"Debug: Extracting Layout Fields (Site) from {pdf_path}")

try:
    data = extract_urar_layout_fields(pdf_path, full_text=full_text)
    
    # Filter for Site keys
    site_keys = [
        "siteDimensions", "siteArea", "siteAreaUnit", "siteShape", "siteView",
        "zoningClassification", "zoningCompliance", "highestAndBestUse",
        "femaFloodHazard", "femaFloodZone", "femaMapNumber", "femaMapDate",
        "utilitiesTypical", "adverseSiteConditions"
    ]
    
    site_data = {k: v for k, v in data.items() if k in site_keys}
    
    print("\n--- RESULTS ---")
    print(json.dumps(site_data, indent=2))
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
