"""Dataclass → JSON projection for the dashboard."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from groom import attend, gates, state, store
from groom.attention import RULE_EVENTS, AttentionEvent
from groom.models import GateInfo, RunTelemetry, WorkflowContainer, WorkflowState

STATE_ORDER = {
    WorkflowState.BLOCKED: 0,
    WorkflowState.RUNNING: 1,
    WorkflowState.IDLE: 2,
    WorkflowState.FINISHED: 3,
}

LOG_TRAIL_LIMIT = 60

SEVERITY_CLASS = {"FATAL": "bad", "ERROR": "bad", "WARNING": "warn"}


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
    """The first line of a gate question that carries content, stripped of its markdown lead-in — what the fleet row shows so a blocked run says *what* it is asking without the operator opening it."""
    for raw_line in question.splitlines():
        line = raw_line.strip().lstrip("#>*-` ").strip()
        if line:
            return line[:140]
    return ""


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


def row_id(wf: WorkflowContainer) -> str:
    """The id a list row shows."""
    if wf.native:
        return wf.run_id or wf.container_id
    return wf.container_id[:4] or "----"


def type_hue(workflow_type: str) -> int:
    """A stable hue per workflow type, so a new kind of workflow gets its own consistent chip color with no CSS change."""
    hue = 0
    for ch in workflow_type:
        hue = (hue * 31 + ord(ch)) % 360
    return hue


def run_id_of(wf: WorkflowContainer) -> str:
    """The telemetry key for a dashboard row."""
    return wf.run_id or wf.container_id


def telemetry_for(wf: WorkflowContainer) -> RunTelemetry | None:
    return state.RUNS.get(run_id_of(wf))


def silence_of(tel: RunTelemetry | None, now: float) -> float:
    if tel is None:
        return 0.0
    return max(0.0, now - max(tel.last_heartbeat_ts, tel.last_span_ts, tel.first_seen_ts, tel.last_telemetry_ts))


def is_live(tel: RunTelemetry | None, now: float) -> bool:
    """Is this run's process emitting *right now*?"""
    if tel is None or tel.terminal:
        return False
    return silence_of(tel, now) <= store.LIVE_AFTER_S


def liveness(wf: WorkflowContainer, tel: RunTelemetry | None, now: float) -> tuple[str, str]:
    """``(class, label)`` for the row's process-liveness chip."""
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
    """Blocked first (it is waiting on *you*), then alive, then presumed-dead, then finished — the order in which a run deserves the operator's attention."""
    if wf.state == WorkflowState.BLOCKED:
        return 0
    if wf.state == WorkflowState.FINISHED or live_cls == "done":
        return 3
    return 1 if live_cls == "live" else 2


def exit_hint(wf: WorkflowContainer) -> str:
    """A short ``exited N`` marker for a finished worker whose exit code is known."""
    if wf.state != WorkflowState.FINISHED or wf.exit_code is None:
        return ""
    return f"exited {wf.exit_code}"


def row_mini(tel: RunTelemetry | None) -> str:
    """The at-a-glance numbers that say whether being in this node is normal: how long it has been open, and how long the agent has been silent."""
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


def gate_dict(gate: GateInfo) -> dict[str, Any]:
    question = gates.extract_question(gate.question) if gate.kind != "machine" else gate.question
    return {
        "file_path": gate.file_path,
        "question": question,
        "preview": question_preview(question),
        "status": gate.status,
        "kind": gate.kind,
    }


def gates_of(wf: WorkflowContainer) -> list[GateInfo]:
    return sorted(wf.gates.values(), key=lambda g: g.file_path)


def reported_gates(wf: WorkflowContainer, tel: RunTelemetry | None) -> list[GateInfo]:
    """Pending gates from telemetry, or a sidecar snapshot for an older producer."""
    if tel is None:
        return gates_of(wf)
    if tel.terminal or tel.wait_kind not in ("operator", "machine"):
        return []
    return [GateInfo(workflow_id=wf.container_id, file_path=tel.wait_gate_path,
                     question=tel.wait_gate_question, kind=tel.wait_kind)]


