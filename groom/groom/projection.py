"""Dataclass → JSON projection for the dashboard.

The browser renders; the server projects. This module is the *only* place a
:mod:`groom.models` dataclass is turned into a wire shape, which is what keeps
groom's two delivery paths honest:

- ``GET /api/state`` — the full-fleet resync a tab pulls when its socket has
  gone quiet or died (see :func:`state_message`)
- the browser websocket — the same ``{"type": "state", ...}`` payload pushed on
  every state change and on the live ticker, plus ``{"type": "run", ...}``
  single-run deltas (see :func:`run_message`)

Both call the functions here, so a tab that resynced over HTTP and a tab that
was pushed to are looking at byte-identical JSON and feed it through one
``applyState()`` on the client. Nothing here emits markup, reads a request, or
touches the network — it is pure ``(dataclasses, clock) -> dict``, which is
also what makes the shapes cheap to assert in a test.

Labels that encode a *judgement* (``alive`` vs ``silent 4m``, the fleet sort
rank) are computed here rather than in the browser: they are policy, they are
thresholded against server-side constants like ``store.LIVE_AFTER_S``, and two
implementations of them would drift. Raw numbers ride along beside every label
so the client can re-format without re-deciding.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from groom import state, store
from groom.models import GateInfo, RunTelemetry, WorkflowContainer, WorkflowState

# Blocked first, then active, then quiet — used for both tree and fleet order.
STATE_ORDER = {
    WorkflowState.BLOCKED: 0,
    WorkflowState.RUNNING: 1,
    WorkflowState.IDLE: 2,
    WorkflowState.FINISHED: 3,
}

# How many log lines the detail pane's trail shows (newest first).
LOG_TRAIL_LIMIT = 60

# Log severities that deserve a color in the trail; everything else reads plain.
SEVERITY_CLASS = {"FATAL": "bad", "ERROR": "bad", "WARNING": "warn"}


# --------------------------------------------------------------------------- #
# Formatting — shared so a pushed label and a resynced label are the same string
# --------------------------------------------------------------------------- #
def fmt_ts(ts: float) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S")


def fmt_clock(ts: float) -> str:
    """Time-of-day only — the log trail is always about the last few minutes."""
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def fmt_duration(seconds: float) -> str:
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60):02d}s"
    return f"{seconds / 3600:.1f}h"


def question_preview(question: str) -> str:
    """The first line of a gate question that carries content, stripped of its
    markdown lead-in — what the fleet row shows so a blocked run says *what* it
    is asking without the operator opening it."""
    for raw_line in question.splitlines():
        line = raw_line.strip().lstrip("#>*-` ").strip()
        if line:
            return line[:140]
    return ""


# --------------------------------------------------------------------------- #
# Identity + filtering
# --------------------------------------------------------------------------- #
def matches(wf: WorkflowContainer, query: str) -> bool:
    if not query:
        return True
    query = query.lower()
    haystacks = [wf.name, wf.repo_name, wf.repo_branch, wf.workflow_type, wf.current_node]
    haystacks += [wf.run_id, wf.activity]
    haystacks += [g.file_path for g in wf.gates.values()]
    return any(query in (h or "").lower() for h in haystacks)


def repo_label(wf: WorkflowContainer) -> str:
    return f"{wf.repo_name}@{wf.repo_branch}" if wf.repo_branch else (wf.repo_name or "—")


def short_id(wf: WorkflowContainer) -> str:
    return wf.container_id[:4] or "----"


def type_hue(workflow_type: str) -> int:
    """A stable hue per workflow type, so a new kind of workflow gets its own
    consistent chip color with no CSS change. ``coder``/``author`` additionally
    have a fixed look in dashboard.css, which wins over the hue."""
    hue = 0
    for ch in workflow_type:
        hue = (hue * 31 + ord(ch)) % 360
    return hue


def run_id_of(wf: WorkflowContainer) -> str:
    """The telemetry key for a dashboard row. A native row *is* its run (the map
    is keyed by run_id); a docker row carries the run id it pushed, if any."""
    return wf.run_id or wf.container_id


def telemetry_for(wf: WorkflowContainer) -> RunTelemetry | None:
    return state.RUNS.get(run_id_of(wf))


# --------------------------------------------------------------------------- #
# Liveness + ordering
# --------------------------------------------------------------------------- #
def silence_of(tel: RunTelemetry | None, now: float) -> float:
    if tel is None:
        return 0.0
    return max(0.0, now - max(tel.last_heartbeat_ts, tel.last_span_ts, tel.first_seen_ts))


def is_live(tel: RunTelemetry | None, now: float) -> bool:
    """Is this run's process emitting *right now*? The one liveness predicate.

    Two ways to be not-running, and both are about the current session only: the
    root span of THIS session landed (``terminal``, cleared the moment a newer
    signal arrives — see ``alerts._clear_stale_terminal``), or nothing has been
    heard inside the live window. Everything else — a root span from an earlier
    session of the same run dir, a docker container that exited — is history, and
    history cannot answer this.
    """
    if tel is None or tel.terminal:
        return False
    return silence_of(tel, now) <= store.LIVE_AFTER_S


def liveness(wf: WorkflowContainer, tel: RunTelemetry | None, now: float) -> tuple[str, str]:
    """``(class, label)`` for the row's process-liveness chip.

    Liveness is a telemetry question, not a docker one: workhorse beats every few
    seconds from a daemon thread for as long as its process exists, so recent
    silence means the process is gone (or frozen below the interpreter) rather
    than merely busy. Telemetry therefore *always* wins over the container's exit
    state; only a run that has never exported anything falls back to it, and a run
    with no evidence either way gets ``unknown`` rather than a guess — ``dead``
    here must mean *observed silent*, not *unobserved*.
    """
    if tel is None:
        if wf.state == WorkflowState.FINISHED:
            return "done", "ended"
        return "unknown", ""
    if tel.terminal:
        return "done", tel.terminal
    silence = silence_of(tel, now)
    if silence <= store.LIVE_AFTER_S:
        return "live", "alive"
    return "dead", f"silent {fmt_duration(silence)}"


def fleet_rank(wf: WorkflowContainer, live_cls: str) -> int:
    """Blocked first (it is waiting on *you*), then alive, then presumed-dead,
    then finished — the order in which a run deserves the operator's attention."""
    if wf.state == WorkflowState.BLOCKED:
        return 0
    if wf.state == WorkflowState.FINISHED or live_cls == "done":
        return 3
    return 1 if live_cls == "live" else 2


