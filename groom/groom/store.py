"""Embedded SQLite persistence for telemetry — the durable, searchable half of
groom's collector role (stdlib ``sqlite3``, no database server).

The in-memory ring in :mod:`groom.state` stays the hot cache for the live
dashboard and alert-rule state; this file is the queryable fleet index that
survives ``groom serve`` restarts. Each run's own ``events.jsonl`` on disk
remains the append-only record-of-truth — SQLite exists for cross-run search
(slowest nodes, error spans, cost per run, who cap-waited), not as the primary
record. Spans older than the retention window are pruned to bound growth.

groom is single-process/single-event-loop and writes are single-statement
inserts, so a plain module-level connection with autocommit is enough — no
pool, no locks (WAL mode keeps concurrent CLI reads from blocking the server).
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

# Days of span/metric history to keep; pruned at startup and on a periodic tick.
RETENTION_DAYS = float(os.environ.get("GROOM_RETENTION_DAYS", "14"))
# How far back the fleet/telemetry views (run_summaries, live_status) scan. The
# whole DB is retained for `RETENTION_DAYS` and stays queryable with raw SQL, but a
# live-ops dashboard only wants recent runs, and bounding the scan here is what keeps
# these queries from doing a full-table GROUP BY / window-function pass that grows
# with total history rather than with what's on screen. Default 24h.
ACTIVE_WINDOW_S = float(os.environ.get("GROOM_ACTIVE_WINDOW_S", "86400"))
# A hard ceiling on rows the live_status window function returns, so a pathological
# metric-cardinality run can't make one query materialize an unbounded result set.
_LIVE_STATUS_CAP = 500
# Logs are one row per line, not one per node visit, so they outgrow spans by
# orders of magnitude on a long run — hence a separate, shorter default window.
LOG_RETENTION_DAYS = float(os.environ.get("GROOM_LOG_RETENTION_DAYS", "3"))
# Pure-liveness counters get a shorter window still. They tick every ~10s per open
# node for the whole life of a run, which on a week-long run is millions of rows:
# in one real store `workhorse.run.heartbeat` alone was 1.77M of 2.21M metric rows,
# 1.23M of them from a single run. Nothing reads their history — the alert rules
# fold heartbeats into an in-memory cache at ingest (groom.alerts.ingest_metrics)
# and `live_status` reads only the newest point per (run_id, name) — so retaining
# a fortnight of them buys nothing and costs most of the file. The *gauges*
# (idle_s, elapsed_s, node.active) are excluded: their history is diagnostic (a
# climbing idle_s is how a wedged turn looks) and they are two orders of magnitude
# smaller.
LIVENESS_RETENTION_DAYS = float(os.environ.get("GROOM_LIVENESS_RETENTION_DAYS", "1"))
_LIVENESS_METRICS = (
    "workhorse.run.heartbeat",
    "workhorse.turn.heartbeat",
    "workhorse.cap_wait.heartbeat",
)

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
    resume_generation INTEGER
);
CREATE INDEX IF NOT EXISTS spans_run ON spans(run_id, start_ts);
CREATE INDEX IF NOT EXISTS spans_node ON spans(node);
CREATE INDEX IF NOT EXISTS spans_status ON spans(status);
CREATE TABLE IF NOT EXISTS metrics (
    run_id TEXT NOT NULL DEFAULT '',
    name   TEXT NOT NULL,
    ts     REAL NOT NULL,
    value  REAL NOT NULL,
    attrs_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS metrics_run ON metrics(run_id, name, ts);
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
    attrs_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS logs_run ON logs(run_id, ts);
CREATE INDEX IF NOT EXISTS logs_node ON logs(run_id, node, ts);
CREATE INDEX IF NOT EXISTS logs_severity ON logs(severity);
"""

_conn: sqlite3.Connection | None = None


def db_path() -> Path:
    """``$GROOM_DB`` (tests point it at a temp file), else the platform data
    dir — read per call so a test's env var takes effect without reimport."""
    env = os.environ.get("GROOM_DB")
    if env:
        return Path(env)
    return Path(user_data_dir("groom")) / "groom.db"


# Columns added to `spans` after the table first shipped. CREATE TABLE IF NOT
# EXISTS silently does nothing on an existing DB, so a new column has to be
# ALTERed in or every query naming it fails on a pre-existing groom.db.
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
)

