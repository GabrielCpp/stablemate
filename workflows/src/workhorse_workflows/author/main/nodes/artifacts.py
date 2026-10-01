"""The whole-run gates on what a run wrote."""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler, markdown, select
from workhorse_workflows.author.main.nodes._blueprint import blueprint
from workhorse_workflows.author.shared.nodes import stubs as _stubs
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import launch_repo_root, survey_repo_root
from workhorse_workflows.author.shared.schemas.main import Defects, VerifyReport
from workhorse_workflows.kit import show_file


def _subsection_ids(text: str, heading: str) -> set[str]:
    """The `### <id>` titles directly under the `## <heading>` section of an epic.md."""
    ids: set[str] = set()
    for root in markdown.split(text or "").sections:
        for section in root.walk():
            if section.level == 2 and section.title.strip().lower() == heading.lower():
                ids.update(c.title.strip() for c in section.children if c.level == 3)
    return ids


@blueprint.node(stub=_stubs.holds)
def verify_reconcile(
    logger: logging.Logger,
    ref: str = "HEAD",
    repo_dir: str = "",
) -> VerifyReport:
    """Scope this run silently dropped, measured against the last committed epics."""
    ref = ref.strip() or "HEAD"
    root = launch_repo_root(repo_dir)
    epics_rel = paths.epics_dir(root)
    epics_path = root / epics_rel

    if show_file(root, ref, epics_rel) is None and not (root / ".git").exists():
        logger.info("not a git repo at %s — reconciliation gate skipped", root)
        return VerifyReport(skipped=True, report="not a git repo — reconciliation gate skipped")
    if not epics_path.is_dir():
        logger.info("no epics dir at %s — skipped", epics_path)
        return VerifyReport(skipped=True, report=f"no epics dir at {epics_rel} — skipped")

    drops: list[str] = []
    checked = 0
    for epic_md in sorted(epics_path.glob("*/epic.md")):
        epic = epic_md.parent.name
        base = show_file(root, ref, str(epic_md.relative_to(root)))
        if base is None:
            continue
        checked += 1
        now = epic_md.read_text(encoding="utf-8")

        for sid in sorted(_subsection_ids(base, "Seeds") - _subsection_ids(now, "Seeds")):
            drops.append(
                f"  - [dropped-seed] ({epic}) seed item '{sid}' was committed but is "
                f"absent now — confirm it was intentionally dropped (record the reason), "
                f"or restore it"
            )
        for slug in sorted(_subsection_ids(base, "Stories") - _subsection_ids(now, "Stories")):
            drops.append(
                f"  - [dropped-story] ({epic}) story '{slug}' was committed but is "
                f"absent now — confirm intentional, or restore it"
            )

    if checked == 0:
        logger.info("no epics with a committed baseline at %s — skipped", ref)
        return VerifyReport(
            skipped=True, report=f"no epics with a committed baseline at {ref} — skipped"
        )

    summary = f"reconcile vs {ref}: {checked} epic(s) checked, {len(drops)} silent drop(s)"
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
