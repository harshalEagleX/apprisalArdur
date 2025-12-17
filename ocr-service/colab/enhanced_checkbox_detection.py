"""
IMPROVED Checkbox Detection Algorithm - Step 6 Replacement
Stricter filtering to eliminate false positives from text and small artifacts
"""

print("\n☑️  Detecting checkboxes with strict filtering...\n")

# Create a copy for visualization
checkbox_image = image_bgr.copy()

# Strategy 1: Edge-based detection for checkbox outlines
print("  🔍 Running edge detection...")
edges = cv2.Canny(enhanced, 50, 150)
kernel_edges = np.ones((3, 3), np.uint8)
dilated_edges = cv2.dilate(edges, kernel_edges, iterations=1)

# Find contours on edge image (for outlines)
contours_edges, _ = cv2.findContours(dilated_edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

# Strategy 2: Contour detection on thresholded image
print("  🔍 Running contour detection...")
# Invert the processed image to detect black squares on white background
inverted = cv2.bitwise_not(processed)
contours_thresh, _ = cv2.findContours(inverted, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

# Combine both sets of contours
all_contours = list(contours_edges) + list(contours_thresh)

print(f"  ✓ Found {len(all_contours)} total contours to analyze")
print("\n  🎯 Filtering for checkbox candidates with STRICT criteria...\n")

checkbox_candidates = []

# STRICTER parameters to avoid false positives
min_size = 15          # INCREASED from 8 - minimum width/height in pixels
max_size = 80          # DECREASED from 100 - maximum width/height in pixels
min_area = 225         # INCREASED from 80 - minimum area (15x15)
max_area = 6400        # Maximum area (80x80)
aspect_ratio_min = 0.6 # STRICTER from 0.5 - more square-like
aspect_ratio_max = 1.7 # STRICTER from 2.0 - more square-like

# Filter contours to find checkboxes
for contour in all_contours:
    # Get bounding rectangle
    x, y, w, h = cv2.boundingRect(contour)
    
    # Calculate aspect ratio and area
    aspect_ratio = float(w) / h if h > 0 else 0
    area = cv2.contourArea(contour)
    bounding_area = w * h
    
    # Skip if basic size constraints not met
    if not (min_size <= w <= max_size and min_size <= h <= max_size):
        continue
    
    if not (min_area <= area <= max_area):
        continue
    
    if not (aspect_ratio_min <= aspect_ratio <= aspect_ratio_max):
        continue
    
    # Approximate the contour to a polygon
    epsilon = 0.04 * cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, epsilon, True)
    
    # Checkboxes should have 4 corners (rectangle-like)
    # Allow 4-6 vertices (stricter than before)
    if len(approx) >= 4 and len(approx) <= 6:
        # Calculate solidity (area / convex hull area)
        hull = cv2.convexHull(contour)
        hull_area = cv2.contourArea(hull)
        solidity = float(area) / hull_area if hull_area > 0 else 0
        
        # Checkboxes have high solidity (>0.65) - STRICTER from 0.5
        if solidity > 0.65:
            # Calculate extent (area / bounding box area)
            extent = float(area) / bounding_area if bounding_area > 0 else 0
            
            # For square shapes, extent should be high (>0.5) - STRICTER from 0.4
            if extent > 0.5:
                # Additional check: perimeter should be reasonable for the area
                perimeter = cv2.arcLength(contour, True)
                # For a perfect square: perimeter² / area ≈ 16
                # For checkboxes, allow some deviation but keep it reasonable
                if perimeter > 0:
                    circularity = (4 * np.pi * area) / (perimeter * perimeter)
                    # Circularity for square ≈ 0.785, allow 0.6-0.9
                    if 0.6 <= circularity <= 0.95:
                        checkbox_candidates.append({
                            'bbox': (x, y, w, h),
                            'area': area,
                            'solidity': solidity,
                            'extent': extent,
                            'vertices': len(approx),
                            'circularity': circularity
                        })

print(f"  ✓ Found {len(checkbox_candidates)} checkbox candidates")

# Non-maximum suppression to remove duplicates
print("  🔧 Removing duplicate detections...")

def is_overlapping(box1, box2, threshold=0.3):
    """Check if two bounding boxes overlap significantly"""
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2
    
    # Calculate intersection area
    x_left = max(x1, x2)
    y_top = max(y1, y2)
    x_right = min(x1 + w1, x2 + w2)
    y_bottom = min(y1 + h1, y2 + h2)
    
    if x_right < x_left or y_bottom < y_top:
        return False
    
    intersection = (x_right - x_left) * (y_bottom - y_top)
    area1 = w1 * h1
    area2 = w2 * h2
    
    # Calculate IoU (Intersection over Union)
    iou = intersection / float(area1 + area2 - intersection)
    
    return iou > threshold

# Sort by circularity (more square-like first), then by area
checkbox_candidates.sort(key=lambda x: (x['circularity'], x['area']), reverse=True)
checkbox_locations = []

for candidate in checkbox_candidates:
    bbox = candidate['bbox']
    
    # Check if this overlaps with any already selected checkbox
    overlap = False
    for selected_bbox in checkbox_locations:
        if is_overlapping(bbox, selected_bbox, threshold=0.3):
            overlap = True
            break
    
    if not overlap:
        checkbox_locations.append(bbox)

checkbox_count = len(checkbox_locations)

print(f"  ✓ After removing duplicates: {checkbox_count} unique checkboxes\n")

# Sort checkboxes by position (top to bottom, left to right)
checkbox_locations.sort(key=lambda box: (box[1], box[0]))

# Draw all detected checkboxes
for i, (x, y, w, h) in enumerate(checkbox_locations, 1):
    # Draw green rectangle
    cv2.rectangle(checkbox_image, (x, y), (x + w, y + h), (0, 255, 0), 3)
    
    # Add checkbox number with background for visibility
    label = str(i)
    label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
    
    # Draw background rectangle for label
    cv2.rectangle(checkbox_image, 
                 (x - 5, y - label_size[1] - 10),
                 (x + label_size[0] + 5, y - 5),
                 (255, 255, 255), -1)
    
    # Draw label text
    cv2.putText(checkbox_image, label, (x, y - 8),
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

print(f"✅ Total checkboxes detected: {checkbox_count}")
print(f"   Checkbox locations: {len(checkbox_locations)} found\n")

# Display edge detection and final result side by side
fig, axes = plt.subplots(1, 3, figsize=(20, 12))
fig.suptitle('Checkbox Detection Pipeline (Strict Filtering)', fontsize=18, fontweight='bold')

axes[0].imshow(edges, cmap='gray')
axes[0].set_title('Edge Detection', fontsize=14)
axes[0].axis('off')

axes[1].imshow(inverted, cmap='gray')
axes[1].set_title('Inverted Threshold', fontsize=14)
axes[1].axis('off')

axes[2].imshow(cv2.cvtColor(checkbox_image, cv2.COLOR_BGR2RGB))
axes[2].set_title(f'Detected Checkboxes: {checkbox_count}', fontsize=14, fontweight='bold')
axes[2].axis('off')

plt.tight_layout()
plt.show()

# Print detailed checkbox information
if checkbox_count > 0:
    print("\n" + "=" * 60)
    print("CHECKBOX DETAILS")
    print("=" * 60)
    for i, (x, y, w, h) in enumerate(checkbox_locations, 1):
        print(f"  Checkbox #{i:2d}: Position ({x:4d}, {y:4d}) | Size {w:2d}x{h:2d} pixels")
    print("=" * 60 + "\n")
else:
    print("\n⚠️  No checkboxes detected.")
    print("     Try adjusting detection parameters if checkboxes exist.\n")
