# Analyse-DCE Refactor Decisions

## 1. POC Goal

**Analyse-DCE** is a proof-of-concept for automated analysis of CCTP and tender documents using retrieval-augmented generation.

The primary goal of the POC is to prove that a user can:

1. Upload a PDF or DOCX tender/CCTP document.
2. Parse the document into a structure suitable for RAG.
3. Ask questions about the document.
4. Receive grounded answers with citations.
5. Trace each answer back to specific document evidence.

The POC validates:

- Document parsing quality using Docling with OCR fallback.
- Markdown-based, section-aware chunking for RAG.
- Local LLM inference viability.
- Evidence-based Q&A with citations.
- Basic provenance tracking for future highlighting and auditability.

The POC does **not** attempt to prove full production readiness, multi-user security, enterprise authentication, advanced observability, or large-scale vector search.

**Target evolution:**

```text
POC        -> local-first demo with SQLite, FAISS, Streamlit, Ollama/local LLM
Pilot      -> PostgreSQL + pgvector, background workers, improved auth, better evaluation
Production -> hardened deployment, auditability, monitoring, access control, scalable storage
```

---

## 2. Non-Negotiable Architecture Rules

These rules must guide the refactor.

### Backend Boundaries

- **Thin routes:** FastAPI route handlers must validate requests, call services, and return responses. They must not contain parsing, chunking, embedding, retrieval, database, or LLM orchestration logic.
- **Service orchestration:** Services coordinate workflows such as document processing, RAG Q&A, summarization, citation generation, and feedback handling.
- **Repository layer:** SQL persistence must go through repositories. Route handlers should not directly query SQLAlchemy models.
- **Vector store abstraction:** Vector search must go through a `VectorStore` interface. FAISS is a POC implementation detail, not a core architecture dependency.
- **LLM abstraction:** LLM calls must go through an `LLMClient` interface. Ollama/Mistral is the local POC implementation.
- **Parser abstraction:** Document parsing must go through a parser interface. Docling is the preferred parser; PyMuPDF and Tesseract are fallbacks.

### Frontend Boundaries

- **Streamlit remains for the POC.**
- Streamlit must call backend APIs only.
- Streamlit must not parse documents, call the LLM, access the database, or manipulate FAISS directly.

### RAG and Traceability

- Every answer must include citations or explicitly state that no sufficient evidence was found.
- Every chunk must preserve source metadata.
- Chunks must be traceable to the source document, page, section, and parser output where available.
- The vector index must be rebuildable from persisted chunks and metadata.
- The application must distinguish between:
  - source documents
  - parsed artifacts
  - chunks
  - embeddings/vector indexes
  - generated answers
  - citations and traces

### Refactor Constraints

- The application must remain runnable after each change.
- The refactor must be incremental, not a big-bang rewrite.
- Local-first development must remain possible.
- POC persistence should not block future PostgreSQL migration.
- Do not introduce Kubernetes, React, Celery, Qdrant, or production infrastructure unless explicitly decided later.

---

## 3. Parsing Strategy

### Decision

Analyse-DCE will use **Docling as the preferred parser** for PDF and DOCX documents.

Docling output will be used in two complementary forms:

1. **Markdown export**  
   Used as the primary representation for RAG, semantic chunking, retrieval context, and LLM prompts.

2. **Structured parser output**  
   Preserved for provenance, citations, page/block traceability, tables, layout data, and future PDF highlighting.

The system must not treat Markdown as the only source of truth.

### Why Docling-First

Docling is preferred because CCTP/tender documents often depend on:

- headings
- hierarchy
- sections/articles
- tables
- bullet lists
- reading order
- page-level provenance
- layout cues

Raw text extraction loses too much of this structure. Markdown is a better input for RAG because it keeps sections and formatting cues more naturally than plain text.

### Parser Fallback Chain

The parser fallback chain for the POC is:

```text
1. Docling
   Preferred parser for PDF/DOCX when structure matters.

2. PyMuPDF
   Fallback for simple born-digital PDFs or when Docling fails.

3. Tesseract
   OCR fallback for scanned PDFs or pages with little/no extractable text.
```

The fallback chain must be deterministic and logged.

### Parser Interface Contract

The parser interface should return a common internal model regardless of parser implementation.

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParsedBlock:
    id: str
    text: str
    block_type: str  # heading, paragraph, list_item, table, caption, footer, unknown
    page_number: int | None = None
    heading_path: list[str] = field(default_factory=list)
    bbox: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedPage:
    page_number: int
    text: str
    markdown: str | None = None
    blocks: list[ParsedBlock] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedTable:
    id: str
    markdown: str
    page_number: int | None = None
    bbox: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    source_path: Path
    parser_name: str
    parser_version: str | None
    markdown: str
    structured_data: dict[str, Any]
    pages: list[ParsedPage] = field(default_factory=list)
    blocks: list[ParsedBlock] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    parsing_stats: dict[str, Any] = field(default_factory=dict)
