"""Parsers turn uploaded bytes into a normalized ParsedDocument.

Default stack, all permissively licensed and CPU-only:

* PDF  -> pypdfium2 (text + line boxes for highlighting). Pages without a text
  layer (scans) are OCR'd with Tesseract, or with Docling when only Docling is
  installed; Docling then reads those pages only, not the whole document.
* DOCX -> converted to PDF with LibreOffice when available (keeps pages and
  boxes for highlighting), else parsed with python-docx (headings, tables).
* TXT / MD -> read as is.

Docling can be enabled for complex layouts (``ZELLES_PARSER=docling``).
"""

from __future__ import annotations

import importlib.util
import io
import logging
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

from zelles.domain.documents import BBox, Block, BlockKind, Page, ParsedDocument
from zelles.ingest.cleaning import clean_text
from zelles.ingest.furniture import strip_furniture
from zelles.ingest.outline import detect_heading

log = logging.getLogger(__name__)

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TEXT = "text/plain"
SUPPORTED_SUFFIXES = {".pdf": PDF, ".docx": DOCX, ".txt": TEXT, ".md": TEXT}


class UnsupportedDocumentError(ValueError):
    """Raised for files we cannot parse."""


def sniff_media_type(data: bytes, filename: str) -> str:
    """Detect the media type from magic bytes, falling back to the extension."""
    if data.startswith(b"%PDF"):
        return PDF
    suffix = Path(filename).suffix.lower()
    if data.startswith(b"PK\x03\x04") and suffix == ".docx":
        return DOCX
    if suffix in (".txt", ".md"):
        try:
            data[:4096].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UnsupportedDocumentError("text file is not UTF-8") from exc
        return TEXT
    raise UnsupportedDocumentError(f"unsupported file type: {filename!r}")


class Parser(Protocol):
    name: str

    def parse(self, data: bytes, filename: str) -> ParsedDocument: ...


# --------------------------------------------------------------------------- helpers
def _blocks_from_lines(lines: Iterable[tuple[str, BBox | None]], page: int | None) -> list[Block]:
    """Group lines into headings and paragraphs, keeping boxes for highlighting."""
    blocks: list[Block] = []
    buffer: list[str] = []
    box: BBox | None = None
    last_bottom: float | None = None
    last_height: float | None = None

    def flush() -> None:
        nonlocal buffer, box
        if buffer:
            text = clean_text(" ".join(buffer))
            if text:
                kind = BlockKind.LIST_ITEM if text[:1] in "-*" else BlockKind.PARAGRAPH
                blocks.append(Block(kind=kind, text=text, page=page, bbox=box))
        buffer, box = [], None

    for raw, line_box in lines:
        line = clean_text(raw)
        if not line:
            flush()
            last_bottom = None
            continue
        heading = detect_heading(line)
        if heading is not None:
            flush()
            blocks.append(
                Block(
                    kind=BlockKind.HEADING,
                    text=heading.label,
                    page=page,
                    bbox=line_box,
                    heading_level=heading.level,
                )
            )
            last_bottom = line_box.y1 if line_box else None
            continue
        starts_item = line[:1] in "-*" or line[:2] in ("o ", "> ")
        big_gap = (
            line_box is not None
            and last_bottom is not None
            and last_height is not None
            and line_box.y0 - last_bottom > 0.8 * last_height
        )
        if starts_item or big_gap:
            flush()
        buffer.append(line)
        if line_box is not None:
            box = line_box if box is None else box.union(line_box)
            last_bottom, last_height = line_box.y1, line_box.y1 - line_box.y0
    flush()
    return blocks


def _tesseract_available() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


def _docling_available() -> bool:
    return importlib.util.find_spec("docling") is not None


def ocr_engine() -> str | None:
    """The OCR engine used for pages without text: Tesseract first, Docling second."""
    if _tesseract_available():
        return "tesseract"
    if _docling_available():
        return "docling"
    return None


