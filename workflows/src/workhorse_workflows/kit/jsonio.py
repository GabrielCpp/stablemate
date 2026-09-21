"""Reading the two JSON dialects a node meets: strict, and the relaxed one VSCode writes."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import json5


def load_jsonc(text: str) -> dict:
    """Parse JSON with Comments (trailing commas, // comments) as used by VSCode."""
    return json5.loads(text)


def load_json(path: Path, label: str, logger: logging.Logger) -> dict:
    """Load a JSON file; logs warnings via caller's logger."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("%s not found at %s", label, path)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("%s unreadable at %s: %s", label, path, exc)
    return {}
