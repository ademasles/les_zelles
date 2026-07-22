"""Upload security helpers for Analyse-DCE backend."""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings

ALLOWED_EXTENSIONS = {".pdf", ".docx"}


def is_allowed_extension(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def validate_upload_size(content: bytes) -> None:
    max_bytes = settings.max_upload_bytes
    if len(content) > max_bytes:
        msg = f"File too large: {len(content)} bytes (max {max_bytes} bytes)"
        raise ValueError(msg)
