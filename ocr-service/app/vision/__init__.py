"""Cloud-vision integration (Google Cloud Vision) for comparable-photo QC.

Public surface:
  vision_available() -> bool          # configured + library present
  get_vision_client() -> VisionClient | None
  VisionAnnotation                    # labels / text / objects from one image
"""

from app.vision.analyzer import (  # noqa: F401
    GeminiPhotoAnalyzer,
    GoogleVisionPhotoAnalyzer,
    PhotoSignals,
    analyzer_available,
    get_photo_analyzer,
)
from app.vision.vision_client import (  # noqa: F401
    VisionAnnotation,
    VisionClient,
    get_vision_client,
    vision_available,
)
