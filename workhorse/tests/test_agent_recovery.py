"""Tests for AgentRunner.run's resilience ladder: transient retry → compact → reframe.

The worker runs unattended for days, so a *recoverable* failure must never crash the
run — the transient budget is sized in days precisely so an outage is slept through.
What the ladder must never do is answer for the node: when every layer is spent it
raises, leaving a resumable checkpoint, rather than emitting outputs the agent never
gave. These tests script the runner's own ``turn`` (no CLI) over a fake clock (no real
sleeping) and assert both the escalation order and that hard stop.

    ./.venv/bin/python tests/test_agent_recovery.py
    ./.venv/bin/python -m pytest tests/test_agent_recovery.py
"""
from __future__ import annotations

import io
import json
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

from _fakes import FakeBackend, FakeClock, RecordingTelemetry
from workhorse import otel, reload
from workhorse.config_run import AgentResilience
from workhorse.runner import failure, ladder, process
from workhorse.runner.backends.claude import ClaudeBackend
from workhorse.runner.failure import BackendInvocationError, OutputParseError
from workhorse.runner.waits import RecoveryWaitBudgetExceeded
from workhorse.context import WorkflowContext
from workhorse.runner.spec import AgentNode, OutputSpec


def _node(**kw) -> AgentNode:
    return AgentNode(
        type="agent",
        id="review_implementation",
        prompt="Review the work and decide.",
        outputs=[OutputSpec(key="decision"), OutputSpec(key="review")],
        next="next_node",
        **kw,
    )


def _runner(script, backend=None, clock=None, **kw) -> ladder.AgentRunner:
    """The ladder with every collaborator INJECTED and one turn scripted.

    The knobs arrive as ``AgentResilience`` fields, the CLI as an ``AgentBackend``, the
    waiting as a ``Clock`` — the runner reads no configuration, resolves no CLI and owns
    no clock of its own, so a test states all three rather than patching module
    attributes (rule 5). ``script`` stands in for the runner's own *public* ``turn``,
    leaving the compact / reframe / default layers above it real.
    """

    class ScriptedRunner(ladder.AgentRunner):
        def turn(self, prompt, node_id, session_id_path, model=None, **kwargs):
            return script(prompt, node_id, session_id_path, model, **kwargs)

    return ScriptedRunner(
        backend=backend or FakeBackend(),
        resilience=AgentResilience(**kw),
        clock=clock or FakeClock(),
    )


def _run(node, script, backend=None, validate=None, **kw):
    """Drive one node through a scripted ladder (see :func:`_runner`)."""
    # node.prompt is normally a template FILE path; render it inline for the test.
    with patch.object(ladder, "render", lambda tmpl, ctx, wdir: str(tmpl)):
        return _runner(script, backend=backend, **kw).run(
            node, WorkflowContext(initial={}), Path("."), None, validate=validate,
        )


def test_success_on_first_attempt_returns_outputs():
    payload = json.dumps({"decision": "approve", "review": "looks good"})
    _, outputs = _run(_node(), lambda *a, **k: payload)
    assert outputs == {"decision": "approve", "review": "looks good"}


