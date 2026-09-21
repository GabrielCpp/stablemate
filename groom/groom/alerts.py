"""Alert rules over the telemetry stream — what pages the AFK operator."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from groom import state, store
from groom.models import LIVENESS_METRICS, RunTelemetry


@dataclass
class Alert:
    run_id: str
    rule: str
    message: str


def _stall_after_s() -> float:
    return float(os.environ.get("GROOM_STALL_MIN", "90")) * 60


def _stuck_after_s() -> float:
    return float(os.environ.get("GROOM_STUCK_MIN", "75")) * 60


def _wait_after_s() -> float:
    return float(os.environ.get("GROOM_WAIT_MIN", "30")) * 60


def _churn_repeats() -> int:
    return int(os.environ.get("GROOM_CHURN_REPEATS", "5"))


def _giveup_nodes() -> set[str]:
    raw = os.environ.get("GROOM_GIVEUP_NODES", "qa_give_up,fix_give_up")
    return {name.strip() for name in raw.split(",") if name.strip()}


def _evict_grace_s() -> float:
    return float(os.environ.get("GROOM_RUN_EVICT_MIN", "30")) * 60


def _dead_after_s() -> float:
    return float(os.environ.get("GROOM_RUN_DEAD_HOURS", "48")) * 3600


def stale_run_ids(now: float | None = None) -> list[str]:
    """Run ids whose hot-cache entry can be dropped, so :data:`groom.state.RUNS` stops growing one entry per distinct run for the life of the process (and, with it, the per-tick :func:`check_time_rules` walk over that dict):"""
    now = now if now is not None else time.time()
    grace, dead = _evict_grace_s(), _dead_after_s()
    stale: list[str] = []
    for run in state.RUNS.values():
        last_alive = max(run.last_span_ts, run.last_heartbeat_ts, run.first_seen_ts)
        if run.terminal and (now - last_alive) > grace:
            stale.append(run.run_id)
        elif (now - last_alive) > dead:
            stale.append(run.run_id)
    return stale


def _run(run_id: str, now: float) -> RunTelemetry:
    run = state.RUNS.get(run_id)
    if run is None:
        run = RunTelemetry(run_id=run_id, first_seen_ts=now)
        state.RUNS[run_id] = run
    return run


def _clear_stale_terminal(run: RunTelemetry, ts: float) -> None:
    """Drop a terminal verdict that a newer signal has outlived."""
    if run.last_session is None and run.terminal and ts > run.terminal_ts:
        run.terminal = ""
        run.terminal_ts = 0.0
        run.fired.clear()


def _fire(run: RunTelemetry, rule: str, message: str, alerts: list[Alert]) -> None:
    if rule in run.fired:
        return
    run.fired.add(rule)
    alerts.append(Alert(run_id=run.run_id, rule=rule, message=message))


_RESERVED_ATTRS = ("workhorse.", "status_message", "events")


def _label_signature(attrs: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """The workflow-declared dimensions on a span, as a comparable key."""
    return tuple(
        sorted(
            (key, str(value))
            for key, value in attrs.items()
            if not key.startswith(_RESERVED_ATTRS[0]) and key not in _RESERVED_ATTRS[1:]
        )
    )


def _note_progress(run: RunTelemetry) -> None:
    """Forward progress: retire the churn page it disproves."""
    run.fired.discard("CHURN")


def _note_alive(run: RunTelemetry) -> None:
    """A signal arrived under this run's id: retire STALL."""
    run.fired.discard("STALL")


CLEAN_TERMINALS = frozenset({"terminal", "ended"})


def _ended_message(run: RunTelemetry, label: str, attrs: dict[str, Any]) -> str:
    """What the ENDED page says: the verdict first, then the wreckage if there is any."""
    terminal = run.terminal
    if terminal in CLEAN_TERMINALS:
        return f"{label}: finished ({terminal}) — nothing is running for it now"
    detail = str(attrs.get("error.class") or "")
    kind = str(attrs.get("error.kind") or "")
    because = f" [{'/'.join(part for part in (kind, detail) if part)}]" if detail or kind else ""
    return (
        f"{label}: ended '{terminal}'{because} — the run is over and did not get there "
        f"on its own terms"
        + (f" (last in '{run.current_node}')" if run.current_node else "")
    )


