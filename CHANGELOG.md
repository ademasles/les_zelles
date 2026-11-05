# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.2.0] - unreleased

Complete rewrite as an installable Python package (`zelles`). The project is now proprietary (source public, all rights reserved).

### Added
- Ingestion of PDF, DOCX, TXT and Markdown with line bounding boxes, Tesseract OCR fallback and CCTP outline detection (lots, articles).
- Hybrid retrieval: French BM25 with optional dense embeddings and RRF fusion.
- Provider-agnostic LLM layer: Ollama, llama.cpp, vLLM, LM Studio, Anthropic, OpenAI, Mistral, Gemini, OpenRouter, with structured outputs and cost tracking.
- Spec sheet extraction for 25 joinery fields: rules, LLM per field group, quote verification and domain validators.
- Knowledge graph with standards ontology, cross-references and conflict detection; JSON and Cypher exports.
- Product compliance check and clarification questions for the project owner.
- Agent tool registry shared by an agent loop, the HTTP API and an MCP server.
- FastAPI service with background jobs and SSE progress, SQLAlchemy and Alembic storage, web UI, typer CLI.
- Golden-set evaluation harness, CI, Docker image and compose file.

### Changed
- Rules cover more real CCTP wordings (dotted AFNOR standards, SWC / TL global, facade dB apart from box and inlet ratings, plaxé and laqué finishes, "type X ou équivalent" routed by subject) and no longer emit free-text catch-alls for air inlets, caulking or profiles.
- The evaluation matcher treats separator, dotted-abbreviation and ordinal variants as equal ("NF P 20-501" = "20.501", "D.T.U. n°39" = "DTU 39", "1er" = "1").

### Removed
- The previous FastAPI backend and Streamlit frontend, with their torch, sentence-transformers, FAISS and PyMuPDF (AGPL) dependencies.
