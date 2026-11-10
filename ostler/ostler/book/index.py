"""The book searched without running it: `index` writes what `search` finds in one service to
`index.tsv` beside it, and `search` reads those files and the decisions as text."""

from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from typing import Any

from ostler.book import decisions
from ostler.book.search import Item, items

FILE = "index.tsv"


@dataclass(frozen=True)
class Entry:
    kind: str
    name: str
    address: str
    lines: tuple[str, ...]


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
    rows = ["\t".join((i.kind, escape(i.name), escape(i.address), escape("\n".join(i.lines)))) for i in found]
    return "".join(row + "\n" for row in rows)


def parse(text: str) -> list[Entry]:
    out: list[Entry] = []
    for row in text.splitlines():
        kind, name, address, body = row.split("\t", 3)
        out.append(Entry(kind, name, address, tuple(unescape(body))))
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


def book_root(start: str) -> str | None:
    here = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(here, "services")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def read_decisions(directory: str) -> list[Entry]:
    root = os.path.join(directory, "decisions")
    if not os.path.isdir(root):
        return []
    out: list[Entry] = []
    for name in sorted(os.listdir(root)):
        if name.endswith(".md"):
            decision = decisions.parse(os.path.join(root, name))
            for number, text in decision.lines():
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


def services_of(root: str) -> list[str]:
    base = os.path.join(root, "services")
    return [f"services.{n}" for n in sorted(os.listdir(base)) if os.path.isdir(os.path.join(base, n)) and not n.startswith((".", "_"))]


def hits(entries: list[Entry], term: str, kind: str | None) -> list[tuple[Entry, list[str]]]:
    wanted = term.lower()
    found = []
    for entry in entries:
        if kind is not None and entry.kind != kind:
            continue
        lines = [line.strip() for line in entry.lines if wanted in line.lower()]
        if lines:
            found.append((entry, lines))
    return found


def cmd_index(service: Any, args: Any) -> int:
    path, changed = write(service, args.service)
    print(f"{path}: {'changed' if changed else 'unchanged'}")
    return 0


def cmd_search_book(args: Any) -> int:
    root = book_root(os.getcwd())
    if root is None:
        raise SystemExit("no services directory above the current directory")
    names = [args.service] if args.service else services_of(root)
    found = False
    for name in names:
        if not os.path.isdir(os.path.join(root, *name.split("."))):
            raise SystemExit(f"no service {name!r} under {root}")
        matched = hits(entries_of(root, name), args.term, args.kind)
        if not matched:
            continue
        found = True
        if not args.service:
            print(f"== {name}")
        for entry, lines in matched:
            print(f"{entry.kind:9} {entry.address}")
            for line in lines:
                print(f"    {line}")
    if not found:
        print(f"nothing in {args.service or 'the book'} says {args.term!r}" + (f" as a {args.kind}" if args.kind else ""))
    return 0 if found else 1
