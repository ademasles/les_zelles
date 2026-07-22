"""Compat — delegates to the new markdown-aware chunker.

Keeps the legacy chunk_text() signature for backward compat with tests.
"""

from __future__ import annotations

from app.preprocessing.markdown.section_splitter import chunk_markdown


def chunk_text(pages: list[dict], max_chars: int = 3000) -> list[dict]:
    """Legacy-compat: delegates to new markdown-aware chunker."""
    all_chunks = []
    chunk_index = 0

    for page_data in pages:
        text = page_data.get("text", "")
        doc_name = page_data.get("doc_name", "unknown")
        page_number = page_data.get("page_number")

        new_chunks = chunk_markdown(
            text,
            document_id=doc_name,
            page_start=page_number,
            max_chars=max_chars,
        )

        for c in new_chunks:
            c["chunk_id"] = chunk_index
            c["doc_name"] = doc_name
            c["page_number"] = page_number
            c["raw_text"] = text
            c["start_char"] = 0
            c["end_char"] = len(c["text"])
            all_chunks.append(c)
            chunk_index += 1

        if not new_chunks and text.strip():
            all_chunks.append(
                {
                    "chunk_id": chunk_index,
                    "text": text,
                    "doc_name": doc_name,
                    "page_number": page_number,
                    "start_char": 0,
                    "end_char": len(text),
                    "raw_text": text,
                }
            )
            chunk_index += 1

    return all_chunks
