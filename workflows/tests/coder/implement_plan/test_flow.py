"""End-to-end state-machine tests for the implement-plan flow."""
from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows.coder.implement_plan.flow import ImplementPlan
from coder.implement_plan._support import (
    _Agent,
    _command,
    _decomposition,
    _issue,
    _review,
    _task,
)

def test_dependent_packets_become_separate_verified_remote_commits(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan = tmp_path / "private-plan.md"
    plan.write_text("# Build two ordered pieces\n", encoding="utf-8")
    first = _task("first-piece", "src/first.txt")
    second = _task("second-piece", "src/second.txt", depends_on=["first-piece"])
    agent = _Agent(
        repo,
        _decomposition(second, first),
        edits={
            "first-piece": {"src/first.txt": "first-piece\n"},
            "second-piece": {"src/second.txt": "second-piece\n"},
        },
    )
    run_env = env()

    result = drive_flow(
        ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), run_env, agent
    )

    assert result.status == "complete"
    assert agent.calls == [
        "decompose-implementation-plan",
        "implement-plan-task-tests",
        "implement-plan-task-code",
        "implement-plan-task-tests",
        "implement-plan-task-code",
        "review-plan-implementation",
    ]
    subjects = git(repo, "log", "--format=%s", "--reverse").stdout.splitlines()
    assert subjects[-2:] == [
        "feat: implement first piece",
        "feat: implement second piece",
    ]
    assert git(repo, "rev-parse", "HEAD").stdout == git(origin, "rev-parse", "main").stdout
    worklist = json.loads(
        (run_env.writer.run_dir / "implement-plan" / "worklist.json").read_text()
    )
    assert [item["status"] for item in worklist["tasks"]] == ["done", "done"]
    review_worklist = json.loads(
        (run_env.writer.run_dir / "implement-plan" / "review-worklist.json").read_text()
    )
    assert review_worklist["status"] == "approved"
    assert review_worklist["issues"] == []


def test_failed_packet_gate_gets_one_repair_turn(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text("# Repair\n", encoding="utf-8")
    task = _task(
        "repair-me",
        "src/value.txt",
        verification=[
            _command("from pathlib import Path; assert Path('src/value.txt').read_text() == 'fixed\\n'")
        ],
    )
    agent = _Agent(
        repo,
        _decomposition(task),
        edits={"repair-me": {"src/value.txt": "broken\n"}},
        repair_edits={"repair-me": {"src/value.txt": "fixed\n"}},
    )

    result = drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)

    assert result.status == "complete"
    assert agent.count("repair-plan-task") == 1


def test_planning_turn_may_not_edit_the_repository(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text("# Plan only\n", encoding="utf-8")
    task = _task("later", "src/later.txt")
    agent = _Agent(
        repo,
        _decomposition(task),
        planning_edits={"src/planning-leak.txt": "no\n"},
    )

    with pytest.raises(WorkflowFailed, match="expected a clean worktree"):
        drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)


def test_implementation_turn_may_not_commit(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text("# No agent commit\n", encoding="utf-8")
    task = _task("owned", "src/owned.txt")
    agent = _Agent(
        repo,
        _decomposition(task),
        edits={"owned": {"src/owned.txt": "owned\n"}},
        commit_on_task="owned",
    )

    with pytest.raises(WorkflowFailed, match="agent turn moved HEAD"):
        drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)


def test_an_edit_to_a_file_no_packet_owns_widens_the_packet(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """An *existing* file that no packet declares is not a collision, so it is adopted.

    The check exists to keep two packets off the same file. A path nobody claims — the
    shared `conftest.py` a packet's own tests are built on — puts no one's work at risk,
    and failing the turn for it is unrepairable: reverting removes what the tests need.
    Trespass into a packet that is already published is still refused, at
    `extend_task_paths`.
    """
    plan = tmp_path / "plan.md"
    plan.write_text("# Scoped edit\n", encoding="utf-8")
    task = _task("scoped", "src/owned.txt")
    agent = _Agent(
        repo,
        _decomposition(task),
        edits={"scoped": {"src/owned.txt": "owned\n", "README.md": "no\n"}},
    )

    result = drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)

    assert result.status == "complete"
    assert (repo / "README.md").read_text(encoding="utf-8") == "no\n"


