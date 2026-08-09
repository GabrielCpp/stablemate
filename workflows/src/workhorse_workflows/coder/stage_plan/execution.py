"""Blueprint nodes that drive, archive, and gate a phase-by-phase plan run."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from git.exc import GitError
from workhorse.pyflow import WorkflowFailed

from workhorse_workflows.coder.implement_plan import repository
from workhorse_workflows.coder.implement_plan.schemas import (
    PlanImplementationResult,
    VerificationResult,
)
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.stage_plan.inventory import (
    assert_slice_unchanged,
    write_stage_worklist,
)
from workhorse_workflows.coder.stage_plan.schemas import (
    PreparedSlices,
    StageOutcome,
    StagePlanContext,
    StagedPlanResult,
    StagedSlice,
)
from workhorse_workflows.kit import open_repo


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def assert_published_at(context: StagePlanContext, expected_head: str) -> None:
    """The repository is clean, on the checkpointed branch, and pushed at `expected_head`.

    A phase's own `implement-plan` asserts far more than this — replacement refs, hook
    configuration, every other ref. This is the boundary between two phases, where the
    only claim worth re-checking is the one the next phase's snapshot will demand anyway.
    """
    root = Path(context.repo_root)
    try:
        repo = open_repo(root)
        branch = repo.active_branch.name
        head = repo.git.rev_parse("HEAD").strip()
        remote = repo.git.ls_remote("origin", f"refs/heads/{context.branch}")
    except (GitError, TypeError) as exc:
        raise WorkflowFailed(f"cannot inspect repository {root}: {exc}") from exc
    if branch != context.branch:
        raise WorkflowFailed(f"repository left checkpointed branch {context.branch}")
    if head != expected_head:
        raise WorkflowFailed(
            f"HEAD moved from checkpointed commit {expected_head[:12]} to {head[:12]}"
        )
    changed = repository.changed_paths(root)
    if changed:
        raise WorkflowFailed(f"expected a clean worktree, found: {', '.join(changed)}")
    published = remote.split()[0] if remote.split() else ""
    if published != expected_head:
        raise WorkflowFailed(
            f"origin/{context.branch} is at {published[:12] or '(missing)'}, "
            f"not the checkpointed {expected_head[:12]}"
        )


@blueprint.node
def project_stage_progress(
    logger,
    context: StagePlanContext,
    prepared: PreparedSlices,
    index: int,
    outcomes: list[StageOutcome],
    blocked: str = "",
) -> None:
    write_stage_worklist(
        context, prepared, current_index=index, outcomes=outcomes, blocked=blocked
    )
    logger.info("projected staged plan progress %d/%d", len(outcomes), len(prepared.slices))


@blueprint.node
def enter_stage(
    logger, context: StagePlanContext, staged: StagedSlice, expected_head: str
) -> None:
    """Refuse to start a phase whose document, branch or published HEAD has drifted."""
    assert_slice_unchanged(staged)
    assert_published_at(context, expected_head)
    logger.info("entering plan phase %s at %s", staged.id, expected_head[:12])


@blueprint.node
def record_stage_outcome(
    logger,
    context: StagePlanContext,
    staged: StagedSlice,
    result: PlanImplementationResult,
    sub_dir: str,
    expected_parent: str,
) -> StageOutcome:
    """Archive one finished phase before the next handoff empties its scope.

    A handoff keyed on the workflow *class* reuses one artifact scope, and every fresh
    entry empties it. Nine phases through the same `implement-plan` would therefore leave
    the operator the ninth phase's evidence and no trace of the eight that produced the
    commits under review — so the parent copies each phase out as it finishes.
    """
    if result.status != "complete":
        raise WorkflowFailed(
            f"plan phase {staged.id} returned {result.status or 'no status'}"
        )
    if result.plan_digest != staged.digest:
        raise WorkflowFailed(
            f"plan phase {staged.id} implemented a different document than the checkpointed one"
        )
    if not result.final_commit or result.final_commit == expected_parent:
        raise WorkflowFailed(f"plan phase {staged.id} produced no commit")
    assert_published_at(context, result.final_commit)
    archive = Path(context.stage_dir) / "phases" / staged.id
    source = Path(sub_dir)
    if source.is_dir():
        shutil.rmtree(archive, ignore_errors=True)
        shutil.copytree(source, archive)
    outcome = StageOutcome(
        id=staged.id,
        slice_digest=staged.digest,
        plan_digest=context.plan_digest,
        task_count=result.task_count,
        review_issue_count=result.review_issue_count,
        review_passes=result.review_passes,
        final_commit=result.final_commit,
    )
    _atomic_json(archive.parent / f"{staged.id}.json", outcome.model_dump(mode="json"))
    logger.info(
        "plan phase %s landed %d commits ending at %s",
        staged.id,
        result.task_count,
        result.final_commit[:12],
    )
    return outcome


@blueprint.node
def verify_staged_candidate(
    logger,
    context: StagePlanContext,
    prepared: PreparedSlices,
    outcomes: list[StageOutcome],
    expected_head: str,
) -> VerificationResult:
    """Run the whole plan's gate once, against the isolated tree every phase built up.

    Each phase gated only its own slice, and a slice is deliberately partial — the phase
    that adds a module and the phase that wires it in both pass alone. This is where the
    source plan's own repository-wide verification finally runs.
    """
    if len(outcomes) != len(prepared.slices):
        raise WorkflowFailed("staged gate reached before every phase finished")
    assert_published_at(context, expected_head)
    with repository.committed_tree(Path(context.repo_root), expected_head) as candidate:
        result = repository.run_commands(candidate, prepared.final_verification)
    assert_published_at(context, expected_head)
    if not result.passed:
        raise WorkflowFailed(f"staged plan verification failed:\n{result.findings}")
    logger.info("staged candidate %s passed the plan's own gate", expected_head[:12])
    return result


@blueprint.node
def complete_stages(
    logger,
    context: StagePlanContext,
    prepared: PreparedSlices,
    outcomes: list[StageOutcome],
    expected_head: str,
) -> StagedPlanResult:
    """Write the run's evidence after the aggregate gate passed, never before."""
    assert_published_at(context, expected_head)
    if len(outcomes) != len(prepared.slices):
        raise WorkflowFailed("completion reached without an outcome for every phase")
    manifest = {
        "version": 1,
        "plan_digest": context.plan_digest,
        "source_path": context.source_path,
        "branch": context.branch,
        "base_commit": context.base_commit,
        "final_commit": expected_head,
        "summary": prepared.summary,
        "phases": [
            {
                "id": staged.id,
                "title": staged.title,
                "covers": staged.covers,
                "path": staged.path,
                "status": "done",
                **outcomes[index].model_dump(mode="json", exclude={"id"}),
            }
            for index, staged in enumerate(prepared.slices)
        ],
        "final_verification": "passed against the published candidate",
    }
    _atomic_json(Path(context.stage_dir) / "completion.json", manifest)
    logger.info("completed %d staged phases at %s", len(outcomes), expected_head[:12])
    return StagedPlanResult(
        status="complete",
        plan_digest=context.plan_digest,
        stage_count=len(outcomes),
        task_count=sum(outcome.task_count for outcome in outcomes),
        review_issue_count=sum(outcome.review_issue_count for outcome in outcomes),
        final_commit=expected_head,
    )


__all__ = [
    "assert_published_at",
    "complete_stages",
    "enter_stage",
    "project_stage_progress",
    "record_stage_outcome",
    "verify_staged_candidate",
]
