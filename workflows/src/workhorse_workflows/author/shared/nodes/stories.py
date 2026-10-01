"""The per-story gates: the story contract, its grounding in the book, and its attempts ledger."""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler, markdown, refs, registry
from ostler.model import (
    required_section_problems,
    section_order_problems,
    status_bullet,
)
from workhorse_workflows.author.shared.nodes.blueprint import blueprint
from workhorse_workflows.author.shared.nodes import stubs as _stubs
from workhorse_workflows.author.shared.paths import survey_repo_root
from workhorse_workflows.author.shared.schemas.main import Defects, Ledger

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


__all__ = ["check_story_grounding", "record_attempt", "validate_story"]
