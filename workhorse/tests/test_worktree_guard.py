"""Tests for workhorse/runner/worktree_guard.py — the `git` an agent turn sees in a shared tree."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from workhorse.config_run import AgentResilience
from workhorse.pyflow import Workflow
from workhorse.runner import process, worktree_guard

HAVE_GIT = shutil.which("git") is not None


def _repo(path: Path) -> None:
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.email", "test@example.com"),
        ("config", "user.name", "Test"),
    ):
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)
    (path / "doc.md").write_text("committed\n")
    subprocess.run(["git", "-C", str(path), "add", "doc.md"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "one"], check=True,
                   capture_output=True)


def _agent_runs(command: str, repo: Path) -> tuple[int, str]:
    """Run `command` through a shell the way an agent CLI's bash tool would."""
    lines: list[str] = []
    code = f"import subprocess, sys; sys.exit(subprocess.call({command!r}, shell=True))"
    _, rc = process.stream_subprocess(
        [sys.executable, "-u", "-c", code],
        "repair",
        30,
        lines.append,
        resilience=AgentResilience(),
        cwd=str(repo),
    )
    return rc, "".join(lines)


def test_discarding_commands_are_refused():
    for argv in (
        ["stash"],
        ["stash", "push", "--", "doc.md"],
        ["stash", "pop"],
        ["stash", "drop"],
        ["-C", "/repo", "stash"],
        ["checkout", "--", "doc.md"],
        ["checkout", "main"],
        ["switch", "main"],
        ["restore", "doc.md"],
        ["restore", "--staged", "--worktree", "doc.md"],
        ["reset", "--hard"],
        ["reset", "--hard", "HEAD~1"],
        ["clean", "-fd"],
    ):
        assert worktree_guard.refusal(argv) is not None, argv


def test_reading_and_recording_commands_pass_through():
    for argv in (
        [],
        ["status"],
        ["diff", "--", "doc.md"],
        ["show", "HEAD:doc.md"],
        ["log", "--oneline", "-5"],
        ["stash", "list"],
        ["-c", "core.pager=cat", "stash", "show"],
        ["-C", "checkout", "status"],
        ["restore", "--staged", "doc.md"],
        ["reset"],
        ["reset", "doc.md"],
        ["clean", "-n"],
        ["add", "doc.md"],
        ["commit", "-m", "x"],
    ):
        assert worktree_guard.refusal(argv) is None, argv


def test_a_guarded_turn_cannot_stash_away_another_runs_edit():
    if not HAVE_GIT:
        return
    with tempfile.TemporaryDirectory() as tmp:
        repo, run_dir = Path(tmp) / "repo", Path(tmp) / "run"
        repo.mkdir()
        run_dir.mkdir()
        _repo(repo)
        (repo / "doc.md").write_text("another run's edit\n")

        with worktree_guard.guarding(run_dir):
            rc, out = _agent_runs("git stash && git stash pop", repo)
            status_rc, status = _agent_runs("git status --porcelain", repo)

        assert rc != 0
        assert "refused" in out and "git show HEAD:<path>" in out
        assert (repo / "doc.md").read_text() == "another run's edit\n"
        assert subprocess.run(["git", "-C", str(repo), "stash", "list"], capture_output=True,
                              text=True, check=True).stdout == ""
        assert status_rc == 0 and "M doc.md" in status


def test_an_unguarded_turn_gets_the_real_git():
    if not HAVE_GIT:
        return
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        _repo(repo)
        (repo / "doc.md").write_text("edit\n")

        rc, _ = _agent_runs("git stash", repo)

        assert rc == 0
        assert (repo / "doc.md").read_text() == "committed\n"


def test_the_path_is_restored_when_the_scope_ends():
    with tempfile.TemporaryDirectory() as tmp:
        with worktree_guard.guarding(Path(tmp)):
            inside = worktree_guard.guarded_path("/usr/bin")
        assert inside.split(":")[0] == str((Path(tmp) / "worktree-guard").resolve())
        assert worktree_guard.guarded_path("/usr/bin") == "/usr/bin"


class _Engine:
    """The one engine seam `Workflow.agent` reaches: where the run lives, and the turn."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.worktree_dispatched = False
        self.paths: list[str] = []

    def agent(self, prompt: str, **_: Any) -> None:
        self.paths.append(worktree_guard.guarded_path("/usr/bin"))


class _Shared(Workflow):
    PROTECT_WORKTREE = True

    def start(self) -> None:
        return None


class _Private(Workflow):
    def start(self) -> None:
        return None


def test_only_a_workflow_that_declares_it_runs_turns_guarded():
    with tempfile.TemporaryDirectory() as tmp:
        engines = {}
        for flow in (_Shared, _Private):
            wf = flow()
            engine = _Engine(Path(tmp))
            wf._engine = engine  # pyright: ignore[reportPrivateUsage]
            wf.agent("prompts/repair.md", returns=dict)
            engines[flow] = engine.paths[0]

        assert engines[_Shared].startswith(str((Path(tmp) / "worktree-guard").resolve()))
        assert engines[_Private] == "/usr/bin"


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
