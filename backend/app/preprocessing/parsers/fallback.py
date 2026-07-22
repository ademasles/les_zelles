"""Parser fallback orchestration — Docling first, chain fallback on failure."""

from __future__ import annotations

import logging
from pathlib import Path

from app.preprocessing.parsers.base import DocumentParser, ParsedDocument
from app.preprocessing.parsers.registry import get_fallback_chain

logger = logging.getLogger(__name__)

_PARSER_CACHE: dict[str, DocumentParser] = {}


def parse_with_fallback(file_path: Path) -> ParsedDocument:
    chain = get_fallback_chain(file_path)
    if not chain:
        msg = f"No parser available for {file_path.suffix}"
        raise ValueError(msg)

    errors: list[str] = []
    for parser in chain:
        try:
            result = parser.parse(file_path)
            parser_name = type(parser).__name__.replace("Parser", "").lower()
            if errors:
                result.parsing_stats["fallback_used"] = True
                result.parsing_stats["fallback_chain"] = [
                    type(p).__name__ for p in chain
                ]
                result.parsing_stats["fallback_errors"] = errors
                logger.warning(
                    "Fallback to %s after errors: %s", parser_name, errors
                )
            return result
        except Exception as e:
            errors.append(f"{type(parser).__name__}: {e}")
            logger.warning("Parser %s failed: %s", type(parser).__name__, e)
            continue

    msg = f"All parsers failed for {file_path.name}: {'; '.join(errors)}"
    raise RuntimeError(msg)
