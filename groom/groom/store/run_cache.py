"""One run's spans read once and kept, topped up from the rows that changed since, with the views built from them kept beside them."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from groom import memory
from groom.span_views import SpanList
from groom.store.connection import _READING_FROM, on_reset, read_connection, register_table
from groom.store.costs import (
    _cache_read,
    _cache_write,
    _charge,
    _charges,
    _duration,
    _input,
    _output,
)
from groom.store.profile_parts import _kept_attr
from groom.store.spans import _RUN_SPAN_COLUMNS

KEPT_RUNS = 6

PATCH_LIMIT = 500


@dataclass(frozen=True, slots=True)
class _Mark:
    count: int
    top: int
    rewrites: int


@dataclass(slots=True)
class _Entry:
    mark: _Mark
    spans: SpanList
    charges: dict[str, float | None]


_REWRITES_DDL = """
CREATE TABLE IF NOT EXISTS span_rewrites (
    run_id TEXT PRIMARY KEY,
    count  INTEGER NOT NULL DEFAULT 0
);
CREATE TRIGGER IF NOT EXISTS span_rewritten AFTER UPDATE ON spans BEGIN
    INSERT INTO span_rewrites (run_id, count) VALUES (OLD.run_id, 1)
        ON CONFLICT (run_id) DO UPDATE SET count = count + 1;
    INSERT INTO span_rewrites (run_id, count) VALUES (NEW.run_id, 1)
        ON CONFLICT (run_id) DO UPDATE SET count = count + 1;
END;
CREATE TRIGGER IF NOT EXISTS span_deleted AFTER DELETE ON spans BEGIN
    INSERT INTO span_rewrites (run_id, count) VALUES (OLD.run_id, 1)
        ON CONFLICT (run_id) DO UPDATE SET count = count + 1;
END;
"""

register_table("span_rewrites", _REWRITES_DDL)

_SELECT = (
    f"{_charges('run_id = ?')}SELECT {_RUN_SPAN_COLUMNS}, {_duration} AS profile_duration_ms,"  # noqa: S608
    f" {_charge} AS profile_cost_usd, {_output} AS profile_output_tokens,"
    f" {_input} AS profile_input_tokens, {_cache_read} AS profile_cache_read_tokens,"
    f" {_cache_write} AS profile_cache_write_tokens,"
    " est_cost_usd, spans.rowid AS row_id, resume_generation, charges.charge_usd AS session_charge"
    " FROM spans LEFT JOIN charges USING (span_id)"
    " WHERE run_id = ?"
)

_CHARGES = (
    f"{_charges('run_id = ?')}SELECT spans.span_id, charges.charge_usd FROM spans"  # noqa: S608
    " LEFT JOIN charges USING (span_id) WHERE run_id = ? AND name = 'agent_turn'"
)


def _span(row: sqlite3.Row) -> dict[str, Any]:
    span = dict(row)
    span.pop("session_charge")
    attrs = json.loads(span.pop("attrs_json") or "{}")
    span["attrs"] = {k: v for k, v in attrs.items() if _kept_attr(k)}
    return span


def _order(span: dict[str, Any]) -> tuple[float, int]:
    return (span["start_ts"], span["row_id"])


def _database(conn: sqlite3.Connection) -> str:
    return str(conn.execute("PRAGMA database_list").fetchone()[2])


def _rewrites(conn: sqlite3.Connection, run: str) -> int:
    """How many times a span of ``run`` was changed in place or deleted. An archive is read-only, so none of its spans ever is."""
    if _READING_FROM.get() is not None:
        return 0
    row = conn.execute("SELECT count FROM span_rewrites WHERE run_id = ?", (run,)).fetchone()
    return int(row[0]) if row else 0


def _mark(conn: sqlite3.Connection, run: str) -> _Mark:
    row = conn.execute("SELECT COUNT(*), COALESCE(MAX(rowid), 0) FROM spans WHERE run_id = ?", (run,)).fetchone()
    return _Mark(int(row[0]), int(row[1]), _rewrites(conn, run))


def _rows(conn: sqlite3.Connection, run: str, extra: str = "", params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    return conn.execute(f"{_SELECT}{extra} ORDER BY start_ts, spans.rowid", (run, run, *params)).fetchall()


def _full(conn: sqlite3.Connection, run: str, mark: _Mark) -> _Entry:
    rows = _rows(conn, run)
    spans = [_span(row) for row in rows]
    memory.note_read(len(spans))
    charges = {row["span_id"]: row["session_charge"] for row in rows if row["name"] == "agent_turn"}
    return _Entry(mark, SpanList(spans), charges)


def _refreshed(conn: sqlite3.Connection, run: str, mark: _Mark, entry: _Entry | None) -> _Entry:
    """The entry for ``mark``: topped up by rowid when rows were only added or replaced, read whole after a span was changed in place or deleted. A turn that arrives late changes the session charge of the turns after it, so those are read again too."""
    if entry is None or mark.rewrites != entry.mark.rewrites or mark.top < entry.mark.top:
        return _full(conn, run, mark)
    charges: dict[str, float | None] = {row[0]: row[1] for row in conn.execute(_CHARGES, (run, run))}
    changed = [span_id for span_id, charge in charges.items() if span_id in entry.charges and entry.charges[span_id] != charge]
    if len(changed) > PATCH_LIMIT:
        return _full(conn, run, mark)
    marks = ", ".join("?" * len(changed))
    extra = f" AND (spans.rowid > ? OR span_id IN ({marks}))" if changed else " AND spans.rowid > ?"
    rows = _rows(conn, run, extra, (entry.mark.top, *changed))
    fresh = {row["span_id"]: _span(row) for row in rows}
    kept = [span for span in entry.spans if span["span_id"] not in fresh]
    merged = sorted([*kept, *fresh.values()], key=_order)
    if len(merged) != mark.count:
        return _full(conn, run, mark)
    memory.note_read(len(rows))
    return _Entry(mark, SpanList(merged), charges)


class _RunCache:
    def __init__(self, capacity: int = KEPT_RUNS) -> None:
        self.capacity = capacity
        self.lock = threading.Lock()
        self.entries: OrderedDict[tuple[str, str], _Entry] = OrderedDict()
        self.loading: dict[tuple[str, str], threading.Lock] = {}

    def clear(self) -> None:
        with self.lock:
            self.entries.clear()

    def spans(self, run: str) -> SpanList:
        conn = read_connection()
        key = (_database(conn), run)
        with self.lock:
            gate = self.loading.setdefault(key, threading.Lock())
        with gate:
            mark = _mark(conn, run)
            with self.lock:
                entry = self.entries.get(key)
            if entry is None or entry.mark != mark:
                entry = _refreshed(conn, run, mark, entry)
            with self.lock:
                self.entries[key] = entry
                self.entries.move_to_end(key)
                while len(self.entries) > self.capacity:
                    gone, _ = self.entries.popitem(last=False)
                    self.loading.pop(gone, None)
            return entry.spans


CACHE = _RunCache()


def run_spans(run: str) -> SpanList:
    """Every span of ``run`` in the database this context reads, oldest first, with the cost, token and duration figures the profile computes."""
    return CACHE.spans(run)


def forget() -> None:
    """Drop every kept run."""
    CACHE.clear()


on_reset(forget)
