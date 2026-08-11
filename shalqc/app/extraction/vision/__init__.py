"""
extraction.vision — UAD 3.6 vision extraction.

The 2.6 pipeline uses deterministic code for PERCEPTION and an LLM for CHECKING.
For a flattened 3.6 report that is backwards: perception is the messy,
layout-dependent, visual problem (an LLM's strength) and checking is closed-form
arithmetic (code's strength). This package inverts the two for the 3.6 path only:

    vision/  -> the model TRANSCRIBES pixels. It never judges, never infers,
                never normalizes. `null` is a first-class answer.
    verify.py-> deterministic arithmetic decides whether the transcription is
                faithful to the page.
    language/-> the existing judge decides compliance, unchanged.

Nothing here answers "did the appraiser comply" — that stays with the judge, and
the "LLM judges, no hardcode" doctrine is untouched.
"""

from app.extraction.vision.budget import BudgetExceeded, BudgetGovernor  # noqa: F401
from app.extraction.vision.provider import VisionProvider, get_vision_provider  # noqa: F401

__version__ = "vis-1.0.0"