def note_native_ending(run: RunTelemetry, ending: str) -> list[Alert]:
    """Page for a **native** run that stopped without its root span saying so."""
    alerts: list[Alert] = []
    label = f"{run.workflow or 'run'} {run.run_id}"
    where = f" in node '{run.current_node}'" if run.current_node else ""
    if ending == "died":
        _fire(
            run,
            "DIED",
            f"{label}: process {run.pid or '?'} is gone{where} and left no terminal — "
            "killed, OOM'd or crashed. Nothing is running for it now; it resumes from "
            "its last checkpoint.",
            alerts,
        )
    else:
        _fire(
            run,
            "ENDED",
            f"{label}: ended '{ending}'{where} — read from the run's own record, which "
            "means its telemetry never got its last flush out.",
            alerts,
        )
    return alerts


def _activity(attrs: dict[str, Any]) -> str:
    """Current activity from pyflow, with the retired prefixed spelling as fallback."""
    return str(attrs.get("activity") or attrs.get("wf.activity") or "")


def _accept_session(run: RunTelemetry, record: dict[str, Any]) -> bool:
    """Replace session-local observations on resume; ignore delayed older exports."""
    generation = record.get("resume_generation")
    if generation is None:
        return True
    session = (int(record.get("pid") or 0), str(generation))
    if run.last_session == session:
        return True
    if run.last_session is not None and int(generation) <= int(run.last_session[1]):
        return False
    run.last_session = session
    run.current_node = ""
    run.activity = ""
    run.node_elapsed_s = 0.0
    run.turn_active = None
    run.turn_idle_s = 0.0
    run.turn_elapsed_s = 0.0
    run.wait_kind = ""
    run.wait_elapsed_s = 0.0
    run.wait_gate_path = ""
    run.wait_gate_question = ""
    run.wait_series = None
    run.closed_wait_series = set()
    run.terminal = ""
    run.terminal_ts = 0.0
    run.last_heartbeat_ts = 0.0
    run.last_beat_ts = 0.0
    run.backend = ""
    run.model = ""
    run.gas = None
    run.fired.clear()
    return True


