"""Document model shared by parsers, chunking, retrieval and highlighting."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class BlockKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"


class BBox(BaseModel):
    """Rectangle in PDF points with a top-left origin (y grows downwards)."""

    x0: float
    y0: float
    x1: float
    y1: float

    def union(self, other: BBox) -> BBox:
        return BBox(
            x0=min(self.x0, other.x0),
            y0=min(self.y0, other.y0),
            x1=max(self.x1, other.x1),
            y1=max(self.y1, other.y1),
        )


class Block(BaseModel):
    """A unit of layout: a heading, a paragraph, a list item or a whole table."""

    kind: BlockKind = BlockKind.PARAGRAPH
    text: str
    page: int | None = None
    bbox: BBox | None = None
    heading_level: int | None = None


class Page(BaseModel):
    number: int
    width: float | None = None
    height: float | None = None
    text: str = ""
    ocr: bool = False


class ParsedDocument(BaseModel):
    """Normalized output of every parser."""

    filename: str
    media_type: str
    pages: list[Page] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)
    parser: str = "unknown"
    warnings: list[str] = Field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.blocks)

    @property
    def is_paginated(self) -> bool:
        return any(b.page is not None for b in self.blocks)


class Chunk(BaseModel):
    """A retrieval unit that follows the CCTP outline (lot, article, sub-article)."""

    id: str
    index: int
    text: str
    page_start: int | None = None
    page_end: int | None = None
    section_path: list[str] = Field(default_factory=list)
    lot: str | None = None
    article: str | None = None
    has_table: bool = False
    block_ids: list[int] = Field(
        default_factory=list, description="Indices into ParsedDocument.blocks."
    )

    @property
    def heading(self) -> str:
        return self.section_path[-1] if self.section_path else ""

    @property
    def scope(self) -> str | None:
        """Top-level article this chunk belongs to (what its requirements apply to)."""
        for label in self.section_path:
            if label != self.lot:
                return label
        return None

    def locator(self) -> str:
        """Human-readable location, e.g. 'Lot 05 · 3.2.1 Menuiseries PVC · p. 14'."""
        parts: list[str] = []
        if self.lot:
            parts.append(self.lot)
        if self.heading:
            parts.append(self.heading)
        if self.page_start is not None:
            pages = (
                f"p. {self.page_start}"
                if self.page_end in (None, self.page_start)
                else f"pp. {self.page_start}-{self.page_end}"
            )
            parts.append(pages)
        return " · ".join(parts)
