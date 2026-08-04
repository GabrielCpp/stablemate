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

from _fakes import FakeBackend, FakeClock
from workhorse.config_run import AgentResilience
from workhorse.runner import failure, ladder
from workhorse.runner.failure import BackendInvocationError, OutputParseError
from workhorse.context import WorkflowContext
from workhorse.runner.spec import AgentNode, OutputSpec


def _node() -> AgentNode:
    return AgentNode(
        type="agent",
        id="review_implementation",
        prompt="Review the work and decide.",
        outputs=[OutputSpec(key="decision"), OutputSpec(key="review")],
        next="next_node",
    )


def _runner(script, backend=None, **kw) -> ladder.AgentRunner:
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
        clock=FakeClock(),
    )


def _run(node, script, backend=None, **kw):
    """Drive one node through a scripted ladder (see :func:`_runner`)."""
    # node.prompt is normally a template FILE path; render it inline for the test.
    with patch.object(ladder, "render", lambda tmpl, ctx, wdir: str(tmpl)):
        return _runner(script, backend=backend, **kw).run(
            node, WorkflowContext(initial={}), Path("."), None,
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