def test_rendered_prompt_is_written_and_only_path_is_printed():
    run_dir = Path(tempfile.mkdtemp())
    prompt_path = run_dir / "review_implementation" / "prompt.md"
    payload = json.dumps({"decision": "approve", "review": "looks good"})

    def fake_invoke(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        assert prompt == "Hello hunter2"
        assert prompt_path.read_text(encoding="utf-8") == "Hello hunter2"
        return payload

    stdout = io.StringIO()
    with redirect_stdout(stdout), \
         patch.object(ladder, "render", lambda tmpl, ctx, wdir: f"Hello {ctx['secret']}"):
        _, outputs = _runner(fake_invoke).run(
            _node(),
            WorkflowContext(initial={"secret": "hunter2"}),
            Path("."),
            None,
            run_dir=run_dir,
        )

    assert outputs == {"decision": "approve", "review": "looks good"}
    assert str(prompt_path) in stdout.getvalue()
    assert "hunter2" not in stdout.getvalue()
    assert "secret" not in stdout.getvalue()


def _demand_review_string(outputs):
    """The stand-in for `returns.model_validate`: keys present, shapes checked."""
    if not isinstance(outputs.get("review"), str):
        raise ValueError("review: Input should be a valid string")


def test_a_wrong_shaped_reply_is_corrected_in_session_not_fatal():
    """Every declared key present, one value the wrong shape — the emission that used
    to sail through key extraction and kill the run downstream as 'returned something
    that is not a PlanResult'. With the validator inside the corrective-retry loop the
    agent is re-asked in the SAME session with the shape error quoted, and the mended
    reply ends the node normally."""
    calls = {"n": 0}
    prompts: list[str] = []

    def script(prompt, node_id, sid, model=None, **kwargs):
        calls["n"] += 1
        prompts.append(prompt)
        if calls["n"] == 1:
            return json.dumps({"decision": "approve", "review": ["a", "list"]})
        return json.dumps({"decision": "approve", "review": "mended"})

    _, outputs = _run(_node(), script, validate=_demand_review_string)

    assert outputs == {"decision": "approve", "review": "mended"}
    assert calls["n"] == 2
    # The correction happened at the cheap layer: the retry prompt quotes the shape
    # error rather than reframing the task from scratch.
    assert "did not validate" in prompts[1]
    assert "valid string" in prompts[1]


def test_a_persistently_wrong_shape_stops_the_run_instead_of_passing_it_on():
    """When every corrective turn and reframe still returns the wrong shape, the
    ladder raises — the node's answer is never handed downstream malformed."""
    def script(prompt, node_id, sid, model=None, **kwargs):
        return json.dumps({"decision": "approve", "review": ["still", "a", "list"]})

    with pytest.raises(OutputParseError, match="did not validate"):
        _run(
            _node(),
            script,
            validate=_demand_review_string,
            max_output_retries=0,
            max_rephrase_attempts=0,
        )


def test_empty_result_then_reframe_succeeds():
    """An empty result (the original 'No result event' bug) raises invoke error;
    the node is reframed and the next attempt succeeds — no crash."""
    calls = {"n": 0}
    good = json.dumps({"decision": "continue", "review": "ok"})

    def fake_invoke(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            # Mirrors what a backend's turn raises when the result text is empty.
            raise BackendInvocationError(
                "No 'result' event received from Claude for node 'review_implementation'",
                transient=True,
            )
        return good

    _, outputs = _run(_node(), fake_invoke)

    assert outputs == {"decision": "continue", "review": "ok"}
    assert calls["n"] == 2, "should reframe once then succeed"


def test_persistent_failure_raises_instead_of_answering_for_the_node():
    """When every layer is spent the ladder stops the run — it does not invent outputs.

    A null ``decision`` from a review node is not a degraded answer, it is a fabricated
    one: every node downstream then does real work on a verdict nobody gave, and the
    run reports success. Raising here ends the run at a checkpoint an operator can
    resume once the cause is cleared, which is the only outcome that stays recoverable.
    """
    def always_fail(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        raise BackendInvocationError("No 'result' event received", transient=True)

    try:
        _run(_node(), always_fail, max_rephrase_attempts=3)
        raise AssertionError("the exhausted ladder must raise, not default the outputs")
    except BackendInvocationError:
        pass


def test_a_reload_is_neither_retried_nor_reframed():
    """The ladder must let a reload past untouched — it is not a verdict on the turn.

    Every other exit from ``run`` spends something: a reframe, a compaction attempt, a
    backoff out of a budget measured in days. A reload spends none of them, because the
    operator cut the turn deliberately and the *next*, genuine failure is entitled to the
    full ladder. Reframing here would also be actively wrong: it would open a fresh
    session and re-ask the question against the very code the reload is replacing.
    """
    calls = {"n": 0}
    clock = FakeClock()

    def cut(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        calls["n"] += 1
        raise reload.ReloadRequested("reload requested during review_implementation")

    try:
        _run(_node(), cut, clock=clock, max_rephrase_attempts=3)
        raise AssertionError("a reload must propagate, not be recovered from")
    except reload.ReloadRequested as exc:
        assert exc.core is False

    assert calls["n"] == 1, "the reload was retried or reframed"
    assert clock.slept == [], f"a reload entered a backoff: {clock.slept}"


def test_the_cut_turn_closes_its_span_and_closes_it_cleanly():
    """The span survives the interrupt — that is half of what the feature promises.

    Left open, the turn dangles in the collector and the tokens it really burned before
    the cut are never attributed to it, which is precisely the ambiguity a restart-based
    reload produces and this one exists to avoid. Closed with an ERROR status, groom
    counts a deliberate reload among the failures.
    """
    fake = RecordingTelemetry()

    def cut(prompt, node_id, sid, model=None, **kwargs):
        raise reload.ReloadRequested("reload requested during review_implementation")

    runner = ladder.AgentRunner(
        backend=FakeBackend(turn=cut),
        resilience=AgentResilience(),
        clock=FakeClock(),
    )
    previous = otel.install(otel.TelemetryHost(active=fake))
    try:
        runner.turn("p", "review_implementation", None, timeout=60)
        raise AssertionError("a reload must propagate out of the turn")
    except reload.ReloadRequested:
        pass
    finally:
        otel.install(previous)

    assert fake.turns_opened == ["review_implementation"]
    assert fake.turns_closed == [None], "the cut turn's span dangled or closed as an error"


def test_a_reload_during_compaction_is_not_read_as_compaction_being_unavailable():
    """``/compact`` is best-effort, but only about compaction *failing*.

    Swallowing the reload here returns ``False``, which the ladder reads as "compaction
    can't help" and answers with a reframe — a fresh session and a whole new turn under
    the code being replaced.
    """
    def cut(cmd, node_id, timeout, on_line, **kwargs):
        raise reload.ReloadRequested("reload requested during review_implementation")

    with tempfile.TemporaryDirectory() as tmp:
        sid_path = Path(tmp) / "session"
        sid_path.write_text("session-abc")
        with patch.object(process, "stream_subprocess", cut):
            try:
                ClaudeBackend().compact(
                    sid_path, "review_implementation",
                    timeout=1.0,
                    resilience=AgentResilience(),
                )
                raise AssertionError("the reload was swallowed as a compaction failure")
            except reload.ReloadRequested:
                pass


def test_reframe_count_then_stop():
    """Exactly max_rephrase_attempts+1 invocations before the ladder gives up."""
    calls = {"n": 0}

    def always_fail(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        calls["n"] += 1
        raise BackendInvocationError("No 'result' event received", transient=True)

    try:
        _run(_node(), always_fail, max_rephrase_attempts=2)
    except BackendInvocationError:
        pass

    assert calls["n"] == 3, "initial + 2 reframes, then stop (no further invoke)"


def test_a_node_can_spend_a_smaller_reframe_budget_than_the_run():
    """`retries=0` means one invocation and then the raise — no fresh-session re-ask.

    A reframe throws the session away and re-asks at full price, which is the right
    default when the turn's *reply* is the deliverable. For a node whose deliverable is
    a **file**, it is not: the caller can read the partial draft off disk and repair it
    for a fraction of the cost, so the reframes only multiply the node's wall-clock
    budget before the run stops. Only the node knows which kind it is, hence the
    override. The `is None` resolution is what this pins — a truthiness test would read
    a deliberate 0 as "unset" and hand the node the run's budget back.
    """
    calls = {"n": 0}

    def always_fail(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        calls["n"] += 1
        raise BackendInvocationError("No 'result' event received", transient=True)

    try:
        _run(_node(retries=0), always_fail, max_rephrase_attempts=3)
        raise AssertionError("the exhausted ladder must raise, not default the outputs")
    except BackendInvocationError:
        pass

    assert calls["n"] == 1, "retries=0 must not spend the run's reframe budget"


def test_a_node_without_its_own_budget_still_uses_the_runs():
    """The override is opt-in: an unset `retries` leaves `max_rephrase_attempts` in charge."""
    calls = {"n": 0}

    def always_fail(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        calls["n"] += 1
        raise BackendInvocationError("No 'result' event received", transient=True)

    assert _node().retries is None
    try:
        _run(_node(), always_fail, max_rephrase_attempts=2)
    except BackendInvocationError:
        pass

    assert calls["n"] == 3, "initial + 2 reframes from the run-level budget"


def test_a_node_can_spend_a_larger_reframe_budget_than_the_run():
    """The override widens as well as narrows — it replaces the run's number, both ways."""
    calls = {"n": 0}

    def always_fail(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        calls["n"] += 1
        raise BackendInvocationError("No 'result' event received", transient=True)

    try:
        _run(_node(retries=3), always_fail, max_rephrase_attempts=1)
    except BackendInvocationError:
        pass

    assert calls["n"] == 4, "initial + 3 reframes from the node's own budget"


def test_unparseable_output_reframes_then_stops():
    """A node that always returns unparseable text exhausts output retries, then
    reframes, then stops — it never passes off unparsed text as the node's answer."""
    def junk(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        return "I cannot produce JSON, sorry."

    try:
        _run(_node(), junk, max_output_retries=1, max_rephrase_attempts=1)
        raise AssertionError("unparseable output must end the run, not be defaulted")
    except (BackendInvocationError, OutputParseError):
        pass


def test_new_node_starts_clean_dropping_prior_session(tmp_path=None):
    """A fresh node (resume_session=False) must NOT chain a previous node's
    session: the stale .session_id is dropped before the first invocation."""
    import tempfile
    sid_path = Path(tempfile.mkdtemp()) / ".session_id"
    sid_path.write_text("prev-node-session-abc")  # left by an earlier node

    good = json.dumps({"decision": "continue", "review": "ok"})
    with patch.object(ladder, "render", lambda tmpl, ctx, wdir: str(tmpl)):
        _runner(lambda *a, **k: good).run(
            _node(), WorkflowContext(initial={}), Path("."), sid_path,
        )

    # The stub never re-wrote it, so a cleared file means "started clean".
    assert not sid_path.exists(), "new node should drop the prior node's session"


def test_interrupted_node_keeps_session_for_resume(tmp_path=None):
    """An interrupted node (resume_session=True) keeps its session so the CLI
    can --resume and continue where it left off."""
    import tempfile
    sid_path = Path(tempfile.mkdtemp()) / ".session_id"
    sid_path.write_text("this-node-session-xyz")

    good = json.dumps({"decision": "continue", "review": "ok"})
    with patch.object(ladder, "render", lambda tmpl, ctx, wdir: str(tmpl)):
        _runner(lambda *a, **k: good).run(
            _node(), WorkflowContext(initial={}), Path("."), sid_path,
            resume_session=True,
        )

    assert sid_path.exists() and sid_path.read_text() == "this-node-session-xyz", \
        "interrupted node must keep its session for --resume"


def test_context_overflow_is_detected():
    assert failure.is_context_overflow("API Error: prompt is too long: 200000 tokens > 200000") is True
    assert failure.is_context_overflow("the conversation is too long to continue") is True
    assert failure.is_context_overflow("rate limit") is False
    assert failure.is_context_overflow("spending cap reached") is False


def test_overflow_compacts_then_continues_same_prompt():
    """On context overflow the runner compacts the session and retries the SAME
    prompt (preserving progress) rather than reframing."""
    calls = {"n": 0}
    good = json.dumps({"decision": "approve", "review": "done"})

    def fake_invoke(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise BackendInvocationError("Context window exhausted", overflow=True)
        # second invocation (after compaction) succeeds; must be the original prompt
        assert "reframe" not in prompt.lower() and "do your best" not in prompt.lower()
        return good

    compacted = {"n": 0}

    def fake_compact(session_id_path, node_id, model=None, **kwargs):
        compacted["n"] += 1
        return True  # compaction succeeded

    _, outputs = _run(
        _node(),
        fake_invoke,
        backend=FakeBackend(compact=fake_compact),
        max_rephrase_attempts=2,
    )

    assert outputs == {"decision": "approve", "review": "done"}
    assert compacted["n"] == 1, "should compact exactly once"
    assert calls["n"] == 2, "invoke, compact, then invoke again — no reframe"


def test_overflow_falls_back_to_reframe_when_compaction_fails():
    """If compaction can't help, the runner reframes (fresh session) then stops."""
    def always_overflow(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        raise BackendInvocationError("prompt is too long", overflow=True)

    def failed_compact(session_id_path, node_id, model=None, **kwargs):
        return False  # /compact unavailable/ineffective

    try:
        _run(
            _node(),
            always_overflow,
            backend=FakeBackend(compact=failed_compact),
            max_rephrase_attempts=1,
            max_compact_attempts=1,
        )
        raise AssertionError("compaction failed and reframing failed — must stop")
    except BackendInvocationError:
        pass


def test_overflow_compaction_attempts_are_bounded():
    """Compaction is tried at most max_compact_attempts times, then reframe."""
    compacted = {"n": 0}

    def always_overflow(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        raise BackendInvocationError("context window exceeded", overflow=True)

    def ok_compact(session_id_path, node_id, model=None, **kwargs):
        compacted["n"] += 1
        return True  # succeeds but the node keeps overflowing anyway

    try:
        _run(
            _node(),
            always_overflow,
            backend=FakeBackend(compact=ok_compact),
            max_rephrase_attempts=1,
            max_compact_attempts=2,
        )
    except BackendInvocationError:
        pass

    assert compacted["n"] == 2, "compaction must be bounded by max_compact_attempts"


def test_non_recoverable_backend_error_aborts_without_reframe():
    """A non-transient, non-overflow backend failure (e.g. an opencode 'Unexpected
    server error') is non-recoverable: reframing can't bring back a crashed CLI, so
    it is not worth the reframe budget and the ladder re-raises at once
    for a clean abort."""
    calls = {"n": 0}

    def fatal(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        calls["n"] += 1
        raise BackendInvocationError(
            "opencode CLI exited with code 1 for node 'review_implementation': "
            "Unexpected server error. Check server logs for details.",
            transient=False,
        )

    try:
        _run(_node(), fatal, max_rephrase_attempts=3)
        raise AssertionError("expected re-raise on a non-recoverable backend failure")
    except BackendInvocationError:
        pass

    assert calls["n"] == 1, "non-recoverable failure must not reframe"


def test_transient_failure_still_reframes_not_aborts():
    """Guard for the non-recoverable fast-path: a TRANSIENT failure must still spend
    the reframe budget, NOT take the immediate abort path."""
    calls = {"n": 0}

    def transient_fail(prompt, node_id, sid, model=None, timeout=None, **kwargs):
        calls["n"] += 1
        raise BackendInvocationError("overloaded", transient=True)

    try:
        _run(_node(), transient_fail, max_rephrase_attempts=2)
    except BackendInvocationError:
        pass

    assert calls["n"] == 3, "transient failure should reframe (initial + 2), then stop"


def test_retry_wait_budget_is_shared_across_output_retries():
    """A parse retry cannot renew the node's transient-backoff allowance."""
    calls = {"n": 0}
    clock = FakeClock()

    def backend_turn(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] in {1, 3}:
            raise BackendInvocationError("network unavailable", transient=True)
        return "not json"

    runner = ladder.AgentRunner(
        backend=FakeBackend(backend_turn),
        resilience=AgentResilience(
            max_output_retries=1,
            max_invoke_retries=1,
            max_rephrase_attempts=0,
            invoke_backoff_base_s=5,
            invoke_backoff_cap_s=5,
            retry_wait_budget_s=5,
        ),
        clock=clock,
    )
    try:
        with patch.object(ladder, "render", lambda tmpl, ctx, wdir: str(tmpl)):
            runner.run(_node(), WorkflowContext(initial={}), Path("."), None)
        raise AssertionError("the second transient wait must exceed the shared budget")
    except RecoveryWaitBudgetExceeded as exc:
        assert exc.kind == "retry"

    assert calls["n"] == 3
    assert sum(clock.slept) == 5


def test_reframe_wait_budget_is_cumulative_for_the_node():
    """A high reframe attempt count cannot turn into unbounded recovery sleeping."""
    calls = {"n": 0}
    clock = FakeClock()

    def transient_fail(*args, **kwargs):
        calls["n"] += 1
        raise BackendInvocationError("overloaded", transient=True)

    runner = _runner(
        transient_fail,
        clock=clock,
        max_rephrase_attempts=5,
        reframe_wait_budget_s=10,
    )
    try:
        with patch.object(ladder, "render", lambda tmpl, ctx, wdir: str(tmpl)):
            runner.run(_node(), WorkflowContext(initial={}), Path("."), None)
        raise AssertionError("the second reframe pause must exceed the shared budget")
    except RecoveryWaitBudgetExceeded as exc:
        assert exc.kind == "reframe"

    assert calls["n"] == 2
    assert clock.slept == [10]


def test_a_day_long_outage_is_slept_through_not_failed_through():
    """The transient budget has to outlast the outage it exists for.

    A home or office link can be down for a working day. The old ladder gave a network
    failure four retries capped at five minutes — about fifteen minutes end to end —
    so an outage measured in hours ended the run inside it every time. Nothing is
    consumed while waiting and the checkpoint is untouched, so the only cost of waiting
    is wall clock; the cost of not waiting is the whole run. This asserts on the
    seconds the clock was ASKED for, so a day passes in microseconds.
    """
    clock = FakeClock()
    runner = ladder.AgentRunner(
        backend=FakeBackend(
            lambda *a, **k: (_ for _ in ()).throw(
                BackendInvocationError(
                    "API Error: Unable to connect to API (ENOTIMP)", transient=True
                )
            )
        ),
        resilience=AgentResilience(),
        clock=clock,
    )

    try:
        runner.turn("p", "n", None, timeout=AgentResilience().result_timeout_s)
        raise AssertionError("a permanently down link must still end the turn")
    except BackendInvocationError:
        pass

    assert sum(clock.slept) > 24 * 3600, (
        f"the transient ladder rode out only {sum(clock.slept) / 3600:.1f}h — "
        "an outage lasting a working day would still kill an unattended run"
    )
    # Ticked, not one silent 30-minute block: a collector must be able to tell this
    # wait from a wedged turn, so no single sleep exceeds the notice interval.
    assert max(clock.slept) <= AgentResilience().cap_tick_s, clock.slept


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