def run_row(
    wf: WorkflowContainer, tel: RunTelemetry | None = None, now: float | None = None
) -> dict[str, Any]:
    """A fleet row projected from the latest telemetry, with legacy sidecar support."""
    now = now if now is not None else time.time()
    live_cls, live_label = liveness(wf, tel, now)
    state = _row_state(wf, tel)
    gates = reported_gates(wf, tel)
    gate_path = gates[0].file_path if gates else ""
    hint = exit_hint(wf)
    age = silence_of(tel, now)
    return {
        "id": wf.container_id,
        "run_id": run_id_of(wf),
        "name": wf.name,
        "repo": repo_label(wf),
        "row_id": row_id(wf),
        "type": wf.workflow_type,
        "type_hue": type_hue(wf.workflow_type),
        "state": state,
        "live": live_cls,
        "live_label": live_label,
        "silence_s": age,
        "telemetry_age_s": age,
        "node": tel.current_node if tel else wf.current_node,
        "node_elapsed_s": tel.node_elapsed_s if tel else 0.0,
        "wait_kind": tel.wait_kind if tel else "",
        "wait_elapsed_s": tel.wait_elapsed_s if tel else 0.0,
        "turn_active": tel.turn_active if tel else None,
        "turn_elapsed_s": tel.turn_elapsed_s if tel else 0.0,
        "turn_idle_s": tel.turn_idle_s if tel else 0.0,
        "mini": row_mini(tel),
        "activity": tel.activity if tel else wf.activity,
        "doing": (
            gate_path
            if gate_path
            else (tel.activity if tel else "")
            or (tel.current_node if tel else "")
        ),
        "question": "",
        "gate_path": gate_path,
        "gate_count": len(gates),
        "exit_code": wf.exit_code,
        "exit_hint": hint,
        "pid": tel.pid if (tel and tel.pid) else wf.pid,
        "native": bool(wf.native),
        "rank": fleet_rank_for(state, live_cls),
    }


def _row_state(wf: WorkflowContainer, tel: RunTelemetry | None) -> str:
    """The row's state, derived purely from telemetry."""
    if tel is not None:
        if tel.terminal:
            return WorkflowState.FINISHED.value
        if tel.wait_kind in ("operator", "machine"):
            return WorkflowState.BLOCKED.value
        return WorkflowState.RUNNING.value
    return wf.state.value


def fleet_rank_for(state: str, live_cls: str) -> int:
    """Blocked first (it is waiting on *you*), then alive, then presumed-dead, then finished — the order in which a run deserves the operator's attention."""
    if state == WorkflowState.BLOCKED.value:
        return 0
    if state == WorkflowState.FINISHED.value or live_cls == "done":
        return 3
    return 1 if live_cls == "live" else 2


def fleet_rows(
    workflows: list[WorkflowContainer], query: str = "", now: float | None = None
) -> list[dict[str, Any]]:
    """The fleet in display order: blocked first, then alive, then presumed-dead, then finished; ties broken by name so the list does not shuffle on a tick."""
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


def attend_summary() -> dict[str, Any]:
    """The attendant's status, small enough to ride every ``state`` frame."""
    try:
        latest = store.attend_latest_by_run()
    except Exception:
        latest = {}
    by_run = {
        run_id: {
            "job_id": row.get("job_id", ""),
            "session_id": (list(row.get("session_ids") or []) or [""])[-1],
            "status": row.get("status", ""),
            "kind": row.get("kind", ""),
            "reason": row.get("reason", ""),
            "started_at": row.get("started_at", 0),
            "ended_at": row.get("ended_at"),
        }
        for run_id, row in latest.items()
    }
    rev = 0.0
    for row in latest.values():
        rev = max(rev, float(row.get("started_at") or 0), float(row.get("ended_at") or 0))
    return {"mode": attend.mode(), "by_run": by_run, "rev": rev, "count": len(by_run)}


