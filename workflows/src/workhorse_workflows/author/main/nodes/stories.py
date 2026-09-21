"""One story at a time: pick it, validate it, ground it, and read the operator's notes."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from ostler import Ostler, backlog as ostler_backlog, markdown, refs, registry
from ostler.model import (
    required_section_problems,
    section_order_problems,
    status_bullet,
)
from workhorse import worklist as wl
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.main.nodes._blueprint import blueprint
from workhorse_workflows.author.main.nodes import _stubs
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.kit import poll_run_inbox
from workhorse_workflows.author.shared.schemas.edit import ResolvedBullet
from workhorse_workflows.author.shared.schemas.main import (
    Defects,
    Feedback,
    Ledger,
    MockupGate,
    Pruned,
    SeededStory,
    StoryChoice,
    StoryMutation,
)

MOCKUP_LAYER = "frontend"
MOCKUP_REQUIRED = "required"
MOCKUP_PRESERVE = "preserve"


_OPEN_QUESTION_PHRASES = [
    "decision to surface",
    "decisions to surface",
    "to be decided",
    "to be determined",
    "to be confirmed",
    "to be defined",
    "open question",
    "open questions",
    "decide whether",
    "decide if",
    "decide between",
    "accept, or tune",
    "accept or tune",
    "we should decide",
    "needs a decision",
    "to be discussed",
]
_OPEN_QUESTION_WORDS = {"tbd", "todo", "fixme"}
_WORD_CHARS = "_-"
_NO_PRIOR_IMPLEMENTATION = "No prior implementation reference exists."




def _kebab(text: str, *, max_len: int = 60) -> str:
    """Lowercase kebab id from free text: alnum runs joined by single dashes."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug or "story"


def resolve_bullet(root: Path, bullet: str) -> ResolvedBullet:
    """Resolve one requested bullet against the repo's backlog."""
    backlog_path = root / paths.backlog_file(root)
    raw = bullet.strip()
    bare = raw[1:-1].strip() if raw.startswith("[") and raw.endswith("]") else raw

    if backlog_path.is_file():
        try:
            text = backlog_path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        for item in markdown.split(text).walk_bullets():
            bid, btext = item.bracketed
            if bid and (
                bare == bid
                or raw.lstrip("-").strip() == item.text.strip()
                or (btext and btext == raw)
            ):
                return ResolvedBullet(id=bid, source_bullet=item.text.strip(), from_backlog=True)

    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", bare):
        return ResolvedBullet(id=bare, source_bullet=bare)
    return ResolvedBullet(id=_kebab(raw), source_bullet=raw)


@blueprint.node
def seed_story(
    logger: logging.Logger,
    epic: str = "",
    bullet: str = "",
    layers: str = "",
    services: str = "",
    repo_dir: str = "",
) -> SeededStory:
    """Register ONE bullet as a new story inside an already-existing epic."""
    epic = epic.strip()
    bullet = bullet.strip()

    if not epic:
        raise WorkflowFailed(
            "no epic supplied — story mode needs the target epic slug "
            "(--params '{\"mode\":\"story\",\"epic\":\"<slug>\",\"bullet\":\"...\"}')"
        )
    if not bullet:
        raise WorkflowFailed(
            "no bullet supplied — story mode needs a backlog [id] or literal bullet text "
            "(--params '{\"mode\":\"story\",\"epic\":\"<slug>\",\"bullet\":\"...\"}')"
        )

    root = survey_repo_root(repo_dir)
    okf = Ostler(root)
    epic_dir_rel = paths.epic_dir(root, epic)
    epic_dir_abs = root / epic_dir_rel

    if not (epic_dir_abs / "epic.md").is_file():
        raise WorkflowFailed(
            f"epic '{epic}' does not exist at {epic_dir_abs}/epic.md — story mode appends to an "
            "EXISTING epic and never creates one; run epic mode first or fix the epic slug"
        )

    resolved = resolve_bullet(root, bullet)
    bullet_id = resolved.id
    source_bullet = resolved.source_bullet
    from_backlog = resolved.from_backlog

    for s in okf.list("story", epic=epic):
        if bullet_id in (s.get("covers") or []):
            slug = str(s.get("slug", ""))
            path = str(s.get("path", "")) or f"{paths.story_dir(epic_dir_rel, slug)}/story.md"
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            reason = f"story '{slug}' already covers '{bullet_id}' — reusing (idempotent)"
            logger.info("story '%s' already covers '%s' — reusing (idempotent)", slug, bullet_id)
            return SeededStory(
                epic_dir=epic_dir_rel,
                story_slug=slug,
                story_dir=str(Path(path).parent),
                story_path=path,
                bullet_id=bullet_id,
                from_backlog=from_backlog,
                reason=reason,
            )

    seed_meta: dict[str, str] = {"sourceBullet": source_bullet}
    if layers.strip():
        seed_meta["layers"] = layers.strip()
    if services.strip():
        seed_meta["services"] = services.strip()
    seeded = okf.add_seed(epic, bullet_id, status="researched", summary=source_bullet,
                          meta=seed_meta)
    if not seeded.ok and layers.strip():
        raise WorkflowFailed(f"`seed add {epic} {bullet_id}` failed: {seeded.message}")

    slug = _kebab(source_bullet)
    res = okf.create_story(epic, slug, source_bullet, covers=[bullet_id])
    if not res.ok:
        raise WorkflowFailed(f"`create story {epic} {slug}` failed: {res.message}")

    story_dir_rel = paths.story_dir(epic_dir_rel, slug)
    reason = (
        f"registered story '{slug}' ({res.entity_id or '?'}) covering seed item "
        f"'{bullet_id}' in epic '{epic}'"
    )
    logger.info(
        "registered story '%s' (%s) covering seed item '%s' in epic '%s'",
        slug,
        res.entity_id or "?",
        bullet_id,
        epic,
    )
    return SeededStory(
        epic_dir=epic_dir_rel,
        story_slug=slug,
        story_dir=story_dir_rel,
        story_path=f"{story_dir_rel}/story.md",
        bullet_id=bullet_id,
        from_backlog=from_backlog,
        reason=reason,
    )


