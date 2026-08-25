"""The two gates that need no command from the repo: the promise, and the tests.

Both read the turn's own account of what it did and compare it to what is on disk, which is
what makes goal setting worth an agent's tokens at all — a claim in a schema is falsifiable
where the same claim in prose is a pep talk.

Neither may invent an obligation the repo did not take on: a turn that promised nothing is
`skipped`, and a service with no `tdd:` key is too. And neither knows what a test file looks
like in any language (invariant 1) — `tdd_gate` only asserts that the paths the turn
reported are really in the diff.

Nothing is mocked: `check_promises` really shells out, so a `clean` is a process that really
exited 0.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest
from workhorse_workflows.coder.shared.dev import (
    changed_files,
    check_promises,
    tdd_gate,
    tdd_mode,
)
from workhorse_workflows.coder.shared.schemas import ImplResult

LOG = logging.getLogger("test")


@pytest.fixture
def service(tmp_path: Path) -> Path:
    """A repo with one service directory, the shape both nodes are handed a `cwd` from."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "api-service").mkdir()
    return tmp_path


def _agents(repo: Path, body: str) -> None:
    (repo / "agents.yml").write_text(body, encoding="utf-8")


def _call(node, **kwargs):
    """Run a node body directly — `@blueprint.node` registers it and returns it unchanged."""
    return node(LOG, **kwargs)


# ------------------------------------------------------------------- promises


def test_a_turn_that_promised_nothing_forfeits_the_check(service: Path) -> None:
    outcome = _call(check_promises, cwd=str(service / "api-service"))

    assert outcome.status == "skipped"
    assert outcome.gate == "goal"


def test_a_promised_command_that_is_green_clears_the_gate(service: Path) -> None:
    outcome = _call(
        check_promises, cwd=str(service / "api-service"), commands=["exit 0"]
    )

    assert outcome.status == "clean"


def test_a_promised_command_that_is_red_is_quoted_back_as_the_failure(service: Path) -> None:
    """The complaint names the promise, not just the exit code — it is the turn's own claim."""
    outcome = _call(
        check_promises,
        cwd=str(service / "api-service"),
        commands=["echo boom >&2; exit 3"],
    )

    assert outcome.status == "dirty"
    assert outcome.gate == "goal"
    assert "would be green" in outcome.output
    assert "boom" in outcome.output
    assert outcome.command == "echo boom >&2; exit 3"


def test_a_promised_server_is_never_run(service: Path) -> None:
    """A command that runs until stopped can never be green — it waits out the whole gate
    timeout and reads as a broken promise over healthy code. The gate refuses it up front
    instead; the promises that can terminate are still held."""
    outcome = _call(
        check_promises,
        cwd=str(service / "api-service"),
        commands=["cd api && go run ./cmd/server", "npm run dev", "tail -f log", "exit 0"],
    )

    assert outcome.status == "clean"


def test_a_turn_that_promised_only_servers_forfeits_the_check(service: Path) -> None:
    outcome = _call(
        check_promises,
        cwd=str(service / "api-service"),
        commands=["go run ./cmd/server &"],
    )

    assert outcome.status == "skipped"


def test_a_command_the_declared_gates_already_ran_is_not_run_twice(service: Path) -> None:
    """It was just proven clean. Re-running it costs the story a full test suite."""
    marker = service / "api-service" / "ran"
    command = f"touch {marker}; exit 1"

    outcome = _call(
        check_promises,
        cwd=str(service / "api-service"),
        commands=[command],
        already_run=[command],
    )

    assert outcome.status == "clean"
    assert not marker.exists()


def test_a_promised_file_in_the_diff_clears_the_gate(service: Path) -> None:
    outcome = _call(
        check_promises,
        cwd=str(service / "api-service"),
        files=["handler.go"],
        changed=["api-service/handler.go"],
    )

    assert outcome.status == "clean"


def test_a_promised_file_missing_from_the_diff_fails_the_gate(service: Path) -> None:
    outcome = _call(
        check_promises,
        cwd=str(service / "api-service"),
        files=["handler.go", "store.go"],
        changed=["api-service/handler.go"],
    )

    assert outcome.status == "dirty"
    assert "store.go" in outcome.output
    assert "handler.go" not in outcome.output


