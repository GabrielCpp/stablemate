"""Tests for the self-update exec-retry in ``ProcessSupervisor.spawn``.

A turn must not be interrupted because the agent CLI is rewriting its own binary
(Claude Code ships a native binary and auto-updates by default) — an
ETXTBSY/ENOENT exec window is retried, and a longer replacement of a previously
working CLI remains transient. A genuinely-absent CLI (a non-interactive PATH with
no nvm shim) fails fast instead of burning the retry budget.

The backoff between retries is a ``FakeClock`` the supervisor is built with, so the
whole file runs in microseconds with nothing patched on the clock — the sleeps are a
list of numbers to assert on. Runnable two ways:
    ./.venv/bin/python tests/test_agent_exec_retry.py     # standalone, no pytest
    ./.venv/bin/python -m pytest tests/test_agent_exec_retry.py
"""
from __future__ import annotations

import errno
import os
from unittest.mock import MagicMock, patch

from _fakes import FakeClock
from workhorse.config_run import AgentResilience
from workhorse.runner import process
from workhorse.runner.failure import BackendInvocationError
from workhorse.runner.waits import (
    RecoveryWaitBudget,
    RecoveryWaitBudgetExceeded,
    recovery_wait_scope,
)

#: The ladder's knobs are injected, never read from the module — so a test states
#: the exec-retry budget it is asserting against instead of patching a global.
RESILIENCE = AgentResilience()


class _PopenFailing:
    """Fake Popen: raise OSError(code) the first n_failures calls, then return ok.

    A class and not a closure with an attribute hung off it, because the attempt
    count is what every test here asserts on — so it is a declared field of the
    double rather than something bolted onto a function object."""

    def __init__(self, n_failures: int, code: int, ok: object | None = None) -> None:
        self.n_failures = n_failures
        self.code = code
        self.ok = ok
        #: Attempts so far, under the key the assertions read.
        self.calls = {"n": 0}

    def __call__(self, cmd, **kwargs):
        self.calls["n"] += 1
        if self.calls["n"] <= self.n_failures:
            raise OSError(self.code, os.strerror(self.code))
        return self.ok if self.ok is not None else MagicMock()


def _supervisor() -> tuple[process.ProcessSupervisor, FakeClock]:
    """A supervisor whose waits are recorded rather than served."""
    clock = FakeClock()
    return process.ProcessSupervisor(clock=clock), clock


def test_self_update_etxtbsy_is_retried_then_succeeds():
    """The binary being overwritten mid-run recovers without failing the turn."""
    proc = MagicMock()
    fake = _PopenFailing(3, errno.ETXTBSY, ok=proc)
    supervisor, clock = _supervisor()
    with patch.object(process.subprocess, "Popen", fake), \
         patch.object(process.shutil, "which", return_value="/x/claude"):
        got = supervisor.spawn(["claude", "-p"], "n", resilience=RESILIENCE)
    assert got is proc
    assert fake.calls["n"] == 4          # 3 busy attempts + 1 success
    assert len(clock.slept) == 3         # one short backoff before each retry


def test_absent_cli_fails_nontransient_after_bounded_retries():
    """A genuinely-absent CLI (which() stays None) fails non-transient — but only AFTER
    the bounded retries, never in an unbounded spin. We accept a few seconds' delay on a
    misconfigured launch as the price of never misreading a self-update rename window as
    'absent' (that misread is exactly what killed okf-builder web-bf3's last item)."""
    fake = _PopenFailing(99, errno.ENOENT)   # always ENOENT, and...
    supervisor, clock = _supervisor()
    with patch.object(process.subprocess, "Popen", fake), \
         patch.object(process.shutil, "which", return_value=None):   # ...never resolves
        try:
            supervisor.spawn(["claude", "-p"], "n", resilience=RESILIENCE)
            raise AssertionError("expected BackendInvocationError for an absent CLI")
        except BackendInvocationError as exc:
            assert exc.transient is False
            assert "does not load nvm" in str(exc)   # the actionable launch-context hint
    assert fake.calls["n"] == RESILIENCE.exec_retry_max + 1   # bounded, not a spin
    assert len(clock.slept) == RESILIENCE.exec_retry_max


def test_exec_wait_budget_is_shared_across_repeated_spawns():
    """Outer turn retries cannot renew the subprocess self-update allowance."""
    resilience = AgentResilience(
        exec_retry_max=1,
        exec_retry_base_s=1,
        exec_retry_cap_s=1,
        exec_retry_wait_budget_s=1,
    )
    fake = _PopenFailing(99, errno.ETXTBSY)
    supervisor, clock = _supervisor()
    budget = RecoveryWaitBudget.from_resilience(resilience)
    with patch.object(process.subprocess, "Popen", fake), \
         patch.object(process.shutil, "which", return_value="/x/claude"), \
         recovery_wait_scope(budget):
        try:
            supervisor.spawn(["claude", "-p"], "n", resilience=resilience)
        except BackendInvocationError:
            pass
        try:
            supervisor.spawn(["claude", "-p"], "n", resilience=resilience)
            raise AssertionError("the second spawn must not renew the exec wait budget")
        except RecoveryWaitBudgetExceeded as exc:
            assert exc.kind == "exec-retry"

    assert clock.slept == [1]


