from __future__ import annotations
from typing import Any

_MISSING = object()


class WorkflowContext:
    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(initial or {})

    def merge(self, data: dict[str, Any]) -> None:
        self._data.update(data)

    def get_dotpath(self, path: str, default: Any = _MISSING) -> Any:
        """Resolve a dot-separated path like 'analysis.status' into the context.

        Raises ``KeyError`` when a segment is missing or would traverse a non-dict
        value — unless ``default`` is supplied, in which case that default is
        returned for any unresolvable path (so callers can guard without try/except)."""
        parts = path.split(".")
        value = self._data
        for part in parts:
            if not isinstance(value, dict) or part not in value:
                if default is not _MISSING:
                    return default
                if not isinstance(value, dict):
                    raise KeyError(f"Cannot traverse '{part}' in non-dict value at path '{path}'")
                raise KeyError(f"Key '{part}' not found (path: '{path}')")
            value = value[part]
        return value

    def has_dotpath(self, path: str) -> bool:
        """True iff ``path`` resolves to a value (used to guard branch lookups)."""
        sentinel = object()
        return self.get_dotpath(path, default=sentinel) is not sentinel

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def __repr__(self) -> str:
        return f"WorkflowContext({self._data!r})"
