"""The runs that ended: one stored summary per run, so History lists without opening any run's records."""

from __future__ import annotations

import json
import logging
import shlex
import sqlite3
import time
from pathlib import Path
from typing import Any

from workhorse.records import LaunchRecord, parse_launch_record

from groom import alerts, archive, docker_io, figures, flows, medians, projection, state, store
from groom.store import STORE, read_connection, reading, register_table, resilient

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS run_summary (
    run_id          TEXT PRIMARY KEY,
    workflow        TEXT NOT NULL DEFAULT '',
    repo            TEXT NOT NULL DEFAULT '',
    branch          TEXT NOT NULL DEFAULT '',
    run_dir         TEXT NOT NULL DEFAULT '',
    native          INTEGER,
    state           TEXT NOT NULL DEFAULT 'pending',
    ending          TEXT NOT NULL DEFAULT '',
    error_class     TEXT NOT NULL DEFAULT '',
    failing_node    TEXT NOT NULL DEFAULT '',
    resume_command  TEXT NOT NULL DEFAULT '',
    resume_container INTEGER NOT NULL DEFAULT 0,
    resume_read     INTEGER NOT NULL DEFAULT 0,
    started_ts      REAL,
    ended_ts        REAL,
    last_ts         REAL NOT NULL DEFAULT 0,
    active_s        REAL NOT NULL DEFAULT 0,
    wall_s          REAL NOT NULL DEFAULT 0,
    cost_usd        REAL,
    est_usd         REAL,
    priced_turns    INTEGER NOT NULL DEFAULT 0,
    turns           INTEGER NOT NULL DEFAULT 0,
    items_done      INTEGER,
    items_total     INTEGER,
    gates           INTEGER NOT NULL DEFAULT 0,
    problems        INTEGER NOT NULL DEFAULT 0,
    sessions_json   TEXT NOT NULL DEFAULT '[]',
    nodes_json      TEXT NOT NULL DEFAULT '[]',
    computed_at     REAL NOT NULL DEFAULT 0,
    archived        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS run_summary_ended ON run_summary(ended_ts DESC);
"""

_ADDED = (
    ("resume_container", "INTEGER NOT NULL DEFAULT 0"),
    ("resume_read", "INTEGER NOT NULL DEFAULT 0"),
    ("archived", "INTEGER NOT NULL DEFAULT 0"),
)

register_table("run_summary", _DDL, _ADDED)

READY, PENDING, UNREADABLE = "ready", "pending", "unreadable"

LABELS = {
    "success": "success",
    "gave-up": "gave up",
    "failed": "failed",
    "interrupted": "interrupted",
    "crashed": "crashed",
    "none": "no ending recorded",
}

ENDING_TOLERANCE_S = 60.0

DERIVED_TOKEN = 8

LAUNCH_FILE = "launch.json"

RUNS_MOUNT = "/runs/"

CONTINUABLE = ("failed", "interrupted", "crashed")
STOPPED = (*CONTINUABLE, "gave-up")
RESUME_READ = 2

_TERMINAL_ENDINGS = {"fail": "failed", "interrupted": "interrupted", "aborted": "crashed"}

_ROOT = "name >= 'run:' AND name < 'run;'"
_TERMINAL = "json_extract(attrs_json, '$.\"workhorse.terminal\"')"


def ending_of(terminal: str, gave_up: bool = False) -> str | None:
    """The ending a recorded terminal stands for, or None when it is not an ending: ``reload`` continues through exec, and an absent or unknown terminal records none."""
    if terminal in alerts.CLEAN_TERMINALS:
        return "gave-up" if gave_up else "success"
    return _TERMINAL_ENDINGS.get(terminal)


def _closed(root_ts: float, last_ts: float) -> bool:
    return bool(root_ts) and root_ts + ENDING_TOLERANCE_S >= last_ts


def _named(repo: str | None, workspace: str | None) -> str:
    return repo or projection.workspace_name(workspace or "")


def _silent(last_ts: float, now: float) -> bool:
    return now - last_ts > alerts.dead_after_s()


@reading
def _last_records() -> dict[str, dict[str, Any]]:
    """Per run, its last span's end and the identity its spans carry. Reads the span index, not the records."""
    rows = read_connection().execute(
        "SELECT run_id, MAX(end_ts) AS last_ts, MAX(workflow) AS workflow, MAX(repo) AS repo,"
        " MAX(workspace_start) AS workspace, MAX(branch) AS branch, MAX(branch_start) AS branch_start"
        " FROM spans WHERE run_id != '' GROUP BY run_id"
    )
    return {row["run_id"]: dict(row) for row in rows}


@reading
def _latest_roots() -> dict[str, tuple[float, str]]:
    """Per run, the end and the recorded terminal of its latest root span."""
    rows = read_connection().execute(
        f"SELECT run_id, end_ts, COALESCE({_TERMINAL}, '') AS terminal FROM spans"  # noqa: S608 - literals only
        f" WHERE run_id != '' AND {_ROOT} ORDER BY end_ts"
    )
    return {row["run_id"]: (row["end_ts"], row["terminal"]) for row in rows}


@reading
def _stored() -> dict[str, dict[str, Any]]:
    rows = read_connection().execute("SELECT run_id, state, last_ts, ended_ts, ending, resume_read FROM run_summary")
    return {row["run_id"]: dict(row) for row in rows}


@reading
def stored(run_id: str) -> dict[str, Any] | None:
    """One run's stored summary row, or None when it has none."""
    row = read_connection().execute("SELECT * FROM run_summary WHERE run_id = ?", (run_id,)).fetchone()
    return dict(row) if row is not None else None


@resilient
def _insert_pending(rows: list[tuple[str, str, str, str, float]]) -> None:
    with STORE.writing() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO run_summary (run_id, workflow, repo, branch, state, ended_ts, last_ts)"
            " VALUES (?, ?, ?, ?, 'pending', ?, 0)",
            rows,
        )


