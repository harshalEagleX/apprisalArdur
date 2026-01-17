import sys
import os
import json

# Add app to path
sys.path.append(os.getcwd())

from app.extraction.layout_extractor import extract_urar_text_fields

# Text Path
txt_path = "test_output/apprisal_002_appraisal.txt"
if not os.path.exists(txt_path):
    print(f"File not found: {txt_path}")
    sys.exit(1)

with open(txt_path, "r") as f:
    full_text = f.read()

print(f"Loaded {len(full_text)} chars.")
data = extract_urar_text_fields(full_text)

print("\n--- RESULTS ---")
print(json.dumps({k: v for k, v in data.items() if "neighborhood" in k.lower() or "market" in k.lower()}, indent=2))
