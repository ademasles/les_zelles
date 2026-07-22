"""Docling parser implementation."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from app.preprocessing.parsers.base import DocumentParser, ParsedDocument

logger = logging.getLogger(__name__)


class DoclingParser(DocumentParser):
    def parse(self, file_path: Path) -> ParsedDocument:
        start = time.perf_counter()

        try:
            from docling.document_converter import DocumentConverter
        except ImportError:
            msg = "docling is not installed"
            raise ImportError(msg) from None

        converter = DocumentConverter()
        result = converter.convert(file_path)
        doc = result.document

        markdown = doc.export_to_markdown()
        structured = doc.model_dump() if hasattr(doc, "model_dump") else {}

        elapsed = time.perf_counter() - start

        parsed = ParsedDocument(
            source_path=file_path,
            parser_name="docling",
            parser_version=getattr(doc, "version", None),
            markdown=markdown,
            structured_data=structured,
            parsing_stats={
                "parser": "docling",
                "duration_s": round(elapsed, 3),
                "fallback_used": False,
            },
        )

        logger.info(
            "Docling parsed %s in %.2fs",
            file_path.name,
            elapsed,
        )

        return parsed
