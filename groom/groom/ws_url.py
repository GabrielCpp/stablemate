from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def ws_url(url: str, path: str, query: str = "") -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(f"the groom URL {url!r} must be an http:// or https:// URL")
    return urlunsplit((
        "wss" if parts.scheme == "https" else "ws", parts.netloc,
        parts.path.rstrip("/") + path, query, "",
    ))