def test_self_update_enoexec_half_written_binary_is_retried_then_succeeds():
    """THE web-bf4 regression: a self-update was caught mid-write — attempt 1 hit ENOENT
    (rename gap, retried), attempt 2 hit ENOEXEC (errno 8, 'exec format error': the new
    binary was present but only half-written, so its header was not yet valid). ENOEXEC is
    the same self-update window at a different instant and MUST be retried, not treated as a
    permanent 'wrong format' failure. Before the fix ENOEXEC was absent from the retryable
    set, so the run died non-recoverably one item short of done."""
    proc = MagicMock()
    calls = {"n": 0}

    def fake(cmd, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(errno.ENOENT, os.strerror(errno.ENOENT))   # rename gap
        if calls["n"] == 2:
            raise OSError(errno.ENOEXEC, os.strerror(errno.ENOEXEC))  # half-written binary
        return proc                                                   # update finished

    supervisor, _ = _supervisor()
    with patch.object(process.subprocess, "Popen", fake), \
         patch.object(process.shutil, "which", return_value="/x/claude"):
        got = supervisor.spawn(["claude", "-p"], "n", resilience=RESILIENCE)
    assert got is proc                    # rode out the update; the turn is NOT failed
    assert calls["n"] == 3


def test_self_update_enoent_rename_recovers_even_when_which_is_blind():
    """THE web-bf3 regression: during a self-update's rename BOTH exec and shutil.which()
    see the binary as absent (ENOENT + which()==None). A single which() probe cannot tell
    this from a never-installed CLI — so we must resolve it in time. Retrying rides the
    rename out and the turn is NOT failed."""
    proc = MagicMock()
    fake = _PopenFailing(2, errno.ENOENT, ok=proc)   # gone for two attempts, then back
    supervisor, _ = _supervisor()
    with patch.object(process.subprocess, "Popen", fake), \
         patch.object(process.shutil, "which", return_value=None):   # blind, like exec
        got = supervisor.spawn(["claude", "-p"], "n", resilience=RESILIENCE)
    assert got is proc                    # recovered, not misclassified as absent
    assert fake.calls["n"] == 3


def test_exhausted_retries_escalate_as_transient():
    """A self-update that never clears hands off to the outer backoff ladder."""
    fake = _PopenFailing(99, errno.ETXTBSY)   # never recovers
    supervisor, _ = _supervisor()
    with patch.object(process.subprocess, "Popen", fake), \
         patch.object(process.shutil, "which", return_value="/x/claude"):
        try:
            supervisor.spawn(["claude", "-p"], "n", resilience=RESILIENCE)
            raise AssertionError("expected BackendInvocationError after exhausting retries")
        except BackendInvocationError as exc:
            assert exc.transient is True   # transient → outer ladder gives it more time
    assert fake.calls["n"] == RESILIENCE.exec_retry_max + 1


def test_cli_that_launched_before_stays_transient_during_long_rename_gap():
    """A package-manager replacement can hide a proven CLI beyond the short retries."""
    proc = MagicMock()
    failures = [OSError(errno.ENOENT, os.strerror(errno.ENOENT))] * (
        RESILIENCE.exec_retry_max + 1
    )
    with patch.object(process.subprocess, "Popen", side_effect=[proc, *failures]), \
         patch.object(process.shutil, "which", return_value=None):
        supervisor, _ = _supervisor()
        assert supervisor.spawn(["opencode", "run"], "n", resilience=RESILIENCE) is proc
        try:
            supervisor.spawn(["opencode", "run"], "n", resilience=RESILIENCE)
            raise AssertionError("expected BackendInvocationError during the rename gap")
        except BackendInvocationError as exc:
            assert exc.transient is True


def test_the_default_supervisor_waits_on_the_real_clock():
    """The seam is an override, not a requirement: built with no arguments, a supervisor
    holds the system clock, so production keeps the backoff it has always had."""
    from workhorse._vendor.stablemate_core.clock import SYSTEM_CLOCK

    assert process.ProcessSupervisor().clock is SYSTEM_CLOCK
    assert process._supervisor.clock is SYSTEM_CLOCK


def test_install_swaps_the_supervisor_and_hands_back_the_old_one():
    """``stream_subprocess`` is what the adapters call, so the injection point for the
    streaming path is the installed supervisor — swapped whole, then put back."""
    supervisor, _ = _supervisor()
    previous = process.install(supervisor)
    try:
        assert process._supervisor is supervisor
    finally:
        assert process.install(previous) is supervisor
    assert process._supervisor is previous


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