def exit_hint(wf: WorkflowContainer) -> str:
    """A short ``exited N`` marker for a finished worker whose exit code is
    known. Empty for still-live or code-less workers."""
    if wf.state != WorkflowState.FINISHED or wf.exit_code is None:
        return ""
    return f"exited {wf.exit_code}"


def row_mini(tel: RunTelemetry | None) -> str:
    """The at-a-glance numbers that say whether being in this node is normal:
    how long it has been open, and how long the agent has been silent."""
    if tel is None:
        return ""
    bits = []
    if tel.wait_kind:
        bits.append(f"waiting {tel.wait_kind} {fmt_duration(tel.wait_elapsed_s)}")
    elif tel.turn_active is True:
        bits.append(f"in turn {fmt_duration(tel.turn_elapsed_s)}")
    elif tel.node_elapsed_s:
        bits.append(f"in node {fmt_duration(tel.node_elapsed_s)}")
    if tel.turn_active is not False and tel.turn_idle_s > 60:
        bits.append(f"agent idle {fmt_duration(tel.turn_idle_s)}")
    return " · ".join(bits)


# --------------------------------------------------------------------------- #
# Wire shapes
# --------------------------------------------------------------------------- #
def gate_dict(gate: GateInfo) -> dict[str, Any]:
    return {
        "file_path": gate.file_path,
        "question": gate.question,
        "preview": question_preview(gate.question),
        "status": gate.status,
    }


def gates_of(wf: WorkflowContainer) -> list[GateInfo]:
    return sorted(wf.gates.values(), key=lambda g: g.file_path)


