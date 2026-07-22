"""Golden-file tests for parser interface and data models.

These tests verify the parser interface contract works correctly.
No live parser execution is required — they test data construction and import.
"""

from __future__ import annotations

from pathlib import Path

from app.preprocessing.parsers.base import (
    DocumentParser,
    ParsedBlock,
    ParsedDocument,
    ParsedPage,
    ParsedTable,
)


def test_parsed_document_defaults() -> None:
    doc = ParsedDocument(
        source_path=Path("/tmp/test.pdf"),
        parser_name="test_parser",
        parser_version="1.0",
        markdown="# Test",
        structured_data={"key": "value"},
    )
    assert doc.parser_name == "test_parser"
    assert doc.markdown == "# Test"
    assert doc.pages == []
    assert doc.blocks == []
    assert doc.tables == []


def test_parsed_page_with_blocks() -> None:
    block = ParsedBlock(
        id="b1",
        text="Some text",
        block_type="paragraph",
        page_number=1,
        heading_path=["Section 1"],
    )
    page = ParsedPage(
        page_number=1,
        text="Page text",
        blocks=[block],
    )
    assert page.page_number == 1
    assert page.blocks[0].heading_path == ["Section 1"]


def test_parsed_table_defaults() -> None:
    table = ParsedTable(
        id="t1",
        markdown="| A | B |\n| --- | --- |\n| 1 | 2 |",
    )
    assert table.page_number is None
    assert table.bbox is None


def test_document_parser_is_abstract() -> None:
    class TestParser(DocumentParser):
        def parse(self, file_path: Path) -> ParsedDocument:
            return ParsedDocument(
                source_path=file_path,
                parser_name="test",
                parser_version="1.0",
                markdown="",
                structured_data={},
            )

    parser = TestParser()
    result = parser.parse(Path("/tmp/doc.pdf"))
    assert result.parser_name == "test"
