"""Ranked full-text search over one row per markdown section of every document root."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ostler import index, markdown, model
from ostler.model import Graph

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS files(
    path TEXT PRIMARY KEY, sha TEXT NOT NULL, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS sections USING fts5(
    root UNINDEXED, type UNINDEXED, node UNINDEXED, path UNINDEXED, anchor UNINDEXED,
    heading, title, slug, body, tokenize='porter unicode61');
"""

_TERM_RE = re.compile(r"\w+")
_SPACE_RE = re.compile(r"\s+")
_H1_RE = re.compile(r"^# +(.+?)\s*$", re.MULTILINE)

_SEARCH_SQL = """
SELECT root, type, node, path, anchor, heading, title,
       bm25(sections, 0, 0, 0, 0, 0, 3.0, 10.0, 5.0, 1.0) AS rank,
       snippet(sections, 8, '[', ']', '…', 24) AS snippet
FROM sections WHERE sections MATCH ?{where}
ORDER BY rank LIMIT ?
"""


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


@dataclass(frozen=True)
class RefreshReport:
    files: int
    sections: int
    indexed: int
    removed: int
    dir: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "files": self.files,
            "sections": self.sections,
            "indexed": self.indexed,
            "removed": self.removed,
            "dir": self.dir,
        }


def documents(graph: Graph) -> list[tuple[str, Path]]:
    seen: set[Path] = set()
    found: list[tuple[str, Path]] = []
    for key, base in graph.doc_roots.items():
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            real = path.resolve()
            if real in seen or not path.is_file():
                continue
            seen.add(real)
            found.append((key, path))
    return found


def _locate(graph: Graph, path: Path) -> tuple[str, str]:
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


def rows_for(root_key: str, path: Path, graph: Graph) -> list[Row]:
    doc = model.read_doc(path)
    fm = doc.frontmatter or {}
    node, rel = _locate(graph, path)
    h1 = _H1_RE.search(doc.body)
    decided = root_key == "decisions"
    summary = str(fm.get("summary") or "") if decided else ""
    title = str(fm.get("title") or (h1.group(1) if h1 else "") or summary)
    folder = path.parent.name if decided else path.stem
    slug = str(fm.get("slug") or fm.get("id") or folder)
    etype = str(fm.get("type") or ("decision" if decided else ""))
    anchors = model.document_anchors(doc)
    rows: list[Row] = []
    if summary:
        rows.append(Row(root_key, etype, node, rel, "", "", title, slug, summary))
    for section, trail in _walk(doc.sections, ()):
        body = _text(section)
        if not body:
            continue
        rows.append(Row(
            root=root_key,
            type=etype,
            node=node,
            path=rel,
            anchor=anchors.get(section.line_start, "") if section.level else "",
            heading=" > ".join(trail),
            title=title,
            slug=slug,
            body=body,
        ))
    return rows


def _match_expression(q: str) -> str:
    return " OR ".join(f'"{term}"*' for term in _TERM_RE.findall(q))


class TextIndex:
    def __init__(self, conn: sqlite3.Connection, directory: str) -> None:
        self._conn = conn
        self._dir = directory

    @classmethod
    def open(cls, store: index.IndexStore | None, graph: Graph) -> TextIndex:
        persistent = store is not None and store.enabled
        if store is not None and persistent:
            digest = index.content_sha(str(graph.root.resolve()).encode("utf-8"))[:16]
            target = store.directory / "textindex" / f"{digest}.sqlite"
            target.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(target)
            where = str(store.directory)
        else:
            conn = sqlite3.connect(":memory:")
            where = ":memory:"
        columns = {row[1] for row in conn.execute("PRAGMA table_info(files)")}
        if columns and "mtime_ns" not in columns:
            conn.executescript("DROP TABLE files; DROP TABLE sections; DROP TABLE meta;")
        conn.executescript(_SCHEMA)
        epoch = store.epoch if store is not None else ""
        current = conn.execute("SELECT value FROM meta WHERE key = 'epoch'").fetchone()
        if not persistent or current is None or current[0] != epoch:
            with conn:
                conn.execute("DELETE FROM sections")
                conn.execute("DELETE FROM files")
                conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('epoch', ?)", (epoch,))
        return cls(conn, where)

    def close(self) -> None:
        self._conn.close()

    def refresh(self, graph: Graph) -> RefreshReport:
        docs = documents(graph)
        known: dict[str, tuple[str, int, int]] = {
            row[0]: (row[1], row[2], row[3])
            for row in self._conn.execute("SELECT path, sha, size, mtime_ns FROM files")
        }
        present: set[str] = set()
        indexed = 0
        with self._conn:
            for key, path in docs:
                _, rel = _locate(graph, path)
                present.add(rel)
                stat = path.stat()
                stamp = (stat.st_size, stat.st_mtime_ns)
                old = known.get(rel)
                if old is not None and old[1:] == stamp:
                    continue
                sha = index.content_sha(path.read_bytes())
                if old is not None and old[0] == sha:
                    self._conn.execute(
                        "UPDATE files SET size = ?, mtime_ns = ? WHERE path = ?", (*stamp, rel)
                    )
                    continue
                if rel in known:
                    self._conn.execute("DELETE FROM sections WHERE path = ?", (rel,))
                for row in rows_for(key, path, graph):
                    self._conn.execute(
                        "INSERT INTO sections(root, type, node, path, anchor, heading, title, slug, body)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (row.root, row.type, row.node, row.path, row.anchor,
                         row.heading, row.title, row.slug, row.body),
                    )
                self._conn.execute(
                    "INSERT OR REPLACE INTO files(path, sha, size, mtime_ns) VALUES (?, ?, ?, ?)",
                    (rel, sha, *stamp),
                )
                indexed += 1
            gone = [p for p in known if p not in present]
            for rel in gone:
                self._conn.execute("DELETE FROM sections WHERE path = ?", (rel,))
                self._conn.execute("DELETE FROM files WHERE path = ?", (rel,))
        total = self._conn.execute("SELECT count(*) FROM sections").fetchone()[0]
        return RefreshReport(
            files=len(docs), sections=total, indexed=indexed, removed=len(gone), dir=self._dir
        )

    def search(
        self,
        q: str,
        *,
        etype: str | None = None,
        root: str | None = None,
        limit: int = 10,
        raw: bool = False,
    ) -> list[dict]:
        expression = q if raw else _match_expression(q)
        if not expression.strip():
            return []
        where = ""
        params: list[Any] = [expression]
        if etype is not None:
            where += " AND type = ?"
            params.append(etype)
        if root is not None:
            where += " AND root = ?"
            params.append(root)
        params.append(limit)
        try:
            found = self._conn.execute(_SEARCH_SQL.format(where=where), params).fetchall()
        except sqlite3.OperationalError as exc:
            raise ValueError(str(exc)) from exc
        return [
            {
                "root": r[0], "type": r[1], "node": r[2], "path": r[3], "anchor": r[4],
                "heading": r[5], "title": r[6], "score": round(-r[7], 3), "snippet": r[8],
            }
            for r in found
        ]


def build(graph: Graph) -> RefreshReport:
    ti = TextIndex.open(index.active(), graph)
    try:
        return ti.refresh(graph)
    finally:
        ti.close()


def search(graph: Graph, q: str, **kw: Any) -> list[dict]:
    ti = TextIndex.open(index.active(), graph)
    try:
        ti.refresh(graph)
        return ti.search(q, **kw)
    finally:
        ti.close()
