"""Find the joinery CCTP and DPGF inside a downloaded DCE, without unpacking it all.

A DCE is a zip of zips: one archive per lot or per document family, sometimes
gigabytes of plans. Only two documents matter here, the CCTP of the exterior
joinery lot and its price breakdown (DPGF, BPU or DQE). Archives are listed
recursively; a nested archive is copied to a temporary file only while it is
listed, so the disk cost stays one archive at a time, and only the chosen
documents are extracted.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from zelles.corpus.boamp import JOINERY, fold

DOCUMENT_SUFFIXES = (".pdf", ".docx", ".doc", ".odt", ".rtf")
SHEET_SUFFIXES = (".xlsx", ".xls", ".ods", ".pdf", ".docx")
CCTP = re.compile(r"c\W?c\W?t\W?p|clauses techniques particulieres")
DPGF = re.compile(r"d\W?p\W?g\W?f|\bbpu\b|\bdqe\b|decomposition du prix")
# A file name that says joinery: "menuiseries ext", "MEXT", "fenetres", "occultations".
JOINERY_NAME = re.compile(r"menuis|\bmext\b|\bme\b|fenetre|occultation|chassis|mur rideau")
INTERIOR_NAME = re.compile(r"menuiseries? (bois )?int|\bmint\b|agencement")
SEP = "!/"  # between an archive and a member inside it


@dataclass(frozen=True)
class Member:
    """A file somewhere in the DCE: ``outer.zip!/inner.zip!/CCTP lot 5.pdf``."""

    path: str
    size: int

    @property
    def name(self) -> str:
        return fold(PurePosixPath(self.path.rsplit(SEP, 1)[-1]).name)

    @property
    def suffix(self) -> str:
        return PurePosixPath(self.name).suffix


def _walk_zip(archive: Path, prefix: str, depth: int) -> Iterator[Member]:
    try:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                path = f"{prefix}{info.filename}"
                if info.filename.lower().endswith(".zip") and depth < 4:
                    with tempfile.TemporaryDirectory() as tmp:
                        inner = Path(tmp) / "inner.zip"
                        with zf.open(info) as src, inner.open("wb") as dst:
                            shutil.copyfileobj(src, dst)
                        yield from _walk_zip(inner, f"{path}{SEP}", depth + 1)
                else:
                    yield Member(path, info.file_size)
    except (zipfile.BadZipFile, NotImplementedError, OSError):
        yield Member(f"{prefix}{SEP}<unreadable archive>", 0)


def members(case_dir: Path) -> list[Member]:
    """Every file of a DCE folder, looking inside archives at any depth."""
    found: list[Member] = []
    for path in sorted(p for p in case_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(case_dir).as_posix()
        if path.suffix.lower() == ".zip":
            found.extend(_walk_zip(path, f"{rel}{SEP}", 0))
        else:
            found.append(Member(rel, path.stat().st_size))
    unique: dict[tuple[str, int], Member] = {}
    for member in found:  # the same CCTP unpacked and zipped counts once
        unique.setdefault((member.name, member.size), member)
    return list(unique.values())


def _names_lot(name: str, numbers: set[str]) -> bool:
    for number in numbers:
        n = number.lstrip("0") or "0"
        if re.search(rf"(?<![0-9])lot\W*0*{n}(?![0-9])|^0*{n}(?![0-9])\W", name):
            return True
    return False


def _is_joinery_name(name: str, numbers: set[str]) -> bool:
    if INTERIOR_NAME.search(name) and "ext" not in name:
        return False
    return bool(JOINERY_NAME.search(name) or JOINERY.search(name)) or _names_lot(name, numbers)


@dataclass
class Selection:
    """The documents picked for the joinery lot, and how sure the pick is."""

    cctp: list[Member] = field(default_factory=list)
    dpgf: list[Member] = field(default_factory=list)
    how: str = "none"  # lot | common | unclear | none
    candidates: list[Member] = field(default_factory=list)


def select(found: list[Member], lot_numbers: set[str]) -> Selection:
    """Pick the joinery CCTP and DPGF by file name.

    ``lot`` means a CCTP named after the joinery lot, ``common`` the only CCTP
    of the DCE (one document for all lots), ``unclear`` several CCTPs and none
    named after the lot: the text has to decide.
    """
    cctps = [m for m in found if m.suffix in DOCUMENT_SUFFIXES and CCTP.search(m.name)]
    sheets = [m for m in found if m.suffix in SHEET_SUFFIXES and DPGF.search(m.name)]
    selection = Selection(candidates=cctps)
    joinery = [m for m in cctps if _is_joinery_name(m.name, lot_numbers)]
    if joinery:
        selection.cctp, selection.how = joinery, "lot"
    elif len(cctps) == 1:
        selection.cctp, selection.how = cctps, "common"
    elif cctps:
        selection.how = "unclear"
    selection.dpgf = [m for m in sheets if _is_joinery_name(m.name, lot_numbers)]
    if not selection.dpgf and len(sheets) == 1:
        selection.dpgf = sheets
    return selection


def extract(case_dir: Path, member: Member, dest: Path) -> Path:
    """Copy one member out of its archives into ``dest``, keeping its file name."""
    parts = member.path.split(SEP)
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / PurePosixPath(parts[-1]).name
    if len(parts) == 1:
        shutil.copyfile(case_dir / parts[0], target)
        return target
    with tempfile.TemporaryDirectory() as tmp:
        archive = case_dir / parts[0]
        for i, inner in enumerate(parts[1:-1]):
            nested = Path(tmp) / f"{i}.zip"
            with zipfile.ZipFile(archive) as zf, zf.open(inner) as src, nested.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            archive = nested
        with zipfile.ZipFile(archive) as zf, zf.open(parts[-1]) as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    return target


def joinery_score(text: str) -> int:
    """How much of a document's opening is about exterior joinery."""
    folded = fold(text)
    return len(JOINERY.findall(folded)) - 3 * len(INTERIOR_NAME.findall(folded))


