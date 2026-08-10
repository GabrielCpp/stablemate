"""Tests for the core agent's spending/usage-cap handling in ``AgentRunner.turn``.

Runs without real sleeping and without any agent CLI: both are INJECTED — the CLI as a
fake backend, the waiting as a ``FakeClock`` that records the seconds it was asked for
and returns at once. A cap that reopens eight days out therefore costs microseconds and
is asserted on as a number (rule 4.2). Runnable two ways:
    ./.venv/bin/python tests/test_agent_cap.py     # standalone, no pytest needed
    ./.venv/bin/python -m pytest tests/test_agent_cap.py
"""
from __future__ import annotations

from datetime import datetime

from _fakes import FakeBackend, FakeClock
from workhorse import control, reload
from workhorse.config_run import AgentResilience
from workhorse.runner import caps, failure, ladder
from workhorse.runner.failure import BackendInvocationError
from workhorse.runner.waits import RecoveryWaitBudgetExceeded

#: The cap ladder's knobs are injected, never read from the module — so a test states
#: the wait budget it asserts against instead of patching a global (rule 5).
RESILIENCE = AgentResilience()


def _turn(cli, prompt="p", node_id="n", *, clock=None, timeout=None, **overrides):
    """Drive ONE agent turn through the recovery ladder with everything injected.

    The CLI is a fake backend, the knobs are ``AgentResilience`` fields, and the waiting
    is the given clock — so the cap branch is exercised end to end without a subprocess,
    a global, or a real second passing.
    """
    runner = ladder.AgentRunner(
        backend=FakeBackend(cli),
        resilience=RESILIENCE.with_overrides(**overrides) if overrides else RESILIENCE,
        clock=clock or FakeClock(),
    )
    return runner.turn(
        prompt,
        node_id,
        None,
        timeout=RESILIENCE.result_timeout_s if timeout is None else timeout,
    )

CAP_MSG = "Claude CLI exited with code 1 for node 'select_gate': success Spending cap reached resets 3:50am"


def _reset_seconds(message: str, now: datetime) -> float:
    """The parsed wait, asserting a time *was* found — the None arm is its own case below."""
    seconds = caps.parse_reset_seconds(message, now)
    assert seconds is not None, message
    return seconds


def test_parse_reset_seconds_variants():
    now = datetime(2026, 6, 1, 2, 10, 0)  # 2:10am
    assert abs(_reset_seconds("resets 3:50am", now) - 100 * 60) < 1  # 1h40m
    assert abs(_reset_seconds("resets at 11pm", now) - (20 * 3600 + 50 * 60)) < 1
    assert abs(_reset_seconds("usage limit, resets 15:50", now) - (13 * 3600 + 40 * 60)) < 1
    # reset time already passed today -> next day's occurrence
    assert abs(_reset_seconds("resets 1:00am", now) - (22 * 3600 + 50 * 60)) < 1
    # no time present -> None (caller uses default)
    assert caps.parse_reset_seconds("overloaded", now) is None
    assert caps.parse_reset_seconds("resets soon", now) is None


def test_cap_reset_beyond_the_node_wait_budget_fails_without_partial_sleep():
    """Sleeping partway to a known-unreached cap reset only delays a resumable stop."""
    clock = FakeClock()
    calls = {"n": 0}

    def capped(*args, **kwargs):
        calls["n"] += 1
        raise BackendInvocationError("spending cap reached", transient=True)

    try:
        _turn(
            capped,
            clock=clock,
            cap_default_wait_s=100,
            cap_wait_margin_s=0,
            cap_wait_budget_s=50,
        )
        raise AssertionError("the cap wait should exceed its cumulative budget")
    except RecoveryWaitBudgetExceeded as exc:
        assert exc.kind == "cap"

    assert calls["n"] == 1
    assert clock.slept == []


def test_invalid_wait_durations_fall_back_but_zero_budget_disables_waiting():
    configured = AgentResilience.from_env(
        {
            "AGENT_CAP_TICK_S": "0",
            "AGENT_CAP_WAIT_BUDGET_S": "inf",
            "AGENT_RETRY_WAIT_BUDGET_S": "nan",
            "AGENT_REFRAME_WAIT_BUDGET_S": "-1",
            "AGENT_EXEC_RETRY_WAIT_BUDGET_S": "0",
        }
    )

    defaults = AgentResilience()
    assert configured.cap_tick_s == defaults.cap_tick_s
    assert configured.cap_wait_budget_s == defaults.cap_wait_budget_s
    assert configured.retry_wait_budget_s == defaults.retry_wait_budget_s
    assert configured.reframe_wait_budget_s == defaults.reframe_wait_budget_s
    assert configured.exec_retry_wait_budget_s == 0


