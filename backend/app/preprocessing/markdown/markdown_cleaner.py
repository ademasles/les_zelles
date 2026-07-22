"""Clean and normalize Markdown before chunking."""

from __future__ import annotations

import re


def clean_markdown(md: str) -> str:
    md = re.sub(r"[ \t]+$", "", md, flags=re.MULTILINE)
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = md.strip()
    return md