def pdf_text(path: Path, pages: int = 3) -> str:
    """Text of the first pages, empty when the PDF has no text layer."""
    import pypdfium2 as pdfium  # noqa: PLC0415

    try:
        pdf = pdfium.PdfDocument(path)
    except pdfium.PdfiumError:
        return ""
    try:
        return "\n".join(
            pdf[i].get_textpage().get_text_range() for i in range(min(pages, len(pdf)))
        )
    finally:
        pdf.close()


def docx_text(path: Path, paragraphs: int = 200) -> str:
    """Text of the first paragraphs of a Word file, empty when it cannot be read."""
    import docx  # noqa: PLC0415

    try:
        document = docx.Document(str(path))
    except Exception:
        return ""
    return "\n".join(p.text for p in document.paragraphs[:paragraphs])


def opening_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return pdf_text(path)
    if path.suffix.lower() == ".docx":
        return docx_text(path)
    return ""


MANIFEST_COLUMNS = (
    "idweb",
    "buyer",
    "departments",
    "joinery_lots",
    "status",
    "how",
    "cctp",
    "cctp_format",
    "text_layer",
    "dpgf",
    "cctp_candidates",
)


def inspect_case(case_dir: Path, lot_numbers: set[str], max_candidates: int = 8) -> dict[str, str]:
    """Pick and extract the joinery CCTP and DPGF of one DCE into ``case_dir/selected``."""
    found = [m for m in members(case_dir) if not m.path.startswith("selected/")]
    selection = select(found, lot_numbers)
    picked = case_dir / "selected"
    if selection.how == "unclear":
        best: tuple[int, Member] | None = None
        with tempfile.TemporaryDirectory() as tmp:
            for member in selection.candidates[:max_candidates]:
                score = joinery_score(opening_text(extract(case_dir, member, Path(tmp))))
                if score > 0 and (best is None or score > best[0]):
                    best = (score, member)
        if best is not None:
            selection.cctp, selection.how = [best[1]], "text"
    cctp_paths = [extract(case_dir, m, picked) for m in selection.cctp]
    for member in selection.dpgf:
        extract(case_dir, member, picked)
    first = cctp_paths[0] if cctp_paths else None
    return {
        "status": "ok" if first else "cctp:unclear",
        "how": selection.how,
        "cctp": " | ".join(m.path for m in selection.cctp),
        "cctp_format": first.suffix.lstrip(".").lower() if first else "",
        "text_layer": ("yes" if opening_text(first).strip() else "no") if first else "",
        "dpgf": " | ".join(m.path for m in selection.dpgf),
        "cctp_candidates": str(len(selection.candidates)),
    }
