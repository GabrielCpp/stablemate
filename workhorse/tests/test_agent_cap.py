"""Tests for the core agent's spending/usage-cap handling in _invoke_claude.

Runs without real sleeping (time.sleep and _sleep_with_notice are patched) and
without the Claude CLI (_run_claude_cli is patched). Runnable two ways:
    ./.venv/bin/python tests/test_agent_cap.py     # standalone, no pytest needed
    ./.venv/bin/python -m pytest tests/test_agent_cap.py
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from workhorse.runner import agent
from workhorse.runner.agent import ClaudeInvocationError

CAP_MSG = "Claude CLI exited with code 1 for node 'select_gate': success Spending cap reached resets 3:50am"


def test_parse_reset_seconds_variants():
    now = datetime(2026, 6, 1, 2, 10, 0)  # 2:10am
    assert abs(agent._parse_reset_seconds("resets 3:50am", now) - 100 * 60) < 1  # 1h40m
    assert abs(agent._parse_reset_seconds("resets at 11pm", now) - (20 * 3600 + 50 * 60)) < 1
    assert abs(agent._parse_reset_seconds("usage limit, resets 15:50", now) - (13 * 3600 + 40 * 60)) < 1
    # reset time already passed today -> next day's occurrence
    assert abs(agent._parse_reset_seconds("resets 1:00am", now) - (22 * 3600 + 50 * 60)) < 1
    # no time present -> None (caller uses default)
    assert agent._parse_reset_seconds("overloaded") is None
    assert agent._parse_reset_seconds("resets soon") is None


SESSION_MSG = (
    "Claude CLI exited with code 1 for node 'review_plan': success "
    "You've hit your session limit · resets 11:30am (America/Toronto)"
)


def test_classification():
    assert agent._is_cap(CAP_MSG) is True
    assert agent._is_cap("rate limit exceeded") is False      # short transient, not a cap
    assert agent._is_cap("overloaded") is False
    assert agent._is_transient(CAP_MSG) is True               # cap is still transient/retryable
    assert agent._is_transient("rate limit") is True
    assert agent._is_transient("syntax error in node") is False
    # A session limit is a scheduled-reset cap — must be waited out, not reframed.
    assert agent._is_cap(SESSION_MSG) is True
    assert agent._is_transient(SESSION_MSG) is True
    # All cap markers must also be transient, else the cap-wait branch never fires.
    for marker in agent._CAP_MARKERS:
        assert agent._is_transient(marker) is True, f"cap marker not transient: {marker}"


def test_session_limit_pauses_until_reset_then_resumes():
    """A session-limit error pauses until its parsed reset (not short backoff)."""
    calls = {"n": 0}

    def fake_cli(prompt, node_id, sid, model, timeout=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ClaudeInvocationError(SESSION_MSG, transient=True)
        return "RESULT_OK"

    slept = []
    with patch.object(agent, "_run_claude_cli", fake_cli), \
         patch.object(agent, "_sleep_with_notice", lambda s, n, l: slept.append(s)):
        out = agent._invoke_claude("p", "review_plan", None)

    assert out == "RESULT_OK"
    assert calls["n"] == 2, "should retry the node after the session-limit wait"
    assert len(slept) == 1 and slept[0] > 0, "should pause once until the reset"


def test_rate_limit_info_parsing():
    """Structured rate_limit_event → (blocked, reset_at) per the CLI's real shape."""
    allowed = {
        "type": "rate_limit_event",
        "rate_limit_info": {"status": "allowed", "resetsAt": 1780437600, "rateLimitType": "five_hour"},
    }
    assert agent._rate_limit_info(allowed) == (False, 1780437600.0)

    blocked = {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": 1780000000}}
    assert agent._rate_limit_info(blocked) == (True, 1780000000.0)

    # Missing / malformed info → no crash, no signal.
    assert agent._rate_limit_info({"type": "rate_limit_event"}) == (False, None)
    assert agent._rate_limit_info({"rate_limit_info": {"status": "allowed", "resetsAt": "n/a"}}) == (False, None)


def test_cap_delay_prefers_structured_reset_at():
    """A structured reset_at epoch drives the wait time precisely (+ margin)."""
    now = 1_000_000.0
    exc = ClaudeInvocationError("blocked", transient=True, reset_at=now + 3600)  # 1h out
    delay, _when = agent._cap_delay_seconds(exc, now=now)
    assert abs(delay - (3600 + agent._CAP_WAIT_MARGIN_S)) < 1

    # A past reset → retry promptly (just the margin).
    exc_past = ClaudeInvocationError("blocked", transient=True, reset_at=now - 50)
    delay_past, _ = agent._cap_delay_seconds(exc_past, now=now)
    assert delay_past == agent._CAP_WAIT_MARGIN_S

    # An absurd far-future reset is bounded.
    exc_far = ClaudeInvocationError("blocked", transient=True, reset_at=now + 999 * 24 * 3600)
    delay_far, _ = agent._cap_delay_seconds(exc_far, now=now)
    assert delay_far == agent._CAP_MAX_STRUCTURED_WAIT_S + agent._CAP_WAIT_MARGIN_S


def test_cap_delay_falls_back_to_text_then_default():
    """Without a structured reset_at, fall back to parsing the message, then default."""
    now_dt = datetime(2026, 6, 1, 2, 10, 0)
    with patch.object(agent, "datetime") as dt:
        dt.now.return_value = now_dt
        dt.fromtimestamp.side_effect = lambda ts: datetime.fromtimestamp(ts)
        exc = ClaudeInvocationError("usage limit, resets 3:50am", transient=True)
        delay, _ = agent._cap_delay_seconds(exc, now=0)  # no reset_at → text path
        assert abs(delay - (100 * 60 + agent._CAP_WAIT_MARGIN_S)) < 1

    exc_none = ClaudeInvocationError("overloaded somehow", transient=True)
    delay_none, _ = agent._cap_delay_seconds(exc_none, now=0)
    assert delay_none == agent._CAP_DEFAULT_WAIT_S


def test_structured_reset_at_drives_invoke_wait():
    """End-to-end: a cap error carrying reset_at makes _invoke_claude sleep until it."""
    now = 2_000_000.0
    calls = {"n": 0}

    def fake_cli(prompt, node_id, sid, model, timeout=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ClaudeInvocationError("blocked", transient=True, reset_at=now + 7200)
        return "OK"

    slept = []
    with patch.object(agent, "_run_claude_cli", fake_cli), \
         patch.object(agent.time, "time", lambda: now), \
         patch.object(agent, "_sleep_with_notice", lambda s, n, l: slept.append(s)):
        out = agent._invoke_claude("p", "n", None)

    assert out == "OK"
    assert len(slept) == 1 and abs(slept[0] - (7200 + agent._CAP_WAIT_MARGIN_S)) < 1


def test_budget_timeout_warns_retry_with_time_budget():
    """After a wall-clock timeout, the retry's prompt is prefixed with a budget
    warning that states the limit, so the next attempt can size its work to fit."""
    seen_prompts = []

    def fake_cli(prompt, node_id, sid, model, timeout=None, **kwargs):
        seen_prompts.append(prompt)
        if len(seen_prompts) == 1:
            raise ClaudeInvocationError(
                "Timeout waiting for result from Claude for node 'implement' after 1200s",
                transient=True,
                timed_out=True,
            )
        return "RESULT_OK"

    with patch.object(agent, "_run_claude_cli", fake_cli), \
         patch.object(agent.time, "sleep", lambda s: None):
        out = agent._invoke_claude("DO THE TASK", "implement", None, timeout=1200)

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
            raise ClaudeInvocationError("overloaded_error", transient=True)
        return "OK"

    with patch.object(agent, "_run_claude_cli", fake_cli), \
         patch.object(agent.time, "sleep", lambda s: None):
        out = agent._invoke_claude("DO THE TASK", "implement", None, timeout=1200)

    assert out == "OK"
    assert seen_prompts == ["DO THE TASK", "DO THE TASK"]


def test_cap_sleeps_until_reset_then_resumes():
    """A cap error pauses (parsed reset, not short backoff) and retries to success."""
    calls = {"n": 0}

    def fake_cli(prompt, node_id, sid, model, timeout=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ClaudeInvocationError(CAP_MSG, transient=True)
        return "RESULT_OK"

    slept = []
    with patch.object(agent, "_run_claude_cli", fake_cli), \
         patch.object(agent, "_sleep_with_notice", lambda s, n, l: slept.append(s)):
        out = agent._invoke_claude("prompt", "select_gate", None)

    assert out == "RESULT_OK"
    assert calls["n"] == 2, "should retry the node after the cap wait"
    assert len(slept) == 1, "should pause exactly once"
    # waited a positive, scheduled amount (parsed reset + margin), never longer than a day
    assert 0 < slept[0] <= 24 * 3600 + agent._CAP_WAIT_MARGIN_S + 1


def test_cap_waits_do_not_consume_short_retry_budget():
    """Even with a tiny short-retry budget, multiple caps are ridden out."""
    calls = {"n": 0}

    def fake_cli(prompt, node_id, sid, model, timeout=None, **kwargs):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise ClaudeInvocationError(CAP_MSG, transient=True)
        return "OK_AFTER_CAPS"

    with patch.object(agent, "_run_claude_cli", fake_cli), \
         patch.object(agent, "_sleep_with_notice", lambda s, n, l: None):
        out = agent._invoke_claude("p", "n", None, max_invoke_retries=1)  # short budget = 1

    assert out == "OK_AFTER_CAPS"
    assert calls["n"] == 4, "3 caps + 1 success, despite max_invoke_retries=1"


def test_cap_wait_safety_bound():
    """A cap that never clears gives up after _MAX_CAP_WAITS instead of looping forever."""
    def always_cap(prompt, node_id, sid, model, timeout=None, **kwargs):
        raise ClaudeInvocationError(CAP_MSG, transient=True)

    with patch.object(agent, "_run_claude_cli", always_cap), \
         patch.object(agent, "_sleep_with_notice", lambda s, n, l: None), \
         patch.object(agent, "_MAX_CAP_WAITS", 3):
        try:
            agent._invoke_claude("p", "n", None)
            raise AssertionError("expected ClaudeInvocationError after exhausting cap waits")
        except ClaudeInvocationError:
            pass


def test_short_transient_uses_bounded_backoff_then_fails():
    """A non-cap transient (overload) retries with backoff and fails fast."""
    calls = {"n": 0}

    def always_overloaded(prompt, node_id, sid, model, timeout=None, **kwargs):
        calls["n"] += 1
        raise ClaudeInvocationError("overloaded", transient=True)

    with patch.object(agent, "_run_claude_cli", always_overloaded), \
         patch.object(agent.time, "sleep", lambda s: None):
        try:
            agent._invoke_claude("p", "n", None, max_invoke_retries=2)
            raise AssertionError("expected ClaudeInvocationError after retries")
        except ClaudeInvocationError as e:
            assert "overloaded" in str(e)
    assert calls["n"] == 3, "initial + 2 retries"


def test_non_transient_fails_immediately():
    calls = {"n": 0}

    def hard_fail(prompt, node_id, sid, model, timeout=None, **kwargs):
        calls["n"] += 1
        raise ClaudeInvocationError("malformed workflow node", transient=False)

    with patch.object(agent, "_run_claude_cli", hard_fail):
        try:
            agent._invoke_claude("p", "n", None)
            raise AssertionError("expected immediate raise on non-transient error")
        except ClaudeInvocationError:
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
