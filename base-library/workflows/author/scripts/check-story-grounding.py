#!/usr/bin/env python3
"""Thin deterministic grounding pre-gate for a written story — ostler-backed (fail-closed).

``validate-story.py`` checks a story is *structurally* a coder-ready contract. It cannot check
that the story is *grounded* — that the surface was actually researched and (when feature docs
are configured) its user journey was actually read. This gate enforces those machine-checkable
preconditions so the adversarial ``audit-story`` agent isn't wasted re-judging a story that
structurally cannot be grounded. It is the author analog of the coder's ``verify_qa_evidence.py``.

Strictly presence/structure — **no semantic judgment** (that is the auditor's job):

  - every seed item this story ``covers`` exists in the epic's seeds (no phantom scope) — read
    from ``epic.md`` via the in-process ostler API (``Ostler.list``);
  - a surface **knowledge record** (a ``knowledge`` Concept) exists that this story grounds in
    (matched generously by slug / seed-item / legacy-surface tokens — proves gather_knowledge ran);
  - **iff** ``features_dir`` is configured: that matched record actually read the feature
    doc / journey — its ``journeys[]`` is non-empty OR ``provenance.sourcesRead`` references a
    path under ``features_dir`` (proves the journey grounding ran, not just that a record exists).

Stdlib-only except for the in-process ``ostler`` API (``from ostler import Ostler``) and PyYAML,
which ships with the system interpreter, to read the matched record's front-matter for the journey
check.

Args:
    argv[1]  story_dir      : repo-relative story folder (…/stories/<slug>)
    argv[2]  epic_dir       : repo-relative epic folder (docs/epics/<epic>)
    argv[3]  knowledge_dir  : repo-relative knowledge-record root (informational)
    argv[4]  features_dir   : repo-relative feature-doc root ('' ⇒ presence-only grounding)

Outputs JSON: {"story_grounding_ok": "yes"|"no", "story_grounding_errors": "<newline-joined>"}
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import NoReturn

from ostler import Ostler

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML ships with the system interpreter here
    yaml = None

_FRONT_MATTER_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*(?:\n|$)", re.S)


def load_record(text: str) -> dict:
    """Parse a knowledge record (``.md`` with YAML front-matter)."""
    if text.lstrip().startswith("---"):
        m = _FRONT_MATTER_RE.match(text)
        if not m or yaml is None:
            return {}
        try:
            data = yaml.safe_load(m.group(1))
        except yaml.YAMLError:
            return {}
        return data if isinstance(data, dict) else {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def emit(ok: bool, errors: list[str]) -> NoReturn:
    print(json.dumps({
        "story_grounding_ok": "yes" if ok else "no",
        "story_grounding_errors": "\n".join(errors),
    }))
    sys.exit(0)


def norm(s: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-")


def tokens(s: object) -> set[str]:
    """Meaningful (≥3 char) sub-tokens of a normalized string."""
    return {t for t in norm(s).split("-") if len(t) >= 3}


def main(logger: logging.Logger) -> None:
    story_dir_rel = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    epic_dir_rel = sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else ""
    features_dir = sys.argv[4].strip() if len(sys.argv) > 4 and sys.argv[4] else ""

    errors: list[str] = []
    if not story_dir_rel or not epic_dir_rel:
        logger.warning("story_dir and epic_dir are required — nothing to check")
        emit(False, ["story_dir and epic_dir are required"])

    root = find_repo_root()
    okf = Ostler(root)
    slug = Path(story_dir_rel).name
    epic = Path(epic_dir_rel).name

    # ── this epic's seed ids + this story's covered seed items (read from epic.md) ──
    try:
        seeds = okf.list("seed", epic=epic)
    except (OSError, ValueError, RuntimeError):
        logger.warning("could not read the epic's seeds via the ostler API for %s", epic)
        emit(False, ["could not read the epic's seeds via the ostler API"])
    seed_by_id = {str(s.get("id", "")).strip(): s for s in seeds if s.get("id")}
    seed_ids = set(seed_by_id)

    stories = okf.list("story", epic=epic)
    story_row = next((s for s in stories if str(s.get("slug", "")).strip() == slug), None)
    story_seed_items = [str(x).strip() for x in ((story_row or {}).get("covers") or [])]

    for sid in story_seed_items:
        if seed_ids and sid not in seed_ids:
            errors.append(f"story claims seed item '{sid}' that is not in the epic's seeds (phantom scope)")

    # legacySurface / currentState of this story's seed items strengthen record matching.
    legacy_surfaces: list[str] = []
    for sid in story_seed_items:
        s = seed_by_id.get(sid, {})
        legacy_surfaces += [s.get("legacySurface"), s.get("currentState")]

    # ── a knowledge record exists that this story grounds in ──
    needles: set[str] = tokens(slug)
    for sid in story_seed_items:
        needles |= tokens(sid)
    for ls in legacy_surfaces:
        needles |= tokens(ls)

    records = okf.list("knowledge")
    matched_path: str | None = None
    if needles:
        for rec in records:
            rec_tokens = (tokens(rec.get("surface")) | tokens(rec.get("route"))
                          | tokens(Path(str(rec.get("path", ""))).stem))
            if needles & rec_tokens:
                matched_path = str(rec.get("path", ""))
                break

    if matched_path is None:
        logger.info("no surface knowledge record grounds story '%s'", slug)
        errors.append(
            "no surface knowledge record grounds this story — gather_knowledge must research the "
            "surface (a knowledge Concept whose surface/route matches this story) before it can be "
            "written"
        )

    # ── feature-doc / journey grounding actually ran (only when features_dir configured) ──
    if features_dir and matched_path:
        record = {}
        rec_file = root / matched_path
        if rec_file.is_file():
            record = load_record(rec_file.read_text(encoding="utf-8"))
        journeys = record.get("journeys")
        sources = (record.get("provenance") or {}).get("sourcesRead") or []
        feat_norm = norm(features_dir)
        read_feature_doc = any(feat_norm and feat_norm in norm(s) for s in sources)
        has_journeys = isinstance(journeys, list) and len(journeys) > 0
        if not (has_journeys or read_feature_doc):
            logger.info("journey grounding did not run for story '%s'", slug)
            errors.append(
                "feature docs are configured but this surface's knowledge record records no "
                "user journey (empty `journeys[]` and no `provenance.sourcesRead` under "
                f"'{features_dir}') — the journey grounding did not run"
            )

    logger.info("story '%s' grounding: %s", slug, "ok" if not errors else f"{len(errors)} error(s)")
    emit(not errors, errors)


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("check-story-grounding"))
