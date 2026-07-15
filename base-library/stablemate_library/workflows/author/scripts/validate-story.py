#!/usr/bin/env python3
"""Hard, deterministic per-story validator for the **bare-minimum** story contract.

A story is intentionally lean: a Context section and Acceptance Criteria, nothing else.
The coder workflow owns the depth (plan, iterate implementation, file follow-ups, QA), so the
author no longer ships a long rubric — long stories still missed defects, and over-specification
just rots. This gate therefore checks only what the contract requires:

  - ``story.md`` exists and has a ``- **Status**:`` line (what coder's selector parses).
  - ``## Context`` is present and non-empty.
  - ``## Acceptance Criteria`` is present and non-empty.
  - no open questions / unresolved decisions shipped to the coder (TBD/TODO/hedges).

Any repo-specific authoring requirement is enforced by that repo's author *flavor* prompt, not by
this generic validator.

Stdlib-only: scripts run under the system ``python3``, not the uv venv.

Args:
    argv[1]  story_dir        : repo-relative story folder (…/stories/<slug>)

Outputs JSON: {"story_ok": "yes"|"no", "story_errors": "<newline-joined>"}
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Each required section: a label + the keywords any of which a heading may contain.
# Bare-minimum contract — Context (what & why) + Acceptance Criteria (how it's judged).
REQUIRED_SECTIONS = [
    ("Context", ["context"]),
    ("Acceptance Criteria", ["acceptance"]),
]

_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")

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
# Standalone code-style markers, guarded so filenames like ``epics-todo.json`` and words
# like "methodology" do not trip the check.
_OPEN_QUESTION_WORD_RE = re.compile(r"(?<![\w-])(tbd|todo|fixme)(?![\w-])", re.IGNORECASE)


def find_open_questions(text: str) -> list[str]:
    """Return one error string per line that ships an unresolved decision/open question."""
    hits: list[str] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        low = raw.lower()
        matched = [p for p in OPEN_QUESTION_PHRASES if p in low]
        word = _OPEN_QUESTION_WORD_RE.search(raw)
        if word:
            matched.append(word.group(1).upper())
        if matched:
            snippet = raw.strip()
            if len(snippet) > 100:
                snippet = snippet[:97] + "..."
            hits.append(f"L{i}: open question / unresolved decision ({', '.join(matched)}): {snippet}")
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


def parse_sections(text: str) -> list[tuple[str, str]]:
    """Return [(heading_lower, body)] for each markdown heading in order."""
    sections: list[tuple[str, list[str]]] = []
    preamble: list[str] = []
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            sections.append((m.group(1).strip().lower(), []))
        elif sections:
            sections[-1][1].append(line)
        else:
            preamble.append(line)
    return [(h, "\n".join(b).strip()) for h, b in sections]


def section_present(sections: list[tuple[str, str]], keywords: list[str]) -> bool:
    for heading, body in sections:
        if any(k in heading for k in keywords) and body.strip():
            return True
    return False


def main() -> None:
    story_dir_rel = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""

    errors: list[str] = []

    if not story_dir_rel:
        print(json.dumps({"story_ok": "no", "story_errors": "no story_dir supplied"}))
        return

    root = find_repo_root()
    story_dir = root / story_dir_rel
    story_md = story_dir / "story.md"

    if not story_md.is_file():
        print(json.dumps({"story_ok": "no", "story_errors": f"story.md missing at {story_md}"}))
        return

    text = story_md.read_text(encoding="utf-8")
    sections = parse_sections(text)

    if not any(line.strip().startswith("- **Status**:") for line in text.splitlines()):
        errors.append("no `- **Status**:` line (coder's selector parses this)")

    for label, keywords in REQUIRED_SECTIONS:
        if not section_present(sections, keywords):
            errors.append(f"missing or empty required section: {label}")

    # A coder-ready story leaves NO decision for the coder to make. Reject any open
    # question / unresolved-decision marker; the writer must resolve it (pick + justify)
    # or escalate via `blocked` instead of writing the indecision into the story.
    errors.extend(find_open_questions(text))

    ok = "no" if errors else "yes"
    print(json.dumps({"story_ok": ok, "story_errors": "\n".join(errors)}))


if __name__ == "__main__":
    main()
