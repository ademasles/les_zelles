"""SQLite-compatible JSON column backed by Text."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Text, TypeDecorator


class JSONText(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any | None, dialect) -> str | None:
        if value is not None:
            return json.dumps(value, ensure_ascii=False)
        return None

    def process_result_value(self, value: str | None, dialect) -> Any | None:
        if value is not None:
            return json.loads(value)
        return None
