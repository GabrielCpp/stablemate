"""Tests for the self-update exec-retry in _spawn_streaming.

A turn must not be interrupted because the agent CLI is rewriting its own binary
(Claude Code ships a native binary and auto-updates by default) — a brief
ETXTBSY/ENOENT exec window is retried. A genuinely-absent CLI (a non-interactive
PATH with no nvm shim) fails fast instead of burning the retry budget.

Runs without real sleeping or a real subprocess (both patched). Runnable two ways:
    ./.venv/bin/python tests/test_agent_exec_retry.py     # standalone, no pytest
    ./.venv/bin/python -m pytest tests/test_agent_exec_retry.py
"""
from __future__ import annotations

import errno
import os
from unittest.mock import MagicMock, patch

from workhorse.runner import agent
from workhorse.runner.agent import BackendInvocationError


def _popen_failing(n_failures: int, code: int, ok: object | None = None):
    """Fake Popen: raise OSError(code) the first n_failures calls, then return ok."""
    calls = {"n": 0}

    def fake(cmd, **kwargs):
        calls["n"] += 1
        if calls["n"] <= n_failures:
            raise OSError(code, os.strerror(code))
        return ok if ok is not None else MagicMock()

    fake.calls = calls
    return fake


def test_self_update_etxtbsy_is_retried_then_succeeds():
    """The binary being overwritten mid-run recovers without failing the turn."""
    proc = MagicMock()
    fake = _popen_failing(3, errno.ETXTBSY, ok=proc)
    with patch.object(agent.subprocess, "Popen", fake), \
         patch.object(agent.time, "sleep") as slept, \
         patch.object(agent.shutil, "which", return_value="/x/claude"):
        got = agent._spawn_streaming(["claude", "-p"], "n")
    assert got is proc
    assert fake.calls["n"] == 4          # 3 busy attempts + 1 success
    assert slept.call_count == 3         # one short backoff before each retry


def test_absent_cli_fails_nontransient_after_bounded_retries():
    """A genuinely-absent CLI (which() stays None) fails non-transient — but only AFTER
    the bounded retries, never in an unbounded spin. We accept a few seconds' delay on a
    misconfigured launch as the price of never misreading a self-update rename window as
    'absent' (that misread is exactly what killed okf-builder web-bf3's last item)."""
    fake = _popen_failing(99, errno.ENOENT)   # always ENOENT, and...
    with patch.object(agent.subprocess, "Popen", fake), \
         patch.object(agent.time, "sleep") as slept, \
         patch.object(agent.shutil, "which", return_value=None):   # ...never resolves
        try:
            agent._spawn_streaming(["claude", "-p"], "n")
            raise AssertionError("expected BackendInvocationError for an absent CLI")
        except BackendInvocationError as exc:
            assert exc.transient is False
            assert "does not load nvm" in str(exc)   # the actionable launch-context hint
    assert fake.calls["n"] == agent._EXEC_RETRY_MAX + 1   # bounded, not a spin
    assert slept.call_count == agent._EXEC_RETRY_MAX


def test_self_update_enoent_rename_recovers_even_when_which_is_blind():
    """THE web-bf3 regression: during a self-update's rename BOTH exec and shutil.which()
    see the binary as absent (ENOENT + which()==None). A single which() probe cannot tell
    this from a never-installed CLI — so we must resolve it in time. Retrying rides the
    rename out and the turn is NOT failed."""
    proc = MagicMock()
    fake = _popen_failing(2, errno.ENOENT, ok=proc)   # gone for two attempts, then back
    with patch.object(agent.subprocess, "Popen", fake), \
         patch.object(agent.time, "sleep"), \
         patch.object(agent.shutil, "which", return_value=None):   # blind, like exec
        got = agent._spawn_streaming(["claude", "-p"], "n")
    assert got is proc                    # recovered, not misclassified as absent
    assert fake.calls["n"] == 3


def test_exhausted_retries_escalate_as_transient():
    """A self-update that never clears hands off to the outer backoff ladder."""
    fake = _popen_failing(99, errno.ETXTBSY)   # never recovers
    with patch.object(agent.subprocess, "Popen", fake), \
         patch.object(agent.time, "sleep"), \
         patch.object(agent.shutil, "which", return_value="/x/claude"):
        try:
            agent._spawn_streaming(["claude", "-p"], "n")
            raise AssertionError("expected BackendInvocationError after exhausting retries")
        except BackendInvocationError as exc:
            assert exc.transient is True   # transient → outer ladder gives it more time
    assert fake.calls["n"] == agent._EXEC_RETRY_MAX + 1


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
