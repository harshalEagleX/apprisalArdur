"""
Compatibility shim for environments where `import fitz` does not resolve
correctly even though PyMuPDF is installed.
"""

from pymupdf import *  # noqa: F401,F403
