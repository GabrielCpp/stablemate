"""The one guard every file read applies to a path a panel asked for."""

from __future__ import annotations


def safe_relpath(path: str) -> str:
    if not path or path.startswith("/") or path.startswith("\\"):
        raise ValueError(f"unsafe path: {path!r}")
    parts = path.replace("\\", "/").split("/")
    if any(part in ("", "..") for part in parts):
        raise ValueError(f"unsafe path: {path!r}")
    return "/".join(parts)