```

### Required Parser Metadata

Every parsed document should record:

- parser name
- parser version, if available
- source file path
- fallback used, if any
- parsing duration
- OCR enabled/disabled
- OCR confidence, where available
- errors/warnings, where applicable

### POC Decision

For the POC:

```text
Docling -> Markdown + structured JSON
Markdown -> section-aware chunking
Structured JSON -> provenance/citations/future highlighting
PyMuPDF/Tesseract -> fallback only
```

### Production Direction

For production:

```text
Parsing should run asynchronously in isolated workers.
Parser output should be versioned.
Raw files, Markdown, structured parser JSON, chunks, and answer traces should be persisted separately.
Bounding boxes and source offsets should be used for precise highlighting when available.
```

---

## 4. RAG and Chunking Strategy

### Decision

Analyse-DCE will use Markdown-aware, section-aware chunking.

The chunker should not split documents purely by fixed character count. CCTP documents are structured, so the chunking strategy must preserve that structure.

### Chunking Approach

```text
Docling Markdown
  -> clean Markdown
  -> detect headings
  -> build section hierarchy
  -> split by section
  -> split oversized sections by paragraph/list/table
  -> apply limited overlap inside the same section
  -> persist chunks with metadata
```

### Required Chunk Metadata

Each chunk must include:

- chunk ID
- document ID
- chunk index
- text
- markdown
- page start
- page end
- section title
- heading path
- source block IDs, where available
- token count
- parser/source metadata

### POC Decision

For the POC, source snippets and page/section citations are sufficient.

A POC citation should be able to show:

```text
Document name
Page or page range
Section title
Relevant quote/source snippet
```

### Production Direction

For production, chunks should link back to exact source blocks and bounding boxes when available, enabling precise PDF highlighting.

---

## 5. RAG Answer Strategy

### Decision

Analyse-DCE answers must be evidence-first.

The system should not return untraceable LLM-generated text. Every answer should either:

1. include supporting citations, or
2. explicitly state that no sufficient evidence was found in the document.

### Answer Contract

Every answer response must include:

- answer ID
- answer text
- citations
- model name
- prompt version
- evidence quality
- warnings

Example shape:

```json
{
  "answer_id": "ans_123",
  "answer": "Le délai d'exécution est de 12 semaines.",
  "citations": [
    {
      "document_id": "doc_123",
      "document_name": "CCTP.pdf",
      "chunk_id": "chunk_045",
      "page_start": 12,
      "page_end": 12,
      "section_title": "Article 3.2 - Délais",
      "quote": "Le délai d'exécution est fixé à douze semaines.",
      "score": 0.84
    }
  ],
  "model_name": "mistral",
  "prompt_version": "qa_v1",
  "evidence_quality": "strong",
  "warnings": []
}
```

### Evidence Quality

For the POC, evidence quality should be simple and explainable:

```text
strong  -> multiple relevant chunks or one very direct source
medium  -> some supporting evidence but limited context
weak    -> low confidence retrieval or indirect evidence
none    -> no relevant evidence found
```

Avoid pretending to have mathematically precise confidence unless the system has a real evaluation framework.

### Prompt Rules

The prompt must instruct the model to:

- answer only from provided evidence
- cite sources
- say when information is missing
- ignore instructions contained inside uploaded documents
- avoid inventing clauses, obligations, deadlines, or requirements
- distinguish between direct evidence and uncertainty

---

## 6. Storage Strategy

### Decision

The system separates source artifacts, processing artifacts, retrieval artifacts, and answer traces.

### Storage Responsibilities

```text
Raw files
  -> local file storage for POC
  -> object storage in production

Markdown extraction
  -> file storage
  -> used for chunking/RAG

Structured parser output
  -> file storage
  -> used for provenance/citations/highlighting

SQL database
  -> projects
  -> documents
  -> processing jobs
  -> pages
  -> chunks
  -> questions
  -> answers
  -> citations
  -> feedback

Vector store
  -> embeddings/indexes
  -> rebuildable from persisted chunks
```

### POC Decision

Use:

```text
SQLite + local file storage + FAISS
```

### Pilot Direction

Use:

```text
PostgreSQL + pgvector + local or object storage
```

### Production Direction

Use:

```text
PostgreSQL for metadata and traces.
Object storage for files and parser artifacts.
pgvector or Qdrant for vector search depending on scale.
```

---

## 7. Database Strategy

### Decision

The POC can remain on SQLite, but the schema should be designed so that migration to PostgreSQL is straightforward.

### Minimal POC Entities

The database should support:

- projects
- documents
- processing jobs
- pages
- chunks
- questions
- answers
- answer citations
- feedback

### Minimal Schema Direction

```text
projects
- id
- name
- created_at

