"""Plan schema, DAG, path, and final-gate validation tests."""
from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows.coder.implement_plan.flow import ImplementPlan
from workhorse_workflows.coder.implement_plan.execution import check_planning_turn
from workhorse_workflows.coder.implement_plan.inventory import (
    _safe_endpoint,
    prepare_plan,
    snapshot_plan,
)
from workhorse_workflows.coder.implement_plan.schemas import PlanDecomposition
from workhorse_workflows.coder.workflow import workflow
from coder.implement_plan._support import _Agent, _command, _context, _decomposition, _task

def test_distinct_fetch_and_push_endpoints_are_refused(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    logger: Any,
) -> None:
    git(repo, "remote", "set-url", "--add", "--push", "origin", str(origin))
    git(repo, "remote", "set-url", "--add", "--push", "origin", str(tmp_path / "shadow.git"))
    plan = tmp_path / "plan.md"
    plan.write_text("# Endpoint identity\n", encoding="utf-8")

    with pytest.raises(WorkflowFailed, match="one endpoint"):
        snapshot_plan(logger, str(plan), str(tmp_path / "run"), str(repo))


def test_invalid_package_scope_is_rejected(
    tmp_path: Path,
    repo: Path,
    logger: Any,
) -> None:
    context = _context(tmp_path, repo, logger)
    task = _task("bad-scope", "src/value.txt") | {"commit_scope": "not-a-package"}

    with pytest.raises(WorkflowFailed, match="invalid commit scope"):
        prepare_plan(logger, PlanDecomposition.model_validate(_decomposition(task)), context)


def test_ignored_top_level_directory_is_not_a_valid_package_scope(
    tmp_path: Path,
    repo: Path,
    logger: Any,
) -> None:
    private = repo / "confidential-scope"
    private.mkdir()
    (private / "notes.txt").write_text("private\n", encoding="utf-8")
    (repo / ".git" / "info" / "exclude").write_text("confidential-scope/\n")
    context = _context(tmp_path, repo, logger)
    task = _task("bad-scope", "src/value.txt") | {"commit_scope": "confidential-scope"}

    with pytest.raises(WorkflowFailed, match="invalid commit scope"):
        prepare_plan(logger, PlanDecomposition.model_validate(_decomposition(task)), context)


def test_code_packet_typed_docs_is_rejected(
    tmp_path: Path,
    repo: Path,
    logger: Any,
) -> None:
    """A valid type can still be the wrong one, and this one ships the work to nobody.

    Release tooling reads the type: a speedup labelled `docs` releases no version, and
    the omission surfaces weeks later as a bug against a version that never had it.
    """
    context = _context(tmp_path, repo, logger)
    task = _task("mislabelled", "src/cache.py") | {"commit_type": "docs"}

    with pytest.raises(WorkflowFailed, match="owns no documentation"):
        prepare_plan(logger, PlanDecomposition.model_validate(_decomposition(task)), context)


def test_docs_packet_reaching_into_a_source_file_is_allowed(
    tmp_path: Path,
    repo: Path,
    logger: Any,
) -> None:
    """A genuine documentation task may still touch code — a docstring lives there."""
    context = _context(tmp_path, repo, logger)
    task = _task("real-docs", "README.md") | {
        "commit_type": "docs",
        "paths": ["README.md", "src/cache.py"],
    }

    plan = prepare_plan(logger, PlanDecomposition.model_validate(_decomposition(task)), context)

    assert plan.tasks[0].commit_type == "docs"


def test_rejected_decomposition_is_reworked_rather_than_ending_the_run(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The one turn here with no rework is the one whose failure costs the whole run.

    A packet three characters over the subject limit, or carrying a scope typo, ended
    a planning turn that was otherwise correct. It gets its verdict back and one more
    attempt, as every other turn in this flow already does.
    """
    plan = tmp_path / "plan.md"
    plan.write_text("# Reworked decomposition\n", encoding="utf-8")
    rejected = _decomposition(_task("bad", "src/value.txt") | {"commit_scope": "not-a-package"})
    accepted = _decomposition(_task("good", "src/value.txt"))
    agent = _Agent(
        repo,
        rejected,
        reworked=[accepted],
        edits={"good": {"src/value.txt": "good\n"}},
    )

    result = drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)

    assert result.status == "complete"
    assert agent.calls.count("decompose-implementation-plan") == 2
    findings = [
        data["findings"]
        for node_id, data in agent.turn_args
        if node_id == "decompose-implementation-plan"
    ]
    assert findings[0] == ""
    assert "invalid commit scope" in findings[1]


def test_decomposition_rework_is_bounded(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A planner that keeps returning the same defect must not loop forever."""
    plan = tmp_path / "plan.md"
    plan.write_text("# Unfixable decomposition\n", encoding="utf-8")
    rejected = _decomposition(_task("bad", "src/value.txt") | {"commit_scope": "not-a-package"})
    agent = _Agent(repo, rejected)

    with pytest.raises(WorkflowFailed, match="invalid commit scope"):
        drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)

    assert agent.calls.count("decompose-implementation-plan") == 3


