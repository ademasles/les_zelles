"""Command-line interface: ``zelles analyze``, ``ask``, ``agent``, ``serve``, ``mcp``, ``eval``, ``corpus``."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from zelles import __version__
from zelles.config import Settings, get_settings
from zelles.domain.spec import FIELD_CATALOG, RequirementStatus, SpecSheet
from zelles.exports import to_csv, to_xlsx
from zelles.llm.registry import create_embedder, create_llm
from zelles.observability import configure_logging

app = typer.Typer(
    help="Cited, verified analysis of joinery tender specifications (CCTP).", no_args_is_help=True
)
console = Console()

ModelOpt = Annotated[
    str | None, typer.Option("--model", "-m", help="provider:model, or 'none' for rules only")
]
EmbedOpt = Annotated[
    str | None, typer.Option("--embeddings", "-e", help="provider:model for hybrid search")
]


def _settings(model: str | None, embeddings: str | None) -> Settings:
    base = get_settings()
    update: dict[str, object] = {}
    if model is not None:
        update["llm_model"] = model
    if embeddings is not None:
        update["embedding_model"] = embeddings
    settings = base.model_copy(update=update)
    configure_logging(settings.log_level, json_output=settings.log_json)
    return settings


def _print_sheet(sheet: SpecSheet) -> None:
    table = Table(title=f"{sheet.filename} · {sheet.model}", show_lines=False)
    for col in ("Field", "Value", "Scope", "Where", "Status"):
        table.add_column(col, overflow="fold")
    colors = {
        RequirementStatus.VERIFIED: "green",
        RequirementStatus.UNVERIFIED: "yellow",
        RequirementStatus.INVALID: "red",
    }
    for req in sheet.requirements:
        table.add_row(
            FIELD_CATALOG[req.field].label,
            req.value,
            req.scope or "",
            req.citation.locator if req.citation else "",
            f"[{colors[req.status]}]{req.status.value}[/] {req.confidence:.0%}",
        )
    console.print(table)
    usage = sheet.usage
    cost = f"${usage.cost_usd:.4f}" if usage.cost_usd is not None else "n/a"
    console.print(
        f"{len(sheet.requirements)} requirements · coverage {sheet.coverage():.0%} · "
        f"{usage.calls} LLM calls · {usage.input_tokens + usage.output_tokens} tokens · cost {cost} · "
        f"{usage.seconds:.1f}s"
    )
    if sheet.summary:
        console.print(f"\n[bold]Brief[/]\n{sheet.summary}")
    for warning in sheet.warnings:
        console.print(f"[yellow]warning:[/] {warning}")


@app.command()
def analyze(
    file: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, help="CCTP as PDF, DOCX, TXT or MD")
    ],
    model: ModelOpt = None,
    embeddings: EmbedOpt = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write .json, .csv or .xlsx")
    ] = None,
    save: Annotated[bool, typer.Option(help="Store in the workspace for ask/agent/serve")] = True,
) -> None:
    """Analyse a CCTP and print its spec sheet."""
    settings = _settings(model, embeddings)

    async def run() -> SpecSheet:
        from zelles.pipeline import analyze as run_pipeline  # noqa: PLC0415

        llm = create_llm(settings.llm_model, settings)
        embedder = create_embedder(settings.embedding_model, settings)
        try:
            with console.status("Analysing...") as status:

                async def progress(stage: str, fraction: float, message: str) -> None:
                    status.update(f"[{fraction:.0%}] {message}")

                analysis = await run_pipeline(
                    file.read_bytes(),
                    file.name,
                    settings=settings,
                    llm=llm,
                    embedder=embedder,
                    progress=progress,
                )
            if save:
                from zelles.storage.workspace import Workspace  # noqa: PLC0415

                workspace = Workspace(settings)
                workspace.register(
                    analysis.document_id, file.name, analysis.document.media_type, file.read_bytes()
                )
                workspace.save(analysis)
                console.print(f"Saved as document [bold]{analysis.document_id}[/]")
            return analysis.sheet
        finally:
            if llm:
                await llm.aclose()
            if embedder:
                await embedder.aclose()

    sheet = asyncio.run(run())
    _print_sheet(sheet)
    if output:
        suffix = output.suffix.lower()
        if suffix == ".json":
            output.write_text(sheet.model_dump_json(indent=2))
        elif suffix == ".csv":
            output.write_text(to_csv(sheet), encoding="utf-8-sig")
        elif suffix == ".xlsx":
            output.write_bytes(to_xlsx(sheet))
        else:
            raise typer.BadParameter("output must end with .json, .csv or .xlsx")
        console.print(f"Wrote {output}")


@app.command()
def ask(
    document_id: Annotated[str, typer.Argument(help="Id printed by 'zelles analyze'")],
    question: Annotated[str, typer.Argument()],
    model: ModelOpt = None,
) -> None:
    """Ask a question about an analysed CCTP and get a cited answer."""
    settings = _settings(model, None)

    async def run() -> None:
        from zelles.qa import answer_question  # noqa: PLC0415
        from zelles.storage.workspace import Workspace  # noqa: PLC0415

        llm = create_llm(settings.llm_model, settings)
        workspace = Workspace(
            settings, embedder=create_embedder(settings.embedding_model, settings)
        )
        doc = await workspace.load(document_id)
        answer = await answer_question(question, doc.index, llm, k=settings.retrieval_top_k)
        console.print(answer.answer)
        for cite in answer.citations:
            mark = "✓" if cite.match_score >= 0.88 else "?"
            console.print(f"  {mark} [{cite.chunk_id}] {cite.locator}: “{cite.quote[:160]}”")
        if llm:
            await llm.aclose()

    asyncio.run(run())


@app.command()
def agent(
    question: Annotated[str, typer.Argument()],
    document_id: Annotated[str | None, typer.Option("--doc", "-d")] = None,
    model: ModelOpt = None,
    max_steps: int = 8,
    trace: Annotated[bool, typer.Option(help="Print every tool call")] = False,
) -> None:
    """Let the agent answer using the tools (search, requirements, graph, product checks)."""
    settings = _settings(model, None)

    async def run() -> None:
        from zelles.agent.loop import Agent  # noqa: PLC0415
        from zelles.agent.tools import ToolContext  # noqa: PLC0415
        from zelles.storage.workspace import Workspace  # noqa: PLC0415

        llm = create_llm(settings.llm_model, settings)
        if llm is None:
            raise typer.BadParameter("the agent needs a model: --model ollama:qwen3:8b")
        workspace = Workspace(settings)

        async def list_docs() -> list[dict[str, object]]:
            return workspace.list_documents()

        result = await Agent(llm, ToolContext(workspace.load, list_docs), max_steps=max_steps).run(
            question, document_id=document_id
        )
        if trace:
            for i, step in enumerate(result.steps, 1):
                console.print(
                    f"[dim]{i}. {step.action} {json.dumps(step.arguments, ensure_ascii=False)}[/]"
                )
        console.print(result.answer)
        await llm.aclose()

    asyncio.run(run())


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    model: ModelOpt = None,
    embeddings: EmbedOpt = None,
) -> None:
    """Run the API and web UI."""
    import uvicorn  # noqa: PLC0415

    from zelles.api.app import create_app  # noqa: PLC0415

    uvicorn.run(create_app(_settings(model, embeddings)), host=host, port=port)


@app.command()
def mcp(model: ModelOpt = None) -> None:
    """Run the MCP server over stdio (for Claude Desktop, IDEs and other agents)."""
    from zelles.mcp_server import run  # noqa: PLC0415

    run(_settings(model, None))


@app.command("eval")
def evaluate(
    golden_dir: Annotated[Path, typer.Argument(file_okay=False)] = Path("evals/golden"),
    model: ModelOpt = None,
    min_f1: Annotated[float, typer.Option(help="Fail (exit 1) below this strict micro F1")] = 0.0,
    blind: Annotated[
        bool,
        typer.Option(help="Counts only: hide case names and missed values (held-out sets)."),
    ] = False,
    json_out: Annotated[
        Path | None, typer.Option("--json", help="Also write the full report as JSON.")
    ] = None,
) -> None:
    """Score extraction against the golden set (per-field precision, recall, F1)."""
    from zelles.corpus.split import SEAL_FILE  # noqa: PLC0415
    from zelles.evaluation.harness import run_eval  # noqa: PLC0415

    settings = _settings(model, None)
    report = asyncio.run(run_eval(golden_dir, settings))
    sealed = (golden_dir / SEAL_FILE).exists()
    if sealed:
        # A sealed test set only ever reports counts, and every look is logged:
        # the number of looks is part of the result.
        with (golden_dir / SEAL_FILE).open("a", encoding="utf-8") as log:
            log.write(
                f"{report.manifest.model_dump_json() if report.manifest else '{}'}"
                f" strict_f1={report.strict_f1:.4f}\n"
            )
    if blind or sealed:
        report = report.blinded()
    if json_out is not None:
        json_out.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    table = Table(title=f"Evaluation · {report.model}")
    for col in ("Case", "Precision", "Recall", "F1", "Strict F1", "Grounded", "Cost"):
        table.add_column(col)
    for case in report.cases:
        cost = f"${case.cost_usd:.4f}" if case.cost_usd is not None else "n/a"
        table.add_row(
            case.name,
            f"{case.precision:.2f}",
            f"{case.recall:.2f}",
            f"{case.f1:.2f}",
            f"{case.strict_f1:.2f}",
            f"{case.grounded_rate:.0%}",
            cost,
        )
    console.print(table)
    if report.manifest is not None:
        m = report.manifest
        console.print(
            f"scorer v{m.scorer_version} · code {m.git_commit or 'unknown'} · "
            f"keys {m.keys_sha256} ({m.cases} cases) · {m.model}"
        )
    for label, p, r, f, (lo, hi) in (
        ("lenient", report.precision, report.recall, report.f1, report.f1_ci),
        (
            "strict",
            report.strict_precision,
            report.strict_recall,
            report.strict_f1,
            report.strict_f1_ci,
        ),
    ):
        console.print(
            f"micro F1 {label:<7} {f:.3f} (95% CI {lo:.3f}-{hi:.3f}) · P {p:.3f} · R {r:.3f}"
        )
    fields = Table(title="Strict errors by field")
    for col in ("Field", "Expected", "Missed", "Predicted", "Extra"):
        fields.add_column(col)
    for name, c in report.fields.items():
        if c.misses or c.extras:
            fields.add_row(name, str(c.expected), str(c.misses), str(c.predicted), str(c.extras))
    console.print(fields)
    for miss in report.misses[:30]:
        console.print(f"  [yellow]missed[/] {miss}")
    if report.strict_f1 < min_f1:
        raise typer.Exit(1)


corpus = typer.Typer(help="Grow the evaluation corpus from public tenders.", no_args_is_help=True)
app.add_typer(corpus, name="corpus")


@corpus.command("find")
def corpus_find(
    out: Annotated[Path, typer.Option("--out", "-o", help="CSV to write")] = Path("leads.csv"),
    days: Annotated[int, typer.Option(help="Notices published in the last N days")] = 60,
    dept: Annotated[
        list[str] | None, typer.Option("--dept", help="Department code, repeatable")
    ] = None,
    include_closed: Annotated[
        bool, typer.Option(help="Also list notices whose deadline has passed")
    ] = False,
    max_records: Annotated[int, typer.Option(help="Notices to scan at most")] = 500,
) -> None:
    """List BOAMP notices with a joinery lot and the link to download the DCE."""
    import httpx  # noqa: PLC0415

    from zelles.corpus.boamp import search, to_csv  # noqa: PLC0415

    with httpx.Client(timeout=30, headers={"User-Agent": "les-zelles-corpus"}) as client:
        leads = list(
            search(
                client,
                days=days,
                open_only=not include_closed,
                departments=dept or (),
                max_records=max_records,
            )
        )
    out.write_text(to_csv(leads), encoding="utf-8")
    table = Table(title=f"{len(leads)} notices with a joinery lot")
    for col in ("Published", "Deadline", "Dept", "Buyer", "Joinery lot"):
        table.add_column(col, overflow="fold")
    for lead in leads[:20]:
        lot = lead.joinery_lots[0]
        table.add_row(
            lead.published,
            lead.deadline[:10],
            " ".join(lead.departments),
            lead.buyer[:40],
            lot.label[:60],
        )
    console.print(table)
    console.print(f"Saved to {out}. Download each DCE from its link; nothing is fetched here.")


@app.command()
def version() -> None:
    """Print the version."""
    console.print(__version__)


if __name__ == "__main__":  # pragma: no cover
    app()


@corpus.command("split")
def corpus_split(
    manifest: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    out: Annotated[Path, typer.Option("--out", "-o", help="Split file (JSON)")] = Path(
        "splits.json"
    ),
    salt: Annotated[
        str | None, typer.Option(help="Seed of the draw; kept from --out when it exists")
    ] = None,
) -> None:
    """Assign downloaded tenders to train, validation and sealed test, one buyer per split.

    Re-running with more tenders keeps every earlier assignment, so the test set
    only grows.
    """
    import secrets  # noqa: PLC0415

    from zelles.corpus.split import SPLITS, Split, assign, read_manifest  # noqa: PLC0415

    existing = Split.model_validate_json(out.read_text()) if out.exists() else None
    split = assign(
        read_manifest(manifest),
        salt=salt or (existing.salt if existing else secrets.token_hex(8)),
        existing=existing,
    )
    out.write_text(split.model_dump_json(indent=2), encoding="utf-8")
    counts = split.counts()
    console.print(" · ".join(f"{s} {counts[s]}" for s in SPLITS) + f" → {out}")
