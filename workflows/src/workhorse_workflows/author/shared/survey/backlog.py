"""The generated, marker-fenced section a survey writes into the backlog."""
from __future__ import annotations

from pathlib import Path


def write_section(path: Path, bullets: list[str], *, begin: str, end: str, heading: str) -> None:
    """Replace the fenced section in the backlog at `path`, or append one under `heading`."""
    section = "\n".join([begin, *bullets, end])
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    first, last = text.find(begin), text.find(end)
    if first != -1 and last > first:
        text = text[:first] + section + text[last + len(end) :]
    else:
        prefix = text.rstrip() + "\n\n" if text.strip() else "# Backlog\n\n"
        text = f"{prefix}{heading}\n\n{section}\n"
    path.write_text(text, encoding="utf-8")


__all__ = ["write_section"]