SESSION_MSG = (
    "Claude CLI exited with code 1 for node 'review_plan': success "
    "You've hit your session limit · resets 11:30am (America/Toronto)"
)


def test_classification():
    assert failure.is_cap(CAP_MSG) is True
    assert failure.is_cap("rate limit exceeded") is False      # short transient, not a cap
    assert failure.is_cap("overloaded") is False
    assert failure.is_transient(CAP_MSG) is True               # cap is still transient/retryable
    assert failure.is_transient("rate limit") is True
    assert failure.is_transient("syntax error in node") is False
    # A session limit is a scheduled-reset cap — must be waited out, not reframed.
    assert failure.is_cap(SESSION_MSG) is True
    assert failure.is_transient(SESSION_MSG) is True
    # All cap markers must also be transient, else the cap-wait branch never fires.
    for marker in failure._CAP_MARKERS:
        assert failure.is_transient(marker) is True, f"cap marker not transient: {marker}"


# OpenRouter (and similar gateways) cap a key per day; the CLI surfaces the raw
# provider error. This is a scheduled-reset cap, NOT a content failure — it must be
# waited out, never reframed/defaulted through (which would advance past a gate).
KEY_LIMIT_MSG = (
    "opencode CLI exited with code 1 for node 'resolve_epics': "
    "Key limit exceeded (daily limit). Manage it using "
    "https://openrouter.ai/workspaces/default/keys/7a2ee3c"
)


def test_daily_key_limit_classified_as_cap():
    """A provider per-key daily limit is a (transient) cap, not a hard failure —
    so the turn waits it out instead of raising into the reframe ladder."""
    assert failure.is_cap(KEY_LIMIT_MSG) is True
    assert failure.is_transient(KEY_LIMIT_MSG) is True
    # The bare phrasings both trip the cap detector.
    assert failure.is_cap("Key limit exceeded") is True
    assert failure.is_cap("daily limit reached") is True


# opencode logs the usage-limit error to its stream but does NOT exit — it retries
# internally until the watchdog reaps it, so the finished turn arrives timed_out=True
# with the limit text in diagnostics. The classifier must read the cap THROUGH the
# timeout, not report a bogus "Timeout waiting for result … after 3600s".
OPENCODE_CAP_DIAG = (
    'stream error providerID=openai modelID=gpt-5.5 session.id=ses_0ec '
    'agent=build mode=primary error.error="AI_APICallError: The usage limit '
    'has been reached"'
)


def test_cap_hang_classified_as_cap_not_timeout():
    """A cap that makes the CLI hang (timed_out=True) is classified as a cap, not a
    timeout — so the run waits the window out under a truthful message instead of
    reporting 'Timeout waiting for result … after Ns'."""
    try:
        failure.classify_turn(
            "opencode",
            "review_implementation",
            result_text=None,
            diagnostics=OPENCODE_CAP_DIAG,
            timed_out=True,
            returncode=0,
            timeout=3600,
        )
        raise AssertionError("expected BackendInvocationError")
    except BackendInvocationError as exc:
        assert "cap reached" in str(exc), "should be framed as a cap"
        assert "Timeout waiting for result" not in str(exc), "must not mis-frame as a timeout"
        assert failure.is_cap(str(exc)), "runner's cap detector must still catch it"
        assert exc.transient is True
        # A cap is waited out by the cap branch, NOT given the budget-overrun warning,
        # so it must not masquerade as a real wall-clock timeout.
        assert exc.timed_out is False