def run_row(
    wf: WorkflowContainer, tel: RunTelemetry | None = None, now: float | None = None
) -> dict[str, Any]:
    """One fleet row. ``doing`` is the single line the row shows under its title:
    the gate file when the run is parked on one (that is the thing the operator
    has to go answer), else its exit hint, else the activity it stamped, else the
    raw node id."""
    now = now if now is not None else time.time()
    gates = gates_of(wf)
    gate = gates[0] if gates else None
    live_cls, live_label = liveness(wf, tel, now)
    hint = exit_hint(wf)
    return {
        "id": wf.container_id,
        "run_id": run_id_of(wf),
        "name": wf.name,
        "repo": repo_label(wf),
        "short_id": short_id(wf),
        "type": wf.workflow_type,
        "type_hue": type_hue(wf.workflow_type),
        "state": wf.state.value,
        "live": live_cls,
        "live_label": live_label,
        "silence_s": silence_of(tel, now),
        "node": wf.current_node or (tel.current_node if tel else ""),
        "node_elapsed_s": tel.node_elapsed_s if tel else 0.0,
        "wait_kind": tel.wait_kind if tel else "",
        "wait_elapsed_s": tel.wait_elapsed_s if tel else 0.0,
        "turn_active": tel.turn_active if tel else None,
        "turn_elapsed_s": tel.turn_elapsed_s if tel else 0.0,
        "turn_idle_s": tel.turn_idle_s if tel else 0.0,
        "mini": row_mini(tel),
        "activity": wf.activity or (tel.activity if tel else ""),
        "doing": gate.file_path if gate else (
            hint or wf.activity or (tel.activity if tel else "") or wf.current_node
        ),
        "question": question_preview(gate.question) if gate and wf.state == WorkflowState.BLOCKED else "",
        "gate_path": gate.file_path if gate else "",
        "gate_count": len(gates),
        "exit_code": wf.exit_code,
        "exit_hint": hint,
        "pid": wf.pid,
        "native": bool(wf.native),
        "rank": fleet_rank(wf, live_cls),
    }


def fleet_rows(
    workflows: list[WorkflowContainer], query: str = "", now: float | None = None
) -> list[dict[str, Any]]:
    """The fleet in display order: blocked first, then alive, then presumed-dead,
    then finished; ties broken by name so the list does not shuffle on a tick."""
    now = now if now is not None else time.time()
    rows = [run_row(wf, telemetry_for(wf), now) for wf in workflows if matches(wf, query)]
    rows.sort(key=lambda row: (row["rank"], row["name"]))
    return rows


def status_bar(workflows: list[WorkflowContainer]) -> dict[str, Any]:
    counts = {s.value: 0 for s in WorkflowState}
    repos: set[str] = set()
    for wf in workflows:
        counts[wf.state.value] += 1
        repos.add(repo_label(wf))
    return {"counts": counts, "repos": len(repos), "workers": len(workflows)}


def state_message(
    workflows: list[WorkflowContainer], query: str = "", now: float | None = None
) -> dict[str, Any]:
    """The whole fleet as one payload — pushed on the socket *and* returned by
    ``GET /api/state``. One shape, one client render path: a resync after a dead
    socket must land the tab in exactly the state a push would have."""
    now = now if now is not None else time.time()
    return {
        "type": "state",
        "ts": now,
        "scanning": bool(state.SCANNING),
        "runs": fleet_rows(workflows, query, now),
        "status": status_bar(workflows),
        # Sibling of "status", not part of it: the fleet counts describe the runs and
        # this describes the collector holding them. A serve whose store has wedged
        # answers every read route 200 with a plausible-looking fleet, so "is groom
        # still storing what it is told" has to be asked separately or not at all.
        "store": store.health_dict(),
    }


def run_message(
    wf: WorkflowContainer, tel: RunTelemetry | None = None, now: float | None = None
) -> dict[str, Any]:
    """A single-run delta. Same row shape as an entry in ``state.runs``, so the
    client merges it into the store without a second code path."""
    now = now if now is not None else time.time()
    return {"type": "run", "ts": now, "run": run_row(wf, tel, now)}


# --------------------------------------------------------------------------- #
# Container + repo picker (GET /repos)
# --------------------------------------------------------------------------- #
def repo_entries(
    entries: list[tuple[WorkflowContainer, list[str]]],
) -> list[dict[str, Any]]:
    """One group per container, each carrying the checkouts found on its volume.

    Grouped rather than flat because that is the shape the server actually has —
    one enumeration per container — and because the label a picker row shows
    (``<container>/<repo>``) is derived from both halves. A workflow with no
    discoverable repo still gets a single volume-root entry so it can be browsed
    at all. Order is the fleet's own: blocked first, then by name.
    """
    groups = []
    for wf, repo_dirs in sorted(entries, key=lambda e: (STATE_ORDER[e[0].state], e[0].name)):
        groups.append(
            {
                "container": wf.container_id,
                "name": wf.name,
                "state": wf.state.value,
                "type": wf.workflow_type,
                "type_hue": type_hue(wf.workflow_type),
                "repos": [
                    {"repo": repo, "label": f"{wf.name}/{repo}" if repo else wf.name}
                    for repo in (repo_dirs or [""])
                ],
            }
        )
    return groups