@blueprint.node
def remove_story(
    logger: logging.Logger,
    story: str = "",
    force: bool = False,
    repo_dir: str = "",
) -> StoryMutation:
    """Delete one story from the planning graph, guarded for manual use."""
    slug = story.strip()
    if not slug:
        raise WorkflowFailed(
            "no story supplied — remove mode needs --params '{\"story\":\"<slug>\"}'"
        )

    okf = Ostler(survey_repo_root(repo_dir))
    row = next((s for s in okf.list("story") if str(s.get("slug", "")).strip() == slug), None)
    if row is None:
        reason = f"story '{slug}' is already absent — idempotent no-op"
        logger.info(reason)
        return StoryMutation(story_slug=slug, reason=reason)

    status = str(row.get("status", "")).strip()
    if status.lower() != "not started" and not force:
        raise WorkflowFailed(
            f"story '{slug}' has status '{status or '<blank>'}' — refusing to delete work that "
            "may already be planned, implemented or reviewed; rerun with "
            "--params '{\"action\":\"remove\",\"story\":\"<slug>\",\"force\":true}' "
            "if this deletion is intentional"
        )

    res = okf.delete_story(slug)
    if not res.ok:
        raise WorkflowFailed(res.message or f"could not delete story '{slug}'")

    epic = str(row.get("epic", ""))
    path = str(row.get("path", ""))
    logger.info("deleted story '%s' from epic '%s'", slug, epic)
    return StoryMutation(
        changed=True,
        epic=epic,
        story_slug=slug,
        story_dir=str(Path(path).parent) if path else "",
        story_path=path,
        reason=res.message,
    )




