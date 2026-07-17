"""Preflight checks for a workflow's `requires:` block.

Standalone + pytest-compatible, per the repo convention. No network, no real tool
installs: the dist lookup and the PATH probe are patched at their seams.
"""

from __future__ import annotations

import sys

import pytest
from pydantic import ValidationError

from workhorse import requirements as rq
from workhorse.graph.loader import load_workflow


def _req(**kw):
    return rq.Requirement(**kw)


# --- schema ------------------------------------------------------------------


def test_requires_exactly_one_kind():
    with pytest.raises(ValidationError):
        _req(dist="ostler", cmd="ostler")
    with pytest.raises(ValidationError):
        _req(version=">=1.0")


def test_invalid_specifier_rejected_at_parse():
    with pytest.raises(ValidationError):
        _req(cmd="git", version="totally-not-a-specifier")


# --- dist: importability, not PATH -------------------------------------------


def test_dist_missing_is_a_problem(monkeypatch):
    def boom(name):
        raise rq.PackageNotFoundError(name)

    monkeypatch.setattr(rq, "_dist_version", boom)
    problems = rq.check_requirements([_req(dist="ostler", version=">=0.1.0")], "wf")
    assert len(problems) == 1
    assert "ostler" in problems[0]
    # The fix hint must name the interpreter that runs script nodes, not PATH.
    assert sys.executable in problems[0]


def test_dist_on_path_but_not_importable_still_fails(monkeypatch):
    """The pipx-isolation trap: a working CLI shim proves nothing about the import.

    This is the case a PATH check would wrongly pass — the whole reason `dist:`
    exists as a distinct kind.
    """

    def boom(name):
        raise rq.PackageNotFoundError(name)

    monkeypatch.setattr(rq, "_dist_version", boom)
    monkeypatch.setattr(rq.shutil, "which", lambda c: "/usr/bin/ostler")
    assert rq.check_requirements([_req(dist="ostler")], "wf")


def test_dist_version_satisfied(monkeypatch):
    monkeypatch.setattr(rq, "_dist_version", lambda n: "0.2.0")
    assert rq.check_requirements([_req(dist="ostler", version=">=0.1.0")], "wf") == []


def test_dist_version_too_old(monkeypatch):
    monkeypatch.setattr(rq, "_dist_version", lambda n: "0.0.9")
    problems = rq.check_requirements([_req(dist="ostler", version=">=0.1.0")], "wf")
    assert "0.0.9" in problems[0] and ">=0.1.0" in problems[0]


# --- cmd: PATH ---------------------------------------------------------------


def test_cmd_missing_from_path(monkeypatch):
    monkeypatch.setattr(rq.shutil, "which", lambda c: None)
    problems = rq.check_requirements([_req(cmd="git")], "wf")
    assert problems == ["git is not on PATH"]


@pytest.mark.parametrize(
    "line,expected",
    [
        ("git version 2.43.0", "2.43.0"),
        ("gh version 2.45.0 (2025-07-18 Ubuntu 2.45.0-1ubuntu0.3)", "2.45.0"),
        ("GNU Make 4.3", "4.3"),
        ("uv 0.11.15 (x86_64-unknown-linux-gnu)", "0.11.15"),
        ("2.1.211 (Claude Code)", "2.1.211"),
        ("ostler 0.1.0", "0.1.0"),
        ("go version go1.24.4 linux/amd64", "1.24.4"),
    ],
)
def test_version_regex_handles_real_world_shapes(line, expected):
    """Every one of these is a real `--version` line captured from this machine."""
    assert rq._VERSION_RE.search(line).group(1) == expected


def test_cmd_version_compared(monkeypatch):
    monkeypatch.setattr(rq.shutil, "which", lambda c: "/usr/bin/git")
    monkeypatch.setattr(rq, "_probe_cmd_version", lambda c: "2.43.0")
    assert rq.check_requirements([_req(cmd="git", version=">=2.30")], "wf") == []
    problems = rq.check_requirements([_req(cmd="git", version=">=99.0")], "wf")
    assert "2.43.0" in problems[0]


def test_unreadable_version_is_not_a_failure(monkeypatch):
    """A tool that's present but won't report a version is unverifiable, not absent.

    Blocking here would strand a workflow on a tool that is in fact installed.
    """
    monkeypatch.setattr(rq.shutil, "which", lambda c: "/usr/bin/weird")
    monkeypatch.setattr(rq, "_probe_cmd_version", lambda c: None)
    assert rq.check_requirements([_req(cmd="weird", version=">=1.0")], "wf") == []


def test_probe_survives_a_tool_that_rejects_version_flag(monkeypatch):
    """`go --version` exits non-zero; the probe must return None, not raise."""

    class Proc:
        stdout = ""
        stderr = "flag provided but not defined: -version"

    monkeypatch.setattr(rq.subprocess, "run", lambda *a, **k: Proc())
    assert rq._probe_cmd_version("go") is None


def test_probe_survives_oserror(monkeypatch):
    def boom(*a, **k):
        raise OSError("exec format error")

    monkeypatch.setattr(rq.subprocess, "run", boom)
    assert rq._probe_cmd_version("broken") is None


# --- optional ----------------------------------------------------------------


def test_optional_missing_tool_never_blocks(monkeypatch):
    """groom is a silent no-op when absent; hard-failing on it would break coder."""
    monkeypatch.setattr(rq.shutil, "which", lambda c: None)
    assert rq.check_requirements([_req(cmd="groom", optional=True)], "wf") == []


def test_optional_does_not_mask_a_hard_requirement(monkeypatch):
    monkeypatch.setattr(rq.shutil, "which", lambda c: None)
    problems = rq.check_requirements(
        [_req(cmd="groom", optional=True), _req(cmd="git")], "wf"
    )
    assert problems == ["git is not on PATH"]


# --- loader wiring -----------------------------------------------------------


_WF = """
name: demo
start: only
requires:
  - dist: ostler
    version: ">=0.1.0"
  - cmd: git
  - cmd: groom
    optional: true
env:
  FOO: bar
nodes:
  - id: only
    type: terminal
"""


def test_loader_shapes_requires_and_env(tmp_path):
    """_shape_graph builds an explicit dict, so an unshaped key is silently dropped.

    env: was dropped exactly this way before requires: landed — assert both survive.
    """
    p = tmp_path / "workflow.yaml"
    p.write_text(_WF)
    graph = load_workflow(p)

    assert [r.name for r in graph.requires] == ["ostler", "git", "groom"]
    assert graph.requires[0].dist == "ostler"
    assert graph.requires[0].version == ">=0.1.0"
    assert graph.requires[2].optional is True
    assert graph.env == {"FOO": "bar"}


def test_workflow_without_requires_is_unaffected(tmp_path):
    p = tmp_path / "workflow.yaml"
    p.write_text("name: bare\nstart: only\nnodes:\n  - id: only\n    type: terminal\n")
    graph = load_workflow(p)
    assert graph.requires == []
    assert rq.check_requirements(graph.requires, graph.name) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