# --------------------------------------------------------------------------- #
# Detail pane (GET /worker/{id}, and the pushed refresh of the open pane)
# --------------------------------------------------------------------------- #
def handle(wf: WorkflowContainer) -> str:
    """The id the detail pane shows — whole, not a fragment.

    A row's ``short_id`` is for scanning a list, where four characters
    disambiguate. The pane is the thing you *paste*: into a workhorse command,
    into a groom URL, into a run-directory path. So a native row reports its
    entire run id, and a docker row the twelve characters docker itself prints
    and accepts. Truncating the run id saved a few pixels of header and cost
    every paste that needed it.
    """
    if wf.native:
        return wf.run_id or wf.container_id
    return wf.container_id[:12]


def cli_label(tel: RunTelemetry | None) -> str:
    """The agent CLI the run's last turn actually used, and the model it drove.

    Both, because neither answers the question alone: two harnesses can drive the
    same model slug, and one harness can be pointed at several models over a run.
    Empty when no turn has exported yet — the pane omits the segment rather than
    printing a placeholder, since "unknown" and "none yet" look the same and only
    one of them is worth reading.
    """
    if tel is None or not tel.backend:
        return ""
    return f"{tel.backend} {tel.model}".strip()


def head(
    wf: WorkflowContainer, tel: RunTelemetry | None = None, now: float | None = None
) -> dict[str, Any]:
    """The activity line at the top of the detail pane — what this run is doing
    right now. The same liveness verdict the row shows, so a run cannot read
    ``alive`` in the list and ``silent 4m`` in the pane."""
    now = now if now is not None else time.time()
    live_cls, live_label = liveness(wf, tel, now)
    return {
        "id": wf.container_id,
        "handle": handle(wf),
        "state": wf.state.value,
        "type": wf.workflow_type,
        "type_hue": type_hue(wf.workflow_type),
        "repo": repo_label(wf),
        "live": live_cls,
        "live_label": live_label,
        "node": wf.current_node or (tel.current_node if tel else ""),
        "pid": wf.pid,
        "cli": cli_label(tel),
        "exit_hint": exit_hint(wf),
        "exit_ok": wf.exit_code == 0,
        "activity": wf.activity or (tel.activity if tel else ""),
    }


