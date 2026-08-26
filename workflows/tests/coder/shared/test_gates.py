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
import subprocess
from pathlib import Path

import pytest
from workhorse_workflows.coder.shared.dev import (
    GATE_ORDER,
    changed_files,
    declared_gates,
    declared_markers,
    gate_command,
    run_gate,
    service_declaration,
    service_keys,
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


def test_the_dispatch_id_is_decomposed_into_the_keys_a_repo_actually_writes(
    repo: Path,
) -> None:
    """`<repo>::<path>` is the workflow's identifier; `api` is what the repo calls it.

    Nobody writes `bench::services/api` in their own `agents.yml`, so a lookup on the raw
    dispatch id found nothing, fell through to the Makefile convention, and ran a gate the
    service had explicitly replaced — the declaration silently doing nothing, which is the
    one failure mode a declarative block must not have.
    """
    _agents(
        repo,
        "services:\n"
        "  go: {test: 'go test ./...'}\n"
        "  api: {test: 'go test -tags integration ./...', lint: 'golangci-lint run'}\n",
    )

    for dispatch_id in ("acme::api", "acme::services/api"):
        declared = service_declaration(dispatch_id, "go", str(repo))
        assert declared["test"] == "go test -tags integration ./...", dispatch_id
        assert declared["lint"] == "golangci-lint run", dispatch_id

    assert service_keys("acme::services/api", "go") == [
        "acme::services/api",
        "services/api",
        "api",
        "go",
    ]
    # A layer the dispatch named without a path still resolves — on its type, as before.
    assert service_declaration("acme", "go", str(repo))["test"] == "go test ./..."


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


def test_the_planner_is_told_the_markers_this_workspace_declares(repo: Path) -> None:
    """Which files mark a service is the repo's answer too, not a list of four this
    package remembers — a repo whose services are marked some other way had to argue with
    that list, and one with a single layer was told about three it does not have."""
    _agents(repo, "workspace:\n  service_markers: [manifest.toml, service.json]\n")

    markers = _call(declared_markers, repo_dir=str(repo))

    assert "`manifest.toml`, `service.json`" in markers.text
    assert repo.name in markers.text


def test_a_workspace_that_declares_no_markers_says_nothing_rather_than_guessing(
    repo: Path,
) -> None:
    """The prompt reads an empty `text` as "go and look", which beats a confident list."""
    _agents(repo, "services:\n  api: {lint: 'true'}\n")

    assert _call(declared_markers, repo_dir=str(repo)).text == ""


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


# ------------------------------------------------------- where the gate runs


def test_a_services_gate_runs_in_the_service_directory_not_the_repo_root(
    repo: Path,
) -> None:
    """The defect this closes cost a benchmark story thirteen repair turns.

    The dispatch hands every state the repo checkout as `cwd`, because that is what an
    agent turn needs. A command declared under `services.api` is written the way `api`'s
    own Makefile writes it, and from the root it does not fail the story — it fails to
    start, and the repair loop is then asked to fix code over a harness error.
    """
    _agents(repo, "services:\n  api-service: {test: 'test -f here.marker'}\n")
    (repo / "api-service" / "here.marker").write_text("", encoding="utf-8")

    outcome = _call(
        run_gate,
        cwd=str(repo),
        service=f"{repo.name}::api-service",
        gate="test",
        repo_dir=str(repo),
    )

    assert outcome.status == "clean"


def test_a_repo_that_is_one_service_still_runs_its_gates_at_the_root(repo: Path) -> None:
    """`<repo>::`, `<repo>::.` and a path that is not there all mean "here"."""
    (repo / "root.marker").write_text("", encoding="utf-8")

    for service in (f"{repo.name}::", f"{repo.name}::.", f"{repo.name}::not-a-dir"):
        _agents(repo, f"services:\n  {service!r}: {{test: 'test -f root.marker'}}\n")
        outcome = _call(
            run_gate, cwd=str(repo), service=service, gate="test", repo_dir=str(repo)
        )
        assert outcome.status == "clean", service


def test_the_turn_is_told_which_directory_its_gates_run_in(repo: Path) -> None:
    """A turn told only the command runs it where it is standing, and watches it fail."""
    _agents(repo, "services:\n  api-service: {test: 'go test ./...'}\n")

    gates = _call(
        declared_gates,
        cwd=str(repo),
        service=f"{repo.name}::api-service",
        repo_dir=str(repo),
    )

    assert gates.text == "test: `go test ./...` (run in `api-service/`)"


def test_the_convention_looks_for_the_makefile_in_the_service_directory(
    repo: Path,
) -> None:
    """`make <gate>` is adopted by the service's Makefile, not by the repo's."""
    _agents(repo, "services: {}\n")
    (repo / "api-service" / "Makefile").write_text("test:\n\t@true\n", encoding="utf-8")

    gates = _call(
        declared_gates,
        cwd=str(repo),
        service=f"{repo.name}::api-service",
        repo_dir=str(repo),
    )

    assert gates.commands == ["make test"]


# --------------------------------------------------- what a recycled turn is re-seeded with


def test_a_new_file_is_in_the_diff_the_gates_read(tmp_path: Path) -> None:
    """A test file this story just added is *new*, and a new file is in no `git diff`.

    Nothing in the dev lane commits before the gates run, so `git diff --name-only HEAD`
    sees modifications and nothing else. `changed_files` is what re-seeds a recycled
    conversation, and a re-seed missing the file the turn had just written told it its own
    work did not exist.
    """
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    (tmp_path / "handler.go").write_text("package api\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "i"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "handler.go").write_text("package api\n\nfunc H() {}\n", encoding="utf-8")
    (tmp_path / "handler_test.go").write_text("package api\n", encoding="utf-8")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "out.bin").write_text("junk", encoding="utf-8")

    paths = _call(changed_files, cwd=str(tmp_path)).paths

    assert "handler_test.go" in paths, "a new file is invisible to the next turn"
    assert "handler.go" in paths
    assert not any(p.startswith("build/") for p in paths), "ignored output is not a change"
