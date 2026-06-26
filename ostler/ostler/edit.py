"""`ostler edit` — safe, format-preserving structured edits across JSON and Markdown.

All operations are **dry-run by default**: they compute the changes and print a unified diff but
write nothing. Pass ``write=True`` to apply.

    set-owner <gap> <story>   point a knowledge gap at its owning story
    relink <old> <new>        replace a path reference everywhere it appears
    rename <old> <new>        rename a story/epic slug and cascade every reference (+ folder move)
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import markdown
from .model import Graph


@dataclass
class FileChange:
    path: Path
    old: str
    new: str

    def diff(self) -> str:
        rel = self.path.as_posix()
        return "".join(difflib.unified_diff(
            self.old.splitlines(keepends=True),
            self.new.splitlines(keepends=True),
            fromfile=f"a/{rel}", tofile=f"b/{rel}",
        ))


@dataclass
class EditPlan:
    changes: list[FileChange]
    moves: list[tuple[Path, Path]]  # (src dir, dst dir)
    error: str = ""

    def render(self) -> str:
        if self.error:
            return f"error: {self.error}"
        if not self.changes and not self.moves:
            return "no changes"
        parts = [c.diff() for c in self.changes]
        for src, dst in self.moves:
            parts.append(f"rename {src.as_posix()} -> {dst.as_posix()}\n")
        return "".join(parts)

    def apply(self) -> None:
        for c in self.changes:
            c.path.write_text(c.new, encoding="utf-8")
        for src, dst in self.moves:
            if src.exists():
                src.rename(dst)


def _doc_files(graph: Graph) -> list[Path]:
    files: list[Path] = []
    for key in ("epics", "knowledge", "specs"):
        root = graph.doc_roots[key]
        if root.is_dir():
            files.extend(p for p in root.rglob("*")
                         if p.is_file() and p.suffix in (".json", ".md"))
    return sorted(set(files))


# ---------------------------------------------------------------------------
def _set_json_owner(raw: str, gap_id: str, owner: str) -> str | None:
    """Targeted, format-preserving edit: set the `owner` of the gap whose id is *gap_id*.

    Edits only that gap's `owner` value (or inserts one right after its `id`) so the rest of the
    file — including predykt's inline-compact object style — is untouched.
    """
    id_match = re.search(r'"id"\s*:\s*"' + re.escape(gap_id) + r'"', raw)
    if not id_match:
        return None
    nxt = re.search(r'"id"\s*:\s*"', raw[id_match.end():])
    end = id_match.end() + nxt.start() if nxt else len(raw)
    region = raw[id_match.end():end]

    om = re.search(r'("owner"\s*:\s*")[^"]*(")', region)
    if om:
        new_region = region[:om.start()] + om.group(1) + owner + om.group(2) + region[om.end():]
        return raw[:id_match.end()] + new_region + raw[end:]
    # No owner key in this gap — insert one immediately after the id value.
    return raw[:id_match.end()] + f', "owner": "{owner}"' + raw[id_match.end():]


def set_owner(graph: Graph, gap_id: str, story_slug: str) -> EditPlan:
    hit = graph.find_gap(gap_id)
    if not hit:
        return EditPlan([], [], error=f"no gap '{gap_id}' found")
    record, _ = hit
    raw = record.path.read_text(encoding="utf-8")

    if record.fmt == "json":
        new = _set_json_owner(raw, gap_id, story_slug)
        if new is None:
            return EditPlan([], [], error=f"gap '{gap_id}' not found in {record.path.name}")
    else:
        doc = markdown.split(raw)
        fm = doc.frontmatter or {}
        for g in fm.get("gaps", []):
            if isinstance(g, dict) and g.get("id") == gap_id:
                g["owner"] = story_slug
        doc.raw_frontmatter = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
        new = doc.render()

    if new == raw:
        return EditPlan([], [])
    return EditPlan([FileChange(record.path, raw, new)], [])


def _replace_token(text: str, old: str, new: str) -> str:
    """Replace whole-token occurrences of *old* (slug/path), respecting word/path boundaries."""
    pattern = re.compile(rf"(?<![\w/-]){re.escape(old)}(?![\w/-])")
    return pattern.sub(new, text)


def relink(graph: Graph, old_path: str, new_path: str) -> EditPlan:
    changes = []
    for path in _doc_files(graph):
        raw = path.read_text(encoding="utf-8")
        if old_path not in raw:
            continue
        new = raw.replace(old_path, new_path)
        if new != raw:
            changes.append(FileChange(path, raw, new))
    return EditPlan(changes, [])


def rename(graph: Graph, old_slug: str, new_slug: str) -> EditPlan:
    changes = []
    for path in _doc_files(graph):
        raw = path.read_text(encoding="utf-8")
        new = _replace_token(raw, old_slug, new_slug)
        if new != raw:
            changes.append(FileChange(path, raw, new))

    moves: list[tuple[Path, Path]] = []
    for epic in graph.epics:
        src = epic.directory / "stories" / old_slug
        if src.is_dir():
            moves.append((src, epic.directory / "stories" / new_slug))

    if not changes and not moves:
        return EditPlan([], [], error=f"slug '{old_slug}' not found")
    return EditPlan(changes, moves)
