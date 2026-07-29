#!/usr/bin/env python3
"""Hard, deterministic per-story validator for the **bare-minimum** story contract — ostler-backed.

A story is intentionally lean: a Context section and Acceptance Criteria, nothing else.
The coder workflow owns the depth (plan, iterate implementation, file follow-ups, QA), so the
author no longer ships a long rubric — long stories still missed defects, and over-specification
just rots. This gate therefore checks only what the contract requires:

  - every required section of ``ostler.registry.STORY_SECTIONS`` is present, and the ones the
    contract marks ``filled`` carry prose (today: ``## Context``, ``## Acceptance Criteria``);
  - the ``- **Status**:`` bullet the coder's selector reads exists under
    ``## Implementation Status``;
  - no open questions / unresolved decisions shipped to the coder (TBD/TODO/hedges).

**The contract is ostler's, not this script's.** It used to keep its own list of required
sections and its own heading regex — a fourth opinion about what "written" means, in a tree that
already had three. Sections are checked with ``ostler.model.section_gaps`` against ostler's own
declaration, the Status field is located with ``ostler.model.status_bullet``, and the file is read
with ostler's markdown parser — so this validator and ``ostler doctor``'s ``unwritten-story``
finding can never disagree.

The story is parsed as a standalone file rather than looked up in the graph: this node runs right
after a story is written, and a story.md not yet listed in its epic's ``## Stories`` should still
be validated on its own terms (``validate-epic-coverage`` is what notices the missing block).

Any repo-specific authoring requirement is enforced by that repo's author *flavor* prompt, not by
this generic validator.

Args:
    argv[1]  story_dir        : repo-relative story folder (…/stories/<slug>)

Outputs JSON: {"story_ok": "yes"|"no", "story_errors": "<newline-joined>"}
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from ostler import markdown, registry
from ostler.model import section_gaps, status_bullet

# Multi-word phrases that signal an UNRESOLVED decision shipped to the coder. A story
# must RESOLVE every decision or escalate it via the writer's `blocked` status — it must not
# write the indecision into the story. These are deliberately specific so a *resolved*
# "Decision (recommended): keep X" does NOT match; only genuine open-endedness does.
OPEN_QUESTION_PHRASES = [
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
# Standalone code-style markers, matched as whole *words* — a word being a run of alphanumerics
# plus ``_`` and ``-``. So a filename like ``epics-todo.json`` is the single token "epics-todo"
# and does not trip the check, while a bare ``TODO decide later`` does.
OPEN_QUESTION_WORDS = {"tbd", "todo", "fixme"}
_WORD_CHARS = "_-"


def words(line: str) -> list[str]:
    """The line's words, a word running over alphanumerics plus ``_`` and ``-``."""
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


def find_open_questions(doc: markdown.MarkdownDoc) -> list[str]:
    """One error string per prose line that ships an unresolved decision/open question.

    Runs over the parsed document's prose — every body line that is not a heading — so a heading
    can never be the thing reported and the line numbers stay file-absolute.
    """
    headings = {s.line_start for s in doc.walk_sections() if s.level}
    hits: list[str] = []
    for i, raw in enumerate(doc.body.split("\n")):
        if i in headings:
            continue
        low = raw.lower()
        matched = [p for p in OPEN_QUESTION_PHRASES if p in low]
        matched += sorted({w.upper() for w in words(low) if w in OPEN_QUESTION_WORDS})
        if matched:
            snippet = raw.strip()
            if len(snippet) > 100:
                snippet = snippet[:97] + "..."
            line_no = doc.body_offset + i + 1
            hits.append(f"L{line_no}: open question / unresolved decision "
                        f"({', '.join(matched)}): {snippet}")
    return hits


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def main(logger: logging.Logger) -> None:
    story_dir_rel = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""

    errors: list[str] = []

    if not story_dir_rel:
        logger.warning("no story_dir supplied")
        print(json.dumps({"story_ok": "no", "story_errors": "no story_dir supplied"}))
        return

    story_md = find_repo_root() / story_dir_rel / "story.md"

    if not story_md.is_file():
        logger.warning("story.md missing at %s", story_md)
        print(json.dumps({"story_ok": "no", "story_errors": f"story.md missing at {story_md}"}))
        return

    doc = markdown.split(story_md.read_text(encoding="utf-8"))

    if status_bullet(doc) is None:
        errors.append(f"no `- **{registry.STORY_STATUS_LABEL}**:` bullet under "
                      f"`## {registry.STORY_STATUS_HEADING}` (coder's selector reads this)")

    for spec, gap in section_gaps(doc, registry.STORY_SECTIONS):
        errors.append(f"required section `## {spec.heading}` is {gap}")

    # A coder-ready story leaves NO decision for the coder to make. Reject any open
    # question / unresolved-decision marker; the writer must resolve it (pick + justify)
    # or escalate via `blocked` instead of writing the indecision into the story.
    errors.extend(find_open_questions(doc))

    ok = "no" if errors else "yes"
    logger.info("story %s: %d error(s)", story_dir_rel, len(errors))
    print(json.dumps({"story_ok": ok, "story_errors": "\n".join(errors)}))


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("validate-story"))
