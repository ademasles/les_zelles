# chunking.py
"""Chunking module for text segmentation based on sentence boundaries.
This module provides functionality to chunk text into manageable segments
while preserving context and structure.
"""
# SPDX-FileCopyrightText: 2025 Anton Demasles <

#-----------------------------------------------------------------------------------------------
# IMPORTS
#-----------------------------------------------------------------------------------------------
import re

#-----------------------------------------------------------------------------------------------
# FUNCTIONS
#-----------------------------------------------------------------------------------------------
import re

MAX_CHARS = 3000

def chunk_text(pages, max_chars=MAX_CHARS):
    """
    Chunk text into segments based on sentence boundaries.
    :param pages: List of dictionaries with 'text', 'doc_name', and 'page_number'.
    :param max_chars: Maximum number of characters per chunk.
    :return: List of dictionaries with 'text', 'doc_name', 'page_number', 'start_char', 'end_char', 'raw_text'.
    """
    all_chunks = []
    chunk_counter = 0  # ID unique par chunk
    for page_data in pages:
        text = page_data.get("text", "")
        doc_name = page_data.get("doc_name", "unknown")
        page_number = page_data.get("page_number", None)

        # Découpe par phrases
        sentences = re.split(r'(?<=[.?!])\s+', text)
        
        chunk_text = ""
        start_char = 0
        chunk_start_offset = 0

        for sentence in sentences:
            if len(chunk_text) + len(sentence) < max_chars:
                if not chunk_text:
                    chunk_start_offset = text.find(sentence, start_char)
                chunk_text += sentence + " "
            else:
                chunk_end_offset = chunk_start_offset + len(chunk_text.strip())
                all_chunks.append({
                    "chunk_id": chunk_counter,
                    "text": chunk_text.strip(),
                    "doc_name": doc_name,
                    "page_number": page_number,
                    "start_char": chunk_start_offset,
                    "end_char": chunk_end_offset,
                    "raw_text": text
                })
                # Nouveau chunk
                chunk_counter += 1
                start_char = chunk_end_offset
                chunk_text = sentence + " "
                chunk_start_offset = text.find(sentence, start_char)

        # Dernier chunk de la page
        if chunk_text.strip():
            chunk_end_offset = chunk_start_offset + len(chunk_text.strip())
            all_chunks.append({
                "chunk_id": chunk_counter,
                "text": chunk_text.strip(),
                "doc_name": doc_name,
                "page_number": page_number,
                "start_char": chunk_start_offset,
                "end_char": chunk_end_offset,
                "raw_text": text
            })
            chunk_counter += 1

    return all_chunks