def _wait_series(attrs: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """OTel series identity includes every attribute, including question and labels."""
    return tuple(sorted((key, str(value)) for key, value in attrs.items()))


def _wait_series_node(series: tuple[tuple[str, str], ...] | None) -> str:
    return dict(series).get("node", "") if series is not None else ""


def ingest_spans(spans: list[dict[str, Any]], now: float | None = None) -> list[Alert]:
    """Fold decoded spans into the hot cache and evaluate the ingest-driven rules."""
    now = now if now is not None else time.time()
    alerts: list[Alert] = []
    giveup = _giveup_nodes()
    for span in spans:
        run_id = span.get("run_id") or ""
        if not run_id:
            continue
        run = _run(run_id, now)
        if not _accept_session(run, span):
            continue
        _note_alive(run)
        run.workflow = span.get("workflow") or run.workflow
        run.repo = span.get("repo") or run.repo
        run.branch = span.get("branch") or run.branch
        run.run_dir = span.get("run_dir") or run.run_dir
        run.workspace = span.get("workspace") or run.workspace
        if span.get("pid") is not None:
            run.pid = span.get("pid")
        run.last_telemetry_ts = now
        run.last_span_ts = now
        _clear_stale_terminal(run, float(span.get("end_ts") or 0.0))
        attrs = span.get("attrs") or {}
        if activity := _activity(attrs):
            run.activity = activity
        events = {event.get("name") for event in attrs.get("events") or []}
        label = f"{run.workflow or 'run'} {run_id}"

        if span.get("name") == "agent_turn":
            if backend := str(attrs.get("backend") or ""):
                run.backend = backend
            if model := str(attrs.get("model") or ""):
                run.model = model

        if span.get("name", "").startswith("run:"):
            run.terminal = str(attrs.get("workhorse.terminal") or "ended")
            run.terminal_ts = float(span.get("end_ts") or now)
            _fire(run, "ENDED", _ended_message(run, label, attrs), alerts)
            continue

        if "watchdog_kill" in events:
            _fire(
                run,
                "WATCHDOG",
                f"{label}: watchdog SIGKILLed a wedged turn at node "
                f"'{span.get('node', '?')}'",
                alerts,
            )
        if span.get("node") in giveup:
            _fire(
                run,
                "GAVE-UP",
                f"{label}: gave up at node '{span.get('node')}' — a unit was "
                f"skipped after exhausting its retries",
                alerts,
            )

        node = span.get("node") or ""
        if node and span.get("name") == node and not attrs.get("workhorse.cut"):
            signature = _label_signature(attrs)
            if run.node_labels.get(node) != signature:
                run.node_labels[node] = signature
                run.node_counts[node] = 1
                _note_progress(run)
            else:
                run.node_counts[node] = run.node_counts.get(node, 0) + 1
            if run.node_counts[node] >= _churn_repeats():
                _fire(
                    run,
                    "CHURN",
                    f"{label}: node '{node}' completed {run.node_counts[node]}× "
                    f"on the same work — likely a loop whose exit condition "
                    f"never trips",
                    alerts,
                )
    return alerts


def ingest_metrics(points: list[dict[str, Any]], now: float | None = None) -> list[Alert]:
    """Fold decoded metric points into the hot cache, and evaluate BLOCKED."""
    now = now if now is not None else time.time()
    alerts: list[Alert] = []
    for point in points:
        run_id = point.get("run_id") or ""
        if not run_id:
            continue
        run = _run(run_id, now)
        if not _accept_session(run, point):
            continue
        _note_alive(run)
        run.workflow = point.get("workflow") or run.workflow
        run.repo = point.get("repo") or run.repo
        run.branch = point.get("branch") or run.branch
        run.run_dir = point.get("run_dir") or run.run_dir
        run.workspace = point.get("workspace") or run.workspace
        if point.get("pid") is not None:
            run.pid = point.get("pid")
        run.last_telemetry_ts = now
        _clear_stale_terminal(run, float(point.get("ts") or 0.0))
        name = point.get("name") or ""
        attrs = point.get("attrs") or {}
        node = str(attrs.get("node", ""))
        value = float(point.get("value") or 0.0)
        if (run.wait_series is not None and attrs.get("wait_kind")
                and _wait_series(attrs) != run.wait_series
                and (name == "workhorse.wait.elapsed_s"
                     or (name == "workhorse.wait.active" and value < 1))):
            continue
        if (name == "workhorse.wait.active" and value >= 1
                and attrs.get("wait_kind")
                and _wait_series(attrs) in run.closed_wait_series):
            continue
        if activity := _activity(attrs):
            run.activity = activity
        if name in LIVENESS_METRICS:
            run.last_heartbeat_ts = now
            run.last_beat_ts = max(run.last_beat_ts, float(point.get("ts") or 0.0))
            if name == "workhorse.run.heartbeat" and node:
                run.current_node = node
        elif name == "workhorse.gas":
            run.gas = value
        elif name == "workhorse.gas.refuels":
            run.node_counts.clear()
            _note_progress(run)
        elif name == "workhorse.node.active":
            if value >= 1:
                if run.current_node != node:
                    run.fired.discard("STUCK")
                    if run.wait_kind and _wait_series_node(run.wait_series) not in ("", node):
                        if run.wait_series is not None:
                            run.closed_wait_series.add(run.wait_series)
                        run.wait_kind = ""
                        run.wait_series = None
                        run.wait_elapsed_s = 0.0
                        run.wait_gate_path = ""
                        run.wait_gate_question = ""
                        run.fired.discard("BLOCKED")
                        run.fired.discard("WAITING")
                run.current_node = node
            elif run.current_node == node:
                run.current_node = ""
                run.node_elapsed_s = 0.0
                run.fired.discard("STUCK")
        elif name == "workhorse.node.elapsed_s":
            if not run.current_node or run.current_node == node:
                run.node_elapsed_s = value
        elif name == "workhorse.wait.active":
            if value >= 1:
                run.wait_series = _wait_series(attrs)
                run.wait_kind = str(attrs.get("wait_kind") or "unknown")
                if run.wait_kind in ("operator", "machine"):
                    run.wait_gate_path = str(attrs.get("gate_path") or "")
                    run.wait_gate_question = str(attrs.get("gate_question") or "")
                else:
                    run.wait_gate_path = ""
                    run.wait_gate_question = ""
                run.fired.discard("STUCK")
                if run.wait_kind == "operator":
                    _fire(
                        run,
                        "BLOCKED",
                        f"{run.workflow or 'run'} {run_id}: parked on an operator gate"
                        + (f" in '{run.current_node}'" if run.current_node else "")
                        + " — it will not move until someone answers it",
                        alerts,
                    )
            else:
                if run.wait_series is not None:
                    run.closed_wait_series.add(run.wait_series)
                run.wait_kind = ""
                run.wait_series = None
                run.wait_elapsed_s = 0.0
                run.wait_gate_path = ""
                run.wait_gate_question = ""
                run.fired.discard("BLOCKED")
                run.fired.discard("WAITING")
        elif name == "workhorse.wait.elapsed_s":
            if not run.wait_kind and (incoming_kind := str(attrs.get("wait_kind") or "")):
                run.wait_series = _wait_series(attrs)
                run.wait_kind = incoming_kind
                if run.wait_kind in ("operator", "machine"):
                    run.wait_gate_path = str(attrs.get("gate_path") or "")
                    run.wait_gate_question = str(attrs.get("gate_question") or "")
                run.fired.discard("STUCK")
                if run.wait_kind == "operator":
                    _fire(
                        run,
                        "BLOCKED",
                        f"{run.workflow or 'run'} {run_id}: parked on an operator gate"
                        + (f" in '{run.current_node}'" if run.current_node else "")
                        + " — it will not move until someone answers it",
                        alerts,
                    )
            if run.wait_kind:
                run.wait_elapsed_s = value
        elif name == "workhorse.turn.active":
            run.turn_active = value >= 1
            if not run.turn_active:
                run.turn_idle_s = 0.0
                run.turn_elapsed_s = 0.0
                run.fired.discard("STUCK")
        elif name == "workhorse.turn.elapsed_s":
            if run.turn_active is not False:
                run.turn_elapsed_s = value
        elif name == "workhorse.turn.idle_s":
            if run.turn_active is not False:
                run.turn_idle_s = value
                if value <= _stuck_after_s():
                    run.fired.discard("STUCK")
    return alerts


def live_status(run: str = "", now: float | None = None) -> list[dict[str, Any]]:
    """Where each run is *right now*, newest heartbeat first — from the hot cache."""
    now = now if now is not None else time.time()
    rows: list[dict[str, Any]] = []
    for tel in state.RUNS.values():
        if not tel.last_beat_ts or (run and tel.run_id != run):
            continue
        wait_kind = tel.wait_kind
        turn_active = tel.turn_active
        rows.append(
            {
                "run_id": tel.run_id,
                "workflow": tel.workflow,
                "run_dir": tel.run_dir,
                "node": tel.current_node,
                "node_elapsed_s": tel.node_elapsed_s,
                "turn_active": turn_active,
                "turn_elapsed_s": 0.0 if turn_active is False else tel.turn_elapsed_s,
                "turn_idle_s": 0.0 if turn_active is False else tel.turn_idle_s,
                "wait_kind": wait_kind,
                "wait_elapsed_s": tel.wait_elapsed_s if wait_kind else 0.0,
                "gas": tel.gas,
                "last_beat_ts": tel.last_beat_ts,
                "alive": (now - tel.last_beat_ts) <= store.LIVE_AFTER_S,
            }
        )
    return sorted(rows, key=lambda entry: entry["last_beat_ts"], reverse=True)


def live_run_ids(now: float | None = None) -> set[str]:
    """The run ids beating *right now* — the only liveness question that means anything."""
    return {entry["run_id"] for entry in live_status(now=now) if entry["alive"]}


def check_time_rules(now: float | None = None) -> list[Alert]:
    """The absence-driven rules, run by the periodic tick:"""
    now = now if now is not None else time.time()
    alerts: list[Alert] = []
    for run in state.RUNS.values():
        if run.terminal:
            continue
        label = f"{run.workflow or 'run'} {run.run_id}"
        last_alive = max(run.last_span_ts, run.last_heartbeat_ts, run.first_seen_ts)
        silence = now - last_alive
        if silence > _stall_after_s():
            _fire(
                run,
                "STALL",
                f"{label}: nothing emitted for {int(silence / 60)} min — no span "
                f"and no heartbeat. A live workhorse beats every few seconds, so "
                f"the process is gone, not merely busy"
                + (f" (last seen in '{run.current_node}')" if run.current_node else ""),
                alerts,
            )
        elif run.wait_kind:
            if run.wait_kind == "operator" and run.wait_elapsed_s > _wait_after_s():
                _fire(
                    run,
                    "WAITING",
                    f"{label}: still parked on an operator gate"
                    + (f" in '{run.current_node}'" if run.current_node else "")
                    + f" after {int(run.wait_elapsed_s / 60)} min — nothing is running "
                    f"for it, and nothing will until it is answered",
                    alerts,
                )
            continue
        elif run.turn_active is True and run.turn_idle_s > _stuck_after_s():
            _fire(
                run,
                "STUCK",
                f"{label}: agent turn in '{run.current_node}' has been silent for "
                f"{int(run.turn_idle_s / 60)} min while the process keeps heartbeating",
                alerts,
            )
        elif (
            run.turn_active is not True
            and run.current_node
            and run.node_elapsed_s > _stuck_after_s()
        ):
            _fire(
                run,
                "STUCK",
                f"{label}: alive (heartbeating) but node '{run.current_node}' has "
                f"been open {int(run.node_elapsed_s / 60)} min"
                + " — the run is not hung, it is not progressing",
                alerts,
            )
    return alerts
