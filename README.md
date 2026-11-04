# les_zelles

**Turn a French joinery tender spec (CCTP) into a cited, verified spec sheet in minutes, with a local model or none at all.**

A joinery contractor answering a public tender (PVC, aluminium or wood windows, doors, curtain walls, shutters) receives a *DCE* with a 40 to 200 page *CCTP*. Before pricing, an estimator has to find every requirement that changes the cost or the product choice: frame material, Uw, glazing build-up, AEV class, acoustic Ra,tr, colours, security class, shutters, installation method, and the standards to comply with. Today that is a manual read, line by line, with a highlighter. Missing one line (an RC2 class on the ground floor, a 36 dB façade) means a wrong quote or a non-compliant delivery.

les_zelles does that read for you and **shows its work**: every value comes with the exact quote, the page and a highlight on the page image. Values that cannot be found in the source are flagged, never silently kept.

```
CCTP (PDF, DOCX, scan) ──► outline-aware parse ──► rules ─┐
                                                          ├─► verify against source ─► spec sheet + knowledge graph
                     hybrid retrieval ──► LLM per field ──┘        (quote, page, bbox)       │
                                                                                            ├─► web UI, JSON/CSV/XLSX
                                                                                            ├─► product compliance check
                                                                                            ├─► questions for the project owner
                                                                                            └─► agent tools (HTTP, MCP, CLI)
```

## What it does

- **Cited spec sheet.** 25 joinery fields in 10 categories, each requirement with value, unit, comparator (`≤ 1.3 W/m².K`), scope (lot, building, room type), confidence and a verified quote.
- **Works without an LLM.** A rules engine written for CCTP wording extracts the common fields for free and deterministically. Add a model to increase recall on the long tail.
- **Local first, cloud optional.** Ollama, llama.cpp, vLLM and LM Studio through one OpenAI-compatible adapter; Anthropic Claude through the official SDK with prompt caching; OpenAI, Mistral, Gemini and OpenRouter as presets. Cost is tracked per document (local runs cost $0).
- **Grounding by construction.** LLM output is schema-constrained, then each quote is located in the source (exact or fuzzy match) and each number must appear in its quote. Domain validators check ranges and formats (Uw, Ug, Sw, AEV classes per EN 12207/12208/12210, RAL codes).
- **Knowledge graph.** Document → Lot → Section → Passage → Requirement, linked to Standards, Certifications, Materials and Topics, with article cross-references ("voir article 3.2") and **conflict detection** when the same scope gets two different values. Exports to JSON and Cypher (Neo4j).
- **Decision support.** Check a manufacturer's product against the CCTP (pass / fail / review per requirement), and draft the clarification questions to send to the architect before pricing (missing, conflicting or inconsistent values).
- **Agent harness.** Ten typed tools (search, read passage, requirements, graph walk, conflicts, product check, clarifications...) exposed identically to the built-in agent loop, the HTTP API and an **MCP server**, so Claude Desktop, an IDE or your own agent can work on your tenders.
- **Measured.** A golden-set evaluation harness reports per-field precision, recall, F1, grounding rate and cost, and runs in CI as a quality gate.

## Quickstart

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ademasles/les_zelles && cd les_zelles
uv sync --extra ocr

# 1. Rules only: free, offline, deterministic
uv run zelles analyze path/to/cctp.pdf -o sheet.xlsx

# 2. With a local model (https://ollama.com)
ollama pull qwen3:8b && ollama pull bge-m3
uv run zelles analyze path/to/cctp.pdf -m ollama:qwen3:8b -e ollama:bge-m3 --save

# 3. With Claude
uv sync --extra anthropic
export ZELLES_LLM_API_KEY=sk-ant-...
uv run zelles analyze path/to/cctp.pdf -m anthropic:claude-sonnet-5-5 --save

# Web UI and API on http://127.0.0.1:8000
uv run zelles serve
```

Or with Docker:

```bash
docker compose up --build                      # rules only
docker compose --profile local up --build      # plus an Ollama container
docker compose exec ollama ollama pull qwen3:8b
```

## Using it

| Interface | Entry point |
|---|---|
| Web UI | `zelles serve`, then open `/`. Upload, follow progress live, browse the sheet with page highlights, ask questions, check a product, view the graph. |
| CLI | `zelles analyze`, `ask`, `agent --trace`, `eval`, `serve`, `mcp`. Run `zelles --help`. |
| REST API | `/api/v1`, OpenAPI docs at `/docs`. Optional `X-API-Key` header. |
| MCP | `zelles mcp` (stdio). See [docs/agent-and-graph.md](docs/agent-and-graph.md) for the Claude Desktop config. |
| Python | `from zelles.pipeline import analyze` |

## Configuration

All settings are environment variables prefixed `ZELLES_` (or a `.env` file). See [.env.example](.env.example) and [`config.py`](src/zelles/config.py).

| Variable | Default | Notes |
|---|---|---|
| `ZELLES_LLM_MODEL` | `none` | `provider:model`, e.g. `ollama:qwen3:8b`, `anthropic:claude-sonnet-5-5` |
| `ZELLES_EMBEDDING_MODEL` | `none` | `none` means BM25 only; `ollama:bge-m3` adds dense retrieval |
| `ZELLES_LLM_CONCURRENCY` | `2` | Use `1` on a single local GPU |
| `ZELLES_DATABASE_URL` | SQLite in `data/` | Any SQLAlchemy URL; migrations run on startup |
| `ZELLES_API_KEY` | unset | Protects the API when set |
| `ZELLES_OCR_ENABLED` | `true` | Tesseract fallback for scanned pages |

Model choice and cost per document are discussed in [docs/models.md](docs/models.md).

## Project layout

```
src/zelles/
  domain/        documents, spec fields, validators (pure, no I/O)
  ingest/        PDF/DOCX/TXT parsing with bboxes, OCR, outline detection, chunking
  retrieval/     French BM25, dense embeddings, RRF fusion
  llm/           provider-agnostic clients, pricing, registry
  extraction/    rules, LLM extractor, quote verification, merge
  graph/         ontology of standards and the knowledge graph
  agent/         typed tool registry and agent loop
  api/  web/     FastAPI app and the static UI
  storage/ jobs/ SQLAlchemy + Alembic, workspace, background jobs with SSE
  evaluation/    golden-set harness
evals/golden/    annotated CCTPs with expected requirements
tests/           unit and integration tests (no network)
docs/            architecture, models, agent and graph, evaluation
```

## Development

```bash
make install   # uv sync + pre-commit hooks
make check     # ruff, mypy --strict, pytest, eval gate
```

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/architecture.md](docs/architecture.md) before a larger change.

## Limits

- The golden set is small and synthetic for now; scores on real tenders will be lower until more annotated CCTPs are added.
- Tables spanning several pages and drawings are not interpreted; requirements stated only in plans or in the DPGF are out of scope.
- Extraction targets French CCTPs. Field labels and the code are in English; prompts ask the model to quote the French source verbatim.

## License

Proprietary. The source is public for reference only; all rights reserved. See [LICENSE](LICENSE).