def test_new_file_the_packet_did_not_declare_is_adopted_and_committed(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The planning turn cannot foresee every file; a new one belongs to nobody else.

    Without this the tests-first turn kills the run whenever the packet's declared
    paths miss the home the repository's layout dictates for its test file.
    """
    plan = tmp_path / "plan.md"
    plan.write_text("# Undeclared companion file\n", encoding="utf-8")
    task = _task("declared", "src/owned.txt")
    agent = _Agent(
        repo,
        _decomposition(task),
        edits={"declared": {"src/owned.txt": "declared\n", "tests/test_owned.py": "x = 1\n"}},
    )

    result = drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)

    assert result.status == "complete"
    committed = git(repo, "show", "--name-only", "--format=", "HEAD").stdout.split()
    assert sorted(committed) == ["src/owned.txt", "tests/test_owned.py"]
    assert git(repo, "status", "--porcelain").stdout == ""


def test_blocked_agent_result_stops_before_verification(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text("# Blocked\n", encoding="utf-8")
    task = _task("blocked", "src/value.txt")
    agent = _Agent(
        repo,
        _decomposition(task),
        edits={"blocked": {"src/value.txt": "partial\n"}},
        blocked_on_task="blocked",
    )

    with pytest.raises(WorkflowFailed, match="implementation blocked"):
        drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)


def _commit_fixture_files(
    repo: Path,
    git: Callable[..., subprocess.CompletedProcess],
    files: dict[str, str],
) -> None:
    """Land gate fixtures (agents.yml, test scripts) in the base commit and at origin."""
    for relative, content in files.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    git(repo, "add", *files)
    git(repo, "commit", "-qm", "chore: add red-gate fixtures")
    git(repo, "push", "-q", "origin", "main")


def test_red_tests_turn_passes_the_gate_once(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text("# TDD packet\n", encoding="utf-8")
    _commit_fixture_files(
        repo,
        git,
        {
            "agents.yml": f"test:\n  {repo.name}: sh tests.sh\n",
            # Named the way a real suite names its failing file: attribution is what
            # separates the packet's own red from a repository already failing elsewhere.
            "tests.sh": "test -f src/value.txt || { echo 'FAIL tests/test_value.py'; exit 1; }\n",
        },
    )
    task = _task("value", "src/value.txt")
    task["paths"].append("tests/test_value.py")
    agent = _Agent(
        repo,
        _decomposition(task),
        test_edits={"value": {"tests/test_value.py": "def test_value(): assert False\n"}},
        edits={"value": {"src/value.txt": "value\n"}},
    )
    run_env = env()

    result = drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), run_env, agent)

    assert result.status == "complete"
    assert agent.count("implement-plan-task-tests") == 1
    assert agent.count("implement-plan-task-code") == 1
    code_args = agent.args_for("implement-plan-task-code")[0]
    assert code_args["red_status"] == "red"
    log = run_env.writer.run_dir / "implement-plan" / "red-gate-value.log"
    assert log.is_file()
    assert code_args["red_log_path"] == str(log)


def test_a_suite_that_collected_the_packet_tests_green_still_owes_a_rework(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A repository already failing elsewhere cannot certify the packet's tests as red.

    Here the suite did reach them and they passed, so the exit code is somebody else's and
    the scenarios exercise nothing missing. That is a rejected verdict like any other: the
    tests turn gets its bounded reworks to make them actually fail, and only past the bound
    does the packet proceed — with the code turn told the gate observed nothing and that it
    must run the packet's own tests itself.
    """
    plan = tmp_path / "plan.md"
    plan.write_text("# Unattributable red\n", encoding="utf-8")
    _commit_fixture_files(
        repo,
        git,
        {
            "agents.yml": f"test:\n  {repo.name}: sh tests.sh\n",
            "tests.sh": (
                "echo 'tests/test_value.py .'; "
                "echo 'FAILED other_package/test_other.py::test_x'; exit 1\n"
            ),
        },
    )
    task = _task("value", "src/value.txt")
    task["paths"].append("tests/test_value.py")
    agent = _Agent(
        repo,
        _decomposition(task),
        test_edits={"value": {"tests/test_value.py": "def test_value(): assert False\n"}},
        edits={"value": {"src/value.txt": "value\n"}},
    )

    result = drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)

    assert result.status == "complete"
    assert agent.count("implement-plan-task-tests") == 1 + ImplementPlan.MAX_TESTS_REWORKS
    feedback = [args["gate_feedback"] for args in agent.args_for("implement-plan-task-tests")]
    assert all(entry.startswith("[unattributed_red]") for entry in feedback[1:])
    code_args = agent.args_for("implement-plan-task-code")[0]
    assert code_args["red_status"] == "unattributed_red"
    # Nothing was attributed, so the code turn is handed no contract to trust.
    assert code_args["red_failing_files"] == ""


