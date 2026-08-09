"""Snapshot a prose plan and prove one proposed phase slicing covers it."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from git.exc import GitError
from workhorse import worklist as wl
from workhorse.pyflow import WorkflowFailed
from workhorse.scriptutil import find_repo_root

from workhorse_workflows.coder.implement_plan.inventory import validate_command
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.stage_plan.schemas import (
    PlanSlicing,
    PreparedSlices,
    StageOutcome,
    StagePlanContext,
    StagedSlice,
)
from workhorse_workflows.kit import open_repo

_SLICE_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,46}[a-z0-9])?$")
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def headings(text: str) -> list[tuple[int, str]]:
    """Every ATX heading as `(depth, text)`, skipping fenced code.

    The fence skip is not cosmetic: this plan family documents its own verification
    gate in a ```bash block, and a `#`-prefixed shell comment inside one would
    otherwise become a phase the slicing is required to cover.
    """
    found: list[tuple[int, str]] = []
    fence = ""
    for line in text.splitlines():
        opening = _FENCE.match(line)
        if fence:
            if opening and line.strip().startswith(fence):
                fence = ""
            continue
        if opening:
            fence = opening.group(1)[0] * 3
            continue
        match = _HEADING.match(line)
        if match:
            found.append((len(match.group(1)), match.group(2).strip()))
    return found


def sibling_headings(text: str, first: str) -> list[str]:
    """Every heading that shares `first`'s depth inside the section that contains it.

    This is what makes coverage checkable rather than self-reported. A slicing turn
    declares the phases it found; without the siblings the declaration is unfalsifiable,
    and a turn that quietly drops the last two phases of a ten-phase plan produces a run
    that reports complete having implemented eight.
    """
    found = headings(text)
    positions = [index for index, (_, title) in enumerate(found) if title == first]
    if len(positions) != 1:
        raise WorkflowFailed(
            f"phase heading {first!r} must appear exactly once in the plan, found {len(positions)}"
        )
    start = positions[0]
    depth = found[start][0]
    parent_depth = next(
        (found[index][0] for index in range(start - 1, -1, -1) if found[index][0] < depth),
        0,
    )
    siblings = []
    for current_depth, title in found[start:]:
        if current_depth <= parent_depth:
            break
        if current_depth == depth:
            siblings.append(title)
    return siblings


@blueprint.node
def snapshot_staged_plan(
    logger, plan_path: str, run_dir: str, repo_dir: str = ""
) -> StagePlanContext:
    """Freeze the source plan and fail before the slicing turn if the repo is unready.

    Every precondition asserted here is asserted again, authoritatively, by each phase's
    own `implement-plan` snapshot. Repeating them is a courtesy to the operator: a dirty
    checkout should cost a second, not a slicing turn.
    """
    repo_root = find_repo_root(repo_dir)
    source = Path(plan_path).expanduser()
    if not source.is_absolute():
        source = repo_root / source
    source = source.resolve()
    try:
        content = source.read_bytes()
        text = content.decode("utf-8")
        repo = open_repo(repo_root)
        branch = repo.active_branch.name
        base_commit = repo.git.rev_parse("HEAD").strip()
        remote = repo.git.ls_remote("origin", f"refs/heads/{branch}")
    except (OSError, UnicodeDecodeError, GitError, TypeError) as exc:
        raise WorkflowFailed(f"cannot snapshot plan {source}: {exc}") from exc
    if not branch or branch == "HEAD":
        raise WorkflowFailed("stage-plan requires a checked-out branch, not detached HEAD")
    if repo.is_dirty(index=True, working_tree=True, untracked_files=True):
        raise WorkflowFailed(
            f"stage-plan requires a clean worktree at {repo_root}; preserve or commit existing work first"
        )
    published = remote.split()[0] if remote.split() else ""
    if published != base_commit:
        raise WorkflowFailed(
            f"origin/{branch} is at {published[:12] or '(missing)'}, not local HEAD "
            f"{base_commit[:12]}; push or reconcile before staging a plan"
        )
    stage_dir = Path(run_dir) / "stage-plan"
    context = StagePlanContext(
        repo_root=str(repo_root),
        source_path=str(source),
        plan_text=text,
        plan_digest=hashlib.sha256(content).hexdigest(),
        stage_dir=str(stage_dir),
        branch=branch,
        base_commit=base_commit,
    )
    _atomic_json(
        stage_dir / "snapshot.json",
        context.model_dump(mode="json", exclude={"plan_text"}),
    )
    logger.info("snapshotted %s as %s", source, context.plan_digest[:12])
    return context


def _validate_declaration(slicing: PlanSlicing, context: StagePlanContext) -> list[str]:
    if slicing.status != "ready":
        detail = slicing.summary.strip() or slicing.status or "no slicing result"
        raise WorkflowFailed(f"plan slicing blocked: {detail}")
    declared = [heading.strip() for heading in slicing.phase_headings]
    if not declared:
        raise WorkflowFailed("plan slicing declared no implementation phases")
    if len(set(declared)) != len(declared):
        raise WorkflowFailed("plan slicing declared the same phase heading twice")
    expected = sibling_headings(context.plan_text, declared[0])
    if declared != expected:
        raise WorkflowFailed(
            "declared phases do not match the plan's own phase headings; "
            f"expected {expected}, got {declared}"
        )
    return declared


@blueprint.node
def prepare_slices(
    logger, slicing: PlanSlicing, context: StagePlanContext
) -> PreparedSlices:
    """Validate one proposed slicing and write each phase as its own plan document."""
    declared = _validate_declaration(slicing, context)
    if not slicing.slices:
        raise WorkflowFailed("plan slicing produced no slices")
    seen: set[str] = set()
    covered: list[str] = []
    staged: list[StagedSlice] = []
    directory = Path(context.stage_dir) / "slices"
    directory.mkdir(parents=True, exist_ok=True)
    for index, proposed in enumerate(slicing.slices):
        identity = proposed.id.strip()
        if not _SLICE_ID.fullmatch(identity):
            raise WorkflowFailed(
                f"slice id {proposed.id!r} must be lowercase kebab-case and at most 48 characters"
            )
        if identity in seen:
            raise WorkflowFailed(f"slice id {identity} is used more than once")
        seen.add(identity)
        if not proposed.covers:
            raise WorkflowFailed(f"slice {identity} covers no phase of the plan")
        body = proposed.body.strip()
        if not body:
            raise WorkflowFailed(f"slice {identity} has no plan document")
        titles = {title for _, title in headings(body)}
        missing = [heading for heading in proposed.covers if heading not in titles]
        if missing:
            raise WorkflowFailed(
                f"slice {identity} claims phases its document does not carry: {', '.join(missing)}"
            )
        covered.extend(heading.strip() for heading in proposed.covers)
        path = directory / f"{index + 1:02d}-{identity}.md"
        path.write_text(body + "\n", encoding="utf-8")
        staged.append(
            StagedSlice(
                id=identity,
                title=proposed.title.strip() or identity,
                covers=[heading.strip() for heading in proposed.covers],
                path=str(path),
                digest=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    if covered != declared:
        raise WorkflowFailed(
            "slices must cover every declared phase exactly once and in plan order; "
            f"expected {declared}, got {covered}"
        )
    if not slicing.final_verification:
        raise WorkflowFailed("plan slicing must declare a repository-wide verification gate")
    prepared = PreparedSlices(
        slices=staged,
        final_verification=[
            validate_command(command, owner="staged final gate")
            for command in slicing.final_verification
        ],
        summary=slicing.summary.strip(),
    )
    _atomic_json(
        Path(context.stage_dir) / "slices.json",
        prepared.model_dump(mode="json"),
    )
    logger.info("prepared %d plan phases from %s", len(staged), context.source_path)
    return prepared


def assert_slice_unchanged(slice_: StagedSlice) -> None:
    """A phase implements the document that was checkpointed, or nothing."""
    try:
        digest = hashlib.sha256(Path(slice_.path).read_bytes()).hexdigest()
    except OSError as exc:
        raise WorkflowFailed(f"cannot read plan phase {slice_.id}: {exc}") from exc
    if digest != slice_.digest:
        raise WorkflowFailed(f"plan phase {slice_.id} changed after it was checkpointed")


def write_stage_worklist(
    context: StagePlanContext,
    prepared: PreparedSlices,
    *,
    current_index: int,
    outcomes: list[StageOutcome],
    blocked: str = "",
) -> None:
    """Project checkpoint authority for operators; never read it back to schedule work."""
    items: list[wl.WorkItem] = []
    for index, staged in enumerate(prepared.slices):
        if index < len(outcomes):
            status, commit_sha = "done", outcomes[index].final_commit
        elif index == current_index and blocked == staged.id:
            status, commit_sha = "blocked", ""
        elif index == current_index:
            status, commit_sha = "active", ""
        else:
            status, commit_sha = "pending", ""
        items.append(
            wl.WorkItem(
                id=staged.id,
                status=status,
                kind="plan-phase",
                order=index + 1,
                payload={
                    "phase": staged.model_dump(mode="json"),
                    "final_commit": commit_sha,
                    "outcome": (
                        outcomes[index].model_dump(mode="json")
                        if index < len(outcomes)
                        else {}
                    ),
                },
            )
        )
    payload = {
        "version": 1,
        "plan_digest": context.plan_digest,
        "branch": context.branch,
        "base_commit": context.base_commit,
        "phases": [item.model_dump(exclude_unset=True, mode="json") for item in items],
    }
    _atomic_json(Path(context.stage_dir) / "worklist.json", payload)


__all__ = [
    "assert_slice_unchanged",
    "headings",
    "prepare_slices",
    "sibling_headings",
    "snapshot_staged_plan",
    "write_stage_worklist",
]
