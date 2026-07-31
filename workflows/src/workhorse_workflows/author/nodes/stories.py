"""One story at a time: pick it, validate it, ground it, and read the operator's notes.

Ported from `base-library/workflows/author/scripts/{seed-story,select-story,validate-story,
check-story-grounding,ledger,check_feedback,prune-bullet}.py`.

Every message keeps its script's wording minus the `[script-name]` prefix: the run record
already names the state that halted, so the prefix was the engine's job.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from ostler import Ostler, markdown, registry
from ostler.model import section_gaps, status_bullet
from workhorse import gates
from workhorse import worklist as wl
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.nodes._blueprint import blueprint
from workhorse_workflows.author.nodes import _stubs
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import feedback_repo_root, survey_repo_root
from workhorse_workflows.author.shared.schemas.main import (
    Defects,
    Feedback,
    Ledger,
    Pruned,
    SeededStory,
    StoryChoice,
)

#: The backlog scope-item contract, shared with the coverage validator: `- [id] …`, read off
#: the parsed list rather than matched line by line, so a bullet inside a fenced example is
#: not a scope item and a wrapped one is still whole.

#: Multi-word phrases that signal an UNRESOLVED decision shipped to the coder. A story must
#: RESOLVE every decision or escalate it via the writer's `blocked` status — it must not write
#: the indecision into the story. These are deliberately specific, so a *resolved*
#: "Decision (recommended): keep X" does NOT match; only genuine open-endedness does.
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
#: Standalone code-style markers, matched as whole *words* — a word being a run of alphanumerics
#: plus `_` and `-`. So a filename like `epics-todo.json` is the single token "epics-todo" and
#: does not trip the check, while a bare `TODO decide later` does.
_OPEN_QUESTION_WORDS = {"tbd", "todo", "fixme"}
_WORD_CHARS = "_-"


# ── story mode's single story ───────────────────────────────────────────────


def _kebab(text: str, *, max_len: int = 60) -> str:
    """Lowercase kebab id from free text: alnum runs joined by single dashes."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug or "story"


def _resolve_bullet(root: Path, bullet: str, backlog_rel: str) -> tuple[str, str, bool]:
    """`(id, sourceBullet, from_backlog)` for the one bullet story mode was pointed at.

    `backlog_rel` is the run's backlog — not always the repo's default one. A repo that
    scopes a run to a subset of its work points `backlog` at a separate file, and this must
    follow: an id resolved against the wrong file comes back `from_backlog=False`, which reads as
    "literal text the operator typed" and makes the prune tail skip the bullet. The story is
    authored, the bullet is never consumed, and the next run re-authors it.
    """
    backlog_path = root / paths.backlog_file(root, backlog_rel)
    raw = bullet.strip()
    bare = raw[1:-1].strip() if raw.startswith("[") and raw.endswith("]") else raw

    if backlog_path.is_file():
        try:
            text = backlog_path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        for item in markdown.split(text).walk_bullets():
            bid, btext = item.bracketed
            # The operator names the bullet by its id, by its text, or by pasting the whole
            # line back — with or without the list marker, which the parse has already taken
            # off, so `raw` is stripped of one here rather than compared against a line.
            if bid and (
                bare == bid
                or raw.lstrip("-").strip() == item.text.strip()
                or (btext and btext == raw)
            ):
                return bid, item.text.strip(), True

    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", bare):
        return bare, bare, False
    return _kebab(raw), raw, False


@blueprint.node
def seed_story(
    logger: logging.Logger,
    epic: str = "",
    epics_dir: str = "",
    bullet: str = "",
    backlog: str = "",
    repo_dir: str = "",
) -> SeededStory:
    """Register ONE bullet as a new story inside an already-existing epic.

    Story mode's setup: one seed added to the epic's `epic.md` and one story added to its
    `## Stories`, so the existing per-story pipeline (write → validate → ground → audit)
    runs unchanged. Story split never re-runs, so sibling stories are untouched.

    Story mode appends to an EXISTING epic and never creates one, so a missing `epic.md` is
    a hard failure with an actionable message rather than a scaffold invented here.
    Idempotent: a story that already covers the resolved id is reused.
    """
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
    backlog_rel = paths.backlog_file(root, backlog)
    # ostler names the folder, not a join here: epic directories carry their creation order
    # (`0001-accounts`) and story mode is invoked with the bare slug, so a literal join would
    # report a missing epic for one that is right there. `epics_dir` still says which root.
    epic_dir_rel = paths.epic_dir(root, epic, epics_dir)
    epic_dir_abs = root / epic_dir_rel

    if not (epic_dir_abs / "epic.md").is_file():
        raise WorkflowFailed(
            f"epic '{epic}' does not exist at {epic_dir_abs}/epic.md — story mode appends to an "
            "EXISTING epic and never creates one; run epic mode first or fix the epic slug"
        )

    bullet_id, source_bullet, from_backlog = _resolve_bullet(root, bullet, backlog_rel)

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

    # Best-effort: an already-present seed id is a no-op for our purpose.
    okf.add_seed(
        epic,
        bullet_id,
        status="researched",
        summary=source_bullet,
        meta={"sourceBullet": source_bullet},
    )

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