@blueprint.node
def check_mockup_needed(
    logger: logging.Logger, story_slug: str = "", repo_dir: str = ""
) -> MockupGate:
    """Design a mockup only for new or materially changed visual behavior."""
    try:
        graph = Ostler(survey_repo_root(repo_dir)).graph
    except (OSError, ValueError, RuntimeError) as exc:
        return MockupGate(evidence=f"knowledge graph unavailable: {exc}")
    found = graph.find_story(story_slug.strip())
    if found is None:
        return MockupGate(evidence="story is absent from the knowledge graph")
    epic, story = found
    if not story.seed_items:
        return MockupGate(evidence="story has no covered seed evidence")

    seeds = {seed.id: seed for seed in epic.seeds}
    layers: list[str] = []
    services: list[str] = []
    untagged: list[str] = []
    required: list[str] = []
    preserved: list[str] = []
    unclassified_design: list[str] = []
    for seed_id in story.seed_items:
        seed = seeds.get(seed_id)
        if seed is None or not seed.layers:
            untagged.append(seed_id)
            continue
        layers += [t for t in seed.layers if t not in layers]
        services += [t for t in seed.services if t not in services]
        if MOCKUP_LAYER not in seed.layers:
            continue
        if seed.design == MOCKUP_REQUIRED:
            required.append(seed_id)
        elif seed.design == MOCKUP_PRESERVE:
            preserved.append(seed_id)
        else:
            unclassified_design.append(
                f"{seed_id} ({seed.design or 'missing'})"
            )

    if untagged:
        return MockupGate(
            layers=layers, services=services,
            evidence="covered seed(s) carry no `layers:`, so a frontend surface cannot be "
                     "ruled out: " + ", ".join(untagged),
        )
    if required:
        return MockupGate(
            layers=layers, services=services,
            evidence="frontend seed(s) require visual design: " + ", ".join(required),
        )
    if unclassified_design:
        return MockupGate(
            layers=layers, services=services,
            evidence="frontend seed(s) have no valid `design:` classification: "
                     + ", ".join(unclassified_design),
        )
    if preserved:
        logger.info(
            "story '%s' preserves existing frontend design (%s)", story_slug, ", ".join(preserved)
        )
        return MockupGate(
            required=False, layers=layers, services=services,
            evidence="frontend seed(s) preserve the existing visual contract: "
                     + ", ".join(preserved),
        )
    logger.info("story '%s' touches no frontend layer (%s)", story_slug, ", ".join(layers))
    return MockupGate(
        required=False, layers=layers, services=services,
        evidence=f"covered seeds are tagged {', '.join(layers)} only — no {MOCKUP_LAYER} work",
    )


@blueprint.node
def select_story(logger: logging.Logger, epic_dir: str = "", repo_dir: str = "",
                 parked: tuple[str, ...] = ()) -> StoryChoice:
    """The next story in this epic whose `story.md` still needs writing."""
    epic_dir_rel = epic_dir.strip()
    if not epic_dir_rel:
        logger.warning("no epic_dir supplied")
        return StoryChoice(reason="no epic_dir supplied")

    epic = Path(epic_dir_rel).name
    okf = Ostler(survey_repo_root(repo_dir))

    try:
        report = okf.next_story_report(epic, skip=frozenset(parked), need="author")
    except (OSError, ValueError, RuntimeError):
        reason = f"could not read stories for epic '{epic}' via ostler's in-process API"
        logger.warning(reason)
        return StoryChoice(reason=reason)

    if report["state"] in ("no-epic", "no-stories"):
        logger.info("%s", report["detail"])
        return StoryChoice(reason=report["detail"])

    items = [
        wl.WorkItem(id=f"authored-{i}", status="done")
        for i in range(int(report["done"]))
    ] + [wl.WorkItem(id=slug, status="pending") for slug in report["remaining"]]
    snap = wl.snapshot(items)

    if report["state"] != "ready":
        logger.info("no story to author in epic '%s': %s", epic, report["detail"])
        return StoryChoice(
            reason=report["detail"], progress=snap.progress, remaining_count=snap.remaining
        )

    story = report["story"]
    slug, path = str(story.get("slug", "")), str(story.get("path", ""))
    logger.info("selected story '%s' — %s", slug, report["detail"])
    return StoryChoice(
        has_story=True,
        story_path=path,
        story_slug=slug,
        story_dir=str(Path(path).parent),
        reason=report["detail"],
        progress=snap.progress,
        remaining_count=snap.remaining,
    )




def _words(line: str) -> list[str]:
    """The line's words, a word running over alphanumerics plus `_` and `-`."""
    out: list[str] = []
    current: list[str] = []
    for ch in line:
        if ch.isalnum() or ch in _WORD_CHARS:
            current.append(ch)
        elif current:
            out.append("".join(current))
            current = []
    if current:
        out.append("".join(current))
    return out


def _open_questions(doc: markdown.MarkdownDoc) -> list[str]:
    """One error string per prose line that ships an unresolved decision."""
    headings = {s.line_start for s in doc.walk_sections() if s.level}
    hits: list[str] = []
    for i, raw in enumerate(doc.body.split("\n")):
        if i in headings:
            continue
        low = raw.lower()
        matched = [p for p in _OPEN_QUESTION_PHRASES if p in low]
        matched += sorted({w.upper() for w in _words(low) if w in _OPEN_QUESTION_WORDS})
        if matched:
            snippet = raw.strip()
            if len(snippet) > 100:
                snippet = snippet[:97] + "..."
            line_no = doc.body_offset + i + 1
            hits.append(
                f"L{line_no}: open question / unresolved decision "
                f"({', '.join(matched)}): {snippet}"
            )
    return hits