def test_final_gate_failure_does_not_publish_last_packet(
    tmp_path: Path,
    repo: Path,
    origin: Path,
    git: Callable[..., subprocess.CompletedProcess],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text("# Red aggregate gate\n", encoding="utf-8")
    task = _task("candidate", "src/candidate.txt")
    proposal = _decomposition(task, final=[_command("raise SystemExit(1)")])
    agent = _Agent(repo, proposal, edits={"candidate": {"src/candidate.txt": "candidate\n"}})
    remote_before = git(origin, "rev-parse", "main").stdout

    with pytest.raises(WorkflowFailed, match="final plan verification failed"):
        drive_flow(ImplementPlan(plan_path=str(plan), repo_dir=str(repo)), env(), agent)

    assert git(origin, "rev-parse", "main").stdout == remote_before
    assert git(repo, "rev-parse", "HEAD").stdout != remote_before


def test_source_plan_drift_blocks_the_next_boundary(
    tmp_path: Path,
    repo: Path,
    logger: Any,
) -> None:
    plan = tmp_path / "plan.md"
    context = _context(tmp_path, repo, logger, "# Original\n", plan=plan)
    plan.write_text("# Changed\n", encoding="utf-8")

    with pytest.raises(WorkflowFailed, match="source plan changed"):
        check_planning_turn(logger, context)


def test_cycle_is_rejected_before_implementation(
    tmp_path: Path,
    repo: Path,
    logger: Any,
) -> None:
    context = _context(tmp_path, repo, logger)
    first = _task("first", "src/first.txt", depends_on=["second"])
    second = _task("second", "src/second.txt", depends_on=["first"])

    with pytest.raises(WorkflowFailed, match="dependency cycle"):
        prepare_plan(logger, PlanDecomposition.model_validate(_decomposition(first, second)), context)


def test_overlapping_ownership_is_ordered_by_the_emitted_sequence(
    tmp_path: Path,
    repo: Path,
    logger: Any,
) -> None:
    """Sharing a file demands an order, and the planner's own sequence already is one.

    Declaring every implied edge is a transitive closure done by hand, so the missing
    one is recorded rather than fatal — the pair is still ordered, and the order is the
    one the decomposition itself emitted.
    """
    context = _context(tmp_path, repo, logger)
    broad = _task("broad", "src")
    narrow = _task("narrow", "src/narrow.txt")

    plan = prepare_plan(
        logger, PlanDecomposition.model_validate(_decomposition(broad, narrow)), context
    )

    assert [task.id for task in plan.tasks] == ["broad", "narrow"]
    assert plan.tasks[1].depends_on == ["broad"]


def test_ordering_a_shared_file_never_contradicts_a_declared_dependency(
    tmp_path: Path,
    repo: Path,
    logger: Any,
) -> None:
    """The declared edge wins: the implied one is only ever added forwards."""
    context = _context(tmp_path, repo, logger)
    broad = _task("broad", "src", depends_on=["narrow"])
    narrow = _task("narrow", "src/narrow.txt")

    plan = prepare_plan(
        logger, PlanDecomposition.model_validate(_decomposition(broad, narrow)), context
    )

    assert [task.id for task in plan.tasks] == ["narrow", "broad"]
    assert plan.tasks[1].depends_on == ["narrow"]


def test_packet_cannot_own_an_ignored_source_plan(
    tmp_path: Path,
    repo: Path,
    logger: Any,
) -> None:
    plan = repo / "notes" / "private-plan.md"
    plan.parent.mkdir()
    plan.write_text("# Internal\n", encoding="utf-8")
    (repo / ".git" / "info" / "exclude").write_text("notes/private-plan.md\n")
    context = _context(tmp_path, repo, logger, "# Internal\n", plan=plan)
    proposal = PlanDecomposition.model_validate(_decomposition(_task("docs", "notes")))

    with pytest.raises(WorkflowFailed, match="private source plan"):
        prepare_plan(logger, proposal, context)


def test_verification_rejects_shell_and_git_executables(
    tmp_path: Path,
    repo: Path,
    logger: Any,
) -> None:
    context = _context(tmp_path, repo, logger)
    task = _task(
        "unsafe-command",
        "src/value.txt",
        verification=[{"argv": ["git", "status"], "cwd": ".", "timeout_s": 30}],
    )

    with pytest.raises(WorkflowFailed, match="not allowed"):
        prepare_plan(logger, PlanDecomposition.model_validate(_decomposition(task)), context)


def test_remote_identity_drops_url_credentials_before_checkpointing() -> None:
    endpoint = _safe_endpoint(
        "https://user:secret@example.com/example-org/api-service.git?access_token=secret"
    )
    ssh_endpoint = _safe_endpoint("git@example.com:example-org/api-service.git")

    assert endpoint == "https://example.com/example-org/api-service.git"
    assert ssh_endpoint == "example.com:example-org/api-service.git"
    assert "user" not in endpoint
    assert "secret" not in endpoint


def test_implement_plan_is_a_registered_coder_flow() -> None:
    assert workflow.flow("implement-plan") is ImplementPlan
    assert "implement-plan" in workflow.flow_names()