# OTel attribute key -> the `spans` column it is promoted to. OTel's attribute model
# is a flat dict whose keys merely *look* dotted, so `usage.output_tokens` is stored
# in attrs_json as a literal key with a dot in it and
# `json_extract(attrs_json,'$.usage.output_tokens')` silently returns NULL — SQLite
# reads the dot as navigation. Only `'$."usage.output_tokens"'` works. Rather than
# make every caller remember that, the handful of fields every cost query wants get
# real columns. The rest stay in attrs_json (quote the key), and the promoted ones
# stay there too, so queries written against the old shape keep working.
_PROMOTED_SPAN_COLUMNS = (
    ("duration_ms", "duration_ms", int),
    ("total_cost_usd", "total_cost_usd", float),
    ("usage.input_tokens", "input_tokens", int),
    ("usage.output_tokens", "output_tokens", int),
    ("usage.cache_read_input_tokens", "cache_read_tokens", int),
    ("usage.cache_creation_input_tokens", "cache_creation_tokens", int),
)

#: Promoted from the decoded span record rather than from its OTel attributes — these
#: two are *resource* attributes, which `otlp.parse_traces` lifts into named fields.
_PROMOTED_SPAN_FIELDS = ("pid", "resume_generation")


def _promoted(span: dict[str, Any], attrs: dict[str, Any]) -> tuple[Any, ...]:
    """The promoted columns' values for one span, in `_PROMOTED_SPAN_COLUMNS` order.

    A missing or unparseable field yields NULL, never 0. Workhorse's normalizer draws
    the same distinction on purpose (`runner/usage.py`): a harness that does not report
    money reports nothing rather than `0.0`, because averaging a real zero together
    with an unknown understates spend. Coercing to 0 here would throw that away at the
    last step.
    """
    values: list[Any] = []
    for key, _column, cast in _PROMOTED_SPAN_COLUMNS:
        raw = attrs.get(key)
        try:
            values.append(None if raw is None or isinstance(raw, bool) else cast(raw))
        except (TypeError, ValueError):
            values.append(None)
    for field in _PROMOTED_SPAN_FIELDS:
        raw = span.get(field)
        try:
            values.append(None if raw is None else int(raw))
        except (TypeError, ValueError):
            values.append(None)
    return tuple(values)


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(spans)")}
    for column, decl in _ADDED_SPAN_COLUMNS:
        if column not in existing:
            conn.execute(f"ALTER TABLE spans ADD COLUMN {column} {decl}")  # noqa: S608
    conn.commit()


def _connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        path = db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(_SCHEMA)
        _migrate(_conn)
    return _conn