def attention_events(workflows: list[WorkflowContainer]) -> list[AttentionEvent]:
    """Current attention conditions, including telemetry without a visible row."""
    events: list[AttentionEvent] = []
    for tel in state.RUNS.values():
        rules = set(tel.fired)
        if tel.terminal:
            rules.add("ENDED")
        elif tel.wait_kind == "operator":
            rules.add("BLOCKED")
        for rule in sorted(rules):
            if rule in RULE_EVENTS:
                events.append(AttentionEvent(
                    run_id=tel.run_id, event=RULE_EVENTS[rule], node=tel.current_node,
                    question=tel.wait_gate_question if rule == "BLOCKED" else "",
                    gate_path=tel.wait_gate_path if rule == "BLOCKED" else "",
                    terminal=tel.terminal,
                ))
    for wf in workflows:
        if telemetry_for(wf) is not None:
            continue
        for gate in reported_gates(wf, None):
            if gate.kind in ("", "operator"):
                events.append(AttentionEvent(
                    run_id=run_id_of(wf), event="blocked", node=wf.current_node,
                    question=gate.question, gate_path=gate.file_path,
                ))
        if wf.state == WorkflowState.FINISHED:
            events.append(AttentionEvent(
                run_id=run_id_of(wf), event="ended", node=wf.current_node,
                message=f"workflow exited with code {wf.exit_code}",
            ))
    return events


def state_message(
    workflows: list[WorkflowContainer], query: str = "", now: float | None = None
) -> dict[str, Any]:
    """The whole fleet as one payload — pushed on the socket *and* returned by ``GET /api/state``."""
    now = now if now is not None else time.time()
    return {
        "type": "state",
        "ts": now,
        "scanning": bool(state.SCANNING),
        "runs": fleet_rows(workflows, query, now),
        "attention": [event.model_dump() for event in attention_events(workflows)],
        "status": status_bar(workflows),
        "store": store.health_dict(),
        "attend": attend_summary(),
    }


def run_message(
    wf: WorkflowContainer, tel: RunTelemetry | None = None, now: float | None = None
) -> dict[str, Any]:
    """A single-run delta."""
    if tel is None:
        tel = telemetry_for(wf)
    now = now if now is not None else time.time()
    return {"type": "run", "ts": now, "run": run_row(wf, tel, now)}


def repo_entries(
    entries: list[tuple[WorkflowContainer, list[str]]],
) -> list[dict[str, Any]]:
    """One group per container, each carrying the checkouts found on its volume."""
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


def handle(wf: WorkflowContainer) -> str:
    """The id the detail pane shows — whole, not a fragment."""
    if wf.native:
        return wf.run_id or wf.container_id
    return wf.container_id[:12]


def cli_label(tel: RunTelemetry | None) -> str:
    """The agent CLI the run's last turn actually used, and the model it drove."""
    if tel is None or not tel.backend:
        return ""
    return f"{tel.backend} {tel.model}".strip()


def head(
    wf: WorkflowContainer, tel: RunTelemetry | None = None, now: float | None = None
) -> dict[str, Any]:
    """The activity line at the top of the detail pane — what this run is doing right now."""
    now = now if now is not None else time.time()
    live_cls, live_label = liveness(wf, tel, now)
    return {
        "id": wf.container_id,
        "handle": handle(wf),
        "state": _row_state(wf, tel),
        "type": wf.workflow_type,
        "type_hue": type_hue(wf.workflow_type),
        "repo": repo_label(wf),
        "live": live_cls,
        "live_label": live_label,
        "node": tel.current_node if tel else wf.current_node,
        "pid": tel.pid if tel else wf.pid,
        "cli": cli_label(tel),
        "exit_hint": exit_hint(wf),
        "exit_ok": wf.exit_code == 0,
        "activity": tel.activity if tel else wf.activity,
    }