@resilient
def _forget_ended(run_ids: list[str]) -> None:
    with STORE.writing() as conn:
        conn.executemany("UPDATE run_summary SET ended_ts = NULL WHERE run_id = ?", [(run_id,) for run_id in run_ids])


def discover(now: float | None = None) -> list[str]:
    """Find the runs whose summary is missing or out of date, give each a pending row, and return their ids newest first. A run that has records after its summary leaves History here."""
    now = now if now is not None else time.time()
    last = _last_records()
    roots = _latest_roots()
    stored = _stored()
    wanted: list[tuple[float, str]] = []
    pending: list[tuple[str, str, str, str, float]] = []
    returned: list[str] = []
    for run_id, found in last.items():
        last_ts = float(found["last_ts"] or 0.0)
        root_ts, terminal = roots.get(run_id, (0.0, ""))
        ended = _closed(root_ts, last_ts) and ending_of(terminal) is not None
        silent = _silent(last_ts, now)
        row = stored.get(run_id)
        if row is None:
            if ended or silent:
                repo = _named(found["repo"], found["workspace"])
                branch = found["branch"] or found["branch_start"] or ""
                pending.append((run_id, found["workflow"] or "", repo, branch, root_ts if ended else last_ts))
                wanted.append((last_ts, run_id))
            continue
        if row["state"] == PENDING or abs(float(row["last_ts"]) - last_ts) > 1e-6 or (row["ending"] in STOPPED and row["resume_read"] < RESUME_READ):
            if ended or silent:
                wanted.append((last_ts, run_id))
            elif row["ended_ts"] is not None:
                returned.append(run_id)
        elif row["ended_ts"] is None and silent:
            wanted.append((last_ts, run_id))
    if pending:
        _insert_pending(pending)
    if returned:
        _forget_ended(returned)
    return [run_id for _, run_id in sorted(wanted, reverse=True)]


def _json_safe(value: Any) -> str:
    return json.dumps(value, default=str)


def _items(progress: tuple[int, int] | None, work_items: int) -> tuple[int | None, int | None]:
    if progress is not None:
        return progress
    return (work_items, work_items) if work_items else (None, None)


def _command(launch: LaunchRecord | None) -> str:
    """The recorded resume argv as one shell line that works from any folder: a `cd` into the recorded cwd, when there is one, then the argv."""
    if launch is None or not launch.resume_argv:
        return ""
    argv = shlex.join(launch.resume_argv)
    return f"cd {shlex.quote(launch.cwd)} && {argv}" if launch.cwd else argv


