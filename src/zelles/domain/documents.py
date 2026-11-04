"""Document model shared by parsers, chunking, retrieval and highlighting."""

from __future__ import annotations

import re
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


_LOT_LABEL = re.compile(r"^\s*lot\b", re.IGNORECASE)
_GENERIC_HEADING = re.compile(
    r"^\s*(?:[\d.]+\s*)?(?:g[ée]n[ée]ralit[ée]s|objet|description|travaux|sp[ée]cifications?|"
    r"prescriptions?|performances?|caract[ée]ristiques?|mat[ée]riaux|fabrication|mise\s+en\s+(?:œ|oe)uvre|"
    r"documents?|normes?|r[ée]glementation|r[ée]f[ée]rences?|essais|contr[ôo]les?|garanties?|"
    r"nettoyage|r[ée]ception|pr[ée]sentation|composition|qualit[ée]|conditions?)\b",
    re.IGNORECASE,
)


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
    page_offsets: list[tuple[int, int]] = Field(
        default_factory=list,
        description="(character offset, page) where each page starts in the chunk text.",
    )

    def page_at(self, offset: int) -> int | None:
        """Page of the character at ``offset`` (chunks can straddle a page break)."""
        page = self.page_start
        for start, number in self.page_offsets:
            if start > offset:
                break
            page = number
        return page

    @property
    def heading(self) -> str:
        return self.section_path[-1] if self.section_path else ""

    @property
    def scope(self) -> str | None:
        """What this chunk's requirements apply to.

        The deepest heading that names a part of the works ("5.2 Fenêtres de
        toit", "2 Menuiseries PVC - Logements"), skipping generic headings such
        as "2.3 Performances" or "Fabrication" that only organise the text.
        """
        labels = [
            label
            for label in self.section_path
            if label != self.lot and not _LOT_LABEL.match(label)
        ]
        specific = [label for label in labels if not _GENERIC_HEADING.search(label)]
        if specific:
            return specific[-1]
        return labels[0] if labels else None

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
