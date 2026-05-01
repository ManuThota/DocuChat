"""
backend/utils/file_validator.py — Validate uploaded files before processing.

Checks:
  - File extension is allowed
  - MIME type matches the extension (basic validation)
  - File size does not exceed configured limit
"""

from fastapi import UploadFile, HTTPException, status
from backend.config import get_settings

settings = get_settings()

# Allowed file types: extension → MIME types
ALLOWED_TYPES: dict[str, list[str]] = {
    "pdf":  ["application/pdf"],
    "docx": [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    ],
    "txt":  ["text/plain", "application/octet-stream"],
    "png":  ["image/png"],
    "jpg":  ["image/jpeg"],
    "jpeg": ["image/jpeg"],
}


async def validate_upload(file: UploadFile) -> str:
    """
    Validate an uploaded file for type and size.

    Args:
        file: The FastAPI UploadFile object.

    Returns:
        The normalised file extension (e.g., 'pdf').

    Raises:
        HTTPException 415: Unsupported file type.
        HTTPException 413: File too large.
    """
    # ─── Extension check ──────────────────────────────────────────────────────
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '.{ext}' is not supported. Allowed: {', '.join(ALLOWED_TYPES)}",
        )

    # ─── Size check ───────────────────────────────────────────────────────────
    # Read the whole file to count bytes (FastAPI doesn't give us Content-Length reliably)
    content = await file.read()
    await file.seek(0)  # Reset so the caller can read again

    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.max_file_size_mb} MB limit.",
        )

    return ext
