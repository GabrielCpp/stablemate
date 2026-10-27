"""The windowed read of one run behind the /feed digest frames."""
from __future__ import annotations

import json
import time
from collections import Counter

from groom import alerts, state, store
from groom.attention import (
    DigestFrame,
    Gate,
    Lap,
    LogLine,
    NodeVisit,
    Standing,
    Window,
)
from groom.projection import fmt_duration

MAX_WARNINGS = 10
SPAN_LIMIT = 1000


def _clock(ts: float) -> str:
    return time.strftime("%H:%M", time.localtime(ts))


def _standing(run_id: str, now: float) -> Standing:
    rows = alerts.live_status(run=run_id, now=now)
    fields = {
        key: rows[0][key]
        for key in (
            "node", "node_elapsed_s", "turn_active", "turn_elapsed_s", "turn_idle_s",
            "wait_kind", "wait_elapsed_s", "gas", "alive",
        )
    } if rows else {}
    telemetry = state.RUNS.get(run_id)
    if telemetry is not None:
        fields.update(
            terminal=telemetry.terminal,
            wait_gate_question=telemetry.wait_gate_question,
            wait_gate_path=telemetry.wait_gate_path,
        )
    return Standing(**fields)


def _window(
    run_id: str, since: float, until: float
) -> tuple[Window, bool]:
    spans = store.query_spans(
        run=run_id, since_ts=since, before_ts=until, limit=SPAN_LIMIT
    )
    charges = store.turn_charges(run_id)
    visits: dict[str, NodeVisit] = {}
    items: Counter[tuple[str, str]] = Counter()
    gates: list[Gate] = []
    cost = 0.0
    tokens = 0
    turns = 0
    for span in reversed(spans):
        attrs = json.loads(span["attrs_json"] or "{}")
        node = span["node"]
        kind = attrs.get("workhorse.span_kind")
        if kind == "wait":
            if attrs.get("workhorse.wait_kind") == "operator":
                gates.append(Gate(
                    kind="operator", node=node,
                    outcome=str(attrs.get("workhorse.wait_outcome") or ""),
                    question=str(attrs.get("workhorse.gate_question") or ""),
                ))
            continue
        if not node:
            continue
        visit = visits.setdefault(node, NodeVisit(node=node))
        if span["name"] == "agent_turn":
            turn_cost = float(charges.get(span["span_id"], attrs.get("total_cost_usd")) or 0.0)
            turn_tokens = int(attrs.get("usage.output_tokens") or 0)
            visit.turns += 1
            visit.cost_usd += turn_cost
            visit.output_tokens += turn_tokens
            turns += 1
            cost += turn_cost
            tokens += turn_tokens
            work_id = attrs.get("work_id")
            if work_id is not None:
                items[(node, str(work_id))] += 1
        elif span["name"] == node:
            visit.visits += 1
    logs = store.query_logs(
        run=run_id, level="WARNING", limit=MAX_WARNINGS, since_ts=since, before_ts=until
    )
    events = [
        event
        for ts, event in state.EVENTS.get(run_id, ())
        if since < ts <= until
    ]
    window = Window(
        nodes=list(visits.values()),
        laps=[Lap(node=node, work_id=work_id, turns=count) for (node, work_id), count in items.items()],
        gates=gates,
        events=events,
        warnings=[
            LogLine(
                ts=row["ts"], level=row["severity"], node=row["node"], message=row["body"]
            )
            for row in reversed(logs)
        ],
        cost_usd=cost,
        output_tokens=tokens,
        turns=turns,
    )
    return window, not spans and not events and not logs


def digest_summary(frame: DigestFrame) -> str:
    standing, window = frame.standing, frame.window
    span = f"{_clock(frame.since)}-{_clock(frame.until)}"
    spend = f"+${window.cost_usd:.2f}"
    if frame.quiet:
        parts = [f"quiet {span}"]
        if standing.terminal:
            parts.append(f"ended {standing.terminal}")
        elif standing.node:
            parts.append(f"in {standing.node} {fmt_duration(standing.node_elapsed_s)}")
        if standing.wait_kind:
            parts.append(f"waiting {standing.wait_kind} {fmt_duration(standing.wait_elapsed_s)}")
        elif standing.turn_active:
            parts.append(f"turn streaming, idle {fmt_duration(standing.turn_idle_s)}")
        if not standing.alive and not standing.terminal:
            parts.append("no heartbeat")
        parts.append(spend)
        return " · ".join(parts)
    parts = [
        span,
        f"{len(window.nodes)} nodes, {window.turns} turns, {spend}",
    ]
    repeated = [lap for lap in window.laps if lap.turns > 1]
    if repeated:
        worst = max(repeated, key=lambda lap: lap.turns)
        count = sum(1 for lap in repeated if lap.node == worst.node)
        parts.append(f"lap {worst.turns} on {worst.node} ({count} items)")
    if window.events:
        names = ", ".join(sorted({event.event for event in window.events}))
        parts.append(f"{len(window.events)} events: {names}")
    if window.gates:
        parts.append(f"{len(window.gates)} gate raised" if len(window.gates) == 1 else f"{len(window.gates)} gates raised")
    if window.warnings:
        parts.append(f"{len(window.warnings)} warnings" if len(window.warnings) != 1 else "1 warning")
    return " · ".join(parts)


def build_digest(
    run_id: str, since: float, until: float, *, now: float | None = None
) -> DigestFrame:
    wall = now if now is not None else time.time()
    window, quiet = _window(run_id, since, until)
    frame = DigestFrame(
        seq=0, ts=wall, since=since, until=until, quiet=quiet, summary="",
        standing=_standing(run_id, wall), window=window,
    )
    return frame.model_copy(update={"summary": digest_summary(frame)})
