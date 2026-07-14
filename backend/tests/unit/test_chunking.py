from preprocessing.chunking import chunk_text


def test_chunk_text_preserves_page_metadata_for_short_page():
    pages = [
        {
            "doc_name": "doc.pdf",
            "page_number": 3,
            "text": "Premiere phrase. Deuxieme phrase? Troisieme phrase!",
        }
    ]

    chunks = chunk_text(pages, max_chars=200)

    assert len(chunks) == 1
    assert chunks[0]["chunk_id"] == 0
    assert chunks[0]["doc_name"] == "doc.pdf"
    assert chunks[0]["page_number"] == 3
    assert chunks[0]["text"] == "Premiere phrase. Deuxieme phrase? Troisieme phrase!"
    assert chunks[0]["raw_text"] == pages[0]["text"]
    assert chunks[0]["start_char"] == 0
    assert chunks[0]["end_char"] == len(chunks[0]["text"])


def test_chunk_text_splits_long_text_into_multiple_chunks():
    pages = [
        {
            "doc_name": "doc.pdf",
            "page_number": 1,
            "text": "Une phrase courte. " + "Mot " * 40 + "Fin.",
        }
    ]

    chunks = chunk_text(pages, max_chars=80)

    assert len(chunks) >= 2
    assert [chunk["chunk_id"] for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk["doc_name"] == "doc.pdf" for chunk in chunks)
    assert all(chunk["page_number"] == 1 for chunk in chunks)
    assert all(chunk["start_char"] <= chunk["end_char"] for chunk in chunks)
