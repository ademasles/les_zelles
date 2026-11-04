"""Outline-aware chunking.

Chunks follow the CCTP structure: a new chunk starts at every heading, carries
the full section path (lot, article, sub-article) and is only split further
when an article is longer than ``max_chars``. Tables are never split.
"""

from __future__ import annotations

from zelles.domain.documents import Block, BlockKind, Chunk, ParsedDocument
from zelles.ingest.outline import detect_heading


def chunk_document(doc: ParsedDocument, *, max_chars: int = 2400) -> list[Chunk]:
    chunks: list[Chunk] = []
    stack: list[tuple[int, str]] = []  # (level, label) of open headings
    lot: str | None = None
    current: list[tuple[int, Block]] = []

    def path() -> list[str]:
        return [label for _, label in stack]

    def article() -> str | None:
        for level, label in reversed(stack):
            if level > 0:
                return label
        return None

    def emit() -> None:
        nonlocal current
        if not current:
            return
        body = [(i, b) for i, b in current if b.kind != BlockKind.HEADING]
        if not body:
            current = []
            return
        pages = [b.page for _, b in current if b.page is not None]
        chunks.append(
            Chunk(
                id=f"c{len(chunks):04d}",
                index=len(chunks),
                text="\n".join(b.text for _, b in current),
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
                section_path=path(),
                lot=lot,
                article=article(),
                has_table=any(b.kind == BlockKind.TABLE for _, b in current),
                block_ids=[i for i, _ in current],
            )
        )
        current = []

    for index, block in enumerate(doc.blocks):
        if block.kind == BlockKind.HEADING:
            emit()
            heading = detect_heading(block.text, style_level=block.heading_level)
            level = block.heading_level if block.heading_level is not None else 1
            if heading is not None and heading.is_lot:
                lot, level, stack = heading.label, 0, []
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, block.text))
            current.append((index, block))
            continue

        size = sum(len(b.text) + 1 for _, b in current)
        if current and size + len(block.text) > max_chars:
            emit()  # continuation chunks keep the section path, not the heading text
        current.append((index, block))
    emit()
    return chunks