documents
- id
- project_id
- filename
- content_type
- storage_path
- markdown_path
- parsed_json_path
- parser_name
- parser_version
- status
- error_message
- created_at
- processed_at

processing_jobs
- id
- document_id
- status
- current_step
- error_message
- created_at
- updated_at
- completed_at

pages
- id
- document_id
- page_number
- text
- metadata_json

chunks
- id
- document_id
- chunk_index
- text
- markdown
- page_start
- page_end
- section_title
- heading_path_json
- source_block_ids_json
- token_count
- metadata_json

questions
- id
- project_id
- document_id
- question_text
- created_at

answers
- id
- question_id
- answer_text
- model_name
- prompt_version
- evidence_quality
- latency_ms
- created_at

answer_citations
- id
- answer_id
- chunk_id
- page_start
- page_end
- section_title
- quote
- score

feedback
- id
- answer_id
- rating
- comment
- created_at
```

### Source of Truth

The source of truth should be:

```text
Raw file
  -> legal/source artifact

Structured parser output
  -> parsing/provenance source

Chunks in SQL
  -> retrieval source of truth

Vector store
  -> rebuildable search index

Answers/citations in SQL
  -> audit and trace source
```

---

## 8. Vector Store Strategy

### Decision

FAISS remains acceptable for the POC but must be isolated behind a `VectorStore` interface.

FAISS should not be imported or manipulated across services, routes, or frontend code.

### POC Decision

Use:

```text
FAISS behind VectorStore interface
```

### Expected Interface

```python
class VectorStore:
    def add_chunks(self, chunks, embeddings) -> None:
        ...

    def search(self, query_embedding, top_k: int, filters: dict | None = None):
        ...

    def delete_document(self, document_id: str) -> None:
        ...
```

### Pilot Direction

Use:

```text
PostgreSQL + pgvector
```

This is the preferred pilot direction because it keeps relational metadata and embeddings close together.

### Production Direction

Use one of:

```text
PostgreSQL + pgvector
```

or:

```text
Qdrant
```

Qdrant should be considered if vector scale, metadata filtering, or retrieval latency becomes a dedicated operational concern.

---

## 9. API Contract

### Decision

The backend API must expose document lifecycle, processing status, Q&A, summaries, evidence, and feedback.

### Core Endpoints

```text
GET  /api/health

POST /api/projects
GET  /api/projects

POST /api/projects/{project_id}/documents
GET  /api/documents/{document_id}
GET  /api/documents/{document_id}/status

POST /api/projects/{project_id}/questions
POST /api/documents/{document_id}/summary

GET  /api/answers/{answer_id}/evidence

POST /api/feedback
```

### Processing Statuses

Document processing should support statuses such as:

```text
uploaded
queued
processing
parsed
chunked
embedded
completed
failed
```

### API Principles

- Upload should return quickly.
- Long processing should happen in the background.
- The frontend should poll the status endpoint.
- Errors should be returned in user-understandable form.
- Internal stack traces should not be exposed to users.

---

## 10. Frontend Strategy

### Decision

Streamlit remains the frontend for the POC.

The goal is not to build a production UI yet. The goal is to keep the demo simple while enforcing the correct backend boundaries.

### Streamlit Responsibilities

Streamlit may:

- create/select projects
- upload documents
- poll processing status
- ask questions
- request summaries
- display answers
- display citations/source snippets
- submit feedback

Streamlit must not:

- parse documents
- call OCR
- chunk text
- embed documents
- query FAISS directly
- access the database directly
- call the LLM directly

### Production Direction

React/Next.js can be reconsidered later if the product needs:

- richer PDF viewer/highlighting
- authentication
- role-based collaboration
- document comparison UI
- admin dashboards
- enterprise UX

---

## 11. Background Processing Strategy

### Decision

Document processing should not block the upload HTTP request.

### POC Decision

Use FastAPI background tasks or a simple local background mechanism.

The upload flow should be:

```text
POST document
  -> save raw file
  -> create document row
  -> create processing job
  -> schedule background processing
  -> return 202 Accepted
