"""Section-aware Markdown chunking.

Strategy:
1. Detect Markdown headings
2. Split by heading boundaries, building a heading path
3. Split oversized sections by paragraph/list/table
4. Apply limited overlap only inside the same section
"""

from __future__ import annotations

import re
from typing import Any

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
OVERLAP_CHARS = 100


def _estimate_token_count(text: str) -> int:
    return len(text.split())


def _split_oversized(
    text: str,
    heading_path: list[str],
    section_title: str,
    start_offset: int,
    doc_id: str,
    chunk_index: int,
    page_start: int | None,
    max_chars: int = 3000,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    paragraphs = re.split(r"(\n\n+)", text)
    current = ""
    i = chunk_index

    for para in paragraphs:
        if not para.strip():
            continue
        if len(current) + len(para) > max_chars and current:
            chunks.append(
                _make_chunk(
                    current,
                    heading_path,
                    section_title,
                    start_offset,
                    doc_id,
                    i,
                    page_start,
                )
            )
            i += 1
            overlap = current[-OVERLAP_CHARS:] if len(current) > OVERLAP_CHARS else ""
            current = overlap + para
        else:
            current += para

    if current.strip():
        chunks.append(
            _make_chunk(
                current,
                heading_path,
                section_title,
                start_offset,
                doc_id,
                i,
                page_start,
            )
        )
    return chunks


def _make_chunk(
    text: str,
    heading_path: list[str],
    section_title: str,
    start_offset: int,
    doc_id: str,
    chunk_index: int,
    page_start: int | None,
) -> dict[str, Any]:
    return {
        "document_id": doc_id,
        "chunk_index": chunk_index,
        "text": text.strip(),
        "markdown": text.strip(),
        "heading_path": heading_path,
        "section_title": section_title,
        "page_start": page_start,
        "page_end": page_start,
        "source_block_ids": [],
        "token_count": _estimate_token_count(text),
        "metadata": {},
    }


def chunk_markdown(
    markdown: str,
    document_id: str = "",
    page_start: int | None = None,
    max_chars: int = 3000,
) -> list[dict[str, Any]]:
    headings = list(HEADING_RE.finditer(markdown))

    if not headings:
        return _split_oversized(
            markdown,
            [],
            "",
            0,
            document_id,
            0,
            page_start,
            max_chars=max_chars,
        )

    chunks: list[dict[str, Any]] = []
    chunk_index = 0
    heading_path: list[str] = []

    for i, match in enumerate(headings):
        level = len(match.group(1))
        title = match.group(2).strip()
        start = match.start()

        heading_path = heading_path[: level - 1]
        heading_path.append(title)

        next_start = headings[i + 1].start() if i + 1 < len(headings) else len(markdown)
        section_text = markdown[start:next_start].strip()

        if len(section_text) <= max_chars:
            chunks.append(
                _make_chunk(
                    section_text,
                    list(heading_path),
                    title,
                    start,
                    document_id,
                    chunk_index,
                    page_start,
                )
            )
            chunk_index += 1
        else:
            sub_chunks = _split_oversized(
                section_text,
                list(heading_path),
                title,
                start,
                document_id,
                chunk_index,
                page_start,
                max_chars=max_chars,
            )
            chunks.extend(sub_chunks)
            chunk_index += len(sub_chunks)

    return chunks
