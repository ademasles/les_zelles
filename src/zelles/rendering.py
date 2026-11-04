"""Page images with highlighted citations (replaces server-side PDF rewriting)."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw

from zelles.domain.documents import BBox, Chunk, ParsedDocument
from zelles.ingest.cleaning import normalize_for_match


def highlight_boxes(
    document: ParsedDocument, chunk: Chunk, quote: str | None, page: int
) -> list[BBox]:
    """Boxes to highlight on a page: the blocks containing the quote, else the whole chunk."""
    blocks = [document.blocks[i] for i in chunk.block_ids if i < len(document.blocks)]
    on_page = [b for b in blocks if b.page == page and b.bbox is not None]
    if quote:
        needle = normalize_for_match(quote)[:80]
        matching = [b for b in on_page if needle and needle in normalize_for_match(b.text)]
        if matching:
            return [b.bbox for b in matching if b.bbox is not None]
    return [b.bbox for b in on_page if b.bbox is not None]


def render_page(pdf_path: Path, page: int, boxes: list[BBox], *, scale: float = 1.6) -> bytes:
    import pypdfium2 as pdfium  # noqa: PLC0415

    pdf = pdfium.PdfDocument(pdf_path)
    try:
        if not 1 <= page <= len(pdf):
            raise IndexError(page)
        image = pdf[page - 1].render(scale=scale).to_pil().convert("RGB")
    finally:
        pdf.close()
    if boxes:
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for box in boxes:
            rect = [box.x0 * scale - 3, box.y0 * scale - 2, box.x1 * scale + 3, box.y1 * scale + 2]
            draw.rectangle(rect, fill=(255, 214, 0, 90), outline=(230, 150, 0, 255), width=2)
        image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()