def _launch_record(run_id: str, run_dir: str) -> LaunchRecord | None:
    """What the run recorded at launch: from its folder for a native run, and from the runs volume of its container while the volume exists."""
    text: str | None = None
    if run_dir and Path(run_dir).is_dir():
        try:
            text = (Path(run_dir) / LAUNCH_FILE).read_text()
        except OSError:
            return None
    elif run_dir.startswith(RUNS_MOUNT):
        container = next((one for one in state.WORKFLOWS.values() if one.run_id == run_id and one.runs_volume), None)
        if container is not None:
            text = docker_io.read_file(container.runs_volume, f"{run_dir.removeprefix(RUNS_MOUNT).strip('/')}/{LAUNCH_FILE}")
    if not text:
        return None
    try:
        return parse_launch_record(text)
    except ValueError:
        return None


def summarize(run_id: str, now: float | None = None) -> dict[str, Any] | None:
    """One run's summary row, from the store functions behind ``groom cost`` and ``groom profile``, or None when the run has no spans."""
    now = now if now is not None else time.time()
    spans = store.run_turn_spans(run_id)
    if not spans:
        return None
    roots = [span for span in spans if span["name"].startswith("run:")]
    last_ts = max(span["end_ts"] for span in spans)
    root = max(roots, key=lambda span: span["end_ts"], default=None)
    terminal = str(root["attrs"].get("workhorse.terminal") or "") if root else ""
    giveup = alerts.giveup_nodes()
    gave_up = any(span["node"] in giveup for span in spans)
    finished = root is not None and _closed(root["end_ts"], last_ts)
    ending = ending_of(terminal, gave_up) if finished else None
    ended_ts: float | None = root["end_ts"] if ending is not None and root is not None else None
    if ending is None and _silent(last_ts, now):
        ending, ended_ts = "none", last_ts
    costs, profile, progress = figures.read(run_id)
    result = store.run_flows(run_id)
    standing = result["standing"]
    done, total = _items(progress, result["work"]["work_items"])
    identity = next((span for span in reversed(spans) if span["workflow"]), spans[-1])
    errors = [span for span in spans if span["status"] == "ERROR" and not span["name"].startswith("run:")]
    attrs = root["attrs"] if root else {}
    broken = ending in ("failed", "crashed", "interrupted")
    run_dir = identity["run_dir"] or ""
    launch = _launch_record(run_id, run_dir) if ending in CONTINUABLE else None
    stopped = next((span for span in reversed(spans) if span["node"] in giveup), None) if ending == "gave-up" else None
    failing = errors[-1]["node"] if broken and errors else stopped["node"] if stopped else ""
    return {
        "run_id": run_id,
        "workflow": identity["workflow"] or "",
        "repo": _named(max((span["repo"] or "" for span in spans), default=""), max((span["workspace_start"] or "" for span in spans), default="")),
        "branch": max((span["branch"] or "" for span in spans), default="") or max((span["branch_start"] or "" for span in spans), default=""),
        "run_dir": run_dir,
        "state": READY,
        "ending": ending or "",
        "error_class": str(attrs.get("error.class") or "") if broken else "",
        "failing_node": failing,
        "resume_command": _command(launch),
        "resume_container": int(launch.container) if launch else 0,
        "resume_read": RESUME_READ,
        "started_ts": profile["observed_start_ts"] if profile else None,
        "ended_ts": ended_ts,
        "last_ts": last_ts,
        "active_s": store.active_seconds(profile["time_s"]) if profile else 0.0,
        "wall_s": profile["time_s"]["wall"] if profile else 0.0,
        "cost_usd": costs["usd"],
        "est_usd": costs["est_usd"],
        "priced_turns": costs["priced_turns"],
        "turns": costs["turns"],
        "items_done": done,
        "items_total": total,
        "gates": standing["gates"],
        "problems": standing["problems"],
        "sessions_json": _json_safe(profile["session_rows"] if profile else []),
        "nodes_json": _json_safe(flows.node_breakdown(result["flows"])),
        "computed_at": now,
    }


@resilient
def _write(row: dict[str, Any]) -> None:
    columns = ", ".join(row)
    marks = ", ".join(f":{name}" for name in row)
    with STORE.writing() as conn:
        conn.execute(f"INSERT OR REPLACE INTO run_summary ({columns}) VALUES ({marks})", row)  # noqa: S608 - names come from summarize


@resilient
def _drop(run_id: str) -> None:
    with STORE.writing() as conn:
        conn.execute("DELETE FROM run_summary WHERE run_id = ? AND state = ?", (run_id, PENDING))


