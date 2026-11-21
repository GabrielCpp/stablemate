"""The book's own folder as a diff: which element classes of the book changed since a commit, and which change reaches the whole book.

The diff covers `services/<name>/` and the files it imports under the book root, uncommitted and untracked work
included. Each changed Python file is read with `ast` in its old and new form. A top-level class whose source differs
is a changed class. A changed element class selects its own plays. A changed module-level name, or a changed class that
is no element, selects the element classes that use it, read through the book's own sources, and a changed line that is neither a class nor a name is a shared change that makes the whole book affected."""

from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ostler.book.bookreach import Graph, named, read_source
from ostler.book.change import Reading, change_in, text_at
from ostler.book.files import files as book_files, outside
from ostler.book.service import Service
from ostler.book.sources import actions, git, kinds

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
    unused: list[str] = field(default_factory=list)


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


@dataclass
class Pieces:
    classes: dict[str, str] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    rest: str = ""


def pieces(text: str) -> Pieces | None:
    """The text split into top-level classes, other named definitions and the rest, without imports or the module docstring."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    lines = text.splitlines()
    found = Pieces()
    rest: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)) or (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)):
            continue
        first = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))])
        segment = "\n".join(lines[first - 1:node.end_lineno or node.lineno])
        defined = named(node)
        if isinstance(node, ast.ClassDef):
            found.classes[node.name] = segment
        elif defined is None:
            rest.append(segment)
        else:
            for name in defined:
                found.names[name] = found.names.get(name, "") + segment + "\n"
    found.rest = "\n".join(rest)
    return found


def changed_defs(path: str, old: str | None, new: str | None) -> tuple[list[str], list[str], str | None]:
    """The classes of a file that are new or differ, the module-level names that are new, differ or are gone, and the reason the whole book is affected, if it is."""
    before = pieces(old) if old is not None else Pieces()
    after = pieces(new) if new is not None else Pieces()
    if before is None or after is None:
        return [], [], f"a book file does not parse: {path}"
    if before.rest != after.rest:
        return [], [], f"{SHARED}: {path}"
    classes = sorted(name for name, segment in after.classes.items() if before.classes.get(name) != segment)
    names = sorted(name for name in {*before.names, *after.names} if before.names.get(name) != after.names.get(name))
    return classes, names, None


def trace(root: Path, module: str, found: BookDiff, changes: dict[str, list[str]], known: dict[tuple[str, str], tuple[str, type]], taken: set[tuple[str, str]]) -> None:
    sources = []
    for path in book_files(root, module):
        text = text_at(str(root), None, path) if path.endswith(".py") else None
        source = read_source(path, dotted_of(path), text) if text is not None else None
        if source is not None:
            sources.append(source)
    graph = Graph(sources)
    seen: set[tuple[str, str, str]] = set()
    for path, names in changes.items():
        for name in names:
            label = f"{path}:{name}"
            result = graph.reach(dotted_of(path), name, lambda m, c: (m, c) in known)
            hits = [h for h in result.hits if (h[0], h[1]) not in taken]
            for where, cls, text in hits:
                if (where, cls, text) not in seen:
                    seen.add((where, cls, text))
                    kind, element = known[(where, cls)]
                    found.hits.append(BookHit(path, text, kind, element))
            if result.hits:
                continue
            if result.hidden:
                found.hits.append(BookHit(path, "", "shared", None, f"{label} cannot be traced: {result.hidden}"))
            elif result.used:
                found.hits.append(BookHit(path, "", "shared", None, f"{label} is used only by names that reach no element of the book"))
            else:
                found.unused.append(label)


def book_diff(service: Service[Any], root: Path, module: str, reading: Reading) -> BookDiff:
    found = BookDiff()
    parts = module.split(".")
    if len(parts) < 2 or not (root / "services" / parts[1]).is_dir():
        return found
    where = str(root)
    specs = ["/".join(parts[:2]), *outside(root, module)]
    try:
        if reading.story:
            change = change_in(where, reading, specs)
            if not change.commits:
                found.notes.append(f"the book folder holds no commit of story {reading.story}: only its uncommitted work is read")
        else:
            try:
                resolved = git(where, "rev-parse", "--verify", "--quiet", f"{reading.base}^{{commit}}").strip()
            except subprocess.CalledProcessError:
                resolved = "HEAD"
                found.notes.append(f"the book folder is judged from its own HEAD: {reading.base} is not a commit there")
            change = change_in(where, Reading(base=resolved), specs)
        known = index_of(service)
        changes: dict[str, list[str]] = {}
        taken: set[tuple[str, str]] = set()
        for path in sorted({*change.spans, *change.untracked}):
            found.files.append(path)
            if not path.endswith(".py"):
                found.unjudged.append(path)
                continue
            span = change.spans.get(path)
            old = text_at(where, span.old, path) if span else None
            names, moved, why = changed_defs(path, old, text_at(where, span.new if span else None, path))
            if why is not None:
                found.hits.append(BookHit(path, "", "shared", None, why))
            loose: list[str] = []
            for name in names:
                match = known.get((dotted_of(path), name))
                if match is None:
                    loose.append(name)
                else:
                    taken.add((dotted_of(path), name))
                    found.hits.append(BookHit(path, name, match[0], match[1]))
            if moved or loose:
                changes[path] = [*moved, *loose]
        if changes:
            trace(root, module, found, changes, known, taken)
    except subprocess.CalledProcessError as wrong:
        found.notes.append(f"the book folder could not be diffed: {(wrong.stderr or '').strip()}")
    return found
