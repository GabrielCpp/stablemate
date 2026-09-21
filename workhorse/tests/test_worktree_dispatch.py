"""`workhorse run --worktree` — cutting a fresh branch and git worktree for a run."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from workhorse.pyflow import run as run_mod
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.run import RunInvocation, run_pyflow
from workhorse.pyflow.transitions import Done, Transition
from workhorse.pyflow.workflow import Workflow
from workhorse.runner import worktree_guard

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
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "one"], check=True, capture_output=True
    )


class Immediate(Workflow):
    """A one-state flow that finishes on entry — enough to drive `run_pyflow` end to end without an agent turn or a second state to check into."""

    def start(self) -> Transition:
        return Done(None)


class _Registry(Registry):
    def directory(self) -> Path:
        return Path(__file__).parent


def _registry() -> Registry:
    registry = _Registry("worktree-dispatch")
    registry.add_flows(main=Immediate)
    registry.entry = Immediate
    return registry


REGISTRY = _registry()


def _run(runs_dir: Path, worktree_dir: Path | None, **kwargs: Any) -> int:
    """Drive one `run_pyflow` call with `resolve_worktree_dir` fixed to `worktree_dir`."""
    with patch.object(run_mod, "resolve_worktree_dir", lambda: worktree_dir):
        return run_pyflow(
            RunInvocation(registry=REGISTRY, runs_dir=runs_dir, flow="main", **kwargs)
        )


def _run_record(runs_dir: Path) -> dict[str, Any]:
    (run_dir,) = [d for d in runs_dir.iterdir() if d.is_dir()]
    return json.loads((run_dir / "run.json").read_text())



def test_worktree_cuts_default_named_branch_and_dir_under_worktree_dir():
    if not HAVE_GIT:
        return
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "acme"
        worktree_dir = Path(tmp) / "worktrees"
        runs_dir = Path(tmp) / "runs"
        repo.mkdir()
        worktree_dir.mkdir()
        _repo(repo)

        code = _run(
            runs_dir, worktree_dir, run_id="t", params={"repo_dir": str(repo)}, worktree=True
        )

        assert code == 0
        record = _run_record(runs_dir)
        assert record["worktree_branch"] == "run/worktree-dispatch-t"
        expected_dir = worktree_dir / "acme-run-worktree-dispatch-t"
        assert record["worktree_path"] == str(expected_dir)
        assert expected_dir.is_dir()
        assert subprocess.run(
            ["git", "-C", str(expected_dir), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip() == "run/worktree-dispatch-t"



def test_worktree_branch_and_base_overrides_are_honored():
    if not HAVE_GIT:
        return
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "acme"
        worktree_dir = Path(tmp) / "worktrees"
        runs_dir = Path(tmp) / "runs"
        repo.mkdir()
        worktree_dir.mkdir()
        _repo(repo)
        subprocess.run(
            ["git", "-C", str(repo), "branch", "side"], check=True, capture_output=True
        )

        code = _run(
            runs_dir, worktree_dir, run_id="t", params={"repo_dir": str(repo)}, worktree=True,
            worktree_branch="feature/thing", worktree_base="side",
        )

        assert code == 0
        record = _run_record(runs_dir)
        assert record["worktree_branch"] == "feature/thing"
        expected_dir = worktree_dir / "acme-feature-thing"
        assert record["worktree_path"] == str(expected_dir)
        assert expected_dir.is_dir()



def test_unset_worktree_dir_fails_naming_the_config_command(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "acme"
        runs_dir = Path(tmp) / "runs"
        repo.mkdir()

        code = _run(runs_dir, None, run_id="t", params={"repo_dir": str(repo)}, worktree=True)

        assert code == 1
        err = capsys.readouterr().out
        assert "farrier config set-worktree" in err



def test_a_colliding_branch_fails_fast_and_creates_nothing(capsys):
    if not HAVE_GIT:
        return
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "acme"
        worktree_dir = Path(tmp) / "worktrees"
        runs_dir = Path(tmp) / "runs"
        repo.mkdir()
        worktree_dir.mkdir()
        _repo(repo)
        subprocess.run(
            ["git", "-C", str(repo), "branch", "run/worktree-dispatch-t"],
            check=True, capture_output=True,
        )

        code = _run(runs_dir, worktree_dir, run_id="t", params={"repo_dir": str(repo)}, worktree=True)

        assert code == 1
        err = capsys.readouterr().out
        assert "run/worktree-dispatch-t" in err
        assert list(worktree_dir.iterdir()) == []


def test_a_colliding_directory_fails_fast_and_creates_nothing(capsys):
    if not HAVE_GIT:
        return
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "acme"
        worktree_dir = Path(tmp) / "worktrees"
        runs_dir = Path(tmp) / "runs"
        repo.mkdir()
        worktree_dir.mkdir()
        _repo(repo)
        target = worktree_dir / "acme-run-worktree-dispatch-t"
        target.mkdir()

        code = _run(runs_dir, worktree_dir, run_id="t", params={"repo_dir": str(repo)}, worktree=True)

        assert code == 1
        err = capsys.readouterr().out
        assert str(target) in err
        assert list(worktree_dir.iterdir()) == [target]



def _dispatched_run_dir(tmp: str, worktree_dir: Path) -> Path:
    repo = Path(tmp) / "acme"
    runs_dir = Path(tmp) / "runs"
    repo.mkdir()
    _repo(repo)
    code = _run(runs_dir, worktree_dir, run_id="t", params={"repo_dir": str(repo)}, worktree=True)
    assert code == 0
    (run_dir,) = [d for d in runs_dir.iterdir() if d.is_dir()]
    return run_dir


def test_run_record_worktree_fields_are_written_at_dispatch():
    if not HAVE_GIT:
        return
    with tempfile.TemporaryDirectory() as tmp:
        worktree_dir = Path(tmp) / "worktrees"
        worktree_dir.mkdir()
        run_dir = _dispatched_run_dir(tmp, worktree_dir)
        record = json.loads((run_dir / "run.json").read_text())
        assert record["worktree_path"] and record["worktree_branch"]


def test_resume_resolves_repo_dir_from_the_recorded_worktree_without_recutting():
    if not HAVE_GIT:
        return
    with tempfile.TemporaryDirectory() as tmp:
        worktree_dir = Path(tmp) / "worktrees"
        worktree_dir.mkdir()
        run_dir = _dispatched_run_dir(tmp, worktree_dir)
        record = json.loads((run_dir / "run.json").read_text())
        recorded_path = record["worktree_path"]

        captured: dict[str, Any] = {}
        original_instantiate = run_mod._instantiate  # noqa: SLF001

        def spy_instantiate(workflow_cls, inputs):
            captured["repo_dir"] = inputs.get("repo_dir")
            return original_instantiate(workflow_cls, inputs)

        with patch.object(run_mod.worktree_mod, "add") as fake_add, \
                patch.object(run_mod, "_instantiate", spy_instantiate):
            code = run_pyflow(RunInvocation(
                registry=REGISTRY, runs_dir=run_dir.parent, flow="main",
                resume_run_dir=run_dir,
            ))

        assert code == 0
        fake_add.assert_not_called()
        assert captured["repo_dir"] == recorded_path


def test_worktree_flag_on_resume_is_ignored_and_notes_the_recorded_one(capsys):
    if not HAVE_GIT:
        return
    with tempfile.TemporaryDirectory() as tmp:
        worktree_dir = Path(tmp) / "worktrees"
        worktree_dir.mkdir()
        run_dir = _dispatched_run_dir(tmp, worktree_dir)
        record = json.loads((run_dir / "run.json").read_text())
        recorded_path = record["worktree_path"]
        capsys.readouterr()

        captured: dict[str, Any] = {}
        original_instantiate = run_mod._instantiate  # noqa: SLF001

        def spy_instantiate(workflow_cls, inputs):
            captured["repo_dir"] = inputs.get("repo_dir")
            return original_instantiate(workflow_cls, inputs)

        with patch.object(run_mod.worktree_mod, "add") as fake_add, \
                patch.object(run_mod, "_instantiate", spy_instantiate):
            code = run_pyflow(RunInvocation(
                registry=REGISTRY, runs_dir=run_dir.parent, flow="main",
                resume_run_dir=run_dir, worktree=True, worktree_branch="something-else",
            ))

        assert code == 0
        fake_add.assert_not_called()
        assert captured["repo_dir"] == recorded_path
        out = capsys.readouterr().out
        assert "ignored" in out and recorded_path in out



def test_dry_run_worktree_creates_no_branch_or_directory(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "acme"
        worktree_dir = Path(tmp) / "worktrees"
        runs_dir = Path(tmp) / "runs"
        repo.mkdir()
        worktree_dir.mkdir()
        if HAVE_GIT:
            _repo(repo)

        with patch.object(run_mod.worktree_mod, "add") as fake_add:
            _run(
                runs_dir, worktree_dir, run_id="t", params={"repo_dir": str(repo)},
                worktree=True, dry_run=True,
            )

        fake_add.assert_not_called()
        assert list(worktree_dir.iterdir()) == []
        out = capsys.readouterr().out
        assert "--dry-run" in out



class _Engine:
    """The one engine seam `Workflow.agent` reaches: where the run lives, the turn, and (now) whether this run owns its tree exclusively."""

    def __init__(self, run_dir: Path, worktree_dispatched: bool) -> None:
        self.run_dir = run_dir
        self.worktree_dispatched = worktree_dispatched
        self.paths: list[str] = []

    def agent(self, prompt: str, **_: Any) -> None:
        self.paths.append(worktree_guard.guarded_path("/usr/bin"))


class _Shared(Workflow):
    PROTECT_WORKTREE = True

    def start(self) -> Transition:
        return Done(None)


def test_a_worktree_dispatched_run_is_not_guarded_even_when_the_workflow_opts_in():
    with tempfile.TemporaryDirectory() as tmp:
        wf = _Shared()
        engine = _Engine(Path(tmp), worktree_dispatched=True)
        wf._engine = engine  # pyright: ignore[reportPrivateUsage]
        wf.agent("prompts/repair.md", returns=dict)

        assert engine.paths[0] == "/usr/bin"


def test_a_non_worktree_run_still_gets_the_guard_it_opted_into():
    with tempfile.TemporaryDirectory() as tmp:
        wf = _Shared()
        engine = _Engine(Path(tmp), worktree_dispatched=False)
        wf._engine = engine  # pyright: ignore[reportPrivateUsage]
        wf.agent("prompts/repair.md", returns=dict)

        assert engine.paths[0].startswith(str((Path(tmp) / "worktree-guard").resolve()))



def test_no_worktree_flag_leaves_repo_dir_and_run_record_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "acme"
        runs_dir = Path(tmp) / "runs"
        repo.mkdir()

        code = _run(runs_dir, None, run_id="t", params={"repo_dir": str(repo)})

        assert code == 0
        record = _run_record(runs_dir)
        assert record["worktree_path"] == "" and record["worktree_branch"] == ""


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