def compute(run_id: str, now: float | None = None) -> bool:
    """Write the summary of one run. Returns whether the run had any spans to read."""
    row = summarize(run_id, now)
    if row is None:
        _drop(run_id)
        return False
    wf = next((one for one in state.WORKFLOWS.values() if one.run_id == run_id), None)
    row["native"] = None if wf is None else int(bool(wf.native))
    _write(row)
    return True


def _item(row: sqlite3.Row) -> dict[str, Any]:
    ready = row["state"] == READY
    covered = ready and row["cost_usd"] is not None and row["priced_turns"] > 0
    return {
        "run_id": row["run_id"],
        "workflow": row["workflow"],
        "type_hue": projection.type_hue(row["workflow"]),
        "repo": row["repo"],
        "branch": row["branch"],
        "ready": ready,
        "unreadable": row["state"] == UNREADABLE,
        "archived": bool(row["archived"]),
        "ending": row["ending"] if ready else "",
        "ending_label": LABELS.get(row["ending"], "") if ready else "",
        "ended_ts": row["ended_ts"],
        "active_s": row["active_s"] if ready else None,
        "wall_s": row["wall_s"] if ready else None,
        "cost_usd": row["cost_usd"] if covered else None,
        "est_usd": row["est_usd"] if ready and not covered else None,
        "priced_turns": row["priced_turns"] if ready else None,
        "turns": row["turns"] if ready else None,
        "items_done": row["items_done"] if ready else None,
        "items_total": row["items_total"] if ready else None,
        "gates": row["gates"] if ready else None,
        "problems": row["problems"] if ready else None,
    }


def totals(items: list[dict[str, Any]]) -> dict[str, Any]:
    """What the table adds up to. A run still being read counts as a run and stays out of every sum and out of the success count."""
    ready = [item for item in items if item["ready"]]
    reported = sum(item["cost_usd"] or 0.0 for item in ready)
    estimate = sum(item["est_usd"] or 0.0 for item in ready)
    unreadable = sum(1 for item in items if item["unreadable"])
    return {
        "runs": len(items),
        "reading": len(items) - len(ready) - unreadable,
        "unreadable": unreadable,
        "spent_usd": reported + estimate,
        "estimate_usd": estimate,
        "partly_priced": sum(1 for item in ready if item["cost_usd"] is not None and item["priced_turns"] < item["turns"]),
        "active_s": sum(item["active_s"] for item in ready),
        "ready": len(ready),
        "success": sum(1 for item in ready if item["ending"] == "success"),
    }


@reading
def listing(alive: set[str], now: float | None = None, archives: bool = False) -> dict[str, Any]:
    """The runs that ended, newest first, with their totals: the last retention window, or every summary there is, archives included. Reads the summary table and the archive folder names, and opens no telemetry file."""
    now = now if now is not None else time.time()
    cutoff = now - store.RETENTION_DAYS * 86400
    where, params = ("ended_ts IS NOT NULL", ()) if archives else ("ended_ts IS NOT NULL AND ended_ts >= ? AND archived = 0", (cutoff,))
    rows = read_connection().execute(f"SELECT * FROM run_summary WHERE {where} ORDER BY ended_ts DESC, run_id", params)  # noqa: S608 - literals only
    items = [_item(row) for row in rows if row["run_id"] not in alive]
    for item in items:
        if item["archived"]:
            item["indexed"] = archive.is_indexed(item["run_id"])
    pool = medians.per_item_costs(alive)
    for item in items:
        item.update(medians.compare(item, pool.get(item["workflow"], {})))
    return {
        "runs": items,
        "totals": totals(items),
        "medians": medians.per_workflow(pool),
        "endings": [[key, label] for key, label in LABELS.items()],
        "unlisted": len(_unlisted()) if archives else 0,
    }


@reading
def comparison(run_id: str) -> dict[str, Any] | None:
    """An ended run's cost per item against the median of the other successful runs of its workflow, or None for a run that has not ended."""
    row = read_connection().execute("SELECT * FROM run_summary WHERE run_id = ?", (run_id,)).fetchone()
    if row is None or row["state"] != READY or row["ended_ts"] is None:
        return None
    item = _item(row)
    return {**medians.compare(item, medians.per_item_costs(set()).get(item["workflow"], {})), "ending": item["ending"], "ending_label": item["ending_label"], "workflow": item["workflow"]}


