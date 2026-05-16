"""
Layered Extraction System

Each layer runs independently and concurrently.
Results are merged by confidence score.

Layer order (all parallel, merged after):
  L0  pdfplumber_extractor    — words + tables from digital PDFs
  L1  checkbox_visual_extractor — OpenCV fill-density for Yes/No
  L2  yesno_resolver          — context-aware Yes/No disambiguation
  L3  grid_resolver           — row×column table field mapping
  L4  spatial_extractor       — existing spatial label matching (enhanced)
  L5  paddle_ocr_extractor    — PaddleOCR for scanned pages
"""