def test_cap_hang_pauses_then_resumes_same_node():
    """End-to-end: an opencode cap-hang pauses the node once and re-runs the SAME
    prompt — it never gets the budget-timeout warning and never reframes."""
    calls = {"n": 0}

    def fake_cli(prompt, node_id, sid, model, timeout=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            failure.classify_turn(
                "opencode", node_id, result_text=None, diagnostics=OPENCODE_CAP_DIAG,
                timed_out=True, returncode=0, timeout=3600,
            )
        return "RESULT_OK"

    seen_prompts = []

    def record_cli(prompt, *a, **k):
        seen_prompts.append(prompt)
        return fake_cli(prompt, *a, **k)

    clock = FakeClock()
    out = _turn(record_cli, "DO THE TASK", "review_implementation", clock=clock, timeout=3600)

    assert out == "RESULT_OK"
    assert calls["n"] == 2, "should re-run the same node after the cap wait"
    assert sum(clock.slept) == RESILIENCE.cap_default_wait_s, \
        "opencode's cap error carries no reset time → default wait"
    assert seen_prompts[1] == "DO THE TASK", "cap retry must reuse the prompt verbatim (no budget warning)"


def test_daily_key_limit_pauses_then_resumes_same_node():
    """The keyed-out node pauses once (no reset in the message → default wait) and
    re-runs the SAME prompt once the key resets — never reframes, never defaults."""
    calls = {"n": 0}

    def fake_cli(prompt, node_id, sid, model, timeout=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise BackendInvocationError(KEY_LIMIT_MSG, transient=True)
        return "RESULT_OK"

    clock = FakeClock()
    out = _turn(fake_cli, node_id="resolve_epics", clock=clock)

    assert out == "RESULT_OK"
    assert calls["n"] == 2, "should re-run the same node after the daily-limit wait"
    assert sum(clock.slept) == RESILIENCE.cap_default_wait_s, \
        "no reset time in the message → falls back to the default cap wait"


def test_session_limit_pauses_until_reset_then_resumes():
    """A session-limit error pauses until its parsed reset (not short backoff)."""
    calls = {"n": 0}

    def fake_cli(prompt, node_id, sid, model, timeout=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise BackendInvocationError(SESSION_MSG, transient=True)
        return "RESULT_OK"

    clock = FakeClock()
    out = _turn(fake_cli, node_id="review_plan", clock=clock)

    assert out == "RESULT_OK"
    assert calls["n"] == 2, "should retry the node after the session-limit wait"
    assert sum(clock.slept) > 0, "should pause until the reset"


def test_rate_limit_info_parsing():
    """Structured rate_limit_event → (blocked, reset_at) per the CLI's real shape."""
    allowed = {
        "type": "rate_limit_event",
        "rate_limit_info": {"status": "allowed", "resetsAt": 1780437600, "rateLimitType": "five_hour"},
    }
    assert failure.rate_limit_info(allowed) == (False, 1780437600.0)

    blocked = {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": 1780000000}}
    assert failure.rate_limit_info(blocked) == (True, 1780000000.0)

    # Missing / malformed info → no crash, no signal.
    assert failure.rate_limit_info({"type": "rate_limit_event"}) == (False, None)
    assert failure.rate_limit_info({"rate_limit_info": {"status": "allowed", "resetsAt": "n/a"}}) == (False, None)


def test_cap_delay_prefers_structured_reset_at():
    """A structured reset_at epoch drives the wait time precisely (+ margin)."""
    now = 1_000_000.0
    clock = FakeClock(datetime.fromtimestamp(now))
    exc = BackendInvocationError("blocked", transient=True, reset_at=now + 3600)  # 1h out
    delay, _when = caps.cap_delay_seconds(exc, resilience=RESILIENCE, clock=clock)
    assert abs(delay - (3600 + RESILIENCE.cap_wait_margin_s)) < 1

    # A past reset → retry promptly (just the margin).
    exc_past = BackendInvocationError("blocked", transient=True, reset_at=now - 50)
    delay_past, _ = caps.cap_delay_seconds(exc_past, resilience=RESILIENCE, clock=clock)
    assert delay_past == RESILIENCE.cap_wait_margin_s

    # An absurd far-future reset is bounded.
    exc_far = BackendInvocationError("blocked", transient=True, reset_at=now + 999 * 24 * 3600)
    delay_far, _ = caps.cap_delay_seconds(exc_far, resilience=RESILIENCE, clock=clock)
    assert delay_far == RESILIENCE.cap_max_wait_s + RESILIENCE.cap_wait_margin_s


def test_cap_delay_falls_back_to_text_then_default():
    """Without a structured reset_at, fall back to parsing the message, then default."""
    # 2:10am, so "resets 3:50am" is 1h40m out — stated by the clock, not patched onto
    # the module: the text path reads the same injected "now" as the epoch path.
    clock = FakeClock(datetime(2026, 6, 1, 2, 10, 0))
    exc = BackendInvocationError("usage limit, resets 3:50am", transient=True)
    delay, _ = caps.cap_delay_seconds(exc, resilience=RESILIENCE, clock=clock)
    assert abs(delay - (100 * 60 + RESILIENCE.cap_wait_margin_s)) < 1

    exc_none = BackendInvocationError("overloaded somehow", transient=True)
    delay_none, _ = caps.cap_delay_seconds(exc_none, resilience=RESILIENCE, clock=clock)
    assert delay_none == RESILIENCE.cap_default_wait_s


def test_structured_reset_at_drives_invoke_wait():
    """End-to-end: a cap error carrying reset_at makes the turn sleep until it."""
    now = 2_000_000.0
    calls = {"n": 0}

    def fake_cli(prompt, node_id, sid, model, timeout=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise BackendInvocationError("blocked", transient=True, reset_at=now + 7200)
        return "OK"

    clock = FakeClock(datetime.fromtimestamp(now))
    out = _turn(fake_cli, clock=clock)

    assert out == "OK"
    assert abs(sum(clock.slept) - (7200 + RESILIENCE.cap_wait_margin_s)) < 1


def test_budget_timeout_warns_retry_with_time_budget():
    """After a wall-clock timeout, the retry's prompt is prefixed with a budget
    warning that states the limit, so the next attempt can size its work to fit."""
    seen_prompts = []

    def fake_cli(prompt, node_id, sid, model, timeout=None, **kwargs):
        seen_prompts.append(prompt)
        if len(seen_prompts) == 1:
            raise BackendInvocationError(
                "Timeout waiting for result from Claude for node 'implement' after 1200s",
                transient=True,
                timed_out=True,
            )
        return "RESULT_OK"

    out = _turn(fake_cli, "DO THE TASK", "implement", timeout=1200)

    assert out == "RESULT_OK"
    assert len(seen_prompts) == 2
    # First attempt sees the original prompt verbatim.
    assert seen_prompts[0] == "DO THE TASK"
    # Retry is warned it overran and told its budget (~20 min / 1200s).
    assert "TIME BUDGET" in seen_prompts[1]
    assert "20 min" in seen_prompts[1] and "1200s" in seen_prompts[1]
    assert seen_prompts[1].endswith("DO THE TASK")


def test_non_timeout_transient_retries_prompt_unchanged():
    """A plain transient (overload/network) retries the SAME prompt — no budget
    warning is injected (only real wall-clock timeouts get one)."""
    seen_prompts = []

    def fake_cli(prompt, node_id, sid, model, timeout=None, **kwargs):
        seen_prompts.append(prompt)
        if len(seen_prompts) == 1:
            raise BackendInvocationError("overloaded_error", transient=True)
        return "OK"

    out = _turn(fake_cli, "DO THE TASK", "implement", timeout=1200)

    assert out == "OK"
    assert seen_prompts == ["DO THE TASK", "DO THE TASK"]


def test_cap_sleeps_until_reset_then_resumes():
    """A cap error pauses (parsed reset, not short backoff) and retries to success."""
    calls = {"n": 0}

    def fake_cli(prompt, node_id, sid, model, timeout=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise BackendInvocationError(CAP_MSG, transient=True)
        return "RESULT_OK"

    clock = FakeClock()
    out = _turn(fake_cli, "prompt", "select_gate", clock=clock)

    assert out == "RESULT_OK"
    assert calls["n"] == 2, "should retry the node after the cap wait"
    # waited a positive, scheduled amount (parsed reset + margin), never longer than a day
    assert 0 < sum(clock.slept) <= 24 * 3600 + RESILIENCE.cap_wait_margin_s + 1


def test_cap_waits_do_not_consume_short_retry_budget():
    """Even with a tiny short-retry budget, multiple caps are ridden out."""
    calls = {"n": 0}

    def fake_cli(prompt, node_id, sid, model, timeout=None, **kwargs):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise BackendInvocationError(CAP_MSG, transient=True)
        return "OK_AFTER_CAPS"

    out = _turn(fake_cli, max_invoke_retries=1)  # short budget = 1

    assert out == "OK_AFTER_CAPS"
    assert calls["n"] == 4, "3 caps + 1 success, despite max_invoke_retries=1"


def test_cap_wait_safety_bound():
    """A cap that never clears gives up after ``max_cap_waits`` instead of looping forever."""
    def always_cap(prompt, node_id, sid, model, timeout=None, **kwargs):
        raise BackendInvocationError(CAP_MSG, transient=True)

    try:
        _turn(always_cap, max_cap_waits=3)
        raise AssertionError("expected BackendInvocationError after exhausting cap waits")
    except BackendInvocationError:
        pass


def test_short_transient_uses_bounded_backoff_then_fails():
    """A non-cap transient (overload) retries with backoff and fails fast."""
    calls = {"n": 0}

    def always_overloaded(prompt, node_id, sid, model, timeout=None, **kwargs):
        calls["n"] += 1
        raise BackendInvocationError("overloaded", transient=True)

    try:
        _turn(always_overloaded, max_invoke_retries=2)
        raise AssertionError("expected BackendInvocationError after retries")
    except BackendInvocationError as e:
        assert "overloaded" in str(e)
    assert calls["n"] == 3, "initial + 2 retries"


def _armed(*requests):
    """Arm a scripted control channel for the duration of one turn."""
    channel = control.FakeChannel(*requests)
    control.arm(channel)
    return channel


def test_a_reload_ends_a_cap_wait_instead_of_sleeping_the_window_out():
    """The wait this whole channel exists for. A weekly cap reopens days out, and an
    operator who has already pushed the fix should not have to wait for the window."""
    calls = {"n": 0}

    def capped(prompt, node_id, sid, model, timeout=None, **kwargs):
        calls["n"] += 1
        raise BackendInvocationError(CAP_MSG, transient=True)

    channel = _armed(control.Request(action="reload", core=True))
    clock = FakeClock()
    try:
        _turn(capped, node_id="select_gate", clock=clock)
        raise AssertionError("expected the cap wait to be cut by the reload")
    except reload.ReloadRequested as exc:
        assert exc.core is True, "the --core flag has to survive the wait it interrupted"
    finally:
        control.arm(None)

    assert calls["n"] == 1, "the node must not be re-run — the reload unwinds it"
    assert clock.slept == [], "the request arrives before the first tick is slept"
    assert channel.replies == [{"ok": True, "cut": True}]


def test_an_at_boundary_reload_does_not_shorten_the_cap_wait_it_arrives_in():
    """Being delivered is not being honoured. A request the wait declines must leave the
    window intact, or `--at-boundary` would cut a six-day cap short by arriving."""
    calls = {"n": 0}

    def capped(prompt, node_id, sid, model, timeout=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise BackendInvocationError(CAP_MSG, transient=True)
        return "RESULT_OK"

    channel = _armed(control.Request(action="reload", at_boundary=True))
    clock = FakeClock()
    try:
        out = _turn(capped, node_id="select_gate", clock=clock)
        # Held, not dropped: the state boundary is where an --at-boundary reload lands.
        held = control.outstanding()
    finally:
        control.arm(None)

    assert out == "RESULT_OK"
    assert 0 < sum(clock.slept) <= 24 * 3600 + RESILIENCE.cap_wait_margin_s + 1
    assert channel.replies == [{"ok": True, "cut": False}]
    assert held is not None and held.at_boundary is True


def test_an_action_this_run_does_not_know_is_answered_not_obeyed():
    """A newer CLI talking to an older run must not be able to end its wait."""
    calls = {"n": 0}

    def capped(prompt, node_id, sid, model, timeout=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise BackendInvocationError(CAP_MSG, transient=True)
        return "RESULT_OK"

    channel = _armed(control.Request(action="teleport"))
    clock = FakeClock()
    try:
        out = _turn(capped, node_id="select_gate", clock=clock)
    finally:
        control.arm(None)

    assert out == "RESULT_OK"
    assert sum(clock.slept) > 0, "an unknown action must not cut the wait short"
    assert channel.replies and "error" in channel.replies[0]


def test_a_reload_ends_a_transient_backoff_too():
    """The other ticked wait. A backoff at its cap is half an hour of unreachability."""
    def always_overloaded(prompt, node_id, sid, model, timeout=None, **kwargs):
        raise BackendInvocationError("overloaded", transient=True)

    _armed(control.Request(action="reload"))
    clock = FakeClock()
    try:
        _turn(always_overloaded, clock=clock, max_invoke_retries=5)
        raise AssertionError("expected the backoff to be cut by the reload")
    except reload.ReloadRequested:
        pass
    finally:
        control.arm(None)

    assert clock.slept == []


def test_an_unattached_run_sleeps_exactly_as_it_did_before_the_channel():
    """The regression guard on the default. With nothing armed there is no fd to select
    on, so a tick is one `clock.sleep` through the injected clock — which is what every
    other cap assertion in this file depends on."""
    calls = {"n": 0}

    def capped(prompt, node_id, sid, model, timeout=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise BackendInvocationError(KEY_LIMIT_MSG, transient=True)
        return "OK"

    clock = FakeClock()
    assert _turn(capped, node_id="resolve_epics", clock=clock) == "OK"
    ticks = RESILIENCE.cap_default_wait_s / RESILIENCE.cap_tick_s
    assert len(clock.slept) == int(ticks), clock.slept
    assert sum(clock.slept) == RESILIENCE.cap_default_wait_s


def test_non_transient_fails_immediately():
    calls = {"n": 0}

    def hard_fail(prompt, node_id, sid, model, timeout=None, **kwargs):
        calls["n"] += 1
        raise BackendInvocationError("malformed workflow node", transient=False)

    try:
        _turn(hard_fail)
        raise AssertionError("expected immediate raise on non-transient error")
    except BackendInvocationError:
        pass
    assert calls["n"] == 1, "non-transient must not retry"


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
