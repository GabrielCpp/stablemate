"""Reading the two JSON dialects a node meets: strict, and the relaxed one VSCode writes.

Both live here rather than in the engine because they are read by *nodes*, not by the
driver — the driver's own checkpoint I/O is strict `json` and needs neither. Keeping the
pair together is also what confines ``json5`` to this distribution.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import json5


def load_jsonc(text: str) -> dict:
    """Parse JSON with Comments (trailing commas, // comments) as used by VSCode.

    A real JSON5 parse, not a strip-then-`json.loads`. The stripping version deleted from
    `//` to end of line without knowing what a string literal is, so any workspace file
    holding a URL — `{"url": "https://example.com"}` — was truncated mid-string and then
    reported as invalid JSON. `.code-workspace` files routinely hold URLs and `//` paths.
    """
    return json5.loads(text)


def load_json(path: Path, label: str, logger: logging.Logger) -> dict:
    """Load a JSON file; logs warnings via caller's logger. Returns {} on failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("%s not found at %s", label, path)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("%s unreadable at %s: %s", label, path, exc)
    return {}
