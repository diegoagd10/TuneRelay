"""Typed read access to untyped JSON/TOML documents.

This is the only module allowed to hold `Any` (see `tests/test_typing_rules.py`):
parsed documents are untyped at the boundary, and every getter here returns one
concrete type or `None` so the rest of the code never sees `Any`.
"""

import json
from typing import Any


class JsonObject:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @classmethod
    def parse(cls, text: str) -> "JsonObject":
        """Parse a JSON document whose top level must be an object; raises ValueError otherwise."""
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("expected a JSON object")  # noqa: TRY004 - malformed input, not a type bug
        return cls(value)  # pyright: ignore[reportUnknownArgumentType]

    @classmethod
    def parse_list(cls, text: str) -> list["JsonObject"]:
        """Parse a JSON array, keeping only its object items; raises ValueError if it is not an array."""
        value = json.loads(text)
        if not isinstance(value, list):
            raise ValueError("expected a JSON array")  # noqa: TRY004 - malformed input, not a type bug
        return [cls(item) for item in value if isinstance(item, dict)]  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]

    def text(self, key: str) -> str | None:
        value = self._data.get(key)
        return value if isinstance(value, str) else None

    def integer(self, key: str) -> int | None:
        value = self._data.get(key)
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value)
        return None

    def number(self, key: str) -> float | None:
        value = self._data.get(key)
        if isinstance(value, bool):
            return None
        return float(value) if isinstance(value, int | float) else None

    def flag(self, key: str) -> bool | None:
        value = self._data.get(key)
        return value if isinstance(value, bool) else None

    def obj(self, key: str) -> "JsonObject | None":
        value = self._data.get(key)
        return JsonObject(value) if isinstance(value, dict) else None  # pyright: ignore[reportUnknownArgumentType]

    def objects(self, key: str) -> list["JsonObject"]:
        value = self._data.get(key)
        if not isinstance(value, list):
            return []
        return [JsonObject(item) for item in value if isinstance(item, dict)]  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]

    def texts(self, key: str) -> list[str]:
        value = self._data.get(key)
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str)]  # pyright: ignore[reportUnknownVariableType]

    def text_map(self, key: str) -> dict[str, str]:
        value = self._data.get(key)
        if not isinstance(value, dict):
            return {}
        return {k: v for k, v in value.items() if isinstance(k, str) and isinstance(v, str)}  # pyright: ignore[reportUnknownVariableType]
