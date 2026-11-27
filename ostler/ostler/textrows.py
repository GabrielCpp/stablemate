"""The rows the text index holds: one per markdown section of every document root, of the company, team and
product pages and of the artifacts docs, and one per element of every service book."""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ostler import markdown
from ostler.registry import REGISTRY_BY_NAME

if TYPE_CHECKING:
    from ostler.model import Graph

_SPACE_RE = re.compile(r"\s+")
_H1_RE = re.compile(r"^# +(.+?)\s*$", re.MULTILINE)
_LINE_RE = re.compile(r":\d+$")

BOOKS = "books"
PAGES = "pages"
DOCS = "docs"
BOOK_SOURCE = "book:"
BOOK_KINDS = ("rule", "defect", "endpoint", "interaction", "action", "journey", "screen", "component", "scene",
              "decision", "company", "team", "product", "question", "event", "outside")


@dataclass(frozen=True)
class Row:
    root: str
    type: str
    node: str
    path: str
    anchor: str
    heading: str
    title: str
    slug: str
    body: str
    source: str = ""
    context: str = ""


@dataclass(frozen=True)
class Document:
    root: str
    path: Path
    type: str = ""
    superseded: bool = False
    name: str = ""


def _markdown_under(key: str, base: Path) -> Iterable[Path]:
    """A root's markdown files: the specs root holds its documents where the format puts a spec, and run products below them."""
    spec = REGISTRY_BY_NAME["spec"]
    return base.glob(spec.location) if key == spec.doc_root else base.rglob("*.md")


def _book_root(graph: Graph) -> str | None:
    from ostler._vendor.stablemate_core import config as core_config
    from ostler.book.index import book_root

    try:
        return book_root(str(graph.root))
    except core_config.ConfigError as exc:
        print(f"ostler search: no book read: {exc}", file=sys.stderr)
        return None


def _pages(graph: Graph) -> Iterable[Document]:
    """The company, team and product pages the code at the graph root reads, as `ostler book pages` lists them."""
    from ostler.book import pages

    root = _book_root(graph)
    if root is None:
        return
    for level in pages.levels(root, str(graph.root)):
        for page in pages.load(level):
            yield Document(PAGES, Path(level.folder) / f"{page.slug}.md", level.kind, page.superseded(), f"{level.address}/{page.slug}.md")


def _docs() -> Iterable[Document]:
    from ostler._vendor.stablemate_core import config as core_config

    base = core_config.resolve_artifacts_dir() / "docs"
    if base.is_dir():
        for path in sorted(base.rglob("*.md")):
            yield Document(DOCS, path, name=f"{DOCS}/{path.relative_to(base).as_posix()}")


def documents(graph: Graph, roots: set[str] | None = None) -> list[Document]:
    """Every markdown document of the wanted roots, each once: the graph's document roots, then the pages, then the docs."""
    def wanted(key: str) -> bool:
        return roots is None or key in roots

    candidates: list[Document] = [
        Document(key, path)
        for key, base in graph.doc_roots.items()
        if wanted(key) and base.is_dir()
        for path in sorted(_markdown_under(key, base))
    ]
    if wanted(PAGES):
        candidates.extend(_pages(graph))
    if wanted(DOCS):
        candidates.extend(_docs())
    seen: set[Path] = set()
    found: list[Document] = []
    for doc in candidates:
        real = doc.path.resolve()
        if real in seen or not doc.path.is_file():
            continue
        seen.add(real)
        found.append(doc)
    return found


def book_rows(module: str, entries: Iterable[Any]) -> list[Row]:
    """One row per element of a service book: a decision's lines, and the rules of one action, share one row."""
    grouped: dict[tuple[str, str], tuple[str, str, list[str]]] = {}
    for entry in entries:
        address = _LINE_RE.sub("", entry.address) if entry.kind == "decision" else entry.address
        path = address if address.startswith(module) else f"{module}/{address}"
        _, _, lines = grouped.setdefault((entry.kind, path), (entry.name, entry.reach, []))
        lines.extend(entry.lines)
    return [
        Row(root=BOOKS, type=kind, node=path, path=path, anchor="", heading="", title=name, slug=name,
            body=_SPACE_RE.sub(" ", " ".join(lines)).strip(), source=f"{BOOK_SOURCE}{module}", context=reach)
        for (kind, path), (name, reach, lines) in grouped.items()
    ]


def locate(graph: Graph, path: Path) -> tuple[str, str]:
    root = graph.root.resolve()
    real = path.resolve()
    rel = real.relative_to(root).as_posix() if real.is_relative_to(root) else real.as_posix()
    return rel.removesuffix(".md"), rel


def _text(section: markdown.Section) -> str:
    start = section.line_start + (1 if section.level else 0)
    end = section.children[0].line_start if section.children else section.line_end
    return _SPACE_RE.sub(" ", " ".join(section.body_lines[start:end])).strip()


def _walk(
    sections: list[markdown.Section], trail: tuple[str, ...]
) -> list[tuple[markdown.Section, tuple[str, ...]]]:
    out: list[tuple[markdown.Section, tuple[str, ...]]] = []
    for section in sections:
        here = trail + ((section.title.strip(),) if section.level else ())
        out.append((section, here))
        out.extend(_walk(section.children, here))
    return out


def rows_for(
    root_key: str, path: Path, graph: Graph, etype: str = "", superseded: bool = False, name: str = ""
) -> list[Row]:
    from ostler import model

    doc = model.read_doc(path)
    fm = doc.frontmatter or {}
    node, rel = (name.removesuffix(".md"), name) if name else locate(graph, path)
    h1 = _H1_RE.search(doc.body)
    title = str(fm.get("title") or (h1.group(1) if h1 else ""))
    slug = str(fm.get("slug") or fm.get("id") or path.stem)
    etype = etype or str(fm.get("type") or "")
    anchors = model.document_anchors(doc)
    rows: list[Row] = []
    for section, trail in _walk(doc.sections, ()):
        body = _text(section)
        if not body:
            continue
        heading = " > ".join(trail)
        if superseded:
            heading = f"{heading or title or path.stem} (superseded)"
        rows.append(Row(
            root=root_key,
            type=etype,
            node=node,
            path=rel,
            anchor=anchors.get(section.line_start, "") if section.level else "",
            heading=heading,
            title=title,
            slug=slug,
            body=body,
            source=rel,
        ))
    return rows


def book_texts(graph: Graph) -> Iterator[tuple[str, str | None]]:
    """Each service book the graph root reads, with the text `ostler book index` keeps for it, or None when it fails to load."""
    from ostler.book.index import book_modules, text_of

    root = _book_root(graph)
    if root is None:
        return
    _, names, _ = book_modules(str(graph.root))
    if root not in sys.path:
        sys.path.insert(0, root)
    for name in names:
        try:
            text = text_of(root, name)
        except (Exception, SystemExit) as exc:
            print(f"ostler search: skipped {name}: {exc}", file=sys.stderr)
            text = None
        yield name, text
