"""Tests for reconcile-artifacts.py — the write-time scope-drop gate (OKF model).

Builds a real git repo, commits a baseline ``epic.md`` whose ``## Seeds`` / ``## Stories``
subsections are the IDed entities, mutates the working-tree ``epic.md``, and asserts the gate
flags subsection ids that were committed but silently removed (and only those). This script reads
``epic.md`` directly (no ostler) and compares parsed ``### <id>`` titles vs the git baseline.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "reconcile-artifacts.py"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _epic_md(seeds: list[str], stories: list[str]) -> str:
    parts = ["---", "type: epic", "id: E-e1", "title: e1", "status: in_progress", "---", "",
             "# e1", "", "## Seeds", ""]
    for s in seeds:
        parts += [f"### {s}", "", "- status: researched", f"- sourceBullet: {s}", "", f"Seed {s}.", ""]
    parts += ["## Stories", ""]
    for sl in stories:
        parts += [f"### {sl}", "", f"- title: {sl}", f"- id: S-{sl}", "- covers: (none)",
                  "- depends on: (none)", ""]
    return "\n".join(parts) + "\n"


def _write_epic(repo: Path, seeds: list[str], stories: list[str]) -> None:
    epic = repo / "docs" / "epics" / "e1"
    epic.mkdir(parents=True, exist_ok=True)
    (epic / "epic.md").write_text(_epic_md(seeds, stories), encoding="utf-8")


def _init_repo(repo: Path, seeds: list[str], stories: list[str]) -> None:
    _write_epic(repo, seeds, stories)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "baseline")


def _run(repo: Path, *args: str) -> dict:
    env = dict(os.environ, AGENT_REPO_DIR=str(repo))
    proc = subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_no_drops_passes(tmp_path):
    _init_repo(tmp_path, ["s1", "s2"], ["a"])
    out = _run(tmp_path)  # working tree == baseline
    assert out["reconcile_ok"] == "yes", out["reconcile_errors"]


def test_additions_do_not_block(tmp_path):
    _init_repo(tmp_path, ["s1"], ["a"])
    _write_epic(tmp_path, ["s1", "s2", "s3"], ["a", "b"])  # only added
    out = _run(tmp_path)
    assert out["reconcile_ok"] == "yes", out["reconcile_errors"]


def test_silent_seed_drop_blocks(tmp_path):
    _init_repo(tmp_path, ["s1", "s2"], ["a"])
    _write_epic(tmp_path, ["s1"], ["a"])  # seed s2 silently removed
    out = _run(tmp_path)
    assert out["reconcile_ok"] == "no"
    assert "dropped-seed" in out["reconcile_errors"]
    assert "s2" in out["reconcile_errors"]


def test_silent_story_drop_blocks(tmp_path):
    _init_repo(tmp_path, ["s1"], ["a", "b"])
    _write_epic(tmp_path, ["s1"], ["a"])  # story b removed
    out = _run(tmp_path)
    assert out["reconcile_ok"] == "no"
    assert "dropped-story" in out["reconcile_errors"]
    assert "b" in out["reconcile_errors"]


def test_skip_when_not_git(tmp_path):
    _write_epic(tmp_path, ["s1"], ["a"])  # no git init
    out = _run(tmp_path)
    assert out["reconcile_ok"] == "skip"
