import sys
import os
import re

# Add app to path
sys.path.append(os.getcwd())

from app.extraction.layout_extractor import _extract_comps_from_text_v2

# Read the text file
txt_path = "test_output/apprisal_002_appraisal.txt"
if not os.path.exists(txt_path):
    print(f"File not found: {txt_path}")
    sys.exit(1)

with open(txt_path, "r") as f:
    full_text = f.read()

print(f"Loaded {len(full_text)} chars.")

# Run extraction
data = _extract_comps_from_text_v2(full_text)

print("\n--- RESULTS ---")
comps = data.get("comparables", [])
print(f"Found {len(comps)} comparables.")

for i, c in enumerate(comps):
    print(f"\nComp {i+1}:")
    for k, v in c.items():
        print(f"  {k}: {v}")
