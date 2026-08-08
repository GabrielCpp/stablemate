"""Alert rules over the telemetry stream — what pages the AFK operator.

Ingest-driven rules fire the moment their evidence arrives (a watchdog-kill
span event, a give-up node span, the Nth repeat of a churning node); the
absence-driven rules (STALL, STUCK) are evaluated by a periodic tick,
since silence by definition never triggers an ingest. All rules dedupe per
``(run_id, rule)`` via ``RunTelemetry.fired`` — one page per failure mode per
run, not one per span.

``fired`` is also what the dashboard renders as a run's alert badges, so the
three rules that describe a *current* condition retire themselves when the
condition lifts: STALL on any signal arriving (see :func:`_note_alive`), STUCK
when its node closes or the run moves to another, CHURN on forward progress.
Without that a page is permanent — a laptop that idle-sleeps past the stall
window marks its run dead for the life of the groom process, however healthily
it resumes. WATCHDOG and GAVE-UP stay set because they report events that
happened.

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
``GROOM_CHURN_REPEATS`` (5), ``GROOM_GIVEUP_NODES``
(qa_give_up,fix_give_up — groom, not workhorse, knows these names: the engine
stays workflow-agnostic and just reports node spans).

CHURN counts repeats *on the same work*, keyed by the workflow's declared
labels. It used to count bare node repeats and reset only on a gas refuel, which
made it structurally unfirable-but-always-firing for the pyflow engine: pyflow
has no gas tank, nothing emits ``workhorse.gas.refuels``, and so a drain-shaped
workflow tripped the rule on its fifth healthy iteration and never untripped.
The labels carry which unit each iteration was for, which is the forward-progress
signal the refuel counter used to report — and the one an engine without a tank
still emits.
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
    rule: str  # STALL | STUCK | CHURN | WATCHDOG | GAVE-UP
    message: str


def _stall_after_s() -> float:
    return float(os.environ.get("GROOM_STALL_MIN", "90")) * 60


def _stuck_after_s() -> float:
    # Deliberately above workhorse's own 1h default per-turn timeout, so a node
    # that is merely slow gets force-killed and retried by the runner before
    # groom would page anyone about it.
    return float(os.environ.get("GROOM_STUCK_MIN", "75")) * 60


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
    """Run ids whose hot-cache entry can be dropped, so :data:`groom.state.RUNS`
    stops growing one entry per distinct run for the life of the process (and, with
    it, the per-tick :func:`check_time_rules` walk over that dict):

    - a **terminated** run, kept a grace window after its root span so a just-finished
      run doesn't vanish from the dashboard mid-glance, then evicted;
    - a run **silent past the dead window** — no span, no heartbeat for so long its
      process is certainly gone even though it never emitted a terminal (SIGKILL/OOM).

    Native dashboard rows are retired alongside their run (see ``state.evict_runs``).
    """
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
    """Drop a terminal verdict that a newer signal has outlived.

    ``run_id`` is derived from the run dir, so ``--resume-run`` reuses it and the
    root span of an EARLIER session arrives under the same key. Nothing else ever
    unsets ``terminal`` — the engine has no "a new session started" signal, because
    a root span only exports when it *ends* — so without this a resumed run stayed
    marked dead for the life of the groom process: rendered finished on the
    dashboard while it was actively emitting, and eventually evicted from the fleet.

    Any span or metric stamped after the root span's own end proves a live process,
    which is the only thing "running right now" means. The fired-rule set goes with
    it: this is a new session, and it deserves its own pages.
    """
    if run.terminal and ts > run.terminal_ts:
        run.terminal = ""
        run.terminal_ts = 0.0
        run.fired.clear()


def _fire(run: RunTelemetry, rule: str, message: str, alerts: list[Alert]) -> None:
    if rule in run.fired:
        return
    run.fired.add(rule)
    alerts.append(Alert(run_id=run.run_id, rule=rule, message=message))


#: Span attribute keys that are workhorse's own, not the workflow's `labels:`.
#: ``workhorse.seq`` and ``workhorse.depth`` increment on every span, so a
#: signature that kept them would never match itself and churn could not fire at
#: all — the mirror of the bug this signature exists to fix.
_RESERVED_ATTRS = ("workhorse.", "status_message", "events")


def _label_signature(attrs: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """The workflow-declared dimensions on a span, as a comparable key.

    These are the graph's ``labels:`` — okf-builder stamps ``work_id`` and
    ``progress``, coder stamps the story — rendered against the live context and
    stamped on every span of that node visit. They answer "which unit of work was
    this?", which is precisely what distinguishes a drain iterating over its
    worklist from a loop rerunning one item forever.
    """
    return tuple(
        sorted(
            (key, str(value))
            for key, value in attrs.items()
            if not key.startswith(_RESERVED_ATTRS[0]) and key not in _RESERVED_ATTRS[1:]
        )
    )


def _note_progress(run: RunTelemetry) -> None:
    """Forward progress: retire the churn page it disproves.

    ``fired`` is what the dashboard renders as a run's alert badges, so a CHURN
    left set after the run demonstrably moved on marks a healthy run as looping
    for the life of the groom process. It re-fires if the churn recurs.
    """
    run.fired.discard("CHURN")


def _note_alive(run: RunTelemetry) -> None:
    """A signal arrived under this run's id: retire STALL.

    STALL asserts the process is *gone* — not slow, gone. Anything arriving for
    the run refutes that outright, so the page is not merely stale, it is false.
    A host that suspends mid-run (an idle laptop sleeping past the stall window)
    produces exactly this: real silence, a true page, and then a recovery the run
    has no way to announce. If the run goes quiet again, the next periodic tick
    fires STALL again on its own.

    A late buffered export from a genuinely dead process clears it spuriously —
    and then nothing further arrives and the next tick re-fires. Self-correcting,
    which a permanently wrong badge is not.
    """
    run.fired.discard("STALL")


def _activity(attrs: dict[str, Any]) -> str:
    """Current activity from pyflow, with the retired prefixed spelling as fallback."""
    return str(attrs.get("activity") or attrs.get("wf.activity") or "")


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
        _note_alive(run)
        run.workflow = span.get("workflow") or run.workflow
        run.repo = span.get("repo") or run.repo
        run.branch = span.get("branch") or run.branch
        run.run_dir = span.get("run_dir") or run.run_dir
        run.workspace = span.get("workspace") or run.workspace
        if span.get("pid") is not None:
            run.pid = span.get("pid")
        run.last_span_ts = now
        _clear_stale_terminal(run, float(span.get("end_ts") or 0.0))
        attrs = span.get("attrs") or {}
        if activity := _activity(attrs):
            run.activity = activity
        events = {event.get("name") for event in attrs.get("events") or []}
        label = f"{run.workflow or 'run'} {run_id}"

        if span.get("name", "").startswith("run:"):
            # The root span only exports when the run ENDS — its arrival is the
            # "run over" signal that retires this run from absence-rule watch. It
            # retires only the session it closed: a later resume under the same
            # run_id clears it again via ``_clear_stale_terminal``.
            run.terminal = str(attrs.get("workhorse.terminal") or "ended")
            run.terminal_ts = float(span.get("end_ts") or now)
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

        # Churn: node-span repeats ON THE SAME WORK. Only completed NODE spans
        # count (agent_turn retries are the ladder doing its job), and a repeat
        # under a different label signature is progress, not a repeat.
        node = span.get("node") or ""
        if node and span.get("name") == node:
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
        _note_alive(run)
        run.workflow = point.get("workflow") or run.workflow
        run.repo = point.get("repo") or run.repo
        run.branch = point.get("branch") or run.branch
        run.run_dir = point.get("run_dir") or run.run_dir
        run.workspace = point.get("workspace") or run.workspace
        if point.get("pid") is not None:
            run.pid = point.get("pid")
        _clear_stale_terminal(run, float(point.get("ts") or 0.0))
        name = point.get("name") or ""
        attrs = point.get("attrs") or {}
        node = str(attrs.get("node", ""))
        value = float(point.get("value") or 0.0)
        if activity := _activity(attrs):
            run.activity = activity
        if name in _LIVENESS_METRICS:
            run.last_heartbeat_ts = now
        elif name == "workhorse.gas.refuels":
            run.node_counts.clear()
            _note_progress(run)
        elif name == "workhorse.node.active":
            if value >= 1:
                if run.current_node != node:
                    # Moved to a different node: whatever it was parked in, it is
                    # demonstrably not parked there now.
                    run.fired.discard("STUCK")
                run.current_node = node
            elif run.current_node == node:
                # Only the node that closed clears the pointer — a stale 0 for an
                # already-superseded node must not blank the one now running.
                run.current_node = ""
                run.node_elapsed_s = 0.0
                # STUCK asserts this node is open past the threshold. It just
                # closed, so the assertion is now false rather than merely old.
                run.fired.discard("STUCK")
        elif name == "workhorse.node.elapsed_s":
            if not run.current_node or run.current_node == node:
                run.node_elapsed_s = value
        elif name == "workhorse.wait.active":
            if value >= 1:
                run.wait_kind = str(attrs.get("wait_kind") or "unknown")
                run.fired.discard("STUCK")
            else:
                run.wait_kind = ""
                run.wait_elapsed_s = 0.0
        elif name == "workhorse.wait.elapsed_s":
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
        elif run.wait_kind:
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
