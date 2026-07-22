"""Parser registry — selects parser by file extension and settings."""

from __future__ import annotations

from pathlib import Path

from app.preprocessing.parsers.base import DocumentParser
from app.preprocessing.parsers.docling_parser import DoclingParser
from app.preprocessing.parsers.pymupdf_parser import PyMuPDFParser
from app.preprocessing.parsers.tesseract_parser import TesseractParser


def get_parser_for_file(file_path: Path) -> DocumentParser:
    ext = file_path.suffix.lower()
    if ext in (".pdf", ".docx"):
        return DoclingParser()
    msg = f"Unsupported file extension: {ext}"
    raise ValueError(msg)


def get_fallback_chain(file_path: Path) -> list[DocumentParser]:
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        return [DoclingParser(), PyMuPDFParser(), TesseractParser()]
    if ext == ".docx":
        return [DoclingParser(), TesseractParser()]
    return []
