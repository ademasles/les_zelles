from zelles.config import Settings
from zelles.domain.spec import Citation, Requirement, RequirementStatus, SpecField
from zelles.graph.knowledge import EdgeType, NodeType, build_graph
from zelles.graph.ontology import lookup, standard_key
from zelles.insights import ProductSpec, Verdict, clarification_questions, compare_product
from zelles.pipeline import analyze


def test_standard_keys() -> None:
    assert standard_key("DTU 36.5") == standard_key("NF DTU 36.5")
    info = lookup("NF EN 14351-1+A2")
    assert info is not None and info.code == "NF EN 14351-1"
    assert lookup("NF EN 1627") is not None and lookup("NF EN 16270") is None


async def test_graph_structure(sample_bytes: bytes, settings: Settings) -> None:
    analysis = await analyze(sample_bytes, "cctp.md", settings=settings)
    g = analysis.graph
    dtu = g.nodes["std:nf-dtu-36.5"]
    assert dtu.type == NodeType.STANDARD
    governs = [n.id for _, n in g.neighbors(dtu.id, EdgeType.GOVERNS, "out")]
    assert governs == ["topic:installation"]
    citing = [n.label for _, n in g.neighbors(dtu.id, EdgeType.CITES, "in")]
    assert any("1.2 Normes" in label for label in citing)
    pvc = g.find("PVC", NodeType.MATERIAL)
    assert pvc and g.neighbors(pvc[0].id, EdgeType.USES, "in")
    assert "MERGE (n:Standard" in g.to_cypher()
    assert g.conflicts() == []


async def test_conflicts_and_clarifications(sample_bytes: bytes, settings: Settings) -> None:
    analysis = await analyze(sample_bytes, "cctp.md", settings=settings)
    sheet = analysis.sheet
    uw = next(r for r in sheet.requirements if r.field == SpecField.UW and r.numeric_value == 1.3)
    sheet.requirements.append(uw.model_copy(update={"value": "Uw ≤ 1,4", "numeric_value": 1.4}))
    graph = build_graph(sheet, analysis.chunks)
    conflicts = graph.conflicts()
    assert len(conflicts) == 1 and conflicts[0].field == SpecField.UW
    questions = clarification_questions(sheet, graph)
    assert any(q.reason == "conflict" for q in questions)
    assert not any(q.reason == "missing" and q.field == SpecField.UW for q in questions)


def test_cross_references() -> None:
    from zelles.domain.documents import Chunk
    from zelles.domain.spec import SpecSheet

    chunks = [
        Chunk(
            id="c0000",
            index=0,
            text="2.1 Description\nVoir article 2.3 pour les performances.",
            section_path=["Lot 05 - M", "2 PVC", "2.1 Description"],
            lot="Lot 05 - M",
        ),
        Chunk(
            id="c0001",
            index=1,
            text="2.3 Performances\nUw ≤ 1,3",
            section_path=["Lot 05 - M", "2 PVC", "2.3 Performances"],
            lot="Lot 05 - M",
        ),
    ]
    graph = build_graph(SpecSheet(document_id="x", filename="f", model="rules"), chunks)
    refs = [e for e in graph.edges if e.type == EdgeType.REFERS_TO]
    assert len(refs) == 1 and refs[0].target.endswith("2-3-performances")


async def test_product_check(sample_bytes: bytes, settings: Settings) -> None:
    sheet = (await analyze(sample_bytes, "cctp.md", settings=settings)).sheet
    product = ProductSpec(
        name="Range 70",
        frame_material="PVC",
        uw=1.2,
        sw=0.45,
        aev="A*4 E*7B V*A3",
        acoustic_db=29,
        colors=["RAL 9016"],
    )
    checks = {(c.field, c.required): c for c in compare_product(sheet, product)}
    assert checks[(SpecField.UW, "Uw ≤ 1,3 W/m2.K")].verdict == Verdict.PASS
    assert checks[(SpecField.SW, "Facteur solaire Sw ≥ 0,40")].verdict == Verdict.PASS
    assert checks[(SpecField.AEV, "A*3 E*7B V*A2")].verdict == Verdict.PASS
    assert checks[(SpecField.AEV, "A*4 E*9A V*C3")].verdict in (Verdict.FAIL, Verdict.REVIEW)
    assert checks[(SpecField.ACOUSTIC, "Ra,tr ≥ 30 dB")].verdict == Verdict.FAIL
    assert checks[(SpecField.FRAME_MATERIAL, "Aluminium")].verdict == Verdict.FAIL


def test_missing_fields_become_questions() -> None:
    from zelles.domain.spec import SpecSheet

    sheet = SpecSheet(
        document_id="x",
        filename="f",
        model="rules",
        requirements=[
            Requirement(
                field=SpecField.UW,
                value="Uw = 13",
                status=RequirementStatus.INVALID,
                citation=Citation(chunk_id="c0000", quote="Uw = 13"),
            ),
        ],
    )
    reasons = {(q.reason, q.field) for q in clarification_questions(sheet)}
    assert ("missing", SpecField.FRAME_MATERIAL) in reasons
    assert ("missing", SpecField.UW) in reasons
    assert ("invalid", SpecField.UW) in reasons
