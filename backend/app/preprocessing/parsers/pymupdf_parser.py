"""PyMuPDF fallback parser for simple born-digital PDFs."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from app.preprocessing.parsers.base import DocumentParser, ParsedDocument, ParsedPage

logger = logging.getLogger(__name__)


class PyMuPDFParser(DocumentParser):
    def parse(self, file_path: Path) -> ParsedDocument:
        import fitz

        start = time.perf_counter()
        doc = fitz.open(file_path)
        pages: list[ParsedPage] = []
        all_text_parts: list[str] = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            all_text_parts.append(text)
            pages.append(
                ParsedPage(
                    page_number=page_num + 1,
                    text=text,
                )
            )

        elapsed = time.perf_counter() - start
        full_text = "\n\n".join(all_text_parts)

        parsed = ParsedDocument(
            source_path=file_path,
            parser_name="pymupdf",
            parser_version=fitz.version,
            markdown=full_text,
            pages=pages,
            parsing_stats={
                "parser": "pymupdf",
                "duration_s": round(elapsed, 3),
                "num_pages": len(pages),
                "fallback_used": False,
            },
        )

        logger.info("PyMuPDF parsed %s in %.2fs", file_path.name, elapsed)
        return parsed
