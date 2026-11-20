"""The book's own folder as a diff: which element classes of the book changed since a commit, and which change reaches the whole book.

The diff covers `services/<name>/` and the files it imports under the book root, uncommitted and untracked work
included. Each changed Python file is read with `ast` in its old and new form. A top-level class whose source differs
is a changed class, and a changed line outside every class is a shared change that makes the whole book affected."""

from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ostler.book.files import outside
from ostler.book.service import Service
from ostler.book.sources import actions, changed_in_tree, git, kinds

SHARED = "a shared book file changed"


@dataclass
class BookHit:
    path: str
    name: str
    kind: str
    element: type | None
    why: str = ""


@dataclass
class BookDiff:
    files: list[str] = field(default_factory=list)
    unjudged: list[str] = field(default_factory=list)
    hits: list[BookHit] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def dotted_of(path: str) -> str:
    parts = path.removesuffix(".py").split("/")
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def index_of(service: Service[Any]) -> dict[tuple[str, str], tuple[str, type]]:
    found: list[tuple[str, type]] = [
        *kinds(service),
        *(("action", e) for e in actions(service)),
        *(("outside", e) for e in service.outside),
        *(("event", e) for e in service.events),
        *(("journey", e) for e in service.journeys),
    ]
    return {(element.__module__, element.__name__): (kind, element) for kind, element in reversed(found)}


def pieces(text: str, bare: bool) -> tuple[dict[str, str], str] | None:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    lines = text.splitlines()
    classes: dict[str, str] = {}
    rest: list[str] = []
    for node in tree.body:
        if bare and (isinstance(node, (ast.Import, ast.ImportFrom)) or (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))):
            continue
        first = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))])
        segment = "\n".join(lines[first - 1:node.end_lineno or node.lineno])
        if isinstance(node, ast.ClassDef):
            classes[node.name] = segment
        else:
            rest.append(segment)
    return classes, "\n".join(rest)


def changed_classes(path: str, old: str | None, new: str | None) -> tuple[list[str], str | None]:
    """The names of the classes of a file that are new or differ, and the reason the whole book is affected, if it is."""
    bare = old is None or new is None
    before = pieces(old, bare) if old is not None else ({}, "")
    after = pieces(new, bare) if new is not None else ({}, "")
    if before is None or after is None:
        return [], f"a book file does not parse: {path}"
    if before[1] != after[1]:
        return [], f"{SHARED}: {path}"
    return sorted(name for name, segment in after[0].items() if before[0].get(name) != segment), None


def read_old(root: str, base: str, path: str) -> str | None:
    try:
        return git(root, "show", f"{base}:./{path}")
    except subprocess.CalledProcessError:
        return None


def read_new(root: str, path: str) -> str | None:
    try:
        return (Path(root) / path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def book_diff(service: Service[Any], root: Path, module: str, base: str) -> BookDiff:
    found = BookDiff()
    parts = module.split(".")
    if len(parts) < 2 or not (root / "services" / parts[1]).is_dir():
        return found
    where = str(root)
    specs = ["/".join(parts[:2]), *outside(root, module)]
    try:
        try:
            resolved = git(where, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").strip()
        except subprocess.CalledProcessError:
            resolved = "HEAD"
            found.notes.append(f"the book folder is judged from its own HEAD: {base} is not a commit there")
        tracked, untracked = changed_in_tree(where, resolved, tuple(specs))
        known = index_of(service)
        for path in sorted({*tracked, *untracked}):
            found.files.append(path)
            if not path.endswith(".py"):
                found.unjudged.append(path)
                continue
            names, why = changed_classes(path, read_old(where, resolved, path), read_new(where, path))
            if why is not None:
                found.hits.append(BookHit(path, "", "shared", None, why))
            for name in names:
                match = known.get((dotted_of(path), name))
                if match is None:
                    found.hits.append(BookHit(path, name, "shared", None, f"{SHARED}: {path}"))
                else:
                    found.hits.append(BookHit(path, name, match[0], match[1]))
    except subprocess.CalledProcessError as wrong:
        found.notes.append(f"the book folder could not be diffed: {(wrong.stderr or '').strip()}")
    return found
