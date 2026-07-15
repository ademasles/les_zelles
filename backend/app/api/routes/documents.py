import os
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from nlp.qa import answer_queries
from nlp.summarization import summarize_cctp
from preprocessing.chunking import chunk_text
from preprocessing.cleaning import clean_pages
from preprocessing.extraction import extract_text_from_file
from preprocessing.loading import load_queries
from utils.highlight import highlight_chunk

router = APIRouter(tags=["documents"])

# In-memory stores shared across document routes
documents: dict = {}
query_results_store: dict = {}


# TODO: move orchestration into DocumentService in T2
@router.post("/upload/")
async def upload_file(file: UploadFile = File(...), doc_id: str = Form(...)):
    contents = await file.read()
    temp_path = Path("temp_file") / file.filename
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.write_bytes(contents)

    raw_text = extract_text_from_file(str(temp_path))
    cleaned_text = clean_pages(raw_text)
    chunks = chunk_text(cleaned_text)
    summary_text = summarize_cctp(chunks)

    documents[doc_id] = chunks
    os.remove(temp_path)

    return JSONResponse(
        content=jsonable_encoder(
            {
                "doc_id": doc_id,
                "filename": file.filename,
                "summary": summary_text,
                "num_chunks": len(chunks),
                "status": "indexed",
                "query": f"Document {doc_id} indexé avec succès.",
            }
        )
    )


# TODO: move orchestration into RAGService in T3
@router.post("/query/")
async def query(doc_id: str = Form(...), question: str = Form(...)):
    if doc_id not in documents:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = documents[doc_id]
    answer, top_chunks = answer_queries(chunks, question)

    query_results_store[(doc_id, question)] = {"chunks": top_chunks, "answer": answer}

    return JSONResponse(
        content=jsonable_encoder(
            {
                "doc_id": doc_id,
                "query": question,
                "answer": answer,
                "top_chunks": top_chunks,
            }
        )
    )


# TODO: move orchestration into RAGService in T3
@router.post("/queries/")
async def run_queries(doc_id: str = Form(...)):
    if doc_id not in documents:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = documents[doc_id]
    queries = load_queries("data/queries.csv")
    results = answer_queries(chunks, queries)

    query_results_store[doc_id] = {"results": results}

    return JSONResponse(
        content=jsonable_encoder(
            {
                "doc_id": doc_id,
                "num_questions": len(queries),
                "results": results,
                "status": "completed",
                "query": f"Analyse du document {doc_id} terminée.",
            }
        )
    )


# TODO: move orchestration into DocumentService in T2
@router.get("/summary/")
async def summary(doc_id: str):
    if doc_id not in documents:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = documents[doc_id]
    summary_text = summarize_cctp(chunks)

    return JSONResponse(
        content=jsonable_encoder(
            {
                "doc_id": doc_id,
                "summary": summary_text,
                "status": "completed",
                "query": f"Résumé du document {doc_id} généré.",
            }
        )
    )


@router.get("/highlight/")
def highlight(doc_id: str, chunk_id: int):
    return highlight_chunk(doc_id, chunk_id, documents)