def test_a_suite_that_stops_before_the_packet_tests_costs_no_rework(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A suite that halts upstream never reports on the packet's tests, so there is nothing
    to judge — and nothing a rework could do about it.

    The failure is in a package this layer did not write and its agent may not touch. The
    reworks the gate used to charge here were unwinnable by construction: three high-power
    turns per packet, ending in the same fail-open the engine reaches anyway, with the tests
    turn meanwhile pushed to narrow its own command until the foreign red attributed. The
    gate stands aside on the first pass instead, and still tells the code turn the red is
    unproven.
    """
    plan = tmp_path / "plan.md"
    plan.write_text("# Unreachable tests\n", encoding="utf-8")
    _commit_fixture_files(
        repo,
        git,
        {
            "agents.yml": f"test:\n  {repo.name}: sh tests.sh\n",
            "tests.sh": "echo 'FAILED other_package/test_other.py::test_x'; exit 1\n",
        },
    )
    task = _task("value", "src/value.txt")
    task["paths"].append("tests/test_value.py")
    agent = _Agent(
        repo,
        _decomposition(task),
        test_edits={"value": {"tests/test_value.py": "def test_value(): assert False\n"}},
        edits={"value": {"src/value.txt": "value\n"}},
    )

    result = drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)

    assert result.status == "complete"
    assert agent.count("implement-plan-task-tests") == 1
    code_args = agent.args_for("implement-plan-task-code")[0]
    assert code_args["red_status"] == "unreached"
    assert code_args["red_failing_files"] == ""


def test_all_green_tests_turn_gets_bounded_rework_then_fails_open(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text("# Green suite\n", encoding="utf-8")
    _commit_fixture_files(repo, git, {"agents.yml": f'test:\n  {repo.name}: "true"\n'})
    task = _task("value", "src/value.txt")
    task["paths"].append("tests/test_value.py")
    agent = _Agent(
        repo,
        _decomposition(task),
        test_edits={"value": {"tests/test_value.py": "def test_value(): assert True\n"}},
        edits={"value": {"src/value.txt": "value\n"}},
    )

    result = drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)

    assert result.status == "complete"
    assert agent.count("implement-plan-task-tests") == 1 + ImplementPlan.MAX_TESTS_REWORKS
    assert agent.count("implement-plan-task-code") == 1
    feedback = [args["gate_feedback"] for args in agent.args_for("implement-plan-task-tests")]
    assert feedback[0] == ""
    assert all(entry.startswith("[all_green]") for entry in feedback[1:])
    assert agent.args_for("implement-plan-task-code")[0]["red_status"] == "all_green"


def test_impure_tests_turn_is_reworked_even_without_a_test_command(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text("# Purity\n", encoding="utf-8")
    task = _task("value", "src/value.txt")
    task["paths"].extend(["tests/test_value.py", "src/stray.py"])
    agent = _Agent(
        repo,
        _decomposition(task),
        # `.py` outside the test signatures is production code; a `.txt` beside it would
        # be a fixture, which the tests turn is entitled to write.
        test_edits={
            "value": {
                "tests/test_value.py": "def test_value(): assert False\n",
                "src/stray.py": "STRAY = 1\n",
            }
        },
        edits={"value": {"src/value.txt": "value\n"}},
    )

    result = drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)

    assert result.status == "complete"
    assert agent.count("implement-plan-task-tests") == 1 + ImplementPlan.MAX_TESTS_REWORKS
    feedback = [args["gate_feedback"] for args in agent.args_for("implement-plan-task-tests")]
    assert "impure" in feedback[1]
    assert "src/stray.py" in feedback[1]


def test_regression_only_plan_keeps_the_single_implementation_turn(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text(
        "# Behavior-preserving refactor\n\nTest Scenarios: regression-only\n",
        encoding="utf-8",
    )
    task = _task("value", "src/value.txt")
    agent = _Agent(repo, _decomposition(task), edits={"value": {"src/value.txt": "value\n"}})

    result = drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)

    assert result.status == "complete"
    assert agent.count("implement-plan-task") == 1
    assert agent.count("implement-plan-task-tests") == 0
    assert agent.count("implement-plan-task-code") == 0


def test_review_issues_become_fixed_worklist_before_completion(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("# Implement and independently review\n", encoding="utf-8")
    task = _task("initial", "src/value.txt")
    issue = _issue("missing-edge", "src/value.txt", finding="The edge case is absent.")
    agent = _Agent(
        repo,
        _decomposition(task),
        edits={
            "initial": {"src/value.txt": "initial\n"},
            "review-1-missing-edge": {"src/value.txt": "fixed\n"},
        },
        reviews=[_review(issue), _review(summary="all blocking issues resolved")],
    )
    run_env = env()

    result = drive_flow(
        ImplementPlan(plan_path=str(plan_path), repo_dir=str(repo)), run_env, agent
    )

    assert result.status == "complete"
    assert result.review_issue_count == 1
    assert result.review_passes == 2
    assert agent.calls == [
        "decompose-implementation-plan",
        "implement-plan-task-tests",
        "implement-plan-task-code",
        "review-plan-implementation",
        "fix-plan-review-issue",
        "review-plan-implementation",
    ]
    assert git(origin, "show", "main:src/value.txt").stdout == "fixed\n"
    subjects = git(repo, "log", "--format=%s", "--reverse").stdout.splitlines()
    assert subjects[-2:] == [
        "feat: implement initial",
        "fix: implement missing edge",
    ]
    review_worklist = json.loads(
        (run_env.writer.run_dir / "implement-plan" / "review-worklist.json").read_text()
    )
    assert review_worklist["status"] == "approved"
    assert [item["id"] for item in review_worklist["resolved_issues"]] == [
        "review-1-missing-edge"
    ]
    completion = json.loads(
        (run_env.writer.run_dir / "implement-plan" / "completion.json").read_text()
    )
    assert completion["review"]["fixed_issue_count"] == 1
    assert completion["review"]["resolved_issues"][0]["id"] == "review-1-missing-edge"


def test_failed_post_review_gate_leaves_no_approved_review_worklist(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("# Approval is not authority\n", encoding="utf-8")
    marker = tmp_path / "final-gate-ran"
    task = _task("initial", "src/value.txt")
    agent = _Agent(
        repo,
        _decomposition(
            task,
            final=[
                _command(
                    "from pathlib import Path; "
                    f"marker = Path({str(marker)!r}); "
                    "assert not marker.exists(); "
                    "marker.write_text('ran')"
                )
            ],
        ),
        edits={"initial": {"src/value.txt": "initial\n"}},
        reviews=[_review(summary="looks complete to me")],
    )
    run_env = env()

    with pytest.raises(WorkflowFailed, match="final plan verification failed"):
        drive_flow(ImplementPlan(plan_path=str(plan_path), repo_dir=str(repo)), run_env, agent)

    review_worklist = run_env.writer.run_dir / "implement-plan" / "review-worklist.json"
    assert not review_worklist.exists()
    assert not (run_env.writer.run_dir / "implement-plan" / "completion.json").exists()


def test_review_fix_may_not_edit_outside_issue_ownership(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("# Scoped review fix\n", encoding="utf-8")
    task = _task("initial", "src/value.txt")
    issue = _issue("scoped", "src/value.txt")
    agent = _Agent(
        repo,
        _decomposition(task),
        edits={
            "initial": {"src/value.txt": "initial\n"},
            # A tracked file: the collision case ownership exists to refuse. A file the
            # fix turn creates belonged to nobody, and is adopted instead.
            "review-1-scoped": {"README.md": "not owned\n"},
        },
        reviews=[_review(issue)],
    )

    with pytest.raises(WorkflowFailed, match="does not own"):
        drive_flow(ImplementPlan(plan_path=str(plan_path), repo_dir=str(repo)), env(), agent)


def test_review_must_converge_before_claiming_completion(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("# Bounded review\n", encoding="utf-8")
    task = _task("initial", "src/value.txt")
    reviews = [
        _review(_issue(f"issue-{cycle}", "src/value.txt"))
        for cycle in range(1, ImplementPlan.MAX_REVIEW_FIX_CYCLES + 2)
    ]
    edits = {"initial": {"src/value.txt": "initial\n"}}
    edits.update(
        {
            f"review-{cycle}-issue-{cycle}": {"src/value.txt": f"fixed {cycle}\n"}
            for cycle in range(1, ImplementPlan.MAX_REVIEW_FIX_CYCLES + 1)
        }
    )
    agent = _Agent(repo, _decomposition(task), edits=edits, reviews=reviews)

    with pytest.raises(WorkflowFailed, match="did not converge"):
        run_env = env()
        drive_flow(ImplementPlan(plan_path=str(plan_path), repo_dir=str(repo)), run_env, agent)

    review_worklist = json.loads(
        (run_env.writer.run_dir / "implement-plan" / "review-worklist.json").read_text()
    )
    assert review_worklist["status"] == "blocked"
    assert review_worklist["cycle"] == ImplementPlan.MAX_REVIEW_FIX_CYCLES + 1
    assert review_worklist["issues"][0]["id"].endswith("issue-4")


def test_the_aggregate_gate_gets_a_repair_turn_instead_of_ending_the_run(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A defect only the aggregate gate can see is repaired, not fatal.

    The packet gate passes and the plan-wide one does not, which is the shape of every
    defect that lives between packets rather than inside one. Before, that finding
    arrived after the last packet had been implemented, verified and committed, and
    threw all of it away.
    """
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("# Aggregate\n", encoding="utf-8")
    task = _task("only", "src/value.txt")
    agent = _Agent(
        repo,
        _decomposition(
            task,
            final=[_command("from pathlib import Path; assert Path('shared.txt').is_file()")],
        ),
        edits={"only": {"src/value.txt": "value\n"}},
        repair_edits={"only": {"src/value.txt": "value\n", "shared.txt": "shared\n"}},
    )

    result = drive_flow(ImplementPlan(plan_path=str(plan_path), repo_dir=str(repo)), env(), agent)

    assert result.status == "complete"
    assert agent.count("repair-plan-task") == 1
    assert (repo / "shared.txt").is_file()


def test_the_aggregate_gate_still_ends_the_run_once_repairs_are_spent(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The second chance is bounded — a repair turn that never fixes it still stops."""
    plan_path = tmp_path / "plan.md"
    plan_path.write_text("# Aggregate\n", encoding="utf-8")
    task = _task("only", "src/value.txt")
    agent = _Agent(
        repo,
        _decomposition(
            task,
            final=[_command("from pathlib import Path; assert Path('never.txt').is_file()")],
        ),
        edits={"only": {"src/value.txt": "value\n"}},
        repair_edits={"only": {"src/value.txt": "value\n"}},
    )

    with pytest.raises(WorkflowFailed, match="final plan verification failed"):
        drive_flow(ImplementPlan(plan_path=str(plan_path), repo_dir=str(repo)), env(), agent)
