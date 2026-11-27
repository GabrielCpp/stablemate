"""Ranked full-text search over the rows `textrows` reads: the document roots, the service books, the pages and the docs."""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ostler import index
from ostler.textrows import BOOK_SOURCE, BOOKS, DOCS, PAGES, Row, book_rows, documents, locate, rows_for

if TYPE_CHECKING:
    from ostler.model import Graph

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS files(
    path TEXT PRIMARY KEY, root TEXT NOT NULL, sha TEXT NOT NULL, size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS sections USING fts5(
    root UNINDEXED, type UNINDEXED, node UNINDEXED, path UNINDEXED, anchor UNINDEXED,
    heading, title, slug, body, source UNINDEXED, context UNINDEXED, tokenize='porter unicode61');
"""

_TERM_RE = re.compile(r"\w+")

_SEARCH_SQL = """
SELECT root, type, node, path, anchor, heading, title,
       bm25(sections, 0, 0, 0, 0, 0, 3.0, 10.0, 5.0, 1.0, 0, 0) AS rank,
       snippet(sections, 8, '[', ']', '…', 24) AS snippet, context
FROM sections WHERE sections MATCH ?{where}
ORDER BY rank
"""

ALL_ROOTS = "all"
_RECORD_ROOTS = ("epics", "milestones", "specs", "register")
_SCAFFOLD_TYPE = "fixture"
_HITS_PER_PAGE = 2
_ROW_FORMAT = "with-books-context"


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


def _match_expression(q: str, joiner: str = " OR ") -> str:
    return joiner.join(f'"{term}"*' for term in _TERM_RE.findall(q))


def _expressions(q: str) -> list[str]:
    """Every word first, then any word: a hit that holds them all ranks above one that holds a few."""
    every, some = _match_expression(q, " AND "), _match_expression(q)
    return [every] if every == some else [every, some]


def wanted_roots(root: str | None, etype: str | None = None) -> set[str] | None:
    """The roots a search reads: every root for `all` or a type filter, the named roots for a comma list, else
    every root but the plans and history."""
    if root == ALL_ROOTS or (root is None and etype is not None):
        return None
    if root is None:
        return {"*"}
    return {part.strip() for part in root.split(",") if part.strip()}


def _reads(roots: set[str] | None, key: str) -> bool:
    if roots is None:
        return True
    if "*" in roots:
        return key not in _RECORD_ROOTS
    return key in roots


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
        fts = {row[1] for row in conn.execute("PRAGMA table_info(sections)")}
        if (columns and "root" not in columns) or (fts and "context" not in fts):
            conn.executescript("DROP TABLE files; DROP TABLE sections; DROP TABLE meta;")
        conn.executescript(_SCHEMA)
        epoch = f"{_ROW_FORMAT}:{store.epoch}" if store is not None else _ROW_FORMAT
        current = conn.execute("SELECT value FROM meta WHERE key = 'epoch'").fetchone()
        if not persistent or current is None or current[0] != epoch:
            with conn:
                conn.execute("DELETE FROM sections")
                conn.execute("DELETE FROM files")
                conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('epoch', ?)", (epoch,))
        return cls(conn, where)

    def close(self) -> None:
        self._conn.close()

    def refresh(self, graph: Graph, roots: set[str] | None = None) -> RefreshReport:
        """Bring every document root up to date, and the books when the search reads them: loading a book runs its code."""
        reading = {*graph.doc_roots, PAGES, DOCS, *((BOOKS,) if _reads(roots, BOOKS) else ())}
        docs = documents(graph, reading)
        known: dict[str, tuple[str, str, int, int]] = {
            row[0]: (row[1], row[2], row[3], row[4])
            for row in self._conn.execute("SELECT path, root, sha, size, mtime_ns FROM files")
        }
        present: set[str] = set()
        indexed = 0
        with self._conn:
            for doc in docs:
                rel = doc.name or locate(graph, doc.path)[1]
                present.add(rel)
                stat = doc.path.stat()
                stamp = (stat.st_size, stat.st_mtime_ns)
                old = known.get(rel)
                if old is not None and old[2:] == stamp and old[0] == doc.root:
                    continue
                sha = index.content_sha(doc.path.read_bytes())
                if old is not None and old[1] == sha and old[0] == doc.root:
                    self._conn.execute(
                        "UPDATE files SET size = ?, mtime_ns = ? WHERE path = ?", (*stamp, rel)
                    )
                    continue
                self._replace(rel, doc.root, sha, stamp,
                              rows_for(doc.root, doc.path, graph, doc.type, doc.superseded, doc.name))
                indexed += 1
            if BOOKS in reading:
                indexed += self._refresh_books(graph, known, present)
            gone = [p for p, old in known.items() if p not in present and old[0] in reading]
            self._conn.execute("CREATE TEMP TABLE IF NOT EXISTS gone(path TEXT PRIMARY KEY)")
            self._conn.execute("DELETE FROM gone")
            self._conn.executemany("INSERT INTO gone(path) VALUES (?)", ((rel,) for rel in gone))
            self._conn.execute("DELETE FROM sections WHERE source IN (SELECT path FROM gone)")
            self._conn.execute("DELETE FROM files WHERE path IN (SELECT path FROM gone)")
        total = self._conn.execute("SELECT count(*) FROM sections").fetchone()[0]
        books_read = sum(1 for p in present if p.startswith(BOOK_SOURCE))
        return RefreshReport(
            files=len(docs) + books_read, sections=total, indexed=indexed, removed=len(gone), dir=self._dir
        )

    def insert(self, rows: list[Row]) -> None:
        self._conn.executemany(
            "INSERT INTO sections(root, type, node, path, anchor, heading, title, slug, body, source, context)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ((row.root, row.type, row.node, row.path, row.anchor,
              row.heading, row.title, row.slug, row.body, row.source, row.context) for row in rows),
        )

    def _replace(self, source: str, root: str, sha: str, stamp: tuple[int, int], rows: list[Row]) -> None:
        self._conn.execute("DELETE FROM sections WHERE source = ?", (source,))
        self.insert(rows)
        self._conn.execute(
            "INSERT OR REPLACE INTO files(path, root, sha, size, mtime_ns) VALUES (?, ?, ?, ?, ?)",
            (source, root, sha, *stamp),
        )

    def _refresh_books(self, graph: Graph, known: dict[str, tuple[str, str, int, int]], present: set[str]) -> int:
        """Index each service book from the text `ostler book index` keeps in the user cache; a book that fails to load keeps its old rows."""
        from ostler.book.index import parse
        from ostler.textrows import book_texts

        indexed = 0
        for name, text in book_texts(graph):
            source = f"{BOOK_SOURCE}{name}"
            present.add(source)
            if text is None:
                continue
            sha = index.content_sha(text.encode("utf-8"))
            old = known.get(source)
            if old is not None and old[1] == sha:
                continue
            self._replace(source, BOOKS, sha, (len(text), 0), book_rows(name, parse(text)))
            indexed += 1
        return indexed

    def search(
        self,
        q: str,
        *,
        etype: str | None = None,
        root: str | None = None,
        limit: int = 10,
        raw: bool = False,
        service: str | None = None,
    ) -> list[dict]:
        expressions = [q] if raw else _expressions(q)
        if not expressions[0].strip():
            return []
        where = ""
        params: list[Any] = [""]
        if etype is not None:
            where += " AND type = ?"
            params.append(etype)
        elif root != ALL_ROOTS:
            where += " AND type != ?"
            params.append(_SCAFFOLD_TYPE)
        roots = wanted_roots(root, etype)
        if roots is not None and "*" in roots:
            where += f" AND root NOT IN ({', '.join('?' * len(_RECORD_ROOTS))})"
            params.extend(_RECORD_ROOTS)
        elif roots is not None:
            where += f" AND root IN ({', '.join('?' * len(roots))})"
            params.extend(sorted(roots))
        if service is not None:
            where += " AND (root != ? OR source = ?)"
            params.extend((BOOKS, f"{BOOK_SOURCE}{service}"))
        hits: list[dict] = []
        seen: set[tuple[Any, ...]] = set()
        per_page: Counter[str] = Counter()
        try:
            for expression in expressions:
                params[0] = expression
                for r in self._conn.execute(_SEARCH_SQL.format(where=where), params):
                    if len(hits) == limit:
                        return hits
                    if r[:6] in seen or per_page[r[3]] == _HITS_PER_PAGE:
                        continue
                    seen.add(r[:6])
                    per_page[r[3]] += 1
                    hits.append({
                        "root": r[0], "type": r[1], "node": r[2], "path": r[3], "anchor": r[4],
                        "heading": r[5], "title": r[6], "score": round(-r[7], 3), "snippet": r[8],
                        **({"context": r[9]} if r[9] else {}),
                    })
        except sqlite3.OperationalError as exc:
            raise ValueError(str(exc)) from exc
        return hits


def search_rows(rows: list[Row], q: str, **kw: Any) -> list[dict]:
    """Search rows held in memory, such as the elements of one loaded book."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA)
    ti = TextIndex(conn, ":memory:")
    try:
        ti.insert(rows)
        return ti.search(q, **kw)
    finally:
        ti.close()


def render(hits: list[dict]) -> list[str]:
    """Two lines per hit: score, root and type, where it is and its heading; then the matched text, and the way to it when known."""
    lines: list[str] = []
    for hit in hits:
        where = f"{hit['node']}#{hit['anchor']}" if hit["anchor"] else hit["node"]
        heading = f" — {hit['heading']}" if hit["heading"] else ""
        lines.append(f"{hit['score']:.3f}  {hit['root']}/{hit['type']}  {where}{heading}")
        lines.append(f"        {hit['snippet']}")
        if hit.get("context"):
            lines.append(f"        {hit['context']}")
    return lines


def build(graph: Graph) -> RefreshReport:
    ti = TextIndex.open(index.active(), graph)
    try:
        return ti.refresh(graph)
    finally:
        ti.close()


def search(graph: Graph, q: str, **kw: Any) -> list[dict]:
    ti = TextIndex.open(index.active(), graph)
    try:
        ti.refresh(graph, wanted_roots(kw.get("root"), kw.get("etype")))
        return ti.search(q, **kw)
    finally:
        ti.close()
