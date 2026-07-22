"""Compat — delegates to new parser implementation.

Supports both legacy signatures:
  extract_text_from_file(content: bytes, filename: str)
  extract_text_from_file(path: str)  # old documents.py style
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import NamedTemporaryFile

from app.preprocessing.parsers.fallback import parse_with_fallback


async def extract_text_from_file(content: bytes | str, filename: str | None = None) -> list[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract_sync, content, filename)


def _extract_sync(content: bytes | str, filename: str | None = None) -> list[dict]:
    if isinstance(content, str):
        file_path = Path(content)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {content}")
        doc_name = file_path.name
        if file_path.suffix.lower() not in (".pdf", ".docx"):
            text = file_path.read_text(encoding="utf-8", errors="replace")
            return [{"doc_name": doc_name, "page_number": None, "text": text}]
        parsed = parse_with_fallback(file_path)
    else:
        suffix = Path(filename or "unknown").suffix
        doc_name = filename or "unknown"
        if suffix.lower() not in (".pdf", ".docx"):
            text = content.decode("utf-8", errors="replace")
            return [{"doc_name": doc_name, "page_number": None, "text": text}]
        with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            file_path = Path(tmp.name)
        try:
            parsed = parse_with_fallback(file_path)
        finally:
            file_path.unlink(missing_ok=True)

    pages = [
        {"doc_name": doc_name, "page_number": p.page_number, "text": p.text} for p in parsed.pages
    ]
    if not pages:
        pages = [{"doc_name": doc_name, "page_number": None, "text": parsed.markdown}]
    return pages
