"""Pure name/id transforms — kebab-casing, source ids, path references, quoting.

Stateless string helpers with no knowledge of the ``Source`` record or the layer
stack, so every other module can depend on them without a cycle.
"""
from __future__ import annotations

import os
import re
from pathlib import Path


def kebab(value: str) -> str:
    value = value.removesuffix(".prompt").removesuffix(".instructions")
    value = value.replace(".", "-").replace("_", "-")
    value = re.sub(r"[^a-zA-Z0-9/-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-").lower()
    return value


def normalize_pattern(pattern: str) -> str:
    """Normalize a user-facing glob without destroying glob characters."""
    return (
        pattern.removesuffix(".md")
        .removesuffix(".prompt")
        .removesuffix(".instructions")
        .replace(".", "-")
        .replace("_", "-")
        .lower()
    )


def strip_known_suffix(path: Path) -> str:
    name = path.name
    if name.endswith(".prompt.md"):
        return name.removesuffix(".prompt.md")
    if name.endswith(".instructions.md"):
        return name.removesuffix(".instructions.md")
    return path.stem


def source_id(root: Path, path: Path) -> str:
    rel = path.relative_to(root)
    # For SKILL.md files in directories, use the parent directory name as the skill name.
    # For any other .md files, use the old flat-file logic for backwards compatibility.
    if rel.name == "SKILL.md":
        parts = [kebab(part) for part in rel.parent.parts]
    else:
        parts = [kebab(part) for part in rel.with_name(strip_known_suffix(rel)).parts]
    return "/".join(parts)


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def relative_reference(from_file: Path, to_file: Path) -> str:
    return os.path.relpath(to_file, from_file.parent).replace(os.sep, "/")