def test_path_matching_is_lenient_in_both_directions(service: Path) -> None:
    """A false accusation costs a whole repair lap, so the match forgives the prefix."""
    outcome = _call(
        check_promises,
        cwd=str(service / "api-service"),
        files=["./api-service/store/store.go"],
        changed=["store/store.go"],
    )

    assert outcome.status == "clean"


def test_a_command_that_cannot_launch_is_not_the_promise_gate_s_business(service: Path) -> None:
    """Adjudicating a missing tool belongs to the declared gates, which run first."""
    outcome = _call(
        check_promises,
        cwd=str(service / "api-service"),
        commands=["\0not-a-command"],
    )

    assert outcome.status == "clean"


# ------------------------------------------------------------------------ tdd


def test_a_service_with_no_tdd_key_is_skipped(service: Path) -> None:
    _agents(service, "services:\n  go: {test: 'go test ./...'}\n")

    outcome = _call(
        tdd_gate,
        cwd=str(service / "api-service"),
        service="api",
        service_type="go",
        repo_dir=str(service),
    )

    assert outcome.status == "skipped"
    assert tdd_mode("api", "go", str(service)) == "off"


def test_reported_tests_that_are_in_the_diff_clear_the_gate(service: Path) -> None:
    _agents(service, "services:\n  go: {tdd: required}\n")

    outcome = _call(
        tdd_gate,
        cwd=str(service / "api-service"),
        service="api",
        service_type="go",
        tests_added=["handler_test.go"],
        changed=["api-service/handler.go", "api-service/handler_test.go"],
        repo_dir=str(service),
    )

    assert outcome.status == "clean"


def test_a_required_service_with_no_test_fails_the_gate(service: Path) -> None:
    _agents(service, "services:\n  go: {tdd: required}\n")

    outcome = _call(
        tdd_gate,
        cwd=str(service / "api-service"),
        service="api",
        service_type="go",
        changed=["api-service/handler.go"],
        repo_dir=str(service),
    )

    assert outcome.status == "dirty"
    assert outcome.gate == "tdd"
    assert "fails without it" in outcome.output


def test_a_reported_test_the_diff_does_not_contain_fails_the_gate(service: Path) -> None:
    """The gate reads the diff, not the claim — naming a file you did not write is caught."""
    _agents(service, "services:\n  go: {tdd: required}\n")

    outcome = _call(
        tdd_gate,
        cwd=str(service / "api-service"),
        service="api",
        service_type="go",
        tests_added=["handler_test.go"],
        changed=["api-service/handler.go"],
        repo_dir=str(service),
    )

    assert outcome.status == "dirty"
    assert "handler_test.go" in outcome.output


def test_an_exemption_holds_only_for_a_type_with_nothing_to_test(service: Path) -> None:
    _agents(service, "services:\n  docs: {tdd: required}\n  go: {tdd: required}\n")

    exempt = _call(
        tdd_gate,
        cwd=str(service / "api-service"),
        service="handbook",
        service_type="docs",
        no_test_reason="prose only",
        repo_dir=str(service),
    )
    refused = _call(
        tdd_gate,
        cwd=str(service / "api-service"),
        service="api",
        service_type="go",
        no_test_reason="prose only",
        repo_dir=str(service),
    )

    assert exempt.status == "clean"
    assert refused.status == "dirty"
    assert "prose only" in refused.output


