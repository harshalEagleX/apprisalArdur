def is_valid_pdf(file_path: str) -> bool:
    """
    Check if the file has the PDF magic header %PDF-
    This prevents standard executables renamed as .pdf from being processed by some tools,
    though PyMuPDF is generally robust, this is a good security practice.
    """
    try:
        with open(file_path, 'rb') as f:
            header = f.read(5)
            # Many PDFs start with %PDF-, but some start with garbage followed by %PDF-
            return header.startswith(b'%PDF-')
    except Exception:
        return False