@blueprint.node(stub=_stubs.clean)
def validate_story(logger: logging.Logger, story_dir: str = "", repo_dir: str = "") -> Defects:
    """The bare-minimum story contract, checked deterministically."""
    story_dir_rel = story_dir.strip()
    if not story_dir_rel:
        logger.warning("no story_dir supplied")
        return Defects(errors="no story_dir supplied")

    story_md = survey_repo_root(repo_dir) / story_dir_rel / "story.md"
    if not story_md.is_file():
        logger.warning("story.md missing at %s", story_md)
        return Defects(errors=f"story.md missing at {story_md}")

    doc = markdown.split(story_md.read_text(encoding="utf-8"))
    errors: list[str] = []

    if status_bullet(doc) is None:
        errors.append(
            f"no `- **{registry.STORY_STATUS_LABEL}**:` bullet under "
            f"`## {registry.STORY_STATUS_HEADING}` (coder's selector reads this)"
        )

    for spec, problem in required_section_problems(doc, registry.STORY_SECTIONS):
        errors.append(f"required section `## {spec.heading}` is {problem}")
    errors.extend(section_order_problems(doc, registry.STORY_SECTIONS))

    technical = doc.find_section("Technical Notes")
    if technical is not None and not technical.is_empty:
        pointers = [
            refs.ref_path(span)
            for span in markdown.all_code_spans(technical.body)
            if "::" in span
        ]
        if not pointers and technical.body.strip() != _NO_PRIOR_IMPLEMENTATION:
            errors.append(
                "required section `## Technical Notes` needs an existing `path::symbol` code "
                f"pointer or the exact statement `{_NO_PRIOR_IMPLEMENTATION}`"
            )
        root = survey_repo_root(repo_dir)
        for pointer in pointers:
            target = (root / pointer.strip().removeprefix("./")).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                errors.append(
                    f"technical code pointer `{pointer}::...` names no file "
                    "under the repository"
                )

    errors.extend(_open_questions(doc))

    logger.info("story %s: %d error(s)", story_dir_rel, len(errors))
    return Defects(ok=not errors, errors="\n".join(errors))


@blueprint.node(stub=_stubs.clean)
def check_story_grounding(
    logger: logging.Logger,
    story_dir: str = "",
    epic_dir: str = "",
    features_dir: str = "",
    repo_dir: str = "",
) -> Defects:
    """Was the story written against the surface documentation, or from imagination?"""
    story_dir_rel = story_dir.strip()
    epic_dir_rel = epic_dir.strip()
    if not story_dir_rel or not epic_dir_rel:
        logger.warning("story_dir and epic_dir are required — nothing to check")
        return Defects(errors="story_dir and epic_dir are required")

    okf = Ostler(survey_repo_root(repo_dir))
    slug = Path(story_dir_rel).name
    epic = Path(epic_dir_rel).name
    errors: list[str] = []

    try:
        seeds = okf.list("seed", epic=epic)
    except (OSError, ValueError, RuntimeError):
        logger.warning("could not read the epic's seeds via the ostler API for %s", epic)
        return Defects(errors="could not read the epic's seeds via the ostler API")
    seed_ids = {str(s.get("id", "")).strip() for s in seeds if s.get("id")}

    stories = okf.list("story", epic=epic)
    story_row = next((s for s in stories if str(s.get("slug", "")).strip() == slug), None)
    for sid in [str(x).strip() for x in ((story_row or {}).get("covers") or [])]:
        if seed_ids and sid not in seed_ids:
            errors.append(
                f"story claims seed item '{sid}' that is not in the epic's seeds (phantom scope)"
            )

    if okf.graph.ui_nodes:
        refs = okf.query("surfaces-referenced-by-story", slug)
        cited = [r for r in refs if r.get("kind") == "ui"]
        for path in [str(r.get("path", "")) for r in refs if r.get("kind") == "missing"]:
            errors.append(
                f"story cites '{path}', which resolves to no OKF node — cite the node's id "
                "exactly as the book spells it (a repo-relative path, or path#anchor)"
            )
        if not cited:
            logger.info("story '%s' cites no OKF node", slug)
            errors.append(
                "story cites no OKF node — link the ids of the surface/component/interaction "
                "nodes this story works on from its `## Context`, so the scope is grounded in "
                "the book instead of asserted"
            )

    logger.info(
        "story '%s' grounding: %s", slug, "ok" if not errors else f"{len(errors)} error(s)"
    )
    return Defects(ok=not errors, errors="\n".join(errors))




