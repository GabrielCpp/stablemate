from __future__ import annotations

from urllib.parse import quote, urlencode


def route(prefix: str, container: str, **query: str) -> str:
    path = f"{prefix}/{quote(container, safe='')}"
    if not query:
        return path
    return f"{path}?{urlencode(query, quote_via=quote)}"
