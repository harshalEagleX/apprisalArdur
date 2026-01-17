import sys
import os
import json

# Add app to path
sys.path.append(os.getcwd())

from app.extraction.layout_extractor import extract_urar_neighborhood

# PDF Path
pdf_path = "testFile/apprisal_002.pdf"
if not os.path.exists(pdf_path):
    print(f"File not found: {pdf_path}")
    # Try looking in 'ocr-service/testFile' relative to cwd?
    pdf_path = "ocr-service/testFile/apprisal_002.pdf"
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        sys.exit(1)

print(f"Debug: Extracting Neighborhood from {pdf_path}")

try:
    data = extract_urar_neighborhood(pdf_path)
    print("\n--- RESULTS ---")
    print(json.dumps(data, indent=2))
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
