from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

from groom import prices

logger = logging.getLogger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS spans (
    span_id   TEXT PRIMARY KEY,
    trace_id  TEXT NOT NULL,
    parent_id TEXT NOT NULL DEFAULT '',
    run_id    TEXT NOT NULL DEFAULT '',
    workflow  TEXT NOT NULL DEFAULT '',
    repo      TEXT NOT NULL DEFAULT '',
    branch    TEXT NOT NULL DEFAULT '',
    node      TEXT NOT NULL DEFAULT '',
    name      TEXT NOT NULL DEFAULT '',
    run_dir   TEXT NOT NULL DEFAULT '',
    start_ts  REAL NOT NULL,
    end_ts    REAL NOT NULL,
    status    TEXT NOT NULL DEFAULT 'UNSET',
    attrs_json TEXT NOT NULL DEFAULT '{}',
    duration_ms INTEGER,
    total_cost_usd REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_tokens INTEGER,
    cache_creation_tokens INTEGER,
    pid INTEGER,
    resume_generation INTEGER,
    head_start TEXT,
    head_end TEXT,
    workspace_start TEXT,
    workspace_end TEXT,
    vcs_start TEXT,
    vcs_end TEXT,
    origin_start TEXT,
    origin_end TEXT,
    branch_start TEXT,
    branch_end TEXT,
    repositories_start TEXT,
    repositories_end TEXT
);
CREATE INDEX IF NOT EXISTS spans_run ON spans(run_id, start_ts);
CREATE INDEX IF NOT EXISTS spans_node ON spans(node);
CREATE INDEX IF NOT EXISTS spans_status ON spans(status);
CREATE INDEX IF NOT EXISTS spans_start ON spans(start_ts DESC);
CREATE INDEX IF NOT EXISTS spans_summary
    ON spans(run_id, end_ts, workflow, repo, start_ts, status);