def metrics(
    wf: WorkflowContainer,
    tel: RunTelemetry | None = None,
    facts: dict[str, Any] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """The numbers worth having on screen while deciding whether to intervene."""
    now = now if now is not None else time.time()
    facts = facts or {}
    if tel is None and not facts:
        return {"empty": True, "cells": [], "alerts": [], "run_dir": ""}

    node = tel.current_node if tel else str(facts.get("node") or "")
    elapsed = tel.node_elapsed_s if tel else float(facts.get("node_elapsed_s") or 0.0)
    idle = tel.turn_idle_s if tel else float(facts.get("turn_idle_s") or 0.0)
    turn_active = tel.turn_active if tel else facts.get("turn_active")
    turn_elapsed = tel.turn_elapsed_s if tel else float(facts.get("turn_elapsed_s") or 0.0)
    wait_kind = tel.wait_kind if tel else str(facts.get("wait_kind") or "")
    wait_elapsed = tel.wait_elapsed_s if tel else float(facts.get("wait_elapsed_s") or 0.0)
    last_beat = tel.last_heartbeat_ts if tel else float(facts.get("last_beat_ts") or 0.0)
    started = tel.first_seen_ts if tel else float(facts.get("first_ts") or 0.0)

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
    gas = tel.gas if tel and tel.gas is not None else facts.get("gas")
    if gas is not None:
        cells.append({"key": "gas", "value": f"{float(gas):g}"})
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
    """The run's log lines, newest first — the trail that says *what* the current node has been doing, once the metrics have said it is stuck."""
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


def history_lines(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """History describes timestamped observations, never the run's current state."""
    lines = []
    for row in rows:
        kind = row["kind"]
        node = str(row.get("node") or "")
        if kind == "metric":
            attrs = row.get("attrs") or {}
            node = str(attrs.get("node") or "")
            name = str(row["name"]).removeprefix("workhorse.")
            value = float(row["value"])
            label = name.replace("_s", "").replace("_", " ").replace(".", " ")
            wait = str(attrs.get("wait_kind") or "")
            if wait and name.startswith("wait."):
                label = f"{wait} {label}"
            amount = fmt_duration(value) if name.endswith("_s") else f"{value:g}"
            body = f"{label}: {amount}"
        elif kind == "span":
            duration = fmt_duration(float(row["end_ts"]) - float(row["start_ts"]))
            body = f"{row['name']} · {row['status']} · {duration}"
        else:
            body = str(row.get("body") or "")
        lines.append({
            "ts": fmt_ts(float(row["ts"])), "kind": kind, "level": kind.upper(), "node": node,
            "body": body, "cls": SEVERITY_CLASS.get(str(row.get("severity") or ""), ""),
            "severity": str(row.get("severity") or ""),
        })
    return lines


def run_live(
    wf: WorkflowContainer,
    tel: RunTelemetry | None = None,
    facts: dict[str, Any] | None = None,
    logs: list[dict[str, Any]] | None = None,
    now: float | None = None,
    *, history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The clock-refreshable half of a detail pane: what changes while you watch it."""
    now = now if now is not None else time.time()
    return {
        "head": head(wf, tel, now),
        "metrics": metrics(wf, tel, facts, now),
        "logs": log_lines(logs),
        "history": history_lines(history or []),
    }


def run_detail(
    wf: WorkflowContainer,
    tel: RunTelemetry | None = None,
    facts: dict[str, Any] | None = None,
    logs: list[dict[str, Any]] | None = None,
    now: float | None = None,
    *, history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One run, top to bottom: what it is doing, the gates you can answer, its live metrics, its log trail."""
    now = now if now is not None else time.time()
    return {
        "found": True,
        "id": wf.container_id,
        "run_id": run_id_of(wf),
        "state": _row_state(wf, tel),
        "node": tel.current_node if tel else wf.current_node,
        "gates": [gate_dict(gate) for gate in reported_gates(wf, tel)],
        **run_live(wf, tel, facts, logs, now, history=history),
    }


def detail_message(
    wf: WorkflowContainer,
    tel: RunTelemetry | None = None,
    facts: dict[str, Any] | None = None,
    logs: list[dict[str, Any]] | None = None,
    now: float | None = None,
    *, history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A pushed detail refresh, addressed to the tabs watching this one run."""
    now = now if now is not None else time.time()
    return {
        "type": "detail",
        "ts": now,
        "id": wf.container_id,
        "detail": run_detail(wf, tel, facts, logs, now, history=history),
    }


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
    """The highlight.js language for a path, by extension (or by whole name for the extensionless files that still have a grammar)."""
    base = path.split("/")[-1].lower()
    if base == "dockerfile":
        return "dockerfile"
    if base == "makefile":
        return "makefile"
    _, dot, ext = base.rpartition(".")
    return EXT_LANG.get(ext, "") if dot else ""