# --------------------------------------------------------------------------- PDF
class PdfiumParser:
    """Fast, permissive PDF parser based on pdfium."""

    name = "pdfium"

    def __init__(self, *, ocr: bool = True, ocr_language: str = "fra") -> None:
        self.ocr = ocr
        self.ocr_language = ocr_language

    def parse(self, data: bytes, filename: str) -> ParsedDocument:
        import pypdfium2 as pdfium  # noqa: PLC0415

        doc = ParsedDocument(filename=filename, media_type=PDF, parser=self.name)
        pdf = pdfium.PdfDocument(data)
        raw: list[tuple[list[tuple[str, BBox | None]], float | None]] = []
        try:
            for index in range(len(pdf)):
                page = pdf[index]
                width, height = page.get_size()
                raw.append((self._lines(page, height), height))
                doc.pages.append(Page(number=index + 1, width=width, height=height))
            textless = [i for i, (lines, _) in enumerate(raw) if sum(len(t) for t, _ in lines) < 20]
            if textless and self.ocr:
                self._ocr_pages(pdf, textless, raw, doc)
        finally:
            pdf.close()
        for page_info, lines in zip(doc.pages, strip_furniture(raw), strict=True):
            blocks = _blocks_from_lines(lines, page_info.number)
            doc.blocks.extend(blocks)
            page_info.text = "\n".join(b.text for b in blocks)
        return doc

    def _ocr_pages(
        self,
        pdf: object,
        indices: list[int],
        raw: list[tuple[list[tuple[str, BBox | None]], float | None]],
        doc: ParsedDocument,
    ) -> None:
        """Replace the lines of pages without text by OCR, in place."""
        engine = ocr_engine()
        found: dict[int, list[tuple[str, BBox | None]]] = {}
        if engine == "tesseract":
            for index in indices:
                found[index] = self._ocr(pdf[index])  # type: ignore[index]
        elif engine == "docling":
            try:
                found = docling_ocr(pdf, indices)
            except Exception as exc:  # a failed OCR must not lose the text pages
                log.warning("Docling OCR failed: %s", exc)
                doc.warnings.append(f"Docling OCR failed: {exc}")
            else:
                doc.parser = f"{self.name}+docling-ocr"
        for index in indices:
            if found.get(index):
                raw[index] = (found[index], raw[index][1])
                doc.pages[index].ocr = True
            else:
                reason = "OCR found no text" if engine else "OCR is unavailable"
                doc.warnings.append(f"page {index + 1} has no text layer and {reason}")

    @staticmethod
    def _lines(page: object, page_height: float) -> list[tuple[str, BBox | None]]:
        textpage = page.get_textpage()  # type: ignore[attr-defined]
        try:
            count = textpage.count_chars()
            text = textpage.get_text_range(0, count)
            if len(text) != count:  # rare (non-UCS-2 text): fall back to one call per char
                text = "".join((textpage.get_text_range(i, 1) or " ")[:1] for i in range(count))
            boxes = [
                None if text[i].isspace() else textpage.get_charbox(i, loose=True)
                for i in range(count)
            ]
            return lines_from_chars(text, boxes, page_height)
        finally:
            textpage.close()

    def _ocr(self, page: object) -> list[tuple[str, BBox | None]]:
        import pytesseract  # noqa: PLC0415

        scale = 300 / 72
        image = page.render(scale=scale).to_pil()  # type: ignore[attr-defined]
        data = pytesseract.image_to_data(
            image, lang=self.ocr_language, output_type=pytesseract.Output.DICT
        )
        rows: dict[tuple[int, int, int], list[int]] = {}
        for i, word in enumerate(data["text"]):
            if word.strip():
                key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                rows.setdefault(key, []).append(i)
        lines: list[tuple[str, BBox | None]] = []
        for indices in rows.values():
            words = " ".join(data["text"][i] for i in indices)
            x0 = min(data["left"][i] for i in indices) / scale
            y0 = min(data["top"][i] for i in indices) / scale
            x1 = max(data["left"][i] + data["width"][i] for i in indices) / scale
            y1 = max(data["top"][i] + data["height"][i] for i in indices) / scale
            lines.append((words, BBox(x0=x0, y0=y0, x1=x1, y1=y1)))
        return lines


def lines_from_chars(
    text: str,
    boxes: list[tuple[float, float, float, float] | None],
    page_height: float,
) -> list[tuple[str, BBox | None]]:
    """Split pdfium's page text into lines, each with the union box of its characters.

    pdfium's own text assembly keeps hyphens and small capitals intact
    ("NF EN 14351-1", "Emissivité"), which per-rectangle extraction does not:
    it returns the hyphen and a small-capital initial as separate rectangles.
    Boxes are (left, bottom, right, top) in PDF units; BBox uses a top-left origin.
    """
    lines: list[tuple[str, BBox | None]] = []
    start = 0
    for end in [*(i for i, c in enumerate(text) if c == "\n"), len(text)]:
        line = text[start:end].replace("\r", "").strip()
        chars = [b for b in boxes[start:end] if b is not None and b[2] > b[0]]
        start = end + 1
        if not line:
            continue
        box = (
            BBox(
                x0=min(b[0] for b in chars),
                y0=page_height - max(b[3] for b in chars),
                x1=max(b[2] for b in chars),
                y1=page_height - min(b[1] for b in chars),
            )
            if chars
            else None
        )
        lines.append((line, box))
    return lines