@reading
def _flags() -> dict[str, int]:
    rows = read_connection().execute("SELECT run_id, archived FROM run_summary")
    return {row["run_id"]: row["archived"] for row in rows}


def _covered(name: str, flags: dict[str, int]) -> bool:
    """Does a row stand for this archive folder: under its own name, or under the run id a derived ``<run_id>-<8 hex>`` name extends?"""
    base, _, token = name.rpartition("-")
    return name in flags or (len(token) == DERIVED_TOKEN and base in flags)


def _unlisted() -> list[str]:
    """The archive folders that no summary row stands for yet."""
    flags = _flags()
    return [folder.name for folder in archive.archive_dirs() if not _covered(folder.name, flags)]


def row_from_archive(found: dict[str, Any]) -> dict[str, Any] | None:
    """The summary row of an archive from its manifest: the stored summary when it carries one, else a pending row naming the run, repo and end time."""
    run_id = str(found.get("run_id") or "")
    if not run_id:
        return None
    summary = found.get("summary")
    if isinstance(summary, dict) and summary.get("run_id") == run_id:
        return {**summary, "archived": 1}
    return {
        "run_id": run_id,
        "workflow": found.get("workflow") or "",
        "repo": found.get("repo") or "",
        "branch": found.get("branch") or "",
        "state": PENDING,
        "ended_ts": found.get("max_ts") or None,
        "last_ts": 0,
        "archived": 1,
    }


@resilient
def _insert_archives(rows: list[dict[str, Any]]) -> None:
    with STORE.writing() as conn:
        for row in rows:
            columns = ", ".join(row)
            marks = ", ".join(f":{name}" for name in row)
            conn.execute(f"INSERT OR IGNORE INTO run_summary ({columns}) VALUES ({marks})", row)  # noqa: S608 - names come from row_from_archive


@resilient
def _mark_archived(run_ids: list[str]) -> None:
    with STORE.writing() as conn:
        conn.executemany("UPDATE run_summary SET archived = 1 WHERE run_id = ?", [(run_id,) for run_id in run_ids])


@reading
def _pending_archives() -> list[str]:
    rows = read_connection().execute("SELECT run_id FROM run_summary WHERE archived = 1 AND state = ? ORDER BY ended_ts DESC, run_id", (PENDING,))
    return [row["run_id"] for row in rows]


def discover_archives() -> list[str]:
    """Give every archive a summary row, and return the ids of the archives whose summary must still be read, newest first. An archive that stored its summary needs no read, and a run summarized before it was archived only gets its flag."""
    flags = _flags()
    fresh: list[dict[str, Any]] = []
    marked: list[str] = []
    for folder in archive.archive_dirs():
        if _covered(folder.name, flags):
            if flags.get(folder.name) == 0:
                marked.append(folder.name)
            continue
        row = row_from_archive(archive.manifest(folder))
        if row is not None and row["run_id"] not in flags:
            fresh.append(row)
    if fresh:
        _insert_archives(fresh)
    if marked:
        _mark_archived(marked)
    return _pending_archives()


def keep_archived(summary: dict[str, Any]) -> None:
    """Store the summary of a run that was just archived, flagged as archived."""
    _write({**summary, "archived": 1})


@resilient
def _settle(run_id: str, outcome: str) -> None:
    with STORE.writing() as conn:
        conn.execute("UPDATE run_summary SET state = ? WHERE run_id = ? AND archived = 1 AND state != ?", (outcome, run_id, READY))


def compute_archive(run_id: str, now: float | None = None) -> bool:
    """Read an archive's index once and store its summary. Returns whether it could be read; an archive that cannot be read keeps its row as unreadable."""
    folder = archive.exact_dir(run_id)
    row: dict[str, Any] | None = None
    try:
        if folder is not None:
            with store.reading_from(archive.build_index(folder)):
                row = summarize(run_id, now)
    except Exception:  # noqa: BLE001
        logger.warning("groom: the archive of run %s could not be read", run_id, exc_info=True)
    if row is None:
        _settle(run_id, UNREADABLE)
        return False
    _write({**row, "archived": 1})
    return True


def retry(run_id: str) -> bool:
    """Ask for an unreadable archive summary to be read again. Returns whether the run was waiting on a retry."""
    row = stored(run_id)
    if row is None or not row["archived"] or row["state"] != UNREADABLE:
        return False
    _settle(run_id, PENDING)
    return True
