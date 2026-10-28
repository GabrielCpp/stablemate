"""The whole-run gates on what a run wrote."""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler, select
from workhorse_workflows.author.finalize.nodes._blueprint import blueprint
from workhorse_workflows.author.shared.nodes import stubs as _stubs
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.baseline import epic_scopes
from workhorse_workflows.author.shared.paths import launch_repo_root, survey_repo_root
from workhorse_workflows.author.shared.schemas.main import Defects, EpicBaseline, VerifyReport


@blueprint.node(stub=_stubs.holds)
def verify_reconcile(
    logger: logging.Logger,
    baseline: str = "",
    repo_dir: str = "",
) -> VerifyReport:
    """Scope this run silently dropped, measured against the epics as they stood when it started."""
    start = EpicBaseline.model_validate_json(baseline).epics if baseline.strip() else {}
    if not start:
        logger.info("no epics at run start — reconciliation gate skipped")
        return VerifyReport(skipped=True, report="no epics at run start — skipped")
    root = launch_repo_root(repo_dir)
    epics_path = root / paths.epics_dir(root)
    if not epics_path.is_dir():
        logger.info("no epics dir at %s — skipped", epics_path)
        return VerifyReport(skipped=True, report=f"no epics dir at {epics_path} — skipped")

    drops: list[str] = []
    checked = 0
    for epic, (seeds, stories) in epic_scopes(epics_path).items():
        before = start.get(epic)
        if before is None:
            continue
        checked += 1
        for sid in sorted(set(before.seeds) - seeds):
            drops.append(
                f"  - [dropped-seed] ({epic}) seed item '{sid}' was committed but is "
                f"absent now — confirm it was intentionally dropped (record the reason), "
                f"or restore it"
            )
        for slug in sorted(set(before.stories) - stories):
            drops.append(
                f"  - [dropped-story] ({epic}) story '{slug}' was committed but is "
                f"absent now — confirm intentional, or restore it"
            )

    if checked == 0:
        logger.info("no epic of the run's start is still on disk — skipped")
        return VerifyReport(skipped=True, report="no epic of the run's start is still on disk — skipped")

    summary = f"reconcile vs run start: {checked} epic(s) checked, {len(drops)} silent drop(s)"
    logger.info(summary)
    if not drops:
        return VerifyReport(holds=True, report=summary)

    lines = [
        "This run silently removed planning entities that a prior run committed.",
        "Each is a scope drop with no dangling reference left for `ostler doctor` to catch.",
        "Confirm each was intentional (record the disposition/reason) or restore it — a silent",
        "removal of prior scope is a regression, not a clean re-derivation.",
        "",
        *drops,
    ]
    return VerifyReport(errors="\n".join(lines), report=summary)


def _is_done(status: str) -> bool:
    return select.is_done(status)


def _canonical_epic_names(okf: Ostler, names: list[str]) -> list[str]:
    resolved: list[str] = []
    seen: set[str] = set()
    for name in names:
        try:
            epic = Path(okf.epic_path(name)).name
        except (OSError, ValueError, RuntimeError):
            epic = name
        if epic not in seen:
            resolved.append(epic)
            seen.add(epic)
    return resolved


@blueprint.node(stub=_stubs.clean)
def validate_artifacts(logger: logging.Logger, repo_dir: str = "") -> Defects:
    """Can the coder engine actually walk what this run produced?"""
    okf = Ostler(survey_repo_root(repo_dir))

    try:
        queue = okf.todo()
    except (OSError, ValueError, RuntimeError):
        reason = "could not read the epics index via ostler's in-process API"
        logger.warning(reason)
        return Defects(errors=reason)
    if not queue:
        seen: set[str] = set()
        for milestone in okf.graph.milestones:
            for epic in milestone.epics:
                name = str(epic).strip()
                if name and name not in seen:
                    queue.append(name)
                    seen.add(name)
    if not queue:
        queue = [epic.name for epic in okf.graph.epics]
    queue = _canonical_epic_names(okf, queue)
    if not queue:
        logger.info("no epics found in todo, milestones, or graph")
        return Defects(errors="no epics found in todo, milestones, or graph")

    by_epic: dict[str, list[dict]] = {}
    for s in okf.list("story"):
        by_epic.setdefault(str(s.get("epic", "")), []).append(s)

    loadable = {e.name for e in okf.graph.epics}

    errors: list[str] = []
    selectable = 0
    for raw_epic in queue:
        epic = str(raw_epic)
        if epic not in loadable:
            errors.append(f"epic '{epic}': epic.md missing (ostler cannot load the epic)")
        stories = by_epic.get(epic, [])
        if not stories:
            errors.append(f"epic '{epic}': lists no stories in `## Stories`")
            continue
        for s in stories:
            slug = s.get("slug", "?")
            path = s.get("path", "")
            if not s.get("hasStoryMd"):
                errors.append(
                    f"epic '{epic}' story '{slug}': story.md missing at {path or '<no path>'}"
                )
            elif not s.get("authored"):
                empty = ", ".join(s.get("unwrittenSections") or []) or "its required sections"
                errors.append(
                    f"epic '{epic}' story '{slug}': story.md is still a bare scaffold "
                    f"({empty} empty) at {path}"
                )
            elif not _is_done(str(s.get("status", ""))):
                selectable += 1

    if selectable == 0 and not errors:
        errors.append("no selectable story (coder would have nothing to run)")

    logger.info(
        "artifacts validation: %d error(s), %d selectable stor(y/ies)", len(errors), selectable
    )
    return Defects(ok=not errors, errors="\n".join(errors))


__all__ = ["validate_artifacts", "verify_reconcile"]
