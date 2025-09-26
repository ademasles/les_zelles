# highlight.py
"""Highlight module for processing text chunks and generating highlighted PDF responses.
This module provides functions to highlight specific text chunks in a PDF document and return the modified document.
"""
# SPDX-FileCopyrightText: 2025 Anton Demasles <

#-----------------------------------------------------------------------------------------------
# IMPORTS
#-----------------------------------------------------------------------------------------------
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
import os
import fitz
from io import BytesIO
from docx2pdf import convert

#-----------------------------------------------------------------------------------------------

def highlight_chunk(doc_id: str, chunk_id: int, documents: dict) -> StreamingResponse:
    """
    Highlight a specific text chunk in a PDF document and return the modified document.
    :param doc_id: The ID of the document containing the chunk.
    :param chunk_id: The ID of the chunk to highlight.
    :param documents: Dictionary containing document data with chunks.
    :return: StreamingResponse with the modified PDF document.
    """
    folder = f"data/{doc_id}"
    input_path_pdf = os.path.join(folder, "original.pdf")
    input_path_docx = os.path.join(folder, "original.docx")

    if doc_id not in documents:
        raise HTTPException(status_code=404, detail="Document non trouvé en mémoire")

    chunks = documents[doc_id]
    try:
        chunk = next(c for c in chunks if c.get("chunk_id") == chunk_id)
    except StopIteration:
        raise HTTPException(status_code=404, detail="Chunk ID non trouvé")

    highlight_text = chunk.get("chunk_text", "").strip()
    page = chunk.get("page_number")

    # Convert DOCX if needed
    if not os.path.exists(input_path_pdf) and os.path.exists(input_path_docx):
        tmp_pdf_path = os.path.join(folder, "converted.pdf")
        convert(input_path_docx, tmp_pdf_path)
        input_path_pdf = tmp_pdf_path

    if not os.path.exists(input_path_pdf):
        raise HTTPException(status_code=404, detail="Aucun PDF/DOCX disponible")

    doc = fitz.open(input_path_pdf)
    try:
        text_page = doc[page - 1]
    except IndexError:
        raise HTTPException(status_code=400, detail="Page invalide")

    matches = text_page.search_for(highlight_text)
    if not matches:
        rect = fitz.Rect(50, 100, 500, 150)
        text_page.insert_textbox(rect, highlight_text, color=(1, 0, 0))
        text_page.draw_rect(rect, color=(1, 1, 0), fill=(1, 1, 0, 0.3))
    else:
        for rect in matches:
            text_page.add_highlight_annot(rect)

    output_pdf = BytesIO()
    doc.save(output_pdf)
    output_pdf.seek(0)

    return StreamingResponse(output_pdf, media_type="application/pdf")
