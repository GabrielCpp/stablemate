"""The book searched without running it: `index` writes what `search` finds in one service to
`index.tsv` beside it, and `search` reads those files and the decisions as text."""

from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ostler._vendor.stablemate_core import books
from ostler.book import decisions, pages
from ostler.book.search import Item, items, loose_hits, phrase_hits

FILE = "index.tsv"


@dataclass(frozen=True)
class Entry:
    kind: str
    name: str
    address: str
    lines: tuple[str, ...]
    reach: str = ""


def escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", " ").replace("\r", " ")


def unescape(text: str) -> list[str]:
    lines: list[str] = []
    current: list[str] = []
    chars = iter(text)
    for char in chars:
        if char != "\\":
            current.append(char)
            continue
        following = next(chars, "")
        if following == "n":
            lines.append("".join(current))
            current = []
        else:
            current.append(following)
    lines.append("".join(current))
    return lines


def render(found: list[Item]) -> str:
    rows = ["\t".join((i.kind, escape(i.name), escape(i.address), escape("\n".join(i.lines)), *((escape(i.reach),) if i.reach else ()))) for i in found]
    return "".join(row + "\n" for row in rows)


def parse(text: str) -> list[Entry]:
    out: list[Entry] = []
    for row in text.splitlines():
        kind, name, address, body, *rest = row.split("\t", 4)
        out.append(Entry(kind, name, address, tuple(unescape(body)), rest[0] if rest else ""))
    return out


def package_dir(module: str) -> str:
    return os.path.dirname(importlib.import_module(module).__file__ or "")


def build(service: Any, module: str) -> str:
    return render(items(service, module))


def write(service: Any, module: str) -> tuple[str, bool]:
    path = os.path.join(package_dir(module), FILE)
    text = build(service, module)
    before = None
    if os.path.exists(path):
        with open(path) as f:
            before = f.read()
    with open(path, "w") as f:
        f.write(text)
    return path, before != text


def newest(directory: str) -> float:
    latest = 0.0
    for here, names, files in os.walk(directory):
        names[:] = [n for n in names if n != "__pycache__"]
        for name in files:
            if name.endswith((".py", ".md")):
                latest = max(latest, os.path.getmtime(os.path.join(here, name)))
    return latest


def stale(directory: str) -> bool:
    path = os.path.join(directory, FILE)
    return not os.path.exists(path) or os.path.getmtime(path) < newest(directory)


def book_root(start: str) -> str:
    return str(books.book_home(Path(start)))


def read_levels(root: str) -> dict[str, list[Entry]]:
    found: dict[str, list[Entry]] = {}
    for level in pages.levels(root):
        entries = [Entry(level.kind, page.slug, f"{page.path}:{number}" + (" (superseded)" if page.superseded() else ""), (text,))
                   for page in pages.load(level) for number, text in page.searchable()]
        if entries:
            found[level.heading] = entries
    return found


def read_decisions(directory: str) -> list[Entry]:
    folder = os.path.join(directory, "decisions")
    if not os.path.isdir(folder):
        return []
    out: list[Entry] = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".md"):
            decision = decisions.parse(os.path.join(folder, name))
            for number, text in decision.searchable():
                out.append(Entry("decision", decision.slug, f"decisions/{decision.slug}.md:{number}", (text,)))
    return out


def entries_of(root: str, name: str) -> list[Entry]:
    directory = os.path.join(root, *name.split("."))
    if stale(directory):
        print(f"index stale: {name}", file=sys.stderr)
        from ostler.book.cli import load

        found = parse(build(load(name), name))
    else:
        with open(os.path.join(directory, FILE)) as f:
            found = parse(f.read())
    return [e for e in found if e.kind != "decision"] + read_decisions(directory)


def folders(base: str) -> list[str]:
    return [n for n in sorted(os.listdir(base)) if os.path.isdir(os.path.join(base, n)) and not n.startswith((".", "_"))]


def services_of(root: str) -> list[str]:
    """Every book under the root: a service's package, or one package per surface it is reached by."""
    base = os.path.join(root, "services")
    found: list[str] = []
    for name in folders(base):
        if os.path.isfile(os.path.join(base, name, "service.py")):
            found.append(f"services.{name}")
            continue
        found += [f"services.{name}.{surface}" for surface in folders(os.path.join(base, name))
                  if os.path.isfile(os.path.join(base, name, surface, "service.py"))]
    return found


def cmd_index(service: Any, args: Any) -> int:
    path, changed = write(service, args.service)
    print(f"{path}: {'changed' if changed else 'unchanged'}")
    return 0


def cmd_search_book(args: Any) -> int:
    root = book_root(os.getcwd())
    names = [args.service] if args.service else services_of(root)
    for name in names:
        if not os.path.isdir(os.path.join(root, *name.split("."))):
            raise SystemExit(f"no service {name!r} under {root}")
    wider = read_levels(root)
    books = {**wider, **{name: entries_of(root, name) for name in names}}
    matched = {name: phrase_hits(entries, args.term, args.kind) for name, entries in books.items()}
    if not any(matched.values()):
        matched = {name: loose_hits(entries, args.term, args.kind) for name, entries in books.items()}
    found = False
    for name, rows in matched.items():
        if not rows:
            continue
        found = True
        if not args.service or name in wider:
            print(f"== {name}")
        for entry, lines in rows:
            print(f"{entry.kind:9} {entry.address}")
            for line in lines:
                print(f"    {line}")
            if entry.reach:
                print(f"    {entry.reach}")
    if not found:
        print(f"nothing in {args.service or 'the book'} says {args.term!r}" + (f" as a {args.kind}" if args.kind else ""))
    return 0 if found else 1
