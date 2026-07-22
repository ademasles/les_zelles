# ADR-002: Document Parsing Strategy

**Status:** Accepted  
**Date:** 2026-07-22  
**Deciders:** Architecture team  
**Tags:** parsing, OCR, docling, preprocessing  

---

## Context

Analyse-DCE must extract structured content from PDF and DOCX tender documents (CCTP). The parsed output feeds into section-aware chunking and RAG.

Documents vary widely: born-digital PDFs, scanned images, mixed-content DOCX files, complex tables, multi-level headings.

## Decision

**Docling-first** with deterministic fallback chain: `Docling → PyMuPDF → Tesseract`.

### Parser Interface

All parsers implement the `DocumentParser` ABC defined in `app/preprocessing/parsers/base.py`:

```python
class DocumentParser(ABC):
    @abstractmethod
    def parse(self, file_path: Path) -> ParsedDocument: ...
```

### Fallback Chain (defined in `app/preprocessing/parsers/registry.py`)

| Order | Parser | Suitable for |
|---|---|---|
| 1 | DoclingParser | PDF/DOCX with complex structure: headings, tables, lists, reading order |
| 2 | PyMuPDFParser | Born-digital PDFs where Docling fails |
| 3 | TesseractParser | Scanned PDFs (OCR at 300 DPI) |

The fallback is orchestrated in `app/preprocessing/parsers/fallback.py`. Each failure is logged; the winning parser and fallback history are recorded in `parsing_stats`.

## Consequences

- Docling Markdown provides clean, structured input for section-aware chunking
- Structured JSON from Docling is preserved for provenance and future highlighting
- The parser interface isolates routes/services from parser implementation details
- Fallback ensures no document is left unparsed
- Parsing stats capture duration, fallback, and errors for observability

## Risks

- Docling is a relatively new library; API changes may require pinning
- OCR (Tesseract) is slow on long scanned documents
- DOCX parsing via Docling may have different quality than PDF parsing
- No parser currently handles password-protected or encrypted documents

---

## Related Documents

- `REFACTOR_DECISIONS.md` §3 Parsing Strategy
- `backend/app/preprocessing/parsers/base.py` — Interface definition
- `backend/app/preprocessing/parsers/fallback.py` — Fallback orchestration
- `backend/app/preprocessing/parsers/registry.py` — Parser selection
- `backend/app/preprocessing/markdown/section_splitter.py` — Downstream chunk consumer
