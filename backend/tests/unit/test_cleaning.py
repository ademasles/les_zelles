from preprocessing.cleaning import clean_pages, clean_text


def test_clean_text_normalizes_spacing_and_punctuation():
    text = "  Bonjour\u00a0monde!\r\nLigne 2  avec  espaces.\n\n• Point “test”  "

    cleaned = clean_text(text)

    assert cleaned == 'Bonjour monde! Ligne 2 avec espaces. - Point "test"'


def test_clean_text_returns_empty_string_for_non_text():
    assert clean_text("") == ""
    assert clean_text(None) == ""


def test_clean_pages_mutates_page_text_in_place():
    pages = [
        {"doc_name": "doc.pdf", "page_number": 1, "text": "Texte\u00a0brut."},
        {"doc_name": "doc.pdf", "page_number": 2, "text": "Deuxieme  ligne."},
    ]

    result = clean_pages(pages)

    assert result is pages
    assert pages[0]["text"] == "Texte brut."
    assert pages[1]["text"] == "Deuxieme ligne."