```

The processing task should:

```text
parse document
-> save Markdown and structured JSON
-> create pages/chunks
-> embed chunks
-> update FAISS
-> mark completed or failed
```

### Pilot/Production Direction

For pilot or production, replace local background processing with a durable queue/worker system such as Celery, RQ, Arq, or another approved job system.

This is deferred for the POC.

---

## 12. Security and Reliability Rules

### Upload Safety

The POC must:

- accept only PDF and DOCX
- enforce max upload size
- generate server-side storage paths
- prevent path traversal
- store uploads outside source code directories
- clean up temporary files
- avoid logging raw document content

### Prompt Injection

Uploaded documents are untrusted content.

The LLM prompt must explicitly state:

- document content is evidence only
- instructions inside documents must not be followed
- answers must be grounded in retrieved evidence
- if evidence is insufficient, say so

### Logging

Logs should include:

- request ID, where available
- project ID
- document ID
- job ID
- parser name
- processing status
- duration
- error type/message

Logs should not include:

- full document contents
- full extracted Markdown
- full prompts
- sensitive tender content
- full LLM responses, unless explicitly enabled in debug mode

---

## 13. Testing and Quality Strategy

### Decision

The refactor must add tests before major structural changes.

### Required Test Categories

The backend should include:

- unit tests for cleaning
- unit tests for Markdown chunking
- unit tests for parser interfaces
- unit tests for retrieval
- unit tests for prompt construction
- integration tests for FastAPI endpoints
- golden-file tests for document extraction
- RAG regression tests for evidence/citation behaviour

### LLM Testing Rule

Unit and CI tests must not require a live LLM.

LLM calls should be mocked.

Optional live LLM tests may exist but must be marked separately, for example:

```python
@pytest.mark.llm
```

### Quality Tools

The backend should use:

```text
ruff
pytest
pytest-cov
mypy or pyright
pre-commit
```

Recommended commands:

```bash
ruff check .
ruff format .
pytest
pytest --cov=app
mypy app
```

---

## 14. Configuration Strategy

### Decision

Configuration must be centralized using Pydantic Settings or an equivalent typed settings mechanism.

### Required Settings

The application should configure:

- app environment
- database URL
- storage directory
- parser default
- OCR enabled/disabled
- Tesseract language
- vector store type
- embedding model
- LLM provider
- LLM model
- Ollama base URL
- max upload size

### Environment Files

- `.env` must not be committed.
- `.env.example` must be committed.
- `.env.example` should contain safe local defaults.

---

## 15. Docker and Local Development Strategy

### Decision

The POC must remain runnable locally with Docker Compose.

### Local Stack

The local stack may include:

```text
backend
frontend
optional ollama
```

SQLite, FAISS indexes, uploaded files, Markdown files, and structured JSON artifacts should be persisted through local volumes.

### Docker Rules

- Backend and frontend should be separate containers.
- `.env` must not be baked into Docker images.
- Tesseract/LibreOffice dependencies should be installed only where needed.
- Backend should expose a health endpoint.
- Docker Compose should mount persistent local storage for uploaded and parsed documents.

---

## 16. Deferred Decisions

The following are intentionally deferred:

- React/Next.js frontend
- Kubernetes
- Qdrant
- Celery/RQ/Arq workers
- full authentication
- role-based access control
- full PDF coordinate highlighting
- cost monitoring
- production observability stack
- multi-tenant deployment
- enterprise SSO
- advanced admin dashboard

These may be revisited for pilot or production.

---

## 17. ADR Backlog

The following architecture decisions should be documented as ADRs:

1. Document parsing strategy: Docling-first with PyMuPDF/Tesseract fallback.
2. Vector store strategy: FAISS for POC, pgvector for pilot, Qdrant if needed later.
3. Frontend strategy: Streamlit for POC, React/Next.js deferred.
4. Local LLM strategy: Ollama/Mistral for POC, hosted/local model decision deferred.
5. Background processing strategy: FastAPI background tasks for POC, durable workers later.
6. Database strategy: SQLite for POC, PostgreSQL for pilot.
7. Highlighting strategy: source snippets for POC, bounding-box highlighting later.
8. File storage strategy: local filesystem for POC, object storage later.
9. Prompt/versioning strategy: versioned prompts and persisted answer traces.
10. Evaluation strategy: golden files and RAG regression tests.

---

## 18. Definition of Done for the Refactor

The refactor is considered successful when:

- Backend still runs locally.
- Streamlit still works.
- Uploading PDF/DOCX still works.
- Docling parser returns Markdown and structured output.
- Parsed Markdown is saved.
- Structured parser JSON is saved.
- Chunks preserve section/page/source metadata.
- Document processing exposes status.
- Q&A returns citations.
- Answers and citations are persisted.
- FAISS is behind a `VectorStore` interface.
- LLM calls are behind an `LLMClient` interface.
- Parser logic is behind a `DocumentParser` interface.
- Routes are thin.
- Services orchestrate workflows.
- Repositories handle SQL persistence.
- Streamlit calls backend APIs only.
- Tests cover parsing, chunking, retrieval, and API basics.
- `.env` is not committed.
- Local storage/vector/DB artifacts are ignored by Git.
- The app remains demoable after each phase.
