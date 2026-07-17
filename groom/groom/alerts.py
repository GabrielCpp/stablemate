"""Alert rules over the telemetry stream — what pages the AFK operator.

Ingest-driven rules fire the moment their evidence arrives (a watchdog-kill
span event, a give-up node span, the Nth repeat of a churning node); the
absence-driven rules (STALL, BUDGET) are evaluated by a periodic tick, since
silence by definition never triggers an ingest. All rules dedupe per
``(run_id, rule)`` via ``RunTelemetry.fired`` — one page per failure mode per
run, not one per span.

The rules read the :data:`groom.state.RUNS` hot cache, which this module also
maintains from decoded spans/metrics. Thresholds come from env (read per call
so tests can patch): ``GROOM_STALL_MIN`` (90), ``GROOM_MAX_HOURS`` (24),
``GROOM_CHURN_REPEATS`` (5), ``GROOM_GIVEUP_NODES`` (qa_give_up,fix_give_up —
groom, not workhorse, knows these names: the engine stays workflow-agnostic
and just reports node spans).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from groom import state
from groom.models import RunTelemetry


@dataclass
class Alert:
    run_id: str
    rule: str  # STALL | BUDGET | CHURN | WATCHDOG | GAVE-UP
    message: str


def _stall_after_s() -> float:
    return float(os.environ.get("GROOM_STALL_MIN", "90")) * 60


def _budget_s() -> float:
    return float(os.environ.get("GROOM_MAX_HOURS", "24")) * 3600


def _churn_repeats() -> int:
    return int(os.environ.get("GROOM_CHURN_REPEATS", "5"))


def _giveup_nodes() -> set[str]:
    raw = os.environ.get("GROOM_GIVEUP_NODES", "qa_give_up,fix_give_up")
    return {name.strip() for name in raw.split(",") if name.strip()}


def _run(run_id: str, now: float) -> RunTelemetry:
    run = state.RUNS.get(run_id)
    if run is None:
        run = RunTelemetry(run_id=run_id, first_seen_ts=now)
        state.RUNS[run_id] = run
    return run


def _fire(run: RunTelemetry, rule: str, message: str, alerts: list[Alert]) -> None:
    if rule in run.fired:
        return
    run.fired.add(rule)
    alerts.append(Alert(run_id=run.run_id, rule=rule, message=message))


def ingest_spans(spans: list[dict[str, Any]], now: float | None = None) -> list[Alert]:
    """Fold decoded spans into the hot cache and evaluate the ingest-driven
    rules. Returns the alerts that newly fired (already deduped)."""
    now = now if now is not None else time.time()
    alerts: list[Alert] = []
    giveup = _giveup_nodes()
    for span in spans:
        run_id = span.get("run_id") or ""
        if not run_id:
            continue
        run = _run(run_id, now)
        run.workflow = span.get("workflow") or run.workflow
        run.repo = span.get("repo") or run.repo
        run.branch = span.get("branch") or run.branch
        run.last_span_ts = now
        attrs = span.get("attrs") or {}
        events = {event.get("name") for event in attrs.get("events") or []}
        label = f"{run.workflow or 'run'} {run_id}"

        if span.get("name", "").startswith("run:"):
            # The root span only exports when the run ENDS — its arrival is the
            # "run over" signal that retires this run from STALL/BUDGET watch.
            run.terminal = str(attrs.get("workhorse.terminal") or "ended")
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

        # Churn: node-span repeats since the last refuel. Only completed NODE
        # spans count (agent_turn retries are the ladder doing its job).
        node = span.get("node") or ""
        if node and span.get("name") == node:
            run.node_counts[node] = run.node_counts.get(node, 0) + 1
            if run.node_counts[node] >= _churn_repeats():
                _fire(
                    run,
                    "CHURN",
                    f"{label}: node '{node}' completed {run.node_counts[node]}× "
                    f"with no forward progress (no gas refuel) — likely a loop "
                    f"whose exit condition never trips",
                    alerts,
                )
    return alerts


def ingest_metrics(points: list[dict[str, Any]], now: float | None = None) -> list[Alert]:
    """Fold decoded metric points into the hot cache. The cap-wait heartbeat is
    the one that matters: it is the liveness proof that suppresses STALL during
    a legitimate multi-hour/day cap sleep. A gas refuel marks forward progress
    and resets the churn counters."""
    now = now if now is not None else time.time()
    for point in points:
        run_id = point.get("run_id") or ""
        if not run_id:
            continue
        run = _run(run_id, now)
        run.workflow = point.get("workflow") or run.workflow
        name = point.get("name") or ""
        if name == "workhorse.cap_wait.heartbeat":
            run.last_heartbeat_ts = now
        elif name == "workhorse.gas.refuels":
            run.node_counts.clear()
    return []


def check_time_rules(now: float | None = None) -> list[Alert]:
    """The absence-driven rules, run by the periodic tick:

    - STALL — a live run with NO span and NO cap-wait heartbeat for the stall
      window. A heartbeating cap-wait is provably alive; silence is a hang.
    - BUDGET — a live run older than the wall-clock ceiling (first-seen clock;
      the root span would have arrived if it had ended).
    """
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
                f"{label}: silent for {int(silence / 60)} min — no span and no "
                f"cap-wait heartbeat. Not a cap sleep (those heartbeat); "
                f"likely hung.",
                alerts,
            )
        age = now - run.first_seen_ts
        if age > _budget_s():
            _fire(
                run,
                "BUDGET",
                f"{label}: still running after {age / 3600:.1f} h — past the "
                f"GROOM_MAX_HOURS ceiling",
                alerts,
            )
    return alerts