# ── epic mode's story loop ──────────────────────────────────────────────────


@blueprint.node
def select_story(logger: logging.Logger, epic_dir: str = "", repo_dir: str = "") -> StoryChoice:
    """The next story in this epic whose `story.md` still needs writing.

    **ostler answers the whole question**: `next_story_report(epic, need="author")` walks
    the story DAG in dependency order — the order coder builds in — and returns the first
    story that is not *authored*. This node does not open a `story.md` and does not define
    "written" for itself. It used to: it selected on the presence of a `- **Status**:` line,
    which `ostler create story` writes into every scaffold — so every story was born "done",
    the loop routed straight past writing, and a run produced 44 empty stories and reported
    success. One definition of authored, owned by the graph's owner, is the fix.

    Full rubric validation belongs to `validate_story`; this only advances the loop.
    """
    epic_dir_rel = epic_dir.strip()
    if not epic_dir_rel:
        logger.warning("no epic_dir supplied")
        return StoryChoice(reason="no epic_dir supplied")

    epic = Path(epic_dir_rel).name
    okf = Ostler(survey_repo_root(repo_dir))

    try:
        report = okf.next_story_report(epic, need="author")
    except (OSError, ValueError, RuntimeError):
        reason = f"could not read stories for epic '{epic}' via ostler's in-process API"
        logger.warning(reason)
        return StoryChoice(reason=reason)

    # `state` distinguishes "nothing left to write" from "there was never anything to write" —
    # an absent story is not a finished one, so an epic with no `## Stories` must route back to
    # story split rather than read as authored.
    if report["state"] in ("no-epic", "no-stories"):
        logger.info("%s", report["detail"])
        return StoryChoice(reason=report["detail"])

    # The report's own tallies are the worklist, in DAG order, so the dashboard's "3/12" is
    # identical in shape to every other worklist node in the library.
    items = [
        wl.WorkItem(id=f"authored-{i}", status="done")
        for i in range(int(report["done"]))
    ] + [wl.WorkItem(id=slug, status="pending") for slug in report["remaining"]]
    snap = wl.snapshot(items)

    if report["state"] != "ready":
        logger.info("every story in epic '%s' has a written story.md", epic)
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
        # From ostler, not derived: ostler knows where it actually put the file.
        story_dir=str(Path(path).parent),
        reason=report["detail"],
        progress=snap.progress,
        remaining_count=snap.remaining,
    )


# ── the deterministic story gates ───────────────────────────────────────────


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
    """One error string per prose line that ships an unresolved decision.

    Runs over the parsed document's prose — every body line that is not a heading — so a
    heading can never be the thing reported and the line numbers stay file-absolute.
    """
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
    """The bare-minimum story contract, checked deterministically.

    A story is intentionally lean — a Context section and Acceptance Criteria — because the
    coder workflow owns the depth. So this checks only what the contract requires: every
    required section present and the `filled` ones carrying prose, the `- **Status**:`
    bullet the coder's selector reads, and no open questions shipped to the coder.

    **The contract is ostler's, not this node's.** Sections are checked with
    `section_gaps` against ostler's own declaration and the Status field is located with
    `status_bullet`, so this gate and `ostler doctor`'s `unwritten-story` finding can never
    disagree. The story is parsed as a standalone file rather than looked up in the graph:
    this runs right after a story is written, and a `story.md` not yet listed in its epic's
    `## Stories` should still be validated on its own terms.
    """
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

    for spec, gap in section_gaps(doc, registry.STORY_SECTIONS):
        errors.append(f"required section `## {spec.heading}` is {gap}")

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
    """Was the story written against the surface documentation, or from imagination?

    Strictly presence and structure — no semantic judgment, which is the auditor's job.
    Two checks: every seed item the story `covers` exists in the epic's seeds (no phantom
    scope), and — **iff the graph actually holds OKF UI nodes** — the story cites at least
    one of them and every citation resolves.

    The arming condition is the *graph*, not a configured path: author only ever reads the
    book (okf-builder writes it, from code that exists), so as UI nodes accrue this check
    re-arms itself with no flag, and a greenfield repo whose book is still empty is not
    asked to cite what does not exist yet. `features_dir` is informational, as in the
    script — it is here because the YAML passed it.
    """
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


# ── the rework loop's memory, and the operator's inbox ──────────────────────


