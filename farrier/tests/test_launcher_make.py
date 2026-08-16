"""The generated launcher, driven by real `make`.

Asserting on the rendered string proves the text; it does not prove the Makefile
parses, that `$(eval)` produces the targets it is supposed to, or that a workflow
nobody installed fails cleanly. Those are the behaviours the launcher exists for, so
they are checked by running `make` — with `-n`, so nothing is launched, and with
`FARRIER` pointed at a stub, so discovery is a fixture rather than this machine's
pipx.

    ./.venv/bin/python -m pytest tests/test_launcher_make.py
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from farrier.install import render_agents_mk

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make not installed")


@pytest.fixture
def launcher(tmp_path: Path) -> Path:
    """The rendered launcher, beside a `farrier` stub that reports a fixed set."""
    (tmp_path / "agents.mk").write_text(render_agents_mk(), encoding="utf-8")
    stub = tmp_path / "farrier-stub"
    stub.write_text(
        '#!/bin/sh\n'
        '[ "$1" = "workflows" ] && [ "$2" = "--names" ] && echo "coder okf-builder"\n'
        'exit 0\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return tmp_path


def _make(at: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", "-f", "agents.mk", *args, "FARRIER=./farrier-stub", "STABLEMATE_DIR=/stablemate"],
        cwd=at, capture_output=True, text=True, check=False,
    )


def test_the_generated_launcher_parses(launcher: Path):
    result = _make(launcher, "help")
    assert result.returncode == 0, result.stderr
    assert "agent-install" in result.stdout


def test_a_discovered_workflow_becomes_a_real_target(launcher: Path):
    result = _make(launcher, "-n", "agent-run-coder")
    assert result.returncode == 0, result.stderr
    recipe = result.stdout
    assert 'WORKFLOW="coder"' in recipe
    assert "/proc/sys/kernel/random/uuid" in recipe
    assert 'docker compose -p "$project"' in recipe
    assert "/stablemate/workhorse/compose.yaml" in recipe


def test_the_launch_creates_a_worktree_root_for_this_run_alone(launcher: Path):
    """Two launches must not land in one directory, so the run id is in the path —
    and the launcher, not the container, is what creates it (the container cannot
    make a host directory that is not already bound)."""
    result = _make(launcher, "-n", "agent-run-coder", "AGENT_REPO=/repos/acme")
    assert result.returncode == 0, result.stderr
    recipe = result.stdout
    assert 'worktree_root="/repos/acme/.agents/worktrees/$run_id"' in recipe
    assert 'mkdir -p "$worktree_root"' in recipe
    assert "AGENT_SOURCE_MODE=worktree" in recipe
    # The repo is bound at its own path; the run works in its own tree beneath it.
    assert 'AGENT_REPO_HOST_DIR="/repos/acme"' in recipe
    assert 'AGENT_REPO_DIR="$worktree_root/$repo_name"' in recipe


def test_a_hyphenated_workflow_name_survives_the_eval(launcher: Path):
    """`$(eval)` re-parses its argument as makefile text, which is exactly where a
    name with a hyphen or an unlucky character would come apart."""
    result = _make(launcher, "-n", "agent-run-okf-builder")
    assert result.returncode == 0, result.stderr
    assert 'WORKFLOW="okf-builder"' in result.stdout


def test_a_workflow_nobody_installed_fails_instead_of_launching_nothing(launcher: Path):
    """The reason these are generated targets rather than one `agent-run-%` pattern
    rule: a pattern rule matches anything and would happily launch a container for a
    workflow that does not exist."""
    result = _make(launcher, "-n", "agent-run-typo")
    assert result.returncode != 0
    assert "No rule to make target" in result.stderr


def test_an_unrelated_target_never_pays_for_discovery(launcher: Path):
    """Discovery shells out to pipx, and this file is included by the repo's root
    Makefile — so every `make <anything>` would pay for it if it were unconditional."""
    result = subprocess.run(
        ["make", "-f", "agents.mk", "help", "FARRIER=/nonexistent-binary"],
        cwd=launcher, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "agent-install" in result.stdout


def test_a_profile_reaches_the_container_with_a_config_to_look_it_up_in(launcher: Path):
    """A profile is a name; without the file it names it resolves to nothing and the
    run takes the harness defaults instead. So the launch stages the config too, and
    hands the container the pair."""
    result = _make(launcher, "-n", "agent-run-coder", "PROFILE=cheap",
                   "AGENT_REPO=/repos/acme")
    assert result.returncode == 0, result.stderr
    recipe = result.stdout
    assert 'AGENT_PROFILE="cheap"' in recipe
    # A copy, not the operator's own file: the config is re-read every turn, so a live
    # bind would let an edit move the models of every run already going.
    assert 'install -m 644 "$config_src" "$run_config"' in recipe
    assert 'run_config="$worktree_root/stablemate-config.toml"' in recipe
    # Bound at its own path, so one string means the same file on both sides.
    assert 'AGENT_CONFIG_FILE="$run_config"' in recipe
    assert 'AGENT_CONFIG="$run_config"' in recipe


def test_a_launch_that_names_no_profile_selects_nothing(launcher: Path):
    """The behavior every run had before profiles existed: models resolve from the
    config's top-level tables, and an empty AGENT_PROFILE adds no flag."""
    result = _make(launcher, "-n", "agent-run-coder")
    assert result.returncode == 0, result.stderr
    assert 'AGENT_PROFILE=""' in result.stdout


def test_a_config_that_cannot_be_read_stops_the_launch(launcher: Path):
    """Falling back to the machine's config would run a CI or benchmark launch on
    models nobody chose — and report success."""
    result = _make(launcher, "-n", "agent-run-coder", "CONFIG=/nope/config.toml")
    assert result.returncode == 0, result.stderr
    assert "is not readable" in result.stdout


def test_an_operating_target_without_RUN_says_which_one_to_pass(launcher: Path):
    for target in ("agent-logs", "agent-stop", "agent-clean"):
        result = _make(launcher, target)
        assert result.returncode != 0, target
        assert "set RUN=" in result.stdout + result.stderr, target