# --------------------------------------------------------------------------- DOCX
class DocxParser:
    """Structural DOCX parser: heading styles, paragraphs and tables, no pages."""

    name = "python-docx"

    def parse(self, data: bytes, filename: str) -> ParsedDocument:
        import docx  # noqa: PLC0415
        from docx.table import Table  # noqa: PLC0415
        from docx.text.paragraph import Paragraph  # noqa: PLC0415

        source = docx.Document(io.BytesIO(data))
        doc = ParsedDocument(filename=filename, media_type=DOCX, parser=self.name)
        body = source.element.body
        for child in body.iterchildren():
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "p":
                para = Paragraph(child, source)
                text = clean_text(para.text)
                if not text:
                    continue
                style = (para.style.name if para.style is not None else "") or ""
                style_level = _style_heading_level(style)
                heading = detect_heading(text, style_level=style_level)
                if heading is not None:
                    doc.blocks.append(
                        Block(
                            kind=BlockKind.HEADING, text=heading.label, heading_level=heading.level
                        )
                    )
                else:
                    kind = BlockKind.LIST_ITEM if "list" in style.lower() else BlockKind.PARAGRAPH
                    doc.blocks.append(Block(kind=kind, text=text))
            elif tag == "tbl":
                table = Table(child, source)
                rows = []
                for row in table.rows:
                    cells = [clean_text(c.text) for c in row.cells]
                    deduped = [c for i, c in enumerate(cells) if i == 0 or c != cells[i - 1]]
                    rows.append(" | ".join(deduped))
                text = "\n".join(r for r in rows if r.strip(" |"))
                if text:
                    doc.blocks.append(Block(kind=BlockKind.TABLE, text=text))
        doc.warnings.append(
            "DOCX parsed without pagination: install LibreOffice for page citations"
        )
        return doc


def _style_heading_level(style: str) -> int | None:
    lowered = style.lower()
    for prefix in ("heading", "titre", "title"):
        if lowered.startswith(prefix):
            digits = "".join(c for c in lowered if c.isdigit())
            return int(digits) if digits else 1
    return None


def docx_to_pdf(data: bytes, *, timeout_s: float = 120.0) -> bytes | None:
    """Convert DOCX to PDF with LibreOffice headless. Returns None if unavailable."""
    binary = shutil.which("soffice") or shutil.which("libreoffice")
    if binary is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "input.docx"
        src.write_bytes(data)
        try:
            subprocess.run(  # noqa: S603 - fixed argv, no shell
                [
                    binary,
                    "--headless",
                    "--norestore",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    tmp,
                    str(src),
                ],
                check=True,
                capture_output=True,
                timeout=timeout_s,
                env={"HOME": tmp, "PATH": "/usr/bin:/bin:/usr/local/bin"},
            )
        except (subprocess.SubprocessError, OSError) as exc:
            log.warning("LibreOffice conversion failed: %s", exc)
            return None
        out = Path(tmp) / "input.pdf"
        return out.read_bytes() if out.exists() else None


# --------------------------------------------------------------------------- text
class TextParser:
    name = "text"

    def parse(self, data: bytes, filename: str) -> ParsedDocument:
        text = data.decode("utf-8")
        doc = ParsedDocument(filename=filename, media_type=TEXT, parser=self.name)
        lines = [
            (line.lstrip("#").strip() if line.startswith("#") else line, None)
            for line in text.splitlines()
        ]
        doc.blocks = _blocks_from_lines(lines, None)
        return doc


# --------------------------------------------------------------------------- docling
def _docling_box(box: object, page_height: float) -> BBox:
    """Docling boxes may use a bottom-left origin; BBox uses a top-left one."""
    left, top, right, bottom = (float(getattr(box, k)) for k in ("l", "t", "r", "b"))
    if str(getattr(box, "coord_origin", "")).upper().endswith("TOPLEFT"):
        return BBox(x0=left, y0=top, x1=right, y1=bottom)
    return BBox(x0=left, y0=page_height - top, x1=right, y1=page_height - bottom)


def _docling_convert(data: bytes, filename: str) -> object:  # pragma: no cover - optional
    from docling.datamodel.base_models import DocumentStream  # noqa: PLC0415
    from docling.document_converter import DocumentConverter  # noqa: PLC0415

    stream = DocumentStream(name=filename, stream=io.BytesIO(data))
    return DocumentConverter().convert(stream).document


