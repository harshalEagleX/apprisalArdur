"""
OCR Service Configuration for M1 Mac
Configures paths for Tesseract, Poppler, and ImageMagick binaries.
"""

import os
import platform

# Binary paths for M1 Mac (Homebrew)
M1_BINARY_PATHS = {
    'tesseract': '/opt/homebrew/bin/tesseract',
    'pdfinfo': '/opt/homebrew/bin/pdfinfo',
    'pdftoppm': '/opt/homebrew/bin/pdftoppm',
    'magick': '/opt/homebrew/bin/magick',
}

# Intel Mac paths (fallback)
INTEL_BINARY_PATHS = {
    'tesseract': '/usr/local/bin/tesseract',
    'pdfinfo': '/usr/local/bin/pdfinfo',
    'pdftoppm': '/usr/local/bin/pdftoppm',
    'magick': '/usr/local/bin/magick',
}

# Linux paths (fallback)
LINUX_BINARY_PATHS = {
    'tesseract': '/usr/bin/tesseract',
    'pdfinfo': '/usr/bin/pdfinfo',
    'pdftoppm': '/usr/bin/pdftoppm',
    'magick': '/usr/bin/convert',  # ImageMagick on Linux
}


def get_binary_path(binary_name: str) -> str:
    """
    Get the correct binary path based on the system architecture.
    
    Priority:
    1. Environment variable (e.g., TESSERACT_CMD)
    2. Architecture-specific path
    3. System PATH lookup
    """
    # Check environment variable override
    env_var = f'{binary_name.upper()}_CMD'
    if env_var in os.environ:
        return os.environ[env_var]
    
    # Detect architecture and OS
    system = platform.system()
    machine = platform.machine()
    
    # Mac M1/M2 (arm64)
    if system == 'Darwin' and machine == 'arm64':
        path = M1_BINARY_PATHS.get(binary_name)
        if path and os.path.exists(path):
            return path
    
    # Mac Intel (x86_64)
    elif system == 'Darwin' and machine == 'x86_64':
        path = INTEL_BINARY_PATHS.get(binary_name)
        if path and os.path.exists(path):
            return path
    
    # Linux
    elif system == 'Linux':
        path = LINUX_BINARY_PATHS.get(binary_name)
        if path and os.path.exists(path):
            return path
    
    # Fallback to system PATH
    import shutil
    path = shutil.which(binary_name)
    if path:
        return path
    
    # Last resort: assume it's in PATH
    return binary_name


# Configure Tesseract
TESSERACT_CMD = get_binary_path('tesseract')

# Configure Tesseract language data location (optional)
# For M1 Mac with Homebrew: /opt/homebrew/share/tessdata
if platform.system() == 'Darwin' and platform.machine() == 'arm64':
    TESSDATA_PREFIX = '/opt/homebrew/share/tessdata'
elif platform.system() == 'Darwin':
    TESSDATA_PREFIX = '/usr/local/share/tessdata'
else:
    TESSDATA_PREFIX = '/usr/share/tesseract-ocr/4.00/tessdata'

# Configure Poppler tools
PDFINFO_CMD = get_binary_path('pdfinfo')
PDFTOPPM_CMD = get_binary_path('pdftoppm')

# Configure ImageMagick
MAGICK_CMD = get_binary_path('magick')

# OCR Configuration
OCR_CONFIG = {
    # Tesseract settings
    'tesseract_cmd': TESSERACT_CMD,
    'tessdata_prefix': TESSDATA_PREFIX if os.path.exists(TESSDATA_PREFIX) else None,
    'tesseract_lang': 'eng',  # English language
    'tesseract_config': '--oem 3 --psm 6',  # LSTM engine, uniform block of text
    
    # PDF processing settings
    'pdfinfo_cmd': PDFINFO_CMD,
    'pdftoppm_cmd': PDFTOPPM_CMD,
    'pdf_dpi': 300,  # DPI for PDF to image conversion
    
    # Image processing settings
    'magick_cmd': MAGICK_CMD,
    'image_enhance': True,  # Apply image enhancement for better OCR
    
    # Performance settings
    'max_workers': 4,  # Parallel processing threads
    'timeout_seconds': 30,  # OCR timeout per page
}

# Validation: Check if critical binaries exist
def validate_binaries():
    """Validate that required binaries are available."""
    issues = []
    
    if not os.path.exists(TESSERACT_CMD):
        issues.append(f"Tesseract not found at: {TESSERACT_CMD}")
    
    if not os.path.exists(PDFINFO_CMD):
        issues.append(f"pdfinfo not found at: {PDFINFO_CMD}")
    
    if not os.path.exists(PDFTOPPM_CMD):
        issues.append(f"pdftoppm not found at: {PDFTOPPM_CMD}")
    
    return issues


def get_system_info():
    """Get system information for debugging."""
    return {
        'system': platform.system(),
        'machine': platform.machine(),
        'python_version': platform.python_version(),
        'tesseract_cmd': TESSERACT_CMD,
        'tesseract_exists': os.path.exists(TESSERACT_CMD),
        'pdfinfo_cmd': PDFINFO_CMD,
        'pdfinfo_exists': os.path.exists(PDFINFO_CMD),
        'pdftoppm_cmd': PDFTOPPM_CMD,
        'pdftoppm_exists': os.path.exists(PDFTOPPM_CMD),
        'magick_cmd': MAGICK_CMD,
        'magick_exists': os.path.exists(MAGICK_CMD),
    }


# Export configuration
__all__ = [
    'OCR_CONFIG',
    'TESSERACT_CMD',
    'PDFINFO_CMD',
    'PDFTOPPM_CMD',
    'MAGICK_CMD',
    'validate_binaries',
    'get_system_info',
]
