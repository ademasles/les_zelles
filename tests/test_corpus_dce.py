"""DCE inspection: nested archives, joinery CCTP pick, extraction of chosen files only."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import docx

from zelles.corpus.dce import SEP, inspect_case, members, select


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _docx(text: str) -> bytes:
    document = docx.Document()
    document.add_paragraph(text)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def test_lists_nested_archives_and_counts_a_file_once(tmp_path: Path) -> None:
    inner = _zip({"Lot 05 - CCTP Menuiseries extérieures.pdf": b"x" * 10})
    (tmp_path / "DCE.zip").write_bytes(_zip({"pieces/lots.zip": inner, "RC.pdf": b"rc"}))
    (tmp_path / "Lot 05 - CCTP Menuiseries extérieures.pdf").write_bytes(b"x" * 10)
    found = members(tmp_path)
    assert sorted(m.name for m in found) == ["lot 05 cctp menuiseries exterieures.pdf", "rc.pdf"]
    assert any(
        m.path.endswith(f"lots.zip{SEP}Lot 05 - CCTP Menuiseries extérieures.pdf") for m in found
    )


def test_picks_the_lot_cctp_then_the_only_one() -> None:
    from zelles.corpus.dce import Member

    names = ["CCTP Lot 02 Gros oeuvre.pdf", "CCTP_lot5.pdf", "DPGF lot 05.xlsx", "DPGF lot 02.xlsx"]
    found = [Member(n, 1) for n in names]
    picked = select(found, {"05"})
    assert [m.path for m in picked.cctp] == ["CCTP_lot5.pdf"] and picked.how == "lot"
    assert [m.path for m in picked.dpgf] == ["DPGF lot 05.xlsx"]
    single = select([Member("C.C.T.P. tous corps d'état.pdf", 1)], {"7"})
    assert single.how == "common"
    assert select([Member("CCTP Menuiseries intérieures.pdf", 1)] * 2, set()).how == "unclear"


def test_unclear_cctps_are_settled_by_their_text(tmp_path: Path) -> None:
    (tmp_path / "dce.zip").write_bytes(
        _zip(
            {
                "CCTP A.docx": _docx("Lot 3 : plâtrerie, cloisons, faux plafonds."),
                "CCTP B.docx": _docx("Menuiseries extérieures aluminium, fenêtres et volets."),
                "plans/plan.dwg": b"0" * 1000,
            }
        )
    )
    row = inspect_case(tmp_path, set())
    assert row["how"] == "text" and row["cctp"].endswith("CCTP B.docx")
    assert row["text_layer"] == "yes" and row["cctp_format"] == "docx"
    assert sorted(p.name for p in (tmp_path / "selected").iterdir()) == ["CCTP B.docx"]


def test_ranks_exterior_over_interior_and_metalwork() -> None:
    from zelles.corpus.dce import Member

    names = [
        "CCTP LOT 8 Menuiserie_interieure.pdf",
        "CCTP Lot09 SERR_MEN METALL.pdf",
        "CCTP Lot08 MEN EXT_BSO.pdf",
    ]
    picked = select([Member(n, 1) for n in names], {"08", "09"})
    assert [m.path for m in picked.cctp] == ["CCTP Lot08 MEN EXT_BSO.pdf"]


def test_a_lone_cctp_of_another_trade_is_not_common() -> None:
    from zelles.corpus.dce import Member

    assert select([Member("FOIX COUV DDT-CCTP.pdf", 1)], {"4"}).how == "unclear"  # the text decides


def test_names_from_windows_zip_tools_are_decoded() -> None:
    from zelles.corpus.dce import Member, readable

    assert readable("PiΦces techniques") == "Pièces techniques"
    assert readable("CCTP g\udc82n\udc82ral.pdf") == "CCTP général.pdf"
    member = Member(f"dce.zip{SEP}PiΦces/CCTP.pdf", 1)
    assert member.label == f"dce.zip{SEP}Pièces/CCTP.pdf"


def test_folder_names_count_when_file_names_do_not_say() -> None:
    from zelles.corpus.dce import Member

    names = [
        "DCE/Lot 09_SERR_MEN METALL/X_TVX_CCTP_Lot09.pdf",
        "DCE/Lot 08_MEN EXT_BSO_V2/X_TVX_CCTPV2_Lot08.pdf",
    ]
    picked = select([Member(n, 1) for n in names], {"08", "09"})
    assert [m.path for m in picked.cctp] == [names[1]]
