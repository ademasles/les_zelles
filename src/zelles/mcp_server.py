"""MCP server: the same tools as the agent, for Claude Desktop, IDEs and other agents.

Run with ``zelles mcp`` (stdio). Requires the extra: ``pip install 'les-zelles[mcp]'``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from zelles.agent.tools import ToolContext, ToolRegistry
from zelles.config import Settings
from zelles.domain.spec import Category, SpecField
from zelles.graph.knowledge import EdgeType, NodeType
from zelles.insights import ProductSpec
from zelles.llm.registry import create_embedder, create_llm


def build_server(settings: Settings) -> Any:
    from mcp.server.mcpserver import MCPServer  # noqa: PLC0415

    from zelles.storage.workspace import Workspace  # noqa: PLC0415

    embedder = create_embedder(settings.embedding_model, settings)
    workspace = Workspace(settings, embedder=embedder)
    llm = create_llm(settings.llm_model, settings)
    registry = ToolRegistry()

    async def list_docs() -> list[dict[str, Any]]:
        return workspace.list_documents()

    ctx = ToolContext(load=workspace.load, list_documents=list_docs)
    server = MCPServer(
        name="les_zelles",
        instructions=(
            "Tools over French joinery tender specifications (CCTP): analyse a file, search it, read "
            "cited requirements, walk its knowledge graph, check a product, draft clarification "
            "questions. Start with list_documents or analyze_file. Cite passage ids in answers."
        ),
    )

    async def call(name: str, **arguments: Any) -> Any:
        return await registry.call(ctx, name, {k: v for k, v in arguments.items() if v is not None})

    @server.tool()
    async def analyze_file(path: str) -> dict[str, Any]:
        """Analyse a CCTP file (PDF, DOCX, TXT, MD) from a local path and store it."""
        from zelles.pipeline import analyze  # noqa: PLC0415

        file = Path(path).expanduser()  # noqa: ASYNC240 - no I/O, just a home expansion
        data = await asyncio.to_thread(file.read_bytes)
        analysis = await analyze(data, file.name, settings=settings, llm=llm, embedder=embedder)
        workspace.register(analysis.document_id, file.name, analysis.document.media_type, data)
        workspace.save(analysis)
        return {
            "document_id": analysis.document_id,
            "requirements": len(analysis.sheet.requirements),
            "lots": analysis.sheet.lots,
            "coverage": round(analysis.sheet.coverage(), 2),
        }

    @server.tool()
    async def list_documents() -> Any:
        """List analysed CCTPs with their ids."""
        return await call("list_documents")

    @server.tool()
    async def outline(document_id: str) -> Any:
        """Lots and article structure of a CCTP, with passage ids and pages."""
        return await call("outline", document_id=document_id)

    @server.tool()
    async def search_passages(
        document_id: str, query: str, k: int = 5, lot: str | None = None
    ) -> Any:
        """Hybrid keyword and semantic search over a CCTP's passages."""
        return await call("search_passages", document_id=document_id, query=query, k=k, lot=lot)

    @server.tool()
    async def read_passage(document_id: str, chunk_id: str) -> Any:
        """Full text of one passage by id."""
        return await call("read_passage", document_id=document_id, chunk_id=chunk_id)

    @server.tool()
    async def get_requirements(
        document_id: str,
        field: SpecField | None = None,
        category: Category | None = None,
        verified_only: bool = False,
    ) -> Any:
        """Extracted, cited requirements, optionally filtered by field or category."""
        return await call(
            "get_requirements",
            document_id=document_id,
            field=field,
            category=category,
            verified_only=verified_only,
        )

    @server.tool()
    async def graph_find(document_id: str, text: str, node_type: NodeType | None = None) -> Any:
        """Find knowledge-graph nodes (sections, standards, requirements, topics) by text."""
        return await call("graph_find", document_id=document_id, text=text, node_type=node_type)

    @server.tool()
    async def graph_neighbors(
        document_id: str, node_id: str, relation: EdgeType | None = None
    ) -> Any:
        """Nodes linked to a node in the knowledge graph, optionally by relation."""
        return await call(
            "graph_neighbors", document_id=document_id, node_id=node_id, relation=relation
        )

    @server.tool()
    async def find_conflicts(document_id: str) -> Any:
        """Requirements that contradict each other for the same scope."""
        return await call("find_conflicts", document_id=document_id)

    @server.tool()
    async def check_product(document_id: str, product: ProductSpec) -> Any:
        """Check a product's declared performances against the CCTP requirements."""
        return await call("check_product", document_id=document_id, product=product.model_dump())

    @server.tool()
    async def clarification_questions(document_id: str) -> Any:
        """Draft questions for the project owner (missing, conflicting or invalid values)."""
        return await call("clarification_questions", document_id=document_id)

    return server


def run(settings: Settings) -> None:  # pragma: no cover - needs a stdio client
    build_server(settings).run("stdio")