def metrics(
    wf: WorkflowContainer,
    tel: RunTelemetry | None = None,
    facts: dict[str, Any] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """The numbers worth having on screen while deciding whether to intervene.

    ``facts`` is the durable half (``store.live_status`` merged with that run's
    ``store.run_summaries`` row); ``tel`` is the hot cache. Both are optional — a
    docker row that never exported telemetry reports ``empty`` so the pane can say
    so, rather than rendering a wall of dashes that looks like a broken run.

    Cells are ordered pairs, not a mapping: the order *is* the layout, and a dict
    would hand that decision to whichever JSON serializer touched it last.
    """
    now = now if now is not None else time.time()
    facts = facts or {}
    if tel is None and not facts:
        return {"empty": True, "cells": [], "alerts": [], "run_dir": ""}

    node = (tel.current_node if tel else "") or str(facts.get("node") or "")
    elapsed = (tel.node_elapsed_s if tel else 0.0) or float(facts.get("node_elapsed_s") or 0.0)
    idle = (tel.turn_idle_s if tel else 0.0) or float(facts.get("turn_idle_s") or 0.0)
    turn_active = tel.turn_active if tel and tel.turn_active is not None else facts.get("turn_active")
    turn_elapsed = (tel.turn_elapsed_s if tel else 0.0) or float(
        facts.get("turn_elapsed_s") or 0.0
    )
    wait_kind = (tel.wait_kind if tel else "") or str(facts.get("wait_kind") or "")
    wait_elapsed = (tel.wait_elapsed_s if tel else 0.0) or float(
        facts.get("wait_elapsed_s") or 0.0
    )
    last_beat = max(
        (tel.last_heartbeat_ts if tel else 0.0), float(facts.get("last_beat_ts") or 0.0)
    )
    started = (tel.first_seen_ts if tel else 0.0) or float(facts.get("first_ts") or 0.0)

    cells = [
        {"key": "node", "value": node or "—"},
        {"key": "in node", "value": fmt_duration(elapsed) if elapsed else "—"},
        {"key": "wait", "value": wait_kind or "—"},
        {"key": "in wait", "value": fmt_duration(wait_elapsed) if wait_kind else "—"},
        {"key": "in turn", "value": fmt_duration(turn_elapsed) if turn_active else "—"},
        {
            "key": "agent idle",
            "value": fmt_duration(idle) if turn_active is not False and idle else "—",
        },
    ]
    if facts.get("gas") is not None:
        cells.append({"key": "gas", "value": f"{float(facts['gas']):g}"})
    cells.append(
        {"key": "last beat", "value": f"{fmt_duration(now - last_beat)} ago" if last_beat else "—"}
    )
    cells.append({"key": "uptime", "value": fmt_duration(now - started) if started else "—"})
    if facts.get("span_count") is not None:
        cells.append({"key": "spans", "value": str(facts.get("span_count") or 0)})
    errors = int(facts.get("error_count") or 0)
    cells.append({"key": "errors", "value": str(errors), "cls": "bad" if errors else ""})
    if tel is not None and tel.pid:
        cells.append({"key": "pid", "value": str(tel.pid)})
    return {
        "empty": False,
        "cells": cells,
        "alerts": sorted(tel.fired if tel else ()),
        "run_dir": (tel.run_dir if tel else "") or str(facts.get("run_dir") or ""),
    }


def log_lines(logs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """The run's log lines, newest first — the trail that says *what* the current
    node has been doing, once the metrics have said it is stuck."""
    lines = []
    for row in (logs or [])[:LOG_TRAIL_LIMIT]:
        severity = str(row.get("severity") or "INFO").upper()
        lines.append(
            {
                "ts": fmt_clock(float(row.get("ts") or 0)),
                "level": severity[:4],
                "severity": severity,
                "cls": SEVERITY_CLASS.get(severity, ""),
                "node": str(row.get("node") or ""),
                "body": str(row.get("body") or ""),
            }
        )
    return lines


def run_live(
    wf: WorkflowContainer,
    tel: RunTelemetry | None = None,
    facts: dict[str, Any] | None = None,
    logs: list[dict[str, Any]] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """The clock-refreshable half of a detail pane: what changes while you watch
    it. Pushed to that run's watchers on every tick, so it holds nothing the
    operator can type into and nothing that needs a click to be true."""
    now = now if now is not None else time.time()
    return {
        "head": head(wf, tel, now),
        "metrics": metrics(wf, tel, facts, now),
        "logs": log_lines(logs),
    }


def run_detail(
    wf: WorkflowContainer,
    tel: RunTelemetry | None = None,
    facts: dict[str, Any] | None = None,
    logs: list[dict[str, Any]] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """One run, top to bottom: what it is doing, the gates you can answer, its
    live metrics, its log trail. ``GET /worker/{id}`` returns this and the
    websocket pushes it — one shape, so an open pane and a freshly-opened one
    cannot show different things."""
    now = now if now is not None else time.time()
    return {
        "found": True,
        "id": wf.container_id,
        "run_id": run_id_of(wf),
        "state": wf.state.value,
        "node": wf.current_node,
        "gates": [gate_dict(gate) for gate in gates_of(wf)],
        **run_live(wf, tel, facts, logs, now),
    }


def detail_message(
    wf: WorkflowContainer,
    tel: RunTelemetry | None = None,
    facts: dict[str, Any] | None = None,
    logs: list[dict[str, Any]] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """A pushed detail refresh, addressed to the tabs watching this one run.

    Carries the same ``run_detail`` body the fetch returns rather than a reduced
    slice: the client reconciles it against a keyed component tree, so a re-render
    keeps the answer textarea's DOM node — and therefore a half-typed answer —
    while letting a gate that opened or closed appear without a round trip. Under
    the old fragment swap that was impossible, which is why the pushed refresh
    used to stop short of the form.
    """
    now = now if now is not None else time.time()
    return {
        "type": "detail",
        "ts": now,
        "id": wf.container_id,
        "detail": run_detail(wf, tel, facts, logs, now),
    }


# --------------------------------------------------------------------------- #
# Workspace panels (GET /file/{id})
# --------------------------------------------------------------------------- #
# Extension → highlight.js language. Unmapped extensions get "", which the
# viewer reads as "let highlight.js auto-detect".
EXT_LANG = {
    "js": "javascript", "mjs": "javascript", "cjs": "javascript", "jsx": "javascript",
    "ts": "typescript", "tsx": "typescript", "py": "python", "rb": "ruby", "go": "go",
    "rs": "rust", "java": "java", "kt": "kotlin", "c": "c", "h": "c", "cpp": "cpp",
    "cc": "cpp", "hpp": "cpp", "cs": "csharp", "php": "php", "swift": "swift",
    "scala": "scala", "sh": "bash", "bash": "bash", "zsh": "bash", "yml": "yaml",
    "yaml": "yaml", "json": "json", "toml": "ini", "ini": "ini", "cfg": "ini",
    "md": "markdown", "markdown": "markdown", "html": "xml", "xml": "xml",
    "svg": "xml", "vue": "xml", "css": "css", "scss": "scss", "less": "less",
    "sql": "sql", "lua": "lua", "pl": "perl", "r": "r", "dart": "dart",
}


def file_lang(path: str) -> str:
    """The highlight.js language for a path, by extension (or by whole name for
    the extensionless files that still have a grammar)."""
    base = path.split("/")[-1].lower()
    if base == "dockerfile":
        return "dockerfile"
    if base == "makefile":
        return "makefile"
    _, dot, ext = base.rpartition(".")
    return EXT_LANG.get(ext, "") if dot else ""


# --------------------------------------------------------------------------- #
# Telemetry pane (GET /traces)
# --------------------------------------------------------------------------- #
def run_card(
    summary: dict[str, Any],
    tel: RunTelemetry | None,
    live_ids: frozenset[str] | set[str] = frozenset(),
    now: float | None = None,
) -> dict[str, Any]:
    """One run's summary strip in the telemetry pane. ``doing`` is what the run
    stamped (else its live node), so the pane reads as work in progress rather
    than as a list of opaque run ids.

    ``live`` is recency, from the hot cache when this run is in it and from the
    store's heartbeat window otherwise — never from the span history in
    ``summary``, which can only say what a run has already done."""
    now = now if now is not None else time.time()
    return {
        "run_id": summary["run_id"],
        "workflow": summary.get("workflow") or "run",
        "live": is_live(tel, now) if tel is not None else summary["run_id"] in live_ids,
        "errors": int(summary.get("error_count") or 0),
        "spans": int(summary.get("span_count") or 0),
        "alerts": sorted(tel.fired if tel else ()),
        "window": f"{fmt_ts(summary.get('first_ts') or 0)} → {fmt_ts(summary.get('last_ts') or 0)}",
        "doing": (tel.activity or tel.current_node) if tel else "",
    }


def span_row(span: dict[str, Any]) -> dict[str, Any]:
    return {
        "started": fmt_ts(span.get("start_ts") or 0),
        "run_id": span.get("run_id") or "",
        "node": span.get("node") or "",
        "name": span.get("name") or "",
        "duration": fmt_duration((span.get("end_ts") or 0) - (span.get("start_ts") or 0)),
        "status": str(span.get("status") or "UNSET"),
    }


def traces_view(
    summaries: list[dict[str, Any]],
    spans: list[dict[str, Any]],
    runs: dict[str, RunTelemetry],
    live_ids: frozenset[str] | set[str] = frozenset(),
    now: float | None = None,
    connected_only: bool = True,
) -> dict[str, Any]:
    """The telemetry pane: a per-run summary strip (with any fired alert rules)
    above the filtered span table. Pulled on demand — telemetry is a pull view;
    the pushes are the alerts. ``live_ids`` is ``store.live_run_ids()``, which
    covers the runs no longer (or not yet) in the hot cache.

    By default the pane shows only runs that are **connected right now** — the
    same ``live`` predicate the fleet rows use, not a second notion of it. The
    store keeps two weeks of history, so the unfiltered strip is mostly runs that
    ended days ago; the pane exists to watch what is happening. History is one
    ``connected_only=False`` away (the pane's *show ended* toggle, and any
    explicit ``run=`` search, which asks for a named run and must find it even
    once it is over). Spans follow their run: a span table listing nodes of a run
    the strip above has hidden reads as telemetry from nowhere.
    """
    now = now if now is not None else time.time()
    cards = [run_card(s, runs.get(s["run_id"]), live_ids, now) for s in summaries]
    if connected_only:
        cards = [card for card in cards if card["live"]]
        connected = {card["run_id"] for card in cards}
        spans = [span for span in spans if (span.get("run_id") or "") in connected]
    return {"runs": cards, "spans": [span_row(s) for s in spans]}
