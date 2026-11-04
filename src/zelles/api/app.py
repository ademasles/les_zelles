"""HTTP API (FastAPI) and the bundled web UI."""

import asyncio
import json
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from zelles import __version__
from zelles.agent.loop import Agent, AgentResult
from zelles.agent.tools import ToolContext, ToolError, ToolRegistry
from zelles.config import Settings, get_settings
from zelles.exports import to_csv, to_xlsx
from zelles.ingest.parsers import UnsupportedDocumentError, sniff_media_type
from zelles.insights import ProductSpec, clarification_questions, compare_product
from zelles.jobs.runner import JobManager
from zelles.llm.registry import create_embedder, create_llm
from zelles.observability import configure_logging
from zelles.pipeline import document_id_for
from zelles.qa import Answer, answer_question
from zelles.rendering import highlight_boxes, render_page
from zelles.storage.db import FeedbackRow
from zelles.storage.workspace import DocumentNotFoundError, LoadedDocument, Workspace

STATIC_DIR = Path(__file__).resolve().parent.parent / "web" / "static"


class State:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.llm = create_llm(settings.llm_model, settings)
        self.embedder = create_embedder(settings.embedding_model, settings)
        self.workspace = Workspace(settings, embedder=self.embedder)
        self.jobs = JobManager(settings, self.workspace, llm=self.llm, embedder=self.embedder)
        self.tools = ToolRegistry()
        self.tool_ctx = ToolContext(load=self.workspace.load, list_documents=self._list)

    async def _list(self) -> list[dict[str, Any]]:
        return self.workspace.list_documents()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_output=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = State(settings)
        app.state.zelles = state
        await state.jobs.start()
        try:
            yield
        finally:
            await state.jobs.stop()
            if state.llm is not None:
                await state.llm.aclose()
            if state.embedder is not None:
                await state.embedder.aclose()

    app = FastAPI(
        title="les_zelles",
        version=__version__,
        description="Cited, verified analysis of joinery tender specifications (CCTP).",
        lifespan=lifespan,
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    async def require_key(request: Request) -> None:
        expected = settings.api_key.get_secret_value() if settings.api_key else None
        if expected is None:
            return
        given = request.headers.get("x-api-key") or request.query_params.get("api_key") or ""
        if not secrets.compare_digest(given, expected):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing API key")

    def st(request: Request) -> State:
        state: State = request.app.state.zelles
        return state

    StateDep = Annotated[State, Depends(st)]  # noqa: N806
    api = Depends(require_key)

    async def load(state: State, document_id: str) -> LoadedDocument:
        try:
            return await state.workspace.load(document_id)
        except DocumentNotFoundError as exc:
            raise HTTPException(404, "document not found or not analysed yet") from exc

    # ------------------------------------------------------------------ meta
    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/v1/info", tags=["meta"], dependencies=[api])
    async def info(state: StateDep) -> dict[str, Any]:
        return {
            "version": __version__,
            "llm": state.llm.name if state.llm else "rules",
            "embeddings": state.embedder.name if state.embedder else "none",
            "max_upload_mb": settings.max_upload_mb,
        }

    # ------------------------------------------------------------------ documents
    @app.post("/api/v1/documents", tags=["documents"], dependencies=[api], status_code=202)
    async def upload(
        state: StateDep,
        file: Annotated[UploadFile, File()],
        force: Annotated[bool, Query(description="Re-run even if already analysed")] = False,
    ) -> JSONResponse:
        limit = settings.max_upload_mb * 1024 * 1024
        data = await file.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(413, f"file larger than {settings.max_upload_mb} MB")
        filename = Path(file.filename or "document").name
        try:
            media_type = sniff_media_type(data, filename)
        except UnsupportedDocumentError as exc:
            raise HTTPException(415, str(exc)) from exc
        document_id = document_id_for(data)
        if state.workspace.exists(document_id) and not force:
            return JSONResponse(
                {"document_id": document_id, "job_id": None, "cached": True}, status_code=200
            )
        state.workspace.register(document_id, filename, media_type, data)
        job_id = state.jobs.submit(document_id, filename, data)
        return JSONResponse(
            {"document_id": document_id, "job_id": job_id, "cached": False}, status_code=202
        )

    @app.get("/api/v1/documents", tags=["documents"], dependencies=[api])
    async def list_documents(state: StateDep) -> list[dict[str, Any]]:
        return state.workspace.list_documents()

    @app.get("/api/v1/documents/{document_id}", tags=["documents"], dependencies=[api])
    async def get_sheet(state: StateDep, document_id: str) -> dict[str, Any]:
        doc = await load(state, document_id)
        return {
            "sheet": doc.sheet.model_dump(mode="json"),
            "coverage": round(doc.sheet.coverage(), 3),
            "conflicts": [c.model_dump(mode="json") for c in doc.graph.conflicts()],
            "graph_stats": doc.graph.stats(),
            "paginated": doc.document.is_paginated,
        }

    @app.get(
        "/api/v1/documents/{document_id}/chunks/{chunk_id}", tags=["documents"], dependencies=[api]
    )
    async def get_chunk(state: StateDep, document_id: str, chunk_id: str) -> dict[str, Any]:
        doc = await load(state, document_id)
        for chunk in doc.chunks:
            if chunk.id == chunk_id:
                return {**chunk.model_dump(mode="json"), "locator": chunk.locator()}
        raise HTTPException(404, "chunk not found")

    @app.get("/api/v1/documents/{document_id}/graph", tags=["documents"], dependencies=[api])
    async def get_graph(
        state: StateDep, document_id: str, fmt: Literal["json", "cypher"] = "json"
    ) -> Response:
        doc = await load(state, document_id)
        if fmt == "cypher":
            return Response(doc.graph.to_cypher(), media_type="text/plain; charset=utf-8")
        return JSONResponse(doc.graph.to_node_link())

    @app.get(
        "/api/v1/documents/{document_id}/pages/{page}.png", tags=["documents"], dependencies=[api]
    )
    async def page_image(
        state: StateDep,
        document_id: str,
        page: int,
        chunk_id: str | None = None,
        quote: str | None = None,
    ) -> Response:
        doc = await load(state, document_id)
        pdf = state.workspace.rendition(document_id)
        if pdf is None:
            raise HTTPException(404, "no page rendition for this document")
        boxes = []
        if chunk_id:
            chunk = next((c for c in doc.chunks if c.id == chunk_id), None)
            if chunk is not None:
                boxes = highlight_boxes(doc.document, chunk, quote, page)
        try:
            png = await asyncio.to_thread(render_page, pdf, page, boxes)
        except IndexError as exc:
            raise HTTPException(404, "page out of range") from exc
        return Response(
            png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"}
        )

    @app.get("/api/v1/documents/{document_id}/original", tags=["documents"], dependencies=[api])
    async def original(state: StateDep, document_id: str) -> FileResponse:
        try:
            folder = state.workspace.path(document_id)
        except DocumentNotFoundError as exc:
            raise HTTPException(404, "not found") from exc
        files = sorted(folder.glob("original.*"))
        if not files:
            raise HTTPException(404, "not found")
        return FileResponse(files[0])

    @app.get("/api/v1/documents/{document_id}/export.{fmt}", tags=["documents"], dependencies=[api])
    async def export(
        state: StateDep, document_id: str, fmt: Literal["json", "csv", "xlsx"]
    ) -> Response:
        doc = await load(state, document_id)
        stem = Path(doc.sheet.filename).stem
        if fmt == "json":
            body, media = doc.sheet.model_dump_json(indent=2).encode(), "application/json"
        elif fmt == "csv":
            body, media = to_csv(doc.sheet).encode("utf-8-sig"), "text/csv"
        else:
            body = await asyncio.to_thread(to_xlsx, doc.sheet)
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return Response(
            body,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{stem}.{fmt}"'},
        )

    # ------------------------------------------------------------------ analysis
    class AskBody(BaseModel):
        question: str = Field(min_length=3, max_length=2000)

    @app.post("/api/v1/documents/{document_id}/ask", tags=["analysis"], dependencies=[api])
    async def ask(state: StateDep, document_id: str, body: AskBody) -> Answer:
        doc = await load(state, document_id)
        return await answer_question(
            body.question, doc.index, state.llm, k=settings.retrieval_top_k
        )

    @app.post(
        "/api/v1/documents/{document_id}/check-product", tags=["analysis"], dependencies=[api]
    )
    async def check_product(
        state: StateDep, document_id: str, product: ProductSpec
    ) -> list[dict[str, Any]]:
        doc = await load(state, document_id)
        return [c.model_dump(mode="json") for c in compare_product(doc.sheet, product)]

    @app.get(
        "/api/v1/documents/{document_id}/clarifications", tags=["analysis"], dependencies=[api]
    )
    async def clarifications(state: StateDep, document_id: str) -> list[dict[str, Any]]:
        doc = await load(state, document_id)
        return [c.model_dump(mode="json") for c in clarification_questions(doc.sheet, doc.graph)]

    class FeedbackBody(BaseModel):
        field: str
        value: str
        verdict: Literal["correct", "incorrect", "missing"]
        corrected_value: str | None = None
        chunk_id: str | None = None
        comment: str | None = Field(default=None, max_length=2000)

    @app.post(
        "/api/v1/documents/{document_id}/feedback",
        tags=["analysis"],
        dependencies=[api],
        status_code=201,
    )
    async def feedback(state: StateDep, document_id: str, body: FeedbackBody) -> dict[str, str]:
        if not state.workspace.exists(document_id):
            raise HTTPException(404, "document not found")
        with state.workspace.sessions.begin() as session:
            session.add(FeedbackRow(document_id=document_id, **body.model_dump()))
        return {"status": "saved"}

    # ------------------------------------------------------------------ jobs
    @app.get("/api/v1/jobs/{job_id}", tags=["jobs"], dependencies=[api])
    async def job(state: StateDep, job_id: str) -> dict[str, Any]:
        found = state.jobs.status(job_id)
        if found is None:
            raise HTTPException(404, "job not found")
        return found

    @app.get("/api/v1/jobs/{job_id}/events", tags=["jobs"], dependencies=[api])
    async def job_events(state: StateDep, job_id: str) -> EventSourceResponse:
        current = state.jobs.status(job_id)
        if current is None:
            raise HTTPException(404, "job not found")
        queue = state.jobs.subscribe(job_id)

        async def stream() -> AsyncIterator[dict[str, str]]:
            try:
                snapshot = state.jobs.status(job_id) or current
                yield {"event": "progress", "data": json.dumps(snapshot)}
                if snapshot["status"] in ("done", "failed"):
                    return
                while True:
                    event = await queue.get()
                    yield {"event": "progress", "data": json.dumps(event, default=str)}
                    if event.get("status") in ("done", "failed"):
                        return
            finally:
                state.jobs.unsubscribe(job_id, queue)

        return EventSourceResponse(stream(), ping=15)

    # ------------------------------------------------------------------ agent and tools
    @app.get("/api/v1/tools", tags=["agent"], dependencies=[api])
    async def tools(state: StateDep) -> list[dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.schema()}
            for t in state.tools.tools.values()
        ]

    @app.post("/api/v1/tools/{name}", tags=["agent"], dependencies=[api])
    async def call_tool(state: StateDep, name: str, arguments: dict[str, Any]) -> Any:
        try:
            return await state.tools.call(state.tool_ctx, name, arguments)
        except DocumentNotFoundError as exc:
            raise HTTPException(404, "document not found") from exc
        except ToolError as exc:
            raise HTTPException(400, str(exc)) from exc

    class AgentBody(BaseModel):
        question: str = Field(min_length=3, max_length=4000)
        document_id: str | None = None
        max_steps: int = Field(default=8, ge=1, le=20)

    @app.post("/api/v1/agent", tags=["agent"], dependencies=[api])
    async def run_agent(state: StateDep, body: AgentBody) -> AgentResult:
        if state.llm is None:
            raise HTTPException(409, "the agent needs an LLM: set ZELLES_LLM_MODEL")
        agent = Agent(state.llm, state.tool_ctx, state.tools, max_steps=body.max_steps)
        return await agent.run(body.question, document_id=body.document_id)

    # ------------------------------------------------------------------ UI
    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")

    return app
