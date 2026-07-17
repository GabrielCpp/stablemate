"""Alert rules over the telemetry stream — what pages the AFK operator.

Ingest-driven rules fire the moment their evidence arrives (a watchdog-kill
span event, a give-up node span, the Nth repeat of a churning node); the
absence-driven rules (STALL, STUCK, BUDGET) are evaluated by a periodic tick,
since silence by definition never triggers an ingest. All rules dedupe per
``(run_id, rule)`` via ``RunTelemetry.fired`` — one page per failure mode per
run, not one per span.

STALL and STUCK split what used to be one ambiguous rule. Workhorse now beats
continuously while its process lives, so silence and slowness are different
observations rather than the same one: STALL means the run stopped emitting
(the process died), STUCK means it is emitting but parked in one node. Before
the heartbeat existed, a long agent turn produced exactly the silence STALL
looked for — an open span does not export — so any turn longer than the stall
window paged as hung.

The rules read the :data:`groom.state.RUNS` hot cache, which this module also
maintains from decoded spans/metrics. Thresholds come from env (read per call
so tests can patch): ``GROOM_STALL_MIN`` (90), ``GROOM_STUCK_MIN`` (75),
``GROOM_MAX_HOURS`` (24), ``GROOM_CHURN_REPEATS`` (5), ``GROOM_GIVEUP_NODES``
(qa_give_up,fix_give_up — groom, not workhorse, knows these names: the engine
stays workflow-agnostic and just reports node spans).
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
    rule: str  # STALL | STUCK | BUDGET | CHURN | WATCHDOG | GAVE-UP
    message: str


def _stall_after_s() -> float:
    return float(os.environ.get("GROOM_STALL_MIN", "90")) * 60


def _stuck_after_s() -> float:
    # Deliberately above workhorse's own 1h default per-turn timeout, so a node
    # that is merely slow gets force-killed and retried by the runner before
    # groom would page anyone about it.
    return float(os.environ.get("GROOM_STUCK_MIN", "75")) * 60


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


# Every workhorse liveness tick. All three mean the same thing to the rules —
# the run's process is alive — and differ only in what the run is busy with:
# a cap sleep, a streaming agent turn, or any node at all (the run heartbeat,
# which is the only one a buffered script node produces).
_LIVENESS_METRICS = frozenset(
    {
        "workhorse.cap_wait.heartbeat",
        "workhorse.turn.heartbeat",
        "workhorse.run.heartbeat",
    }
)


def ingest_metrics(points: list[dict[str, Any]], now: float | None = None) -> list[Alert]:
    """Fold decoded metric points into the hot cache.

    Metrics carry the live picture that spans structurally cannot: a span only
    exports when it ends, so a run's CURRENT node — the one that matters when it
    hangs — never appears in the trace. The heartbeats prove the process is
    alive, ``node.active`` says where it is, and ``node.elapsed_s`` /
    ``turn.idle_s`` say whether being there is normal. A gas refuel marks forward
    progress and resets the churn counters.
    """
    now = now if now is not None else time.time()
    for point in points:
        run_id = point.get("run_id") or ""
        if not run_id:
            continue
        run = _run(run_id, now)
        run.workflow = point.get("workflow") or run.workflow
        name = point.get("name") or ""
        attrs = point.get("attrs") or {}
        node = str(attrs.get("node", ""))
        value = float(point.get("value") or 0.0)
        if name in _LIVENESS_METRICS:
            run.last_heartbeat_ts = now
        elif name == "workhorse.gas.refuels":
            run.node_counts.clear()
        elif name == "workhorse.node.active":
            if value >= 1:
                run.current_node = node
            elif run.current_node == node:
                # Only the node that closed clears the pointer — a stale 0 for an
                # already-superseded node must not blank the one now running.
                run.current_node = ""
                run.node_elapsed_s = 0.0
        elif name == "workhorse.node.elapsed_s":
            if not run.current_node or run.current_node == node:
                run.node_elapsed_s = value
        elif name == "workhorse.turn.idle_s":
            run.turn_idle_s = value
    return []


def check_time_rules(now: float | None = None) -> list[Alert]:
    """The absence-driven rules, run by the periodic tick:

    - STALL — a live run emitting NOTHING for the stall window: no span, no
      heartbeat of any kind. Since workhorse beats every few seconds from a
      daemon thread for as long as its process exists, silence here no longer
      means "busy" — it means the process is gone or frozen below the
      interpreter (SIGKILL, OOM, a suspended host).
    - STUCK — the mirror image, and the one a script-heavy workflow actually
      hits: the run IS beating, but has sat in one node past the threshold. It
      is alive and going nowhere. This is invisible to the trace (the node's
      span will not export until it ends) and used to be misfiled as a STALL.
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
                f"{label}: nothing emitted for {int(silence / 60)} min — no span "
                f"and no heartbeat. A live workhorse beats every few seconds, so "
                f"the process is gone, not merely busy"
                + (f" (last seen in '{run.current_node}')" if run.current_node else ""),
                alerts,
            )
        elif run.current_node and run.node_elapsed_s > _stuck_after_s():
            _fire(
                run,
                "STUCK",
                f"{label}: alive (heartbeating) but node '{run.current_node}' has "
                f"been open {int(run.node_elapsed_s / 60)} min"
                + (
                    f", agent silent for {int(run.turn_idle_s / 60)} min"
                    if run.turn_idle_s > 60
                    else ""
                )
                + " — the run is not hung, it is not progressing",
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
