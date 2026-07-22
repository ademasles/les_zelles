"""Tesseract OCR fallback parser for scanned PDFs and images."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from app.preprocessing.parsers.base import DocumentParser, ParsedDocument, ParsedPage

logger = logging.getLogger(__name__)


class TesseractParser(DocumentParser):
    def parse(self, file_path: Path) -> ParsedDocument:
        import fitz
        import pytesseract
        from PIL import Image

        start = time.perf_counter()
        pages: list[ParsedPage] = []
        all_text_parts: list[str] = []

        pdf_doc = fitz.open(file_path)
        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            pix = page.get_pixmap(dpi=300)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img, lang="fra+eng")
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
            parser_name="tesseract",
            parser_version=pytesseract.get_tesseract_version(),
            markdown=full_text,
            pages=pages,
            parsing_stats={
                "parser": "tesseract",
                "duration_s": round(elapsed, 3),
                "num_pages": len(pages),
                "fallback_used": False,
            },
        )

        logger.info("Tesseract parsed %s in %.2fs", file_path.name, elapsed)
        return parsed