CREATE TABLE IF NOT EXISTS metrics (
    run_id TEXT NOT NULL DEFAULT '',
    name   TEXT NOT NULL,
    ts     REAL NOT NULL,
    value  REAL NOT NULL,
    attrs_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS metrics_run ON metrics(run_id, name, ts);
-- Series-major, for the one sweep that is not run-major: prune deletes the
-- never-archived gauges by name across every run, and metrics_run cannot serve
-- that — `name` is not its leading column, so the sweep degraded into a full
-- scan of the largest table in the file, once per chunk. Measured at 350s on a
-- 1 GB store; an index range scan instead.
CREATE INDEX IF NOT EXISTS metrics_name_ts ON metrics(name, ts);
CREATE TABLE IF NOT EXISTS logs (
    run_id   TEXT NOT NULL DEFAULT '',
    workflow TEXT NOT NULL DEFAULT '',
    run_dir  TEXT NOT NULL DEFAULT '',
    node     TEXT NOT NULL DEFAULT '',
    logger   TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'INFO',
    body     TEXT NOT NULL DEFAULT '',
    ts       REAL NOT NULL,
    trace_id TEXT NOT NULL DEFAULT '',
    attrs_json TEXT NOT NULL DEFAULT '{}',
    head     TEXT,
    workspace TEXT,
    vcs TEXT,
    origin TEXT,
    branch TEXT,
    repositories TEXT
);
CREATE INDEX IF NOT EXISTS logs_run ON logs(run_id, ts);
CREATE INDEX IF NOT EXISTS logs_node ON logs(run_id, node, ts);
CREATE INDEX IF NOT EXISTS logs_severity ON logs(severity);
CREATE TABLE IF NOT EXISTS turns (
    run_id     TEXT NOT NULL DEFAULT '',
    workflow   TEXT NOT NULL DEFAULT '',
    flow       TEXT NOT NULL DEFAULT '',
    node       TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    generation INTEGER,
    seq        INTEGER,
    ts         REAL NOT NULL DEFAULT 0,
    backend    TEXT NOT NULL DEFAULT '',
    source     TEXT NOT NULL DEFAULT '',
    path       TEXT NOT NULL DEFAULT '',
    bytes      INTEGER NOT NULL DEFAULT 0,
    sha256     TEXT NOT NULL DEFAULT '',
    head       TEXT,
    PRIMARY KEY (run_id, generation, seq, session_id)
);
CREATE INDEX IF NOT EXISTS turns_visit ON turns(run_id, node, generation, seq);
CREATE INDEX IF NOT EXISTS turns_session ON turns(session_id);
"""


def db_path() -> Path:
    """``$GROOM_DB`` (tests point it at a temp file), else the platform data dir — read per call so a test's env var takes effect without reimport."""
    env = os.environ.get("GROOM_DB")
    if env:
        return Path(env)
    return Path(user_data_dir("groom")) / "groom.db"


_ADDED_SPAN_COLUMNS = (
    ("run_dir", "TEXT NOT NULL DEFAULT ''"),
    ("duration_ms", "INTEGER"),
    ("total_cost_usd", "REAL"),
    ("input_tokens", "INTEGER"),
    ("output_tokens", "INTEGER"),
    ("cache_read_tokens", "INTEGER"),
    ("cache_creation_tokens", "INTEGER"),
    ("pid", "INTEGER"),
    ("resume_generation", "INTEGER"),
    ("head_start", "TEXT"),
    ("head_end", "TEXT"),
    ("workspace_start", "TEXT"),
    ("workspace_end", "TEXT"),
    ("vcs_start", "TEXT"),
    ("vcs_end", "TEXT"),
    ("origin_start", "TEXT"),
    ("origin_end", "TEXT"),
    ("branch_start", "TEXT"),
    ("branch_end", "TEXT"),
    ("repositories_start", "TEXT"),
    ("repositories_end", "TEXT"),
    ("est_cost_usd", "REAL"),
    ("priced_model", "TEXT"),
)


_ADDED_LOG_COLUMNS = (
    ("head", "TEXT"),
    ("workspace", "TEXT"),
    ("vcs", "TEXT"),
    ("origin", "TEXT"),
    ("branch", "TEXT"),
    ("repositories", "TEXT"),
)


_PROMOTED_SPAN_COLUMNS = (
    ("duration_ms", "duration_ms", int),
    ("total_cost_usd", "total_cost_usd", float),
    ("usage.input_tokens", "input_tokens", int),
    ("usage.output_tokens", "output_tokens", int),
    ("usage.cache_read_input_tokens", "cache_read_tokens", int),
    ("usage.cache_creation_input_tokens", "cache_creation_tokens", int),
    ("git.head.start", "head_start", str),
    ("git.head.end", "head_end", str),
    ("workspace.path.start", "workspace_start", str),
    ("workspace.path.end", "workspace_end", str),
    ("workspace.vcs.start", "vcs_start", str),
    ("workspace.vcs.end", "vcs_end", str),
    ("git.origin.start", "origin_start", str),
    ("git.origin.end", "origin_end", str),
    ("git.branch.start", "branch_start", str),
    ("git.branch.end", "branch_end", str),
    ("workhorse.repositories.start", "repositories_start", str),
    ("workhorse.repositories.end", "repositories_end", str),
)


_PROMOTED_SPAN_FIELDS = ("pid", "resume_generation")


_DERIVED_SPAN_COLUMNS = ("est_cost_usd", "priced_model")


_SPAN_VALUE_COLUMNS = (
    *(column for _key, column, _cast in _PROMOTED_SPAN_COLUMNS),
    *_PROMOTED_SPAN_FIELDS,
    *_DERIVED_SPAN_COLUMNS,
)


def _promoted(span: dict[str, Any], attrs: dict[str, Any]) -> tuple[Any, ...]:
    """The promoted and derived columns' values for one span, in `_SPAN_VALUE_COLUMNS` order."""
    values: dict[str, Any] = {}
    for key, column, cast in _PROMOTED_SPAN_COLUMNS:
        raw = attrs.get(key)
        try:
            values[column] = None if raw is None or isinstance(raw, bool) else cast(raw)
        except (TypeError, ValueError):
            values[column] = None
    for field in _PROMOTED_SPAN_FIELDS:
        raw = span.get(field)
        try:
            values[field] = None if raw is None else int(raw)
        except (TypeError, ValueError):
            values[field] = None
    model = str(attrs.get("model") or "")
    values["est_cost_usd"] = _estimated(model, values)
    values["priced_model"] = model if values["est_cost_usd"] is not None else None
    return tuple(values[column] for column in _SPAN_VALUE_COLUMNS)


def _estimated(model: str, tokens: dict[str, Any]) -> float | None:
    """This turn's tokens at the rate card, or NULL when the model is not in it."""
    return prices.estimate(
        model,
        tokens.get("input_tokens"),
        tokens.get("output_tokens"),
        tokens.get("cache_read_tokens"),
        tokens.get("cache_creation_tokens"),
    )


def _add_columns(
    conn: sqlite3.Connection, table: str, added: tuple[tuple[str, str], ...]
) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    for column, decl in added:
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")  # noqa: S608


def _migrate(conn: sqlite3.Connection) -> None:
    for table, added in (
        ("spans", _ADDED_SPAN_COLUMNS),
        ("logs", _ADDED_LOG_COLUMNS),
    ):
        _add_columns(conn, table, added)


@dataclass(frozen=True, slots=True)
class _Table:
    """A table outside the telemetry schema, created by the module that owns it."""

    name: str
    ddl: str
    added: tuple[tuple[str, str], ...]

    def create(self, conn: sqlite3.Connection) -> None:
        conn.executescript(self.ddl)
        _add_columns(conn, self.name, self.added)


_TABLES: dict[str, _Table] = {}


def prepare(conn: sqlite3.Connection) -> None:
    """Give ``conn`` groom's schema, its migrations and every registered table."""
    conn.executescript(_SCHEMA)
    _migrate(conn)
    for table in _TABLES.values():
        table.create(conn)
