"""The whole-run gates, and the git tail that ships what they passed."""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler, markdown, registry, select
from workhorse_workflows.kit import find_repo_root
from workhorse_workflows.author.main.nodes._blueprint import blueprint
from workhorse_workflows.author.main.nodes import _stubs
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import launch_repo_root, survey_repo_root
from workhorse_workflows.author.shared.schemas.main import Committed, Defects, VerifyReport
from workhorse_workflows.kit import commit_paths, show_file



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




@blueprint.node(stub=_stubs.holds)
def verify_integrity(
    logger: logging.Logger,
    epic: str = "",
    repo_dir: str = "",
) -> VerifyReport:
    """`ostler doctor` over the whole graph, as a blocking gate."""
    okf = Ostler(launch_repo_root(repo_dir))

    outcome = okf.doctor(epic=epic.strip() or None)
    if outcome.status == "invalid":
        logger.warning("%s — skipped", outcome.message)
        return VerifyReport(skipped=True, report=f"{outcome.message} — skipped")

    report = outcome.data
    findings = report.get("findings", [])
    errors = [f for f in findings if f.get("severity") == "error"]
    warns = [f for f in findings if f.get("severity") == "warn"]
    summary = (
        f"ostler doctor [{report.get('org', '?')}/{report.get('profile', '?')}]: "
        f"{len(errors)} error(s), {len(warns)} warning(s)"
    )
    logger.info(summary)

    if not errors:
        return VerifyReport(holds=True, report=summary)

    lines = [
        "ostler doctor found referential-integrity errors in the planning-doc graph.",
        "Each is a graph break (a reference that resolves to nothing, or to the wrong epic).",
        "Reconcile each with `ostler edit` (relink / rename) or escalate — never",
        "delete a reference or fabricate an entity to silence the check.",
        "",
    ]
    for f in errors:
        scope = f.get("epic") or f.get("ref") or ""
        scope = f" ({scope})" if scope else ""
        lines.append(f"  - [{f.get('code', '?')}]{scope} {f.get('message', '')}")
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




def _commit_message(mode: str, epic: str, bullet: str, roadmap: str = "") -> str:
    if mode == "incomplete":
        if roadmap:
            return f"author: INCOMPLETE — roadmap {Path(roadmap).stem}, do not merge"
        if epic:
            return f"author: INCOMPLETE — unwritten stories, do not merge ({epic})"
        return "author: INCOMPLETE — unwritten stories, do not merge"
    if mode == "story" and epic:
        trimmed = bullet.strip().splitlines()[0][:72] if bullet.strip() else ""
        return f"author: {epic} — {trimmed}" if trimmed else f"author: {epic}"
    if mode == "epic-edit" and epic:
        trimmed = bullet.strip().splitlines()[0][:72] if bullet.strip() else ""
        epic = registry.epic_slug(epic)
        return f"author: {epic} — {trimmed}" if trimmed else f"author: {epic}"
    if roadmap:
        return f"author: roadmap {Path(roadmap).stem}"
    return "author: epic authoring"


@blueprint.node
def commit_author(
    logger: logging.Logger,
    mode: str = "epic",
    epic: str = "",
    bullet: str = "",
    roadmap: str = "",
    repo_dir: str = "",
    docs_dir: str = "docs",
    id_registry: str = ".agents/ids.json",
) -> Committed:
    """Commit the epic/story docs this run wrote, in the one repo it wrote them in."""
    repo_root = find_repo_root(repo_dir)
    if not (repo_root / ".git").exists():
        logger.info("no .git at %s — nothing to commit", repo_root)
        return Committed()

    scope = [
        rel for rel in (docs_dir.strip(), id_registry.strip()) if rel and (repo_root / rel).exists()
    ]
    if not scope:
        logger.info("nothing author writes exists under %s — nothing to commit", repo_root)
        return Committed()

    committed = commit_paths(repo_root, _commit_message(mode, epic, bullet, roadmap), *scope)
    if committed:
        logger.info("committed %s in %s", " ".join(scope), repo_root)
    return Committed(committed=committed)


__all__ = [
    "commit_author",
    "validate_artifacts",
    "verify_integrity",
    "verify_reconcile",
]
