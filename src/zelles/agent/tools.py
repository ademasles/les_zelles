"""Typed tools over analysed CCTPs: one registry for the agent loop, the MCP server and the API.

Every tool has a Pydantic input model (its JSON schema is what models see), is
read-only, and returns JSON-serialisable data with citations, so whatever
drives it (our agent loop, Claude Desktop through MCP, another framework) gets
grounded answers.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from zelles.domain.documents import Chunk
from zelles.domain.spec import FIELD_CATALOG, Category, RequirementStatus, SpecField, SpecSheet
from zelles.graph.knowledge import EdgeType, KnowledgeGraph, NodeType
from zelles.insights import ProductSpec, clarification_questions, compare_product
from zelles.retrieval.index import DocumentIndex


class DocContext(Protocol):
    """What a tool needs from an analysed document (satisfied by pipeline.Analysis)."""

    document_id: str
    chunks: list[Chunk]
    index: DocumentIndex
    sheet: SpecSheet
    graph: KnowledgeGraph


Loader = Callable[[str], Awaitable[DocContext]]
Lister = Callable[[], Awaitable[list[dict[str, Any]]]]


class ToolError(RuntimeError):
    pass


@dataclass
class ToolContext:
    load: Loader
    list_documents: Lister


class Tool[In: BaseModel]:
    def __init__(
        self,
        name: str,
        description: str,
        input_model: type[In],
        fn: Callable[[ToolContext, In], Awaitable[Any]],
    ) -> None:
        self.name, self.description, self.input_model, self.fn = name, description, input_model, fn

    def schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    async def __call__(self, ctx: ToolContext, arguments: dict[str, Any]) -> Any:
        try:
            parsed = self.input_model.model_validate(arguments or {})
        except ValidationError as exc:
            raise ToolError(f"invalid arguments for {self.name}: {exc}") from exc
        return await self.fn(ctx, parsed)


# ------------------------------------------------------------------ inputs
class NoInput(BaseModel):
    pass


class DocInput(BaseModel):
    document_id: str = Field(description="Id returned by list_documents.")


class SearchInput(DocInput):
    query: str = Field(description="Words to look for, in French works best.")
    k: int = Field(default=5, ge=1, le=15)
    lot: str | None = Field(default=None, description="Restrict to one lot label.")


class PassageInput(DocInput):
    chunk_id: str


class RequirementsInput(DocInput):
    field: SpecField | None = None
    category: Category | None = None
    verified_only: bool = False


class GraphNodeInput(DocInput):
    node_id: str = Field(description="Node id, e.g. 'req:3', 'std:nf-dtu-36.5', 'topic:thermal'.")
    relation: EdgeType | None = None


class GraphFindInput(DocInput):
    text: str
    node_type: NodeType | None = None


class ProductInput(DocInput):
    product: ProductSpec


# ------------------------------------------------------------------ implementations
async def _list_documents(ctx: ToolContext, _: NoInput) -> Any:
    return await ctx.list_documents()


async def _outline(ctx: ToolContext, args: DocInput) -> Any:
    doc = await ctx.load(args.document_id)
    seen: list[dict[str, Any]] = []
    for chunk in doc.chunks:
        entry = {
            "chunk_id": chunk.id,
            "path": chunk.section_path,
            "pages": [chunk.page_start, chunk.page_end],
        }
        seen.append(entry)
    return {"lots": doc.sheet.lots, "sections": seen}


async def _search(ctx: ToolContext, args: SearchInput) -> Any:
    doc = await ctx.load(args.document_id)
    hits = await doc.index.search(args.query, k=args.k, lot=args.lot)
    return [
        {
            "chunk_id": h.chunk.id,
            "locator": h.chunk.locator(),
            "score": round(h.score, 4),
            "text": h.chunk.text[:1200],
        }
        for h in hits
    ]


async def _read_passage(ctx: ToolContext, args: PassageInput) -> Any:
    doc = await ctx.load(args.document_id)
    for chunk in doc.chunks:
        if chunk.id == args.chunk_id:
            return {"chunk_id": chunk.id, "locator": chunk.locator(), "text": chunk.text}
    raise ToolError(f"no passage {args.chunk_id!r}")


async def _requirements(ctx: ToolContext, args: RequirementsInput) -> Any:
    doc = await ctx.load(args.document_id)
    out = []
    for i, req in enumerate(doc.sheet.requirements):
        if args.field and req.field != args.field:
            continue
        if args.category and FIELD_CATALOG[req.field].category != args.category:
            continue
        if args.verified_only and req.status != RequirementStatus.VERIFIED:
            continue
        out.append({"id": f"req:{i}", **req.model_dump(mode="json", exclude={"notes"})})
    return out


async def _graph_neighbors(ctx: ToolContext, args: GraphNodeInput) -> Any:
    doc = await ctx.load(args.document_id)
    if args.node_id not in doc.graph.nodes:
        raise ToolError(f"no node {args.node_id!r}; use graph_find first")
    return [
        {
            "relation": e.type.value,
            "direction": "out" if e.source == args.node_id else "in",
            "node": n.model_dump(mode="json"),
        }
        for e, n in doc.graph.neighbors(args.node_id, args.relation)
    ]


async def _graph_find(ctx: ToolContext, args: GraphFindInput) -> Any:
    doc = await ctx.load(args.document_id)
    return [n.model_dump(mode="json") for n in doc.graph.find(args.text, args.node_type)]


async def _conflicts(ctx: ToolContext, args: DocInput) -> Any:
    doc = await ctx.load(args.document_id)
    return [c.model_dump(mode="json") for c in doc.graph.conflicts()]


async def _check_product(ctx: ToolContext, args: ProductInput) -> Any:
    doc = await ctx.load(args.document_id)
    return [c.model_dump(mode="json") for c in compare_product(doc.sheet, args.product)]


async def _clarifications(ctx: ToolContext, args: DocInput) -> Any:
    doc = await ctx.load(args.document_id)
    return [c.model_dump(mode="json") for c in clarification_questions(doc.sheet, doc.graph)]


TOOLS: list[Tool[Any]] = [
    Tool("list_documents", "List analysed CCTPs with their ids.", NoInput, _list_documents),
    Tool(
        "outline",
        "Lots and article structure of a CCTP, with passage ids and pages.",
        DocInput,
        _outline,
    ),
    Tool(
        "search_passages",
        "Hybrid keyword and semantic search over a CCTP's passages.",
        SearchInput,
        _search,
    ),
    Tool("read_passage", "Full text of one passage by id.", PassageInput, _read_passage),
    Tool(
        "get_requirements",
        "Extracted, cited requirements, optionally filtered by field or category.",
        RequirementsInput,
        _requirements,
    ),
    Tool(
        "graph_find",
        "Find knowledge-graph nodes (sections, standards, requirements, topics) by text.",
        GraphFindInput,
        _graph_find,
    ),
    Tool(
        "graph_neighbors",
        "Nodes linked to a node in the knowledge graph, optionally by relation.",
        GraphNodeInput,
        _graph_neighbors,
    ),
    Tool(
        "find_conflicts",
        "Requirements that contradict each other for the same scope.",
        DocInput,
        _conflicts,
    ),
    Tool(
        "check_product",
        "Check a product's declared performances against the CCTP requirements.",
        ProductInput,
        _check_product,
    ),
    Tool(
        "clarification_questions",
        "Draft questions for the project owner (missing, conflicting values).",
        DocInput,
        _clarifications,
    ),
]


class ToolRegistry:
    def __init__(self, tools: list[Tool[Any]] | None = None) -> None:
        self.tools = {t.name: t for t in (tools or TOOLS)}

    def get(self, name: str) -> Tool[Any]:
        if name not in self.tools:
            raise ToolError(f"unknown tool {name!r}; available: {', '.join(self.tools)}")
        return self.tools[name]

    async def call(self, ctx: ToolContext, name: str, arguments: dict[str, Any]) -> Any:
        return await self.get(name)(ctx, arguments)

    def describe(self) -> str:
        """Compact tool list for prompts."""
        import json  # noqa: PLC0415

        lines = []
        for tool in self.tools.values():
            schema = json.dumps(tool.schema(), ensure_ascii=False, separators=(",", ":"))
            lines.append(f"- {tool.name}: {tool.description}\n  arguments schema: {schema}")
        return "\n".join(lines)

    def openai_tools(self) -> list[dict[str, Any]]:
        """Native function-calling definitions (OpenAI format)."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.schema(),
                },
            }
            for t in self.tools.values()
        ]

    def anthropic_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.schema()}
            for t in self.tools.values()
        ]
