from typing import Any

from zelles.agent.loop import Agent
from zelles.agent.tools import ToolContext, ToolRegistry
from zelles.config import Settings
from zelles.llm.base import Message
from zelles.llm.fake import FakeLLM
from zelles.pipeline import Analysis, analyze


async def _ctx(sample_bytes: bytes, settings: Settings) -> tuple[ToolContext, Analysis]:
    analysis = await analyze(sample_bytes, "cctp.md", settings=settings)

    async def load(document_id: str) -> Analysis:
        assert document_id == analysis.document_id
        return analysis

    async def list_docs() -> list[dict[str, Any]]:
        return [{"id": analysis.document_id, "filename": "cctp.md"}]

    return ToolContext(load=load, list_documents=list_docs), analysis


async def test_tools_registry(sample_bytes: bytes, settings: Settings) -> None:
    ctx, analysis = await _ctx(sample_bytes, settings)
    registry = ToolRegistry()
    doc = analysis.document_id
    reqs = await registry.call(ctx, "get_requirements", {"document_id": doc, "field": "aev"})
    assert {r["value"] for r in reqs} == {"A*3 E*7B V*A2", "A*4 E*9A V*C3"}
    hits = await registry.call(
        ctx, "search_passages", {"document_id": doc, "query": "entrées d'air hygroréglables"}
    )
    assert hits[0]["locator"].endswith("4.2 Entrées d'air")
    nodes = await registry.call(
        ctx, "graph_find", {"document_id": doc, "text": "36.5", "node_type": "Standard"}
    )
    neighbors = await registry.call(
        ctx, "graph_neighbors", {"document_id": doc, "node_id": nodes[0]["id"]}
    )
    assert any(n["relation"] == "GOVERNS" for n in neighbors)
    assert len(registry.openai_tools()) == len(registry.anthropic_tools()) == 10


async def test_agent_loop(sample_bytes: bytes, settings: Settings) -> None:
    ctx, analysis = await _ctx(sample_bytes, settings)
    script = iter(
        [
            {
                "thought": "Look up the thermal requirement",
                "action": "get_requirements",
                "arguments": {"document_id": analysis.document_id, "field": "uw"},
            },
            {"thought": "Bad call to test errors", "action": "no_such_tool", "arguments": {}},
            {
                "thought": "Done",
                "action": "final_answer",
                "arguments": {},
                "answer": "Uw ≤ 1,3 W/m².K for the PVC windows [c0005] and ≤ 1,6 for the hall [c0008].",
            },
        ]
    )

    def responder(system: str, messages: list[Message], schema: type[Any] | None) -> Any:
        if len(messages) > 1:
            assert messages[-1].content.startswith(("Observation", "Tool error"))
        return next(script)

    result = await Agent(FakeLLM(responder), ctx).run("Quel Uw ?", document_id=analysis.document_id)
    assert result.stopped == "answer"
    assert "1,3" in result.answer
    assert [s.action for s in result.steps] == ["get_requirements", "no_such_tool", "final_answer"]
    assert result.steps[0].observation and "1.3" in result.steps[0].observation
    assert result.steps[1].error
