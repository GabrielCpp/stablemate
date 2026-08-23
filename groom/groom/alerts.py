"""Alert rules over the telemetry stream — what pages the AFK operator.

Ingest-driven rules fire the moment their evidence arrives (a watchdog-kill
span event, a give-up node span, the Nth repeat of a churning node, the root
span that says the run is over); the absence-driven rules (STALL, STUCK) are
evaluated by a periodic tick, since silence by definition never triggers an
ingest. All rules dedupe per ``(run_id, rule)`` via ``RunTelemetry.fired`` —
one page per failure mode per run, not one per span.

ENDED is the one rule that is not about a run behaving badly, and it exists
because the absence rules structurally cannot cover a run that *stopped*: a
terminal retires the run from STALL and STUCK, and 30 minutes later evicts it
from the cache entirely. So the loudest possible fleet event — the run is over,
nothing is executing, the queue is idle until someone launches the next one —
was the only one that paged nobody. On a queue an operator is away from, hours
go by before anyone notices, and they are hours nothing was running.

BLOCKED and WAITING exist for the same reason ENDED does: a run parked on an
operator gate is not misbehaving, so no rule described it — and STUCK explicitly
skips a run with an open wait, since being parked is what the gate is for. The
result was that the one condition a page can actually *fix* — a human is the
bottleneck and does not know it — reached only an open browser tab. BLOCKED
fires the moment the gate opens; WAITING is the reminder for a gate that opened
while nobody was looking. Only an ``operator`` wait counts: a cap wait is the
runner throttling itself and no page shortens it.

``fired`` is also what the dashboard renders as a run's alert badges, so the
rules that describe a *current* condition retire themselves when the condition
lifts: STALL on any signal arriving (see :func:`_note_alive`), STUCK when its
node closes or the run moves to another, CHURN on forward progress, BLOCKED and
WAITING when the wait closes.
Without that a page is permanent — a laptop that idle-sleeps past the stall
window marks its run dead for the life of the groom process, however healthily
it resumes. WATCHDOG, GAVE-UP and ENDED stay set because they report events that
happened — and a resume clears the whole set anyway (see
:func:`_clear_stale_terminal`), so the next session's ending pages on its own.

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
    rule: str  # STALL | STUCK | CHURN | WATCHDOG | GAVE-UP | ENDED | DIED
    #      | BLOCKED | WAITING
    message: str


def _stall_after_s() -> float:
    return float(os.environ.get("GROOM_STALL_MIN", "90")) * 60


def _stuck_after_s() -> float:
    # Deliberately above workhorse's own 1h default per-turn timeout, so a node
    # that is merely slow gets force-killed and retried by the runner before
    # groom would page anyone about it.
    return float(os.environ.get("GROOM_STUCK_MIN", "75")) * 60


def _wait_after_s() -> float:
    # Far below the STUCK threshold on purpose: a run parked on an operator gate is
    # not slow, it is finished until a human types something. Every minute past this
    # is a minute nobody knew they were the bottleneck.
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


#: Terminals that mean the run stopped on purpose, having reached the workflow's own
#: end. Everything else — ``fail``, ``aborted``, ``interrupted``, or a terminal
#: workhorse did not stamp at all — stopped for a reason nobody chose.
_CLEAN_TERMINALS = frozenset({"terminal", "ended"})


def _ended_message(run: RunTelemetry, label: str, attrs: dict[str, Any]) -> str:
    """What the ENDED page says: the verdict first, then the wreckage if there is any."""
    terminal = run.terminal
    if terminal in _CLEAN_TERMINALS:
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
    """Page for a **native** run that stopped without its root span saying so.

    Every other ending rule here is ingest-driven, and ENDED is the loudest of them —
    but it hangs off the root span, and a root span only exports if the dying process
    got its exporter flushed. The one class of death that never does is exactly the
    one worth paging about: SIGKILL, the OOM killer, a segfaulting extension. So the
    fleet event an operator most needs — the queue is idle because a run was killed —
    was the single ending that reached nobody. The dashboard row already turned grey
    (``groom.app._native_ending`` reads the same-host evidence), and then the run was
    evicted 30 minutes later, all of it in silence.

    Two endings, two rules, because they are different news. A terminal groom read out
    of ``run.json`` is the run's own account of itself, so it pages as ENDED — the same
    rule and the same dedupe slot the root span would use, which is what stops a
    late-arriving export from paging twice about one ending. ``died`` has no account
    behind it and gets its own rule, so a page that says the process vanished is never
    confused with one that says the run finished badly.
    """
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

        # Which harness ran the turn, latest wins. The ladder chooses a backend per
        # turn and falls through to another when one is capped or broken, so this is
        # a property of the run's last turn rather than of the run — which is exactly
        # why it is worth showing: a run that quietly moved to a different CLI looks
        # identical on every other line of the dashboard.
        if span.get("name") == "agent_turn":
            if backend := str(attrs.get("backend") or ""):
                run.backend = backend
            if model := str(attrs.get("model") or ""):
                run.model = model

        if span.get("name", "").startswith("run:"):
            # The root span only exports when the run ENDS — its arrival is the
            # "run over" signal that retires this run from absence-rule watch. It
            # retires only the session it closed: a later resume under the same
            # run_id clears it again via ``_clear_stale_terminal``.
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

        # Churn: node-span repeats ON THE SAME WORK. Only completed NODE spans
        # count (agent_turn retries are the ladder doing its job), and a repeat
        # under a different label signature is progress, not a repeat.
        #
        # `workhorse.cut` is how a span says it ended without finishing: workhorse
        # closes the whole open scope when a live reload interrupts a run, so the node
        # exports rather than being lost, and stamps why. Counting those would make an
        # operator pushing fixes into a broken flow page for churn on the fifth push —
        # the reload reported as the loop it was breaking.
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
    """Fold decoded metric points into the hot cache, and evaluate BLOCKED.

    This used to return ``[]`` unconditionally — every rule was span- or
    tick-driven. BLOCKED is neither: an operator gate opens a *wait*, which is a
    metric, and the gate is worth paging about the instant it opens rather than
    after a threshold.

    Metrics carry the live picture that spans structurally cannot: a span only
    exports when it ends, so a run's CURRENT node — the one that matters when it
    hangs — never appears in the trace. The heartbeats prove the process is
    alive, ``node.active`` says where it is, and ``node.elapsed_s`` /
    ``turn.idle_s`` say whether being there is normal. A gas refuel marks forward
    progress and resets the churn counters.
    """
    now = now if now is not None else time.time()
    alerts: list[Alert] = []
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
                run.wait_kind = ""
                run.wait_elapsed_s = 0.0
                # The gate was answered: both pages assert a wait that is open right
                # now, so leaving them set badges a moving run as parked forever.
                run.fired.discard("BLOCKED")
                run.fired.discard("WAITING")
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
    return alerts


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
    - WAITING — an operator gate still unanswered past ``GROOM_WAIT_MIN``. Not an
      absence at all, but it needs the tick for the same reason STUCK does: the
      evidence is a duration that no single ingest ever crosses.
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
            # An open wait is never STUCK — the run is parked on purpose. But an
            # operator gate nobody has answered is the one wait a page can shorten,
            # and BLOCKED only fires once, when the gate opens. WAITING is the
            # reminder for the gate that opened while nobody was looking. A cap wait
            # is exempt outright: it is the runner throttling itself.
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