def docling_ocr(pdf: object, indices: list[int]) -> dict[int, list[tuple[str, BBox | None]]]:
    """OCR some pages of an open pdfium document with Docling.

    Only those pages are copied into a new PDF, so a 60-page CCTP with a scanned
    annex costs a few seconds, not a full Docling run. Returns lines per page index.
    """
    import pypdfium2 as pdfium  # noqa: PLC0415

    subset = pdfium.PdfDocument.new()
    try:
        subset.import_pages(pdf, pages=indices)
        buffer = io.BytesIO()
        subset.save(buffer)
    finally:
        subset.close()
    heights = {n + 1: pdf[i].get_size()[1] for n, i in enumerate(indices)}  # type: ignore[index]
    source = _docling_convert(buffer.getvalue(), "ocr.pdf")
    lines: dict[int, list[tuple[str, BBox | None]]] = {}
    for item, _level in source.iterate_items():  # type: ignore[attr-defined]
        text = clean_text(getattr(item, "text", "") or "")
        prov = getattr(item, "prov", None)
        if not text or not prov:
            continue
        page_no = int(prov[0].page_no)
        if page_no not in heights:
            continue
        box = _docling_box(prov[0].bbox, heights[page_no])
        lines.setdefault(indices[page_no - 1], []).append((text, box))
    return lines


class DoclingParser:
    """Layout-aware parser (tables, reading order) for difficult PDFs. Optional extra."""

    name = "docling"

    def parse(self, data: bytes, filename: str) -> ParsedDocument:  # pragma: no cover - optional
        source: Any = _docling_convert(data, filename)
        doc = ParsedDocument(filename=filename, media_type=PDF, parser=self.name)
        heights: dict[int, float] = {}
        for number, page in getattr(source, "pages", {}).items():
            size = getattr(page, "size", None)
            if size is not None:
                heights[int(number)] = float(size.height)
                doc.pages.append(
                    Page(number=int(number), width=float(size.width), height=float(size.height))
                )
        for item, _level in source.iterate_items():
            label = str(getattr(item, "label", "")).lower()
            if "table" in label and hasattr(item, "export_to_markdown"):
                text, kind = item.export_to_markdown(source), BlockKind.TABLE
            else:
                text = clean_text(getattr(item, "text", "") or "")
                kind = (
                    BlockKind.HEADING
                    if "header" in label or "title" in label
                    else BlockKind.PARAGRAPH
                )
            if not text:
                continue
            page_no, bbox = None, None
            if getattr(item, "prov", None):
                prov = item.prov[0]
                page_no = int(prov.page_no)
                bbox = _docling_box(prov.bbox, heights.get(page_no, 0.0))
            level = None
            if kind == BlockKind.HEADING:
                heading = detect_heading(text, style_level=1)
                level = heading.level if heading else 1
            doc.blocks.append(
                Block(kind=kind, text=text, page=page_no, bbox=bbox, heading_level=level)
            )
        for page in doc.pages:
            page.text = "\n".join(b.text for b in doc.blocks if b.page == page.number)
        return doc


# --------------------------------------------------------------------------- facade
def parse_document(
    data: bytes,
    filename: str,
    *,
    parser: str = "auto",
    ocr: bool = True,
    ocr_language: str = "fra",
    convert_docx: bool = True,
) -> tuple[ParsedDocument, bytes | None]:
    """Parse bytes into a ParsedDocument.

    Returns the document and, when available, a PDF rendition used for page
    images and highlights (the original PDF, or a DOCX converted to PDF).
    """
    media_type = sniff_media_type(data, filename)
    if media_type == TEXT:
        return TextParser().parse(data, filename), None

    pdf_bytes: bytes | None = data if media_type == PDF else None
    if media_type == DOCX and convert_docx:
        pdf_bytes = docx_to_pdf(data)
    if media_type == DOCX and pdf_bytes is None:
        return DocxParser().parse(data, filename), None

    assert pdf_bytes is not None
    if parser == "docling":
        doc = DoclingParser().parse(pdf_bytes, filename)
    else:
        doc = PdfiumParser(ocr=ocr, ocr_language=ocr_language).parse(pdf_bytes, filename)
    doc.filename = filename
    if media_type == DOCX:
        doc.media_type = DOCX
        doc.parser = f"libreoffice+{doc.parser}"
    return doc, pdf_bytes