def test_encouraged_logs_the_miss_and_lets_the_story_through(
    service: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """`encouraged` is what a repo says while its harness is still being built."""
    _agents(service, "services:\n  go: {tdd: encouraged}\n")

    with caplog.at_level(logging.WARNING):
        outcome = _call(
            tdd_gate,
            cwd=str(service / "api-service"),
            service="api",
            service_type="go",
            changed=["api-service/handler.go"],
            repo_dir=str(service),
        )

    assert outcome.status == "clean"
    assert "encouraged" in caplog.text


def test_a_service_name_key_beats_its_type_for_the_tdd_mode(service: Path) -> None:
    _agents(service, "services:\n  go: {tdd: off}\n  api: {tdd: required}\n")

    assert tdd_mode("api", "go", str(service)) == "required"


# --------------------------------------------------------------- what the gates read


def test_a_new_file_is_in_the_diff_the_gates_read(tmp_path: Path) -> None:
    """A test file a TDD lap adds is *new*, and a new file is in no `git diff`.

    Nothing in the dev lane commits before the gates run, so `git diff --name-only HEAD`
    sees modifications and nothing else. Both gates above check a claim against this list,
    which made the honest answer "I added `handler_test.go`" indistinguishable from a
    fabrication: the lap repaired the right thing, the gate stayed red, and the story
    escalated to a human with nothing for them to decide.
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

    assert "handler_test.go" in paths, "a new test file is invisible to the tdd gate"
    assert "handler.go" in paths
    assert not any(p.startswith("build/") for p in paths), "ignored output is not a change"


# ------------------------------------------------- the shapes a real turn actually returns


def test_exit_conditions_grouped_per_criterion_are_merged_not_rejected() -> None:
    """A turn satisfying four acceptance criteria groups its promise by criterion.

    That is the better-organised answer and it is exactly as checkable, since the gate runs
    every command and looks for every file whichever criterion claimed it. A benchmark run
    lost a completed implement turn — all gates already green — to this shape being a list
    where the schema said object.
    """
    result = ImplResult.model_validate(
        {
            "status": "done",
            "exit_conditions": [
                {
                    "criteria": "Service.List returns expenses newest-first",
                    "commands": ["go test ./internal/core/..."],
                    "files": ["api/internal/core/services/expense/service.go"],
                },
                {
                    "criteria": "the route is generated and wired",
                    "commands": ["make generate", "go build ./..."],
                    "files": ["api/pkg/api/openapi.yaml"],
                },
            ],
        }
    )

    assert result.exit_conditions.commands == [
        "go test ./internal/core/...",
        "make generate",
        "go build ./...",
    ]
    assert len(result.exit_conditions.files) == 2
    assert result.exit_conditions.criteria[0].startswith("Service.List")


def test_a_test_named_with_its_file_in_parentheses_still_matches_the_diff(
    service: Path,
) -> None:
    """`tests_added` naming the test and parenthesising its file is more informative.

    It is also what a real turn returned, and the gate read it as three files that do not
    exist — a repair lap billed against three tests that had been written.
    """
    _agents(service, "services:\n  go: {tdd: required}\n")

    outcome = _call(
        tdd_gate,
        cwd=str(service / "api-service"),
        service="api",
        service_type="go",
        tests_added=["Test_Service_List_ShouldHandleScenarios (internal/expense/service_test.go)"],
        changed=["api-service/internal/expense/service_test.go"],
        repo_dir=str(service),
    )

    assert outcome.status == "clean", outcome.output


def test_a_promise_written_from_the_repo_root_is_run_from_there(service: Path) -> None:
    """The turn and the gate do not share a working directory.

    Asked what will be green, a turn writes the command the way a person types it at the repo
    root. Run inside the service directory, `cd api-service && …` exits 2 every time, and no
    repair lap can fix a command that is already correct — the loop spends its whole budget
    and hands a human a story with nothing wrong with it.
    """
    outcome = _call(
        check_promises,
        cwd=str(service / "api-service"),
        commands=["cd api-service && true"],
        repo_dir=str(service),
    )

    assert outcome.status == "clean", outcome.output


def test_a_command_with_its_outcome_written_beside_it_is_still_run(service: Path) -> None:
    """A turn asked what will be green answers in the register it has used all turn.

    `cd api && make generate — pass` is an account, not a string a shell can run: the dash
    is an argument and the command exits non-zero forever. The code is finished, the
    command is right, and no repair lap can reach the defect — one benchmark run spent a
    lap per annotated command before its budget ran out.
    """
    outcome = _call(
        check_promises,
        cwd=str(service / "api-service"),
        commands=["true — pass, no output"],
        repo_dir=str(service),
    )

    assert outcome.status == "clean", outcome.output


def test_an_ascii_double_dash_is_left_alone(service: Path) -> None:
    """`--` is a flag prefix and an end-of-options marker; only the typographic dash is prose."""
    outcome = _call(
        check_promises,
        cwd=str(service / "api-service"),
        commands=["exit 3 -- pass"],
        repo_dir=str(service),
    )

    assert outcome.status == "dirty"
    assert outcome.command == "exit 3 -- pass"


def test_a_promise_green_in_neither_directory_is_still_dirty(service: Path) -> None:
    outcome = _call(
        check_promises,
        cwd=str(service / "api-service"),
        commands=["exit 3"],
        repo_dir=str(service),
    )

    assert outcome.status == "dirty"
    assert outcome.command == "exit 3"
