from __future__ import annotations

import contextvars
import functools
import json
import logging
import os
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

from groom.store.schema import (
    _SPAN_VALUE_COLUMNS,
    _TABLES,
    _promoted,
    _Table,
    db_path,
    prepare,
)


logger = logging.getLogger(__name__)
RETENTION_DAYS = float(os.environ.get("GROOM_RETENTION_DAYS", "30"))


ACTIVE_WINDOW_S = float(os.environ.get("GROOM_ACTIVE_WINDOW_S", "86400"))


_P = ParamSpec("_P")


_T = TypeVar("_T")


REOPEN_COOLDOWN_S = 5.0


@dataclass(frozen=True, slots=True)
class StoreHealth:
    """What the store would say if asked whether it is still storing."""

    ok: bool
    path: str
    last_ok_ts: float
    reopens: int
    failures: int
    last_error: str
    last_error_ts: float
    last_write_ts: float
    last_prune_ts: float
    wal_bytes: int
    last_checkpoint_busy: int


class _Store:
    """The process's one SQLite handle, and the discipline that keeps it usable."""

    def __init__(self, monotonic: Callable[[], float] = time.monotonic) -> None:
        self.monotonic = monotonic
        self.lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._path: Path | None = None
        self._readers = threading.local()
        self._generation = 0
        self._reopens = 0
        self._failures = 0
        self._last_error = ""
        self._last_error_ts = 0.0
        self._last_reopen_at = 0.0
        self._last_ok_ts = 0.0
        self._last_write_ts = 0.0
        self._last_prune_ts = 0.0
        self._last_checkpoint_busy = 0

    def connect(self) -> sqlite3.Connection:
        """The open connection, opening (or reopening) it if there isn't one."""
        with self.lock:
            path = db_path()
            if self._conn is not None and self._path != path:
                self._close_quietly()
            if self._conn is None:
                self._conn = self._open(path)
                self._path = path
            return self._conn

    def _open(self, path: Path) -> sqlite3.Connection:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        prepare(conn)
        return conn

    def install(self, table: _Table) -> None:
        """Create a table registered after the connection opened."""
        with self.lock:
            if self._conn is not None:
                table.create(self._conn)

    @contextmanager
    def writing(self) -> Iterator[sqlite3.Connection]:
        """One atomic write."""
        with self.lock:
            conn = self.connect()
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                with suppress(sqlite3.Error):
                    conn.rollback()
                raise
            conn.commit()
            self._last_write_ts = time.time()

    def recycle(self, exc: BaseException, where: str) -> None:
        """Throw the handle away so the next call opens a fresh one."""
        with self.lock:
            self._failures += 1
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._last_error_ts = time.time()
            now = self.monotonic()
            if self._reopens and now - self._last_reopen_at < REOPEN_COOLDOWN_S:
                logger.error(
                    "groom.store: %s failed again while cooling down: %s", where, exc
                )
                raise exc
            self._close_quietly()
            self._reopens += 1
            self._last_reopen_at = now
            logger.error(
                "groom.store: recycling the connection after %s in %s", exc, where
            )

    def reset(self) -> None:
        """Close the connection and forget every failure with it (tests switch ``$GROOM_DB`` between cases, and a counter that survived would be another case's)."""
        with self.lock:
            self._close_quietly()
            self.retire_reader()
            self._path = None
            self._reopens = 0
            self._failures = 0
            self._last_error = ""
            self._last_error_ts = 0.0
            self._last_reopen_at = 0.0
            self._last_ok_ts = 0.0
            self._last_write_ts = 0.0
            self._last_prune_ts = 0.0
            self._last_checkpoint_busy = 0

    def _close_quietly(self) -> None:
        if self._conn is not None:
            with suppress(sqlite3.Error):
                self._conn.rollback()
            with suppress(sqlite3.Error):
                self._conn.close()
        self._conn = None
        self._generation += 1

    def read_connection(self) -> sqlite3.Connection:
        """A read-only connection belonging to the calling thread."""
        path = db_path()
        cached: _Reader | None = getattr(self._readers, "handle", None)
        if (
            cached is not None
            and cached.generation == self._generation
            and cached.path == path
        ):
            return cached.conn
        self.retire_reader()
        with self.lock:
            self.connect()
            if not (self._path or path).exists():
                self._close_quietly()
                self.connect()
            generation, opened = self._generation, self._path or path
        conn = sqlite3.connect(opened, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA query_only=1")
        self._readers.handle = _Reader(conn, generation, opened)
        return conn

    def retire_reader(self) -> None:
        """Drop this thread's read handle; its next query opens a fresh one."""
        cached: _Reader | None = getattr(self._readers, "handle", None)
        self._readers.handle = None
        if cached is not None:
            with suppress(sqlite3.Error):
                cached.conn.close()

    def recycle_reader(self, exc: BaseException, where: str) -> None:
        """A read failed: retire that handle, and leave the writer alone."""
        self._failures += 1
        self._last_error = f"{type(exc).__name__}: {exc}"
        self._last_error_ts = time.time()
        logger.error("groom.store: retiring the read handle after %s in %s", exc, where)
        self.retire_reader()

    def note_ok(self) -> None:
        """Stamp a statement that ran."""
        self._last_ok_ts = time.time()

    def note_prune(self, ts: float | None = None) -> None:
        self._last_prune_ts = ts if ts is not None else time.time()

    def note_checkpoint(self, busy: int) -> None:
        self._last_checkpoint_busy = busy

    def health(self) -> StoreHealth:
        path = db_path()
        wal = path.with_name(path.name + "-wal")
        wal_bytes = wal.stat().st_size if wal.exists() else 0
        return StoreHealth(
            ok=self._last_error_ts <= self._last_ok_ts,
            path=str(path),
            last_ok_ts=self._last_ok_ts,
            reopens=self._reopens,
            failures=self._failures,
            last_error=self._last_error,
            last_error_ts=self._last_error_ts,
            last_write_ts=self._last_write_ts,
            last_prune_ts=self._last_prune_ts,
            wal_bytes=wal_bytes,
            last_checkpoint_busy=self._last_checkpoint_busy,
        )


@dataclass(slots=True)
class _Reader:
    """One thread's read handle, tagged with what it was opened against."""

    conn: sqlite3.Connection
    generation: int
    path: Path


STORE = _Store()


def resilient(fn: Callable[_P, _T]) -> Callable[_P, _T]:
    """Serialize a store call, and heal the connection under it exactly once."""

    name = getattr(fn, "__name__", "store call")

    @functools.wraps(fn)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        with STORE.lock:
            try:
                result = fn(*args, **kwargs)
            except sqlite3.Error as exc:
                STORE.recycle(exc, name)
            else:
                STORE.note_ok()
                return result
            result = fn(*args, **kwargs)
            STORE.note_ok()
            return result

    return wrapper


def reading(fn: Callable[_P, _T]) -> Callable[_P, _T]:
    """:func:`resilient` for a query: heal once, and take no lock doing it."""
    name = getattr(fn, "__name__", "store read")

    @functools.wraps(fn)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        try:
            result = fn(*args, **kwargs)
        except sqlite3.Error as exc:
            STORE.recycle_reader(exc, name)
        else:
            STORE.note_ok()
            return result
        result = fn(*args, **kwargs)
        STORE.note_ok()
        return result

    return wrapper


def _noop_on_empty(zero: Any) -> Callable[[Callable[_P, _T]], Callable[_P, _T]]:
    """Answer a batch with nothing in it *before* :func:`resilient` takes the lock."""

    def decorate(fn: Callable[_P, _T]) -> Callable[_P, _T]:
        @functools.wraps(fn)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
            if args and not args[0]:
                return zero
            return fn(*args, **kwargs)

        return wrapper

    return decorate


def _connection() -> sqlite3.Connection:
    return STORE.connect()


_READING_FROM: contextvars.ContextVar[sqlite3.Connection | None] = (
    contextvars.ContextVar("groom_reading_from", default=None)
)


def read_connection() -> sqlite3.Connection:
    redirected = _READING_FROM.get()
    if redirected is not None:
        return redirected
    return STORE.read_connection()


@contextmanager
def reading_from(path: Path) -> Iterator[None]:
    """Point this context's reads at the SQLite file ``path`` until the block ends."""
    conn = sqlite3.connect(
        f"file:{path}?mode=ro", uri=True, check_same_thread=False, isolation_level=None
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=1")
    token = _READING_FROM.set(conn)
    try:
        yield
    finally:
        _READING_FROM.reset(token)
        conn.close()


def register_table(
    name: str, ddl: str, added: tuple[tuple[str, str], ...] = ()
) -> None:
    """Have every connection the store opens create this table, and the open one too."""
    with STORE.lock:
        table = _Table(name, ddl, added)
        _TABLES[name] = table
        STORE.install(table)


def reset() -> None:
    """Close the module connection so the next call reopens (tests switch GROOM_DB between cases)."""
    STORE.reset()


def health() -> StoreHealth:
    """Whether the collector is still storing what it is told, and since when."""
    return STORE.health()


def health_dict() -> dict[str, Any]:
    """:func:`health` as JSON for the dashboard state payload."""
    return asdict(STORE.health())


@_noop_on_empty(None)
@resilient
def insert_spans(spans: list[dict[str, Any]]) -> None:
    """Upsert decoded spans (see groom.otlp.parse_traces)."""
    if not spans:
        return
    with STORE.writing() as conn:
        promoted = ", ".join(_SPAN_VALUE_COLUMNS)
        placeholders = ", ".join("?" * len(_SPAN_VALUE_COLUMNS))
        conn.executemany(
            "INSERT OR REPLACE INTO spans (span_id, trace_id, parent_id, run_id, workflow,"
            " repo, branch, node, name, run_dir, start_ts, end_ts, status, attrs_json,"
            f" {promoted})"
            f" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, {placeholders})",
            [
                (
                    s["span_id"],
                    s["trace_id"],
                    s.get("parent_id", ""),
                    s.get("run_id", ""),
                    s.get("workflow", ""),
                    s.get("repo", ""),
                    s.get("branch", ""),
                    s.get("node", ""),
                    s.get("name", ""),
                    s.get("run_dir", ""),
                    s.get("start_ts", 0.0),
                    s.get("end_ts", 0.0),
                    s.get("status", "UNSET"),
                    json.dumps(s.get("attrs") or {}),
                    *_promoted(s, s.get("attrs") or {}),
                )
                for s in spans
            ],
        )