@blueprint.node
def record_attempt(
    logger: logging.Logger,
    ledger_path: str = "",
    label: str = "",
    note: str = "",
    repo_dir: str = "",
) -> Ledger:
    """Append this attempt's failure to the story's attempts ledger, and read it back."""
    ledger_rel = ledger_path.strip()
    label = label.strip() or "?"
    note = note.strip() or "(no detail recorded)"

    if not ledger_rel:
        logger.info("no ledger_path supplied — nothing to record")
        return Ledger()

    path = survey_repo_root(repo_dir) / ledger_rel
    heading = f"## Attempt {label}"

    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError:
        existing = ""

    if heading in existing:
        logger.info("attempt %s already recorded in %s — idempotent no-op", label, ledger_rel)
        return Ledger(prior_attempts=existing.strip(), ledger=ledger_rel)

    if not existing.strip():
        existing = "# Attempts ledger\n\nEach entry is an approach that FAILED — do not repeat it.\n"

    updated = existing.rstrip() + "\n" + f"\n{heading}\nFailed: {note}\n"

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8")
    except OSError:
        logger.warning("could not write ledger %s — degrading to the read-only ledger", path)
        return Ledger(prior_attempts=existing.strip(), ledger=ledger_rel)

    logger.info("recorded attempt %s in %s", label, ledger_rel)
    return Ledger(prior_attempts=updated.strip(), ledger=ledger_rel)


@blueprint.node
def check_story_feedback(logger: logging.Logger, run_dir: str = "") -> Feedback:
    """Poll the operator's run-scoped inbox for un-consumed feedback."""
    polled = poll_run_inbox(run_dir, reply_text="folded into a story rework")
    if polled is None:
        logger.info("no outstanding inbox messages")
        return Feedback()
    content, scope = polled
    logger.info("feedback present (scope=%s)", scope)
    return Feedback(present=True, scope=scope, content=content)


@blueprint.node
def prune_bullet(
    logger: logging.Logger,
    bullet_id: str = "",
    from_backlog: bool = False,
    repo_dir: str = "",
) -> Pruned:
    """Remove the one backlog bullet story mode consumed — story mode's tail."""
    bullet_id = bullet_id.strip()

    if not from_backlog or not bullet_id:
        logger.info("bullet '%s' is not from the backlog (or missing) — no-op", bullet_id)
        return Pruned()

    root = survey_repo_root(repo_dir)
    backlog_rel = paths.backlog_file(root)
    backlog_path = root / backlog_rel
    if not backlog_path.is_file():
        logger.info("no backlog at %s — nothing to prune", backlog_path)
        return Pruned()

    try:
        raw = backlog_path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("could not read backlog %s — nothing to prune", backlog_path)
        return Pruned()

    doc = markdown.split(raw)
    offset = doc.body_offset
    bullets = doc.walk_bullets()
    targets = [item for item in bullets if item.bracketed[0] == bullet_id]
    body_drop = ostler_backlog.removal_lines(targets)
    drop = {line + offset for line in body_drop}
    removed = sum(1 for item in targets if item.line_start in body_drop)
    remaining = sum(
        1 for item in bullets if item.bracketed[0] and item.line_start + offset not in drop
    )

    lines = raw.splitlines(keepends=True)
    kept = [line for i, line in enumerate(lines) if i not in drop]

    if removed:
        try:
            backlog_path.write_text("".join(kept), encoding="utf-8")
        except OSError:
            logger.warning(
                "could not write pruned backlog %s — best-effort, continuing", backlog_path
            )

    logger.info(
        "pruned bullet '%s' from %s (removed=%d, remaining=%d)",
        bullet_id,
        backlog_rel,
        removed,
        remaining,
    )
    return Pruned(removed=removed, remaining=remaining)


__all__ = [
    "check_story_feedback",
    "check_story_grounding",
    "prune_bullet",
    "record_attempt",
    "seed_story",
    "select_story",
    "validate_story",
]