def reset() -> None:
    """Close the module connection so the next call reopens (tests switch
    GROOM_DB between cases)."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


def insert_spans(spans: list[dict[str, Any]]) -> None:
    """Upsert decoded spans (see groom.otlp.parse_traces). INSERT OR REPLACE:
    an exporter retry re-sending a batch must not error or duplicate."""
    if not spans:
        return
    conn = _connection()
    promoted = ", ".join(
        [column for _key, column, _cast in _PROMOTED_SPAN_COLUMNS] + list(_PROMOTED_SPAN_FIELDS)
    )
    placeholders = ", ".join(
        "?" * (len(_PROMOTED_SPAN_COLUMNS) + len(_PROMOTED_SPAN_FIELDS))
    )
    conn.executemany(
        "INSERT OR REPLACE INTO spans (span_id, trace_id, parent_id, run_id, workflow,"
        " repo, branch, node, name, run_dir, start_ts, end_ts, status, attrs_json,"
        f" {promoted})"
        f" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, {placeholders})",
        [
            (
                s["span_id"], s["trace_id"], s.get("parent_id", ""), s.get("run_id", ""),
                s.get("workflow", ""), s.get("repo", ""), s.get("branch", ""),
                s.get("node", ""), s.get("name", ""), s.get("run_dir", ""),
                s.get("start_ts", 0.0), s.get("end_ts", 0.0), s.get("status", "UNSET"),
                json.dumps(s.get("attrs") or {}),
                *_promoted(s, s.get("attrs") or {}),
            )
            for s in spans
        ],
    )
    conn.commit()


def insert_metrics(points: list[dict[str, Any]]) -> None:
    if not points:
        return
    conn = _connection()
    conn.executemany(
        "INSERT INTO metrics (run_id, name, ts, value, attrs_json) VALUES (?, ?, ?, ?, ?)",
        [
            (
                p.get("run_id", ""), p["name"], p.get("ts", 0.0),
                float(p.get("value", 0.0)), json.dumps(p.get("attrs") or {}),
            )
            for p in points
        ],
    )
    conn.commit()


def insert_logs(records: list[dict[str, Any]]) -> None:
    """Append decoded log records (see groom.otlp.parse_logs).

    Plain INSERT, unlike spans: a log record has no id to key on, and the SDK's
    BatchLogRecordProcessor does not retry a delivered batch, so there is nothing
    to deduplicate against and no natural primary key to invent.
    """
    if not records:
        return
    conn = _connection()
    conn.executemany(
        "INSERT INTO logs (run_id, workflow, run_dir, node, logger, severity, body,"
        " ts, trace_id, attrs_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                r.get("run_id", ""), r.get("workflow", ""), r.get("run_dir", ""),
                r.get("node", ""), r.get("logger", ""), r.get("severity", "INFO"),
                r.get("body", ""), r.get("ts", 0.0), r.get("trace_id", ""),
                json.dumps(r.get("attrs") or {}),
            )
            for r in records
        ],
    )
    conn.commit()


# Ordered loudest-first; an index into this is "at least this severe".
_SEVERITY_ORDER = ("FATAL", "ERROR", "WARNING", "INFO", "DEBUG", "TRACE")


def query_logs(
    run: str = "",
    node: str = "",
    level: str = "",
    contains: str = "",
    limit: int = 200,
    before_ts: float | None = None,
) -> list[dict[str, Any]]:
    """The log search behind ``groom logs``, newest first.

    ``level`` is a floor, not an equality match — asking for WARNING and being
    shown warnings but no errors would be the opposite of useful. ``before_ts`` is
    the keyset cursor: pass the ``ts`` of the last row of the previous page to fetch
    the next, so a chatty run's logs page instead of loading a whole run at once.
    """
    where, params = [], []
    if run:
        where.append("run_id = ?")
        params.append(run)
    if node:
        where.append("node = ?")
        params.append(node)
    if level:
        wanted = level.strip().upper()
        if wanted in _SEVERITY_ORDER:
            keep = _SEVERITY_ORDER[: _SEVERITY_ORDER.index(wanted) + 1]
            where.append(f"severity IN ({','.join('?' * len(keep))})")
            params.extend(keep)
    if contains:
        where.append("body LIKE ?")
        params.append(f"%{contains}%")
    if before_ts is not None:
        where.append("ts < ?")
        params.append(float(before_ts))
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    conn = _connection()
    rows = conn.execute(
        f"SELECT run_id, workflow, run_dir, node, logger, severity, body, ts, trace_id,"  # noqa: S608
        f" attrs_json FROM logs {clause} ORDER BY ts DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [
        {**dict(row), "attrs": json.loads(row["attrs_json"] or "{}")} for row in rows
    ]


def _promoted_or_attr(column: str, key: str) -> str:
    """The promoted column, falling back to the attribute it was promoted from.

    The columns are populated at ingest and deliberately not backfilled, so every
    span already in the store has NULL in them. Without this fallback an aggregate
    would read as "this run cost nothing" for the whole retention window after the
    columns ship — a wrong answer, and a much worse one than a slow answer, since
    nothing about it looks like missing data.

    Note the quoting. OTel attribute keys are flat strings that merely look nested,
    so the literal key is `usage.output_tokens` and the JSON path has to quote it;
    unquoted, SQLite reads the dot as navigation and silently returns NULL.
    """
    return f"COALESCE({column}, json_extract(attrs_json, '$.\"{key}\"'))"


_cost = _promoted_or_attr("total_cost_usd", "total_cost_usd")
_duration = _promoted_or_attr("duration_ms", "duration_ms")
_output = _promoted_or_attr("output_tokens", "usage.output_tokens")


def node_costs(run: str = "", limit: int = 100) -> list[dict[str, Any]]:
    """Per-node agent spend for a run: where the money and the rework went.

    Only `agent_turn` spans are counted. A node span wraps its turn, so totalling
    both would double every figure; and a node with no turn under it (an in-process
    `self.call`) spent no agent money by definition.

    `turns_per_work_id` is the rework signal. A workflow stamps `work_id` as a label
    (the coder workflow uses the story slug), so a node that averages one turn per
    work item ran once per story and a node averaging four re-ran three times. That
    ratio, not the raw turn count, is what separates an expensive node from a
    *looping* one.

    Cost is summed over rows where it is non-NULL, and two counts say how trustworthy
    that sum is — because a harness can decline to price a turn in two different ways
    and only one of them is visible as a gap:

    * `cost_turns` — turns carrying any cost at all. codex reports **none** under
      subscription auth, so on a codex run this is 0 and every `cost_usd` is NULL.
    * `zero_cost_turns` — turns that reported cost `0` *while reporting output tokens*.
      This is the dangerous one. opencode's cost depends on the provider behind it, not
      on opencode: through OpenRouter a turn reports real money, and through a
      subscription OAuth provider the identical turn reports a literal `0`. A NULL is
      excluded from the sum and shows up as a gap; a zero is summed, so a run that
      spent forty minutes totals $0.00 and looks complete. A turn that emitted tokens
      did not cost nothing — it was not priced. (A genuinely free model reports the
      same way, which is why this is surfaced rather than corrected.)

    So the unit of cost coverage is **harness × provider**, not harness. `backends`
    names who ran each node; the CLI says out loud when either count implies the total
    is partial.
    """
    clauses, params = ["name = 'agent_turn'"], []
    if run:
        clauses.append("run_id = ?")
        params.append(run)
    conn = _connection()
    rows = conn.execute(
        "SELECT node,"  # noqa: S608 — clauses are literals; every value is bound
        " COUNT(*) AS turns,"
        " COUNT(DISTINCT json_extract(attrs_json, '$.work_id')) AS work_items,"
        f" SUM({_cost} IS NOT NULL) AS cost_turns,"
        f" SUM({_cost} = 0 AND COALESCE({_output}, 0) > 0) AS zero_cost_turns,"
        " GROUP_CONCAT(DISTINCT json_extract(attrs_json, '$.backend')) AS backends,"
        f" SUM({_cost}) AS cost_usd,"
        f" SUM({_duration}) / 60000.0 AS minutes,"
        f" SUM({_output}) AS output_tokens"
        f" FROM spans WHERE {' AND '.join(clauses)}"
        # Minutes, not turns, breaks the tie: on a run where nothing priced itself the
        # cost key is uniformly NULL, and ranking the remainder by turn count would put
        # a node with many cheap turns above one that spent an hour in three.
        " GROUP BY node ORDER BY cost_usd DESC NULLS LAST, minutes DESC LIMIT ?",
        (*params, max(1, min(int(limit), 1000))),
    ).fetchall()
    total = sum(row["cost_usd"] or 0.0 for row in rows)
    return [
        {
            **dict(row),
            "share": (row["cost_usd"] or 0.0) / total if total else 0.0,
            "turns_per_work_id": (
                row["turns"] / row["work_items"] if row["work_items"] else None
            ),
        }
        for row in rows
    ]


_VERDICT_SUFFIXES = ("_verdict", "_disposition", "_failure_class", "_refutation_class")


def _profile_turn_summary(turns: list[dict[str, Any]]) -> dict[str, Any]:
    work_items = {
        str(value)
        for turn in turns
        if (value := turn["attrs"].get("work_id") or turn["attrs"].get("wf.work_id"))
    }
    costs = [float(turn["profile_cost_usd"]) for turn in turns if turn["profile_cost_usd"] is not None]
    zeroed = sum(
        turn["profile_cost_usd"] == 0 and (turn["profile_output_tokens"] or 0) > 0
        for turn in turns
    )
    seconds = sum(max(0.0, turn["end_ts"] - turn["start_ts"]) for turn in turns)
    return {
        "turns": len(turns),
        "work_items": len(work_items),
        "turns_per_work": len(turns) / len(work_items) if work_items else None,
        "agent_s": seconds,
        "cost_usd": sum(costs) if costs else None,
        "cost_turns": len(costs),
        "missing_cost_turns": len(turns) - len(costs),
        "cost_coverage": len(costs) / len(turns) if turns else None,
        "zero_cost_output_turns": zeroed,
        "output_tokens": sum(turn["profile_output_tokens"] or 0 for turn in turns),
        "backends": sorted(
            {
                str(turn["attrs"].get("backend"))
                for turn in turns
                if turn["attrs"].get("backend")
            }
        ),
    }


def _profile_groups(
    turns: list[dict[str, Any]], *, verdicts: bool
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for turn in turns:
        for dimension, raw in turn["attrs"].items():
            if not isinstance(raw, str) or not raw:
                continue
            is_verdict = dimension.endswith(_VERDICT_SUFFIXES)
            is_attempt = (
                "." in dimension
                and raw.isdigit()
                and str(int(raw)) == raw
                and not dimension.startswith("workhorse.")
            )
            if (verdicts and is_verdict) or (not verdicts and is_attempt):
                grouped[(dimension, raw, turn["node"])].append(turn)

    rows = []
    for (dimension, value, node), members in grouped.items():
        rows.append(
            {
                "dimension": dimension,
                "value": value,
                "node": node,
                **_profile_turn_summary(members),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["dimension"],
            int(row["value"]) if not verdicts else row["value"],
            row["node"],
        ),
    )


def _span_category(
    span: dict[str, Any], parent_keys: set[tuple[str, str]]
) -> str:
    attrs = span["attrs"]
    kind = str(attrs.get("workhorse.span_kind") or "")
    if kind == "wait":
        return f"wait:{attrs.get('workhorse.wait_kind') or 'unknown'}"
    if span["name"] == "agent_turn":
        return "agent"
    if kind == "infra":
        return "infra"
    has_child = (span["trace_id"], span["span_id"]) in parent_keys
    if not has_child and not kind and not span["name"].startswith("run:"):
        return "deterministic"
    return ""


def _resume_intervals(spans: list[dict[str, Any]]) -> list[tuple[float, float]]:
    sessions: dict[str, dict[str, Any]] = {}
    for span in spans:
        trace = span["trace_id"]
        session = sessions.setdefault(
            trace,
            {"start": span["start_ts"], "end": span["end_ts"], "generation": None},
        )
        session["start"] = min(session["start"], span["start_ts"])
        session["end"] = max(session["end"], span["end_ts"])
        generation = span.get("resume_generation")
        if isinstance(generation, int) and generation > 0:
            session["generation"] = generation

    ordered = sorted(sessions.values(), key=lambda session: session["start"])
    gaps = []
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if (
            current["start"] > previous["end"]
            and previous["generation"] is not None
            and current["generation"] is not None
            and previous["generation"] != current["generation"]
        ):
            gaps.append((previous["end"], current["start"]))
    return gaps


def _profile_time_partition(
    spans: list[dict[str, Any]], start_ts: float, end_ts: float
) -> dict[str, Any]:
    events: dict[float, list[tuple[str, int]]] = defaultdict(list)
    parent_keys = {
        (span["trace_id"], span["parent_id"])
        for span in spans
        if span["parent_id"]
    }
    for span in spans:
        category = _span_category(span, parent_keys)
        if category and span["end_ts"] > span["start_ts"]:
            events[span["start_ts"]].append((category, 1))
            events[span["end_ts"]].append((category, -1))
    for gap_start, gap_end in _resume_intervals(spans):
        events[gap_start].append(("resume_gap", 1))
        events[gap_end].append(("resume_gap", -1))

    points = sorted({start_ts, end_ts, *events})
    active: Counter[str] = Counter()
    totals: Counter[str] = Counter()
    waits: Counter[str] = Counter()
    for left, right in zip(points, points[1:], strict=False):
        for category, delta in events.get(left, []):
            active[category] += delta
        duration = max(0.0, right - left)
        wait_kinds = sorted(
            category.removeprefix("wait:")
            for category, count in active.items()
            if category.startswith("wait:") and count > 0
        )
        if active["resume_gap"] > 0:
            totals["resume_gap"] += duration
        elif wait_kinds:
            kind = wait_kinds[0] if len(wait_kinds) == 1 else "overlap"
            totals["wait"] += duration
            waits[kind] += duration
        elif active["agent"] > 0:
            totals["agent"] += duration
        elif active["infra"] > 0:
            totals["infra"] += duration
        elif active["deterministic"] > 0:
            totals["deterministic"] += duration
        else:
            totals["unclassified"] += duration

    wall = max(0.0, end_ts - start_ts)
    return {
        "wall": wall,
        "agent": totals["agent"],
        "deterministic": totals["deterministic"],
        "infra": totals["infra"],
        "wait": totals["wait"],
        "waits_by_kind": dict(sorted(waits.items())),
        "resume_gap": totals["resume_gap"],
        "unclassified": totals["unclassified"],
    }


def run_profile(run: str) -> dict[str, Any] | None:
    """Partition one run's retained wall time and aggregate its agent rework.

    This reads every span for the named run directly. Reusing :func:`query_spans`
    would silently truncate a long run at its search-page limit and produce a precise-
    looking partial total.
    """
    if not run:
        return None
    rows = _connection().execute(
        f"SELECT {_SPAN_COLUMNS}, duration_ms AS profile_duration_ms,"  # noqa: S608
        f" {_cost} AS profile_cost_usd, {_output} AS profile_output_tokens,"
        " resume_generation FROM spans WHERE run_id = ? ORDER BY start_ts",
        (run,),
    ).fetchall()
    spans = [
        {**dict(row), "attrs": json.loads(row["attrs_json"] or "{}")} for row in rows
    ]
    metric_bounds = _connection().execute(
        "SELECT MIN(ts) AS first_ts, MAX(ts) AS last_ts FROM metrics WHERE run_id = ?",
        (run,),
    ).fetchone()
    metric_start = metric_bounds["first_ts"] if metric_bounds else None
    metric_end = metric_bounds["last_ts"] if metric_bounds else None
    if not spans and metric_start is None:
        return None

    starts = [span["start_ts"] for span in spans]
    ends = [span["end_ts"] for span in spans]
    if metric_start is not None:
        starts.append(metric_start)
        ends.append(metric_end)
    start_ts, end_ts = min(starts), max(ends)
    turns = [span for span in spans if span["name"] == "agent_turn"]
    return {
        "run_id": run,
        "workflow": next((span["workflow"] for span in spans if span["workflow"]), ""),
        "observed_start_ts": start_ts,
        "observed_end_ts": end_ts,
        "time_s": _profile_time_partition(spans, start_ts, end_ts),
        "work": _profile_turn_summary(turns),
        "attempt_groups": _profile_groups(turns, verdicts=False),
        "verdict_groups": _profile_groups(turns, verdicts=True),
    }


# The spans-table columns, named explicitly rather than `SELECT *` so a schema
# migration can't silently change a query result's shape.
_SPAN_COLUMNS = (
    "span_id, trace_id, parent_id, run_id, workflow, repo, branch, node, name,"
    " run_dir, start_ts, end_ts, status, attrs_json"
)


def query_spans(
    run: str = "",
    node: str = "",
    status: str = "",
    slower_than: float | None = None,
    limit: int = 200,
    before_ts: float | None = None,
) -> list[dict[str, Any]]:
    """The /traces search: filter the spans table, newest first. ``slower_than``
    is a minimum duration in seconds. ``before_ts`` is the keyset cursor — the
    ``start_ts`` of the last row of the previous page — so a broad query pages
    rather than materializing everything under one big LIMIT. Raw SQL against
    groom.db remains the ad-hoc escape hatch; this covers the common questions."""
    clauses, params = ["1=1"], []
    if run:
        clauses.append("run_id = ?")
        params.append(run)
    if node:
        clauses.append("node = ?")
        params.append(node)
    if status:
        clauses.append("status = ?")
        params.append(status.upper())
    if slower_than is not None:
        clauses.append("(end_ts - start_ts) >= ?")
        params.append(float(slower_than))
    if before_ts is not None:
        clauses.append("start_ts < ?")
        params.append(float(before_ts))
    params.append(max(1, min(int(limit), 1000)))
    rows = _connection().execute(
        f"SELECT {_SPAN_COLUMNS} FROM spans WHERE {' AND '.join(clauses)}"  # noqa: S608 - literals
        " ORDER BY start_ts DESC LIMIT ?",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def run_summaries(
    limit: int = 50, now: float | None = None, run: str = ""
) -> list[dict[str, Any]]:
    """One row per run for the fleet/telemetry view: workflow, span window, and
    span/error counts. ``run`` narrows it to a single run — the detail pane's
    question, answered by the same aggregate.

    Deliberately says nothing about whether the run is *running*. It used to,
    via ``MAX(name LIKE 'run:%') AS finished``, which is a claim history cannot
    support: a root span proves some session of this run_id ended, and since
    ``--resume-run`` reuses the run_id (it comes from the run dir), that stayed
    true forever — a resumed run read as finished while it was mid-node. Liveness
    is a recency question and only :func:`live_run_ids` answers it.

    Bounded to the last ``ACTIVE_WINDOW_S`` so the GROUP BY scans recent history
    rather than the whole retained table; older runs stay queryable via raw SQL."""
    cutoff = (now if now is not None else time.time()) - ACTIVE_WINDOW_S
    params: list[Any] = [cutoff]
    run_clause = ""
    if run:
        run_clause = "AND run_id = ?"
        params.append(run)
    params.append(max(1, min(int(limit), 500)))
    rows = _connection().execute(
        "SELECT run_id, MAX(workflow) AS workflow, MAX(repo) AS repo,"
        " MIN(start_ts) AS first_ts, MAX(end_ts) AS last_ts,"
        " COUNT(*) AS span_count,"
        " SUM(CASE WHEN status = 'ERROR' THEN 1 ELSE 0 END) AS error_count"
        f" FROM spans WHERE run_id != '' AND end_ts >= ? {run_clause} GROUP BY run_id"  # noqa: S608 - literal clause, bound values
        " ORDER BY last_ts DESC LIMIT ?",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


# The metrics that describe a run's LIVE state, as opposed to its history. Spans
# only export once they end, so for a run still in flight these are the whole
# picture: the trace of a hanging node does not exist yet and never will while it
# hangs.
_LIVE_METRICS = (
    "workhorse.run.heartbeat",
    "workhorse.node.elapsed_s",
    "workhorse.turn.idle_s",
    "workhorse.gas",
)

# How stale the last heartbeat may be before a run is presumed dead. Workhorse
# beats every ~10s, but the SDK's periodic reader only ships metrics every 60s by
# default, so anything under ~2 export intervals would flag healthy runs.
LIVE_AFTER_S = float(os.environ.get("GROOM_LIVE_AFTER_S", "180"))


def live_status(run: str = "", now: float | None = None) -> list[dict[str, Any]]:
    """Where each run is *right now*, newest heartbeat first.

    This is the question the spans table cannot answer. A node's span is written
    on completion, so the node a run is currently sitting in — the only one that
    matters when it will not finish — has no row anywhere in ``spans``. The
    heartbeat metric carries both the timestamp (is the process alive?) and the
    open node name (where is it?), so one query over ``metrics`` answers both.

    ``alive`` False means the process stopped emitting: dead, killed, or frozen.
    ``alive`` True with a large ``node_elapsed_s`` means the opposite failure —
    running fine, going nowhere.
    """
    now = now if now is not None else time.time()
    placeholders = ",".join("?" for _ in _LIVE_METRICS)
    params: list[Any] = list(_LIVE_METRICS)
    # Bound the window-function scan to recent points. A live run beats within
    # LIVE_AFTER_S (180s), so ACTIVE_WINDOW_S (24h) cannot hide one; without this the
    # CTE scanned every metric row ever ingested on each dashboard render.
    params.append(now - ACTIVE_WINDOW_S)
    run_clause = ""
    if run:
        run_clause = "AND run_id = ?"
        params.append(run)
    params.append(_LIVE_STATUS_CAP)
    rows = _connection().execute(
        # One row per (run, metric, attribute-set): the most recent point wins.
        f"""
        WITH latest AS (
            SELECT run_id, name, value, attrs_json, ts,
                   ROW_NUMBER() OVER (
                       PARTITION BY run_id, name ORDER BY ts DESC
                   ) AS rn
            FROM metrics
            WHERE name IN ({placeholders}) AND run_id != '' AND ts >= ? {run_clause}
        )
        SELECT run_id, name, value, attrs_json, ts FROM latest WHERE rn = 1
        LIMIT ?
        """,  # noqa: S608 - placeholders/clause are literals, values are bound
        params,
    ).fetchall()

    runs: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = runs.setdefault(
            row["run_id"],
            {
                "run_id": row["run_id"], "workflow": "", "run_dir": "", "node": "",
                "node_elapsed_s": 0.0, "turn_idle_s": 0.0, "gas": None,
                "last_beat_ts": 0.0, "alive": False,
            },
        )
        attrs = json.loads(row["attrs_json"] or "{}")
        if row["name"] == "workhorse.run.heartbeat":
            entry["last_beat_ts"] = row["ts"]
            entry["node"] = attrs.get("node", "")
            entry["alive"] = (now - row["ts"]) <= LIVE_AFTER_S
        elif row["name"] == "workhorse.node.elapsed_s":
            entry["node_elapsed_s"] = row["value"]
            entry["node"] = entry["node"] or attrs.get("node", "")
        elif row["name"] == "workhorse.turn.idle_s":
            entry["turn_idle_s"] = row["value"]
        elif row["name"] == "workhorse.gas":
            entry["gas"] = row["value"]

    # workflow/run_dir live on the resource, which only the spans table carries.
    for run_id, entry in runs.items():
        span = _connection().execute(
            "SELECT workflow, run_dir FROM spans WHERE run_id = ?"
            " ORDER BY start_ts DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        if span is not None:
            entry["workflow"] = span["workflow"]
            entry["run_dir"] = span["run_dir"]
    return sorted(runs.values(), key=lambda e: e["last_beat_ts"], reverse=True)


def live_run_ids(now: float | None = None) -> set[str]:
    """The run ids beating *right now* — the durable answer to the only liveness
    question that means anything.

    Read from the store rather than the in-memory hot cache on purpose: a groom
    that just restarted has an empty ``state.RUNS`` and would otherwise report
    every live run as not-running until each one's next export lands.
    """
    return {
        entry["run_id"] for entry in live_status(now=now) if entry.get("alive")
    }


# Path fragments that mark a run dir as a test process's, with no ambiguity:
# pytest's tmp_path factory roots every case under `pytest-of-<user>/`, and the
# workhorse/groom suites put their run dirs under `.workhorse-test/`. A path
# containing one of these is not a run anyone will come back to.
_TEST_RUN_DIR_MARKERS = ("/pytest-of-", "/.workhorse-test/", "/.groom-test/")

# `tempfile.mkdtemp`'s naming: `tmp` + random suffix, as a directory sitting
# directly in the temp root. This is the *heuristic* signal — a suite that builds
# its own scratch dir instead of using pytest's leaves no other trace — and it is
# why only the explicit purge consults it, never ingest.
_PY_TEMP_DIR = re.compile(r"^tmp[A-Za-z0-9_]{6,}$")


def _temp_roots() -> tuple[str, ...]:
    """Temp-dir prefixes a throwaway run dir sits under.

    ``/tmp`` is listed unconditionally, not just when it is this host's temp
    root: the producer may be a container while the collector is the host, and
    the run dir on the wire is the *producer's* path.
    """
    roots = {tempfile.gettempdir().rstrip("/"), "/tmp"}
    return tuple(f"{root}/" for root in sorted(roots) if root)


def is_test_run_dir(run_dir: str) -> bool:
    """Did this run dir certainly come from a test process?

    Deliberately narrow, because this is the predicate the ingest path drops on
    and a silent drop of real telemetry is worse than keeping some junk. Only
    the unambiguous markers count; ``/tmp`` alone does not.

    Workhorse already declines to export from a test process
    (``workhorse.otel._under_test``), so this is the collector's belt-and-braces
    half, covering producers on an older version or in a container.
    """
    if not run_dir:
        return False
    return any(marker in run_dir for marker in _TEST_RUN_DIR_MARKERS)


def is_scratch_run_dir(run_dir: str) -> bool:
    """Does this run dir look throwaway — a certain test dir, or a Python temp one?

    The wider net :func:`purge_test_runs` casts. It catches what
    :func:`is_test_run_dir` cannot: a suite that calls ``tempfile.mkdtemp``
    itself, which is how the biggest single junk run in a real store
    (150k+ spans) was written. It is a heuristic — a genuine run launched from a
    ``mkdtemp`` directory matches too — so it is confined to a command the
    operator runs deliberately and can preview with ``--dry-run``, rather than
    to the ingest path where the same guess would delete evidence unasked.
    """
    if is_test_run_dir(run_dir):
        return True
    for root in _temp_roots():
        if run_dir.startswith(root):
            return bool(_PY_TEMP_DIR.match(run_dir[len(root) :].split("/", 1)[0]))
    return False


def test_run_ids() -> set[str]:
    """The run ids whose run dir says they were throwaway (:func:`is_scratch_run_dir`).

    Classified in Python rather than SQL because the predicate is a path
    heuristic, not a LIKE pattern. Only ``spans`` and ``logs`` carry ``run_dir``
    — ``metrics`` does not — so a run that only ever emitted heartbeats before
    its first node completed is invisible here and is left alone.
    """
    conn = _connection()
    pairs: set[tuple[str, str]] = set()
    for table in ("spans", "logs"):
        pairs.update(
            (row["run_id"], row["run_dir"])
            for row in conn.execute(
                f"SELECT DISTINCT run_id, run_dir FROM {table} WHERE run_dir != ''"  # noqa: S608 - literal table name
            )
        )
    return {run_id for run_id, run_dir in pairs if run_id and is_scratch_run_dir(run_dir)}


# Bound on ids per DELETE, so a store holding thousands of test runs does not
# build one statement with thousands of parameters (SQLite caps them).
_PURGE_CHUNK = 500


def purge_test_runs(dry_run: bool = False, vacuum: bool = True) -> dict[str, int]:
    """Delete every span/metric/log belonging to a test run.

    Returns ``{"runs": n, "spans": n, "metrics": n, "logs": n}`` — with
    ``dry_run`` the same counts are reported and nothing is deleted.

    ``vacuum`` rewrites the file afterwards: SQLite keeps freed pages for reuse,
    so a store where test runs were most of the rows stays its old size on disk
    until it is vacuumed, which is the visible half of the problem this solves.
    """
    conn = _connection()
    run_ids = sorted(test_run_ids())
    counts = {"runs": len(run_ids), "spans": 0, "metrics": 0, "logs": 0}
    for start in range(0, len(run_ids), _PURGE_CHUNK):
        chunk = run_ids[start : start + _PURGE_CHUNK]
        marks = ",".join("?" * len(chunk))
        for table in ("spans", "metrics", "logs"):
            verb = "SELECT COUNT(*) AS n FROM" if dry_run else "DELETE FROM"
            cursor = conn.execute(f"{verb} {table} WHERE run_id IN ({marks})", chunk)  # noqa: S608 - literal table name, bound values
            counts[table] += cursor.fetchone()["n"] if dry_run else cursor.rowcount
    if dry_run:
        return counts
    conn.commit()
    if vacuum and counts["runs"]:
        conn.execute("VACUUM")
    return counts


def prune(retention_days: float = RETENTION_DAYS, now: float | None = None) -> int:
    """Drop spans/metrics/logs older than the retention window; rows removed.

    Logs get their own, shorter window (``GROOM_LOG_RETENTION_DAYS``): they are
    the highest-volume table by a wide margin — one row per log line rather than
    one per node visit — so holding them for the span retention would let a few
    chatty week-long runs dominate the file. The liveness counters get a shorter
    one again (``GROOM_LIVENESS_RETENTION_DAYS``, see ``_LIVENESS_METRICS``), for
    the same reason one step further: they are the highest-volume *metric* and the
    only one nothing reads the history of.
    """
    stamp = now if now is not None else time.time()
    cutoff = stamp - retention_days * 86400
    conn = _connection()
    removed = conn.execute("DELETE FROM spans WHERE end_ts < ?", (cutoff,)).rowcount
    removed += conn.execute("DELETE FROM metrics WHERE ts < ?", (cutoff,)).rowcount
    # Never longer than the table-wide window: a liveness setting above it would
    # otherwise read as "keep these longer", which the DELETE above cannot honour.
    liveness_cutoff = stamp - min(LIVENESS_RETENTION_DAYS, retention_days) * 86400
    placeholders = ",".join("?" * len(_LIVENESS_METRICS))
    removed += conn.execute(
        f"DELETE FROM metrics WHERE ts < ? AND name IN ({placeholders})",  # noqa: S608
        (liveness_cutoff, *_LIVENESS_METRICS),
    ).rowcount
    removed += conn.execute(
        "DELETE FROM logs WHERE ts < ?", (stamp - LOG_RETENTION_DAYS * 86400,)
    ).rowcount
    conn.commit()
    return removed
