"""The deterministic gate layer: what a service declares is what runs.

The rule these tests hold down is invariant 1 — the workflow assumes nothing about where it
is deployed. Every command that runs after an implement turn comes out of the repo's own
`agents.yml`, so a stack this package has never heard of gets gates the moment it writes
them down, and a service that declares nothing is skipped rather than failed on a command
somebody guessed.

Nothing is mocked. `run_gate` really shells out, so a `clean` here is a process that really
exited 0 and a `dirty` is one that really did not.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
from workhorse_workflows.coder.shared.dev import (
    GATE_ORDER,
    declared_gates,
    gate_command,
    run_gate,
    service_declaration,
)
from workhorse_workflows.coder.shared.failure import from_gate

LOG = logging.getLogger("test")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """An orchestrating repo with one service directory under it."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "api-service").mkdir()
    return tmp_path


def _agents(repo: Path, body: str) -> None:
    (repo / "agents.yml").write_text(body, encoding="utf-8")


def _call(node, **kwargs):
    """Run a node body directly — `@blueprint.node` registers it and returns it unchanged."""
    return node(LOG, **kwargs)


# ------------------------------------------------------------------ resolution


def test_the_services_block_names_the_command_for_each_gate(repo: Path) -> None:
    """The declared command is used verbatim — no shape is imposed on it."""
    _agents(repo, "services:\n  go: {lint: 'golangci-lint run', test: 'go test ./...'}\n")
    cwd = repo / "api-service"

    assert gate_command("lint", "api", "go", cwd, str(repo)) == "golangci-lint run"
    assert gate_command("test", "api", "go", cwd, str(repo)) == "go test ./..."


def test_a_service_name_beats_its_type(repo: Path) -> None:
    """Two services of one type may run different commands, and the narrower key says so."""
    _agents(
        repo,
        "services:\n"
        "  go: {test: 'go test ./...'}\n"
        "  api: {test: 'go test -tags integration ./...'}\n",
    )

    assert service_declaration("api", "go", str(repo))["test"] == (
        "go test -tags integration ./..."
    )
    assert service_declaration("worker", "go", str(repo))["test"] == "go test ./..."


def test_an_undeclared_gate_resolves_to_no_command(repo: Path) -> None:
    """The opt-in half: nothing declared, nothing guessed, nothing run."""
    _agents(repo, "services:\n  go: {lint: 'golangci-lint run'}\n")

    assert gate_command("test", "api", "go", repo / "api-service", str(repo)) == ""


def test_the_legacy_lint_map_still_wins_over_nothing(repo: Path) -> None:
    """A repo that wrote the old map is already running that gate; moving the key would
    silently turn it off."""
    _agents(repo, "lint:\n  api: sh lint.sh\n")

    assert gate_command("lint", "api", "go", repo / "api-service", str(repo)) == "sh lint.sh"


def test_a_makefile_target_is_the_last_resort(repo: Path) -> None:
    """`make <gate>` is convention, not assumption — it applies only where the service's
    own Makefile actually defines the target."""
    cwd = repo / "api-service"
    (cwd / "Makefile").write_text("lint:\n\t@true\n", encoding="utf-8")

    assert gate_command("lint", "api", "go", cwd, str(repo)) == "make lint"
    assert gate_command("test", "api", "go", cwd, str(repo)) == ""


# ----------------------------------------------------------------- running one


def test_a_passing_command_is_clean(repo: Path) -> None:
    _agents(repo, "services:\n  api: {lint: 'true'}\n")

    outcome = _call(run_gate, cwd=str(repo / "api-service"), service="api", gate="lint",
                    repo_dir=str(repo))

    assert (outcome.gate, outcome.status, outcome.command) == ("lint", "clean", "true")


def test_a_failing_command_is_dirty_and_carries_its_output(repo: Path) -> None:
    _agents(repo, "services:\n  api: {test: 'echo boom >&2; exit 1'}\n")

    outcome = _call(run_gate, cwd=str(repo / "api-service"), service="api", gate="test",
                    repo_dir=str(repo))

    assert outcome.status == "dirty"
    assert "boom" in outcome.output


def test_an_undeclared_gate_is_skipped_not_failed(repo: Path) -> None:
    """A service adopts a gate by declaring it; one that has not is not thereby broken."""
    _agents(repo, "services: {}\n")

    outcome = _call(run_gate, cwd=str(repo / "api-service"), service="api", gate="test",
                    repo_dir=str(repo))

    assert outcome.status == "skipped"
    assert outcome.command == ""


def test_a_missing_cwd_is_skipped(repo: Path) -> None:
    outcome = _call(run_gate, cwd=str(repo / "nope"), service="api", gate="lint",
                    repo_dir=str(repo))

    assert outcome.status == "skipped"


# ------------------------------------------------------- what the turn is told


def test_declared_gates_renders_the_commands_that_will_run(repo: Path) -> None:
    """The implement turn is told what the machine will check, which is the fact the
    'run the tests — MANDATORY' prose was standing in for."""
    _agents(repo, "services:\n  api: {lint: 'golangci-lint run', test: 'go test ./...'}\n")

    gates = _call(declared_gates, cwd=str(repo / "api-service"), service="api",
                  repo_dir=str(repo))

    assert gates.gates == list(GATE_ORDER)
    assert "lint: `golangci-lint run`" in gates.text
    assert "test: `go test ./...`" in gates.text


def test_declared_gates_says_so_when_the_service_declares_none(repo: Path) -> None:
    """An honest 'nothing' beats an instruction to run a command that does not exist."""
    _agents(repo, "services: {}\n")

    gates = _call(declared_gates, cwd=str(repo / "api-service"), service="api",
                  repo_dir=str(repo))

    assert gates.gates == []
    assert gates.text == "(nothing declared)"


# ------------------------------------------------------------- the repair seam


def test_the_report_names_the_gate_that_went_red(repo: Path) -> None:
    """`FailureReport.source` is the gate's own name, so the fix-success rate is trackable
    per gate and a repair turn can say which one failed — including one this package has
    never heard of."""
    _agents(repo, "services:\n  api: {test: 'exit 1'}\n")
    outcome = _call(run_gate, cwd=str(repo / "api-service"), service="api", gate="test",
                    repo_dir=str(repo))

    report = from_gate(outcome, str(repo / "api-service"), 1)

    assert report.source == "test"
    assert report.command == "exit 1"
    assert report.lap == 1
