"""A trial runs in its sandbox, and is void if it committed anywhere else.

Twice now a replay trial's agent has committed its QA artifact through the *enclosing*
stablemate worktree rather than the clone it was handed. The prompt's paths are absolute
and point here; `benchmarks/.replay/` is ignored here; and an agent reading that ignore as
an obstacle force-adds past it. The commit lands on the branch the harness is being
developed on, where nothing surfaces it until a human reads `git log` — and where a push
makes it everyone's.

Both halves are covered below: the trial process is launched standing in the sandbox, and
HEAD is read either side of it so a leak fails that trial instead of being discovered later.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

_spec = importlib.util.spec_from_file_location(
    "replay_sandbox", Path(__file__).parents[1] / "replay.py"
)
assert _spec is not None and _spec.loader is not None
replay = importlib.util.module_from_spec(_spec)
sys.modules["replay_sandbox"] = replay
_spec.loader.exec_module(replay)


def run(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name, encoding="utf-8")
    run("add", name, cwd=repo)
    run("-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", name, cwd=repo)
    return run("rev-parse", "HEAD", cwd=repo)


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A stand-in for the stablemate worktree the harness itself lives in."""
    root = tmp_path / "stablemate"
    root.mkdir()
    run("init", "--quiet", "--initial-branch", "main", cwd=root)
    commit(root, "first")
    monkeypatch.setattr(replay, "STABLEMATE", root)
    return root


# ── the detection ─────────────────────────────────────────────────────────────────────
def test_an_untouched_checkout_reports_no_leak(checkout: Path) -> None:
    before = replay.head_of(checkout)

    assert replay.leaked_commits(before) == []


def test_a_commit_made_during_the_trial_is_reported(checkout: Path) -> None:
    before = replay.head_of(checkout)
    commit(checkout, "stray")

    leaked = replay.leaked_commits(before)

    assert len(leaked) == 1
    assert "stray" in leaked[0]


def test_every_leaked_commit_is_named_not_just_the_last(checkout: Path) -> None:
    """Trial 1 and trial 2 each leaked one; a report of the tip alone hides half the damage."""
    before = replay.head_of(checkout)
    commit(checkout, "stray-one")
    commit(checkout, "stray-two")

    leaked = replay.leaked_commits(before)

    assert [line.split(" ", 1)[1] for line in leaked] == ["stray-two", "stray-one"]


def test_a_reading_git_could_not_answer_never_invents_a_leak(tmp_path: Path,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """`head_of` is tolerant where `git()` is fatal, and an empty reading must stay silent."""
    monkeypatch.setattr(replay, "STABLEMATE", tmp_path)

    assert replay.head_of(tmp_path) == ""
    assert replay.leaked_commits("") == []


# ── the prevention ────────────────────────────────────────────────────────────────────
class _FakeProcess:
    """A workflow run that prints nothing and exits clean."""

    def __init__(self) -> None:
        self.stdout = iter(())

    def wait(self) -> int:
        return 0


def intercept_the_workflow(
    monkeypatch: pytest.MonkeyPatch, on_launch: Callable[[], object] = lambda: None
) -> dict[str, Any]:
    """Replace only the `uv run workhorse-coder` launch, and record how it was made.

    Only that one, because `run_trial` also reads HEAD either side of the trial and those
    readings shell out to git through the same attribute — a blanket fake makes the test
    call itself. *on_launch* runs while the fake process is "executing", which is when a
    leaking trial would be making its commit.
    """
    real_popen = subprocess.Popen
    launched: dict[str, Any] = {}

    def fake_popen(cmd: list[str], **kwargs: Any) -> Any:
        if cmd[0] != "uv":
            return real_popen(cmd, **kwargs)
        launched.update(cmd=cmd, **kwargs)
        on_launch()
        return _FakeProcess()

    monkeypatch.setattr(replay.subprocess, "Popen", fake_popen)
    return launched


def test_the_trial_process_stands_in_the_sandbox(
    checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`cwd=` decides what git repo every agent turn under the run is standing in."""
    sandbox = tmp_path / "work" / "trial" / "app"
    monkeypatch.setattr(replay, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(replay, "checkout", lambda fixture, story, flow, dest: sandbox)
    launched = intercept_the_workflow(monkeypatch)
    fixture = replay.Fixture(name="f", source=Path("app"), app=None, stories=[])

    run_id, rc = replay.run_trial(
        fixture, flow="qa", story="s", label="l", n=1, budget_s=0, cli="opencode"
    )

    assert rc == 0
    assert run_id == "replay-l-qa-s-1"
    assert launched["cwd"] == sandbox
    assert launched["cmd"][:4] == ["uv", "run", "--project", str(checkout)]


def test_the_trial_process_carries_the_sandbox_in_its_environment(
    checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`cwd=` alone leaks: an agent CLI that trusts `$PWD` would still work on the checkout.

    A live trial proved it — `cwd=repo` was in place and the run's own agents still committed
    into the enclosing worktree, because `Popen` moves the child's directory and leaves the
    inherited variable naming the launcher's. `OLDPWD` goes with it: a stale one names this
    checkout just as loudly.
    """
    sandbox = tmp_path / "work" / "trial" / "app"
    monkeypatch.setenv("PWD", str(checkout))
    monkeypatch.setenv("OLDPWD", str(checkout))
    monkeypatch.setattr(replay, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(replay, "checkout", lambda fixture, story, flow, dest: sandbox)
    launched = intercept_the_workflow(monkeypatch)
    fixture = replay.Fixture(name="f", source=Path("app"), app=None, stories=[])

    replay.run_trial(fixture, flow="qa", story="s", label="l", n=1, budget_s=0, cli="opencode")

    assert launched["env"]["PWD"] == str(sandbox)
    assert "OLDPWD" not in launched["env"]


def test_a_trial_that_committed_here_comes_back_failed(
    checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The trial is void, and `cmd_run`'s exit code is what carries that to the caller."""
    sandbox = tmp_path / "work" / "trial" / "app"
    monkeypatch.setattr(replay, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(replay, "checkout", lambda fixture, story, flow, dest: sandbox)

    intercept_the_workflow(monkeypatch, lambda: commit(checkout, "stray"))
    fixture = replay.Fixture(name="f", source=Path("app"), app=None, stories=[])

    _, rc = replay.run_trial(
        fixture, flow="qa", story="s", label="l", n=1, budget_s=0, cli="opencode"
    )

    assert rc == replay.LEAK_RC