@blueprint.node
def record_attempt(
    logger: logging.Logger,
    ledger_path: str = "",
    label: str = "",
    note: str = "",
    repo_dir: str = "",
) -> Ledger:
    """Append this attempt's failure to the story's attempts ledger, and read it back.

    A bounded rework loop otherwise carries only the *latest* failure into the next attempt,
    so the reworker can re-try an approach that already failed two cycles ago and the loop
    spins without accumulating. The ledger is the negative constraint the rework prompt
    reads: "these approaches already failed — do not repeat them".

    Idempotent on `label`, so a resumed state does not duplicate its entry, and it never
    fails the run — a write problem degrades to whatever could be read.
    """
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


def _scope_of(text: str) -> str:
    """The inbox's `SCOPE:` line. Only `epic` is honoured; anything else reworks one story."""
    return "epic" if gates.scope_of(text) == "epic" else "story"


@blueprint.node
def check_story_feedback(
    logger: logging.Logger, feedback_path: str = "", repo_dir: str = ""
) -> Feedback:
    """Poll the operator's inbox for un-consumed feedback. Never blocks, never asks.

    The twin of an `Await`, and its opposite: a human may drop a note at any time while the
    run executes, and this reports whether there is one to fold into a single rework cycle.
    Reading it **consumes** it — the `STATUS:` line is flipped to `CONSUMED` before the flow
    acts — so the same note cannot loop the story forever. A file with real content but no
    `STATUS:` line is treated as NEW, which is the forgiving reading of a human's first
    attempt at the format.

    The resolver here is `feedback_repo_root`, the one this script alone used; see
    `shared/paths.py` on why the four are kept apart.
    """
    if not feedback_path:
        logger.info("no feedback_path supplied")
        return Feedback()

    # `root / abs` == abs (pathlib), so an absolute path works too.
    inbox = feedback_repo_root(repo_dir) / feedback_path
    if not inbox.exists():
        logger.info("no feedback inbox at %s", inbox)
        return Feedback()

    current = inbox.read_text()
    state = gates.status_of(current)

    if state == "NEW":
        inbox.write_text(gates.set_status(current, "CONSUMED"))
        logger.info("feedback present (scope=%s)", _scope_of(current))
        return Feedback(present=True, scope=_scope_of(current), content=current)

    if state == "":
        if current.strip():
            # `set_status` prepends the header when there is none — the same bytes this
            # arm used to write by hand, now from the one implementation of the format.
            inbox.write_text(gates.set_status(current, "CONSUMED"))
            logger.info("untagged feedback content treated as NEW (scope=%s)", _scope_of(current))
            return Feedback(present=True, scope=_scope_of(current), content=current)
        logger.info("no unconsumed feedback")
        return Feedback()

    logger.info("no unconsumed feedback (state=%s)", state)
    return Feedback()


@blueprint.node
def prune_bullet(
    logger: logging.Logger,
    backlog: str = "",
    bullet_id: str = "",
    from_backlog: bool = False,
    repo_dir: str = "",
) -> Pruned:
    """Remove the one backlog bullet story mode consumed — story mode's tail.

    Only when the bullet actually came from the backlog; a literal bullet the operator typed
    has nothing to prune. Best-effort and idempotent: a missing backlog, absent id, or write
    failure is swallowed so the run never dies over a tidy-up.
    """
    bullet_id = bullet_id.strip()

    if not from_backlog or not bullet_id:
        logger.info("bullet '%s' is not from the backlog (or missing) — no-op", bullet_id)
        return Pruned()

    root = survey_repo_root(repo_dir)
    backlog_rel = paths.backlog_file(root, backlog)
    backlog_path = root / backlog_rel
    if not backlog_path.is_file():
        logger.info("no backlog at %s — nothing to prune", backlog_path)
        return Pruned()

    try:
        raw = backlog_path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("could not read backlog %s — nothing to prune", backlog_path)
        return Pruned()

    # One predicate for both halves: an item is a scope item iff it carries an `[id]` handle.
    # The count used to run off a looser bullet regex, which counted a backlog's prose
    # bullets — its surfaces list, say — as outstanding work, so an emptied backlog reported
    # work left in it. Removing by id and counting by anything else is two contracts.
    doc = markdown.split(raw)
    offset = doc.body_offset
    drop: set[int] = set()
    removed = 0
    remaining = 0
    for item in doc.walk_bullets():
        if item.line_start + offset in drop:
            continue  # a sub-bullet already carried off inside the matched item's span
        bid = item.bracketed[0]
        if not bid:
            continue
        if bid == bullet_id:
            removed += 1
            # The span, not the first line: an item with a continuation or sub-bullets goes
            # whole, rather than leaving its tail under whatever bullet follows.
            drop.update(range(item.line_start + offset, item.line_end + offset))
        else:
            remaining += 1

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
