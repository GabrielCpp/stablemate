#!/usr/bin/env python3
"""QA give-up handler (coder). A story failed automated QA after the maximum
rework attempts. We do NOT halt the epic queue: instead we
  1. commit the story's current state behind a clear marker, so the work is
     preserved and shows up in the epic PR diff + commit list for the reviewer;
  2. best-effort comment on the epic PR (only possible once that PR is open —
     during the story loop it usually isn't yet, so the marker commit is the
     reliable signal); then
  3. let the workflow continue to the next story.

Args: <epic> <story_slug> <attempts> [<story_path>] [<run_dir>].
  story_path — explicit story.md path (else derived from root/epic/slug).
  run_dir    — the current run directory; when given, the story slug is added to a
               per-run skip set so select-next-story.py excludes it for the rest of
               this run (belt-and-suspenders over the status marking below).
Prints JSON: {"qa_flagged": "yes"|"no"}.
PR-comment auth uses the configured GitHub token (see
workhorse.scriptutil.resolve_github_token / agents.yml).
All git/GitHub chatter goes to stderr so stdout stays valid JSON.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from workhorse import scriptutil
from workhorse.scriptutil import find_repo_root, fresh_import

logger = logging.getLogger(__name__)


def record_skip(run_dir_arg: str, slug: str) -> None:
    if not run_dir_arg or not slug:
        return
    run_dir = Path(run_dir_arg)
    run_dir.mkdir(parents=True, exist_ok=True)
    skip_file = run_dir / "qa-skip-stories.txt"
    existing = skip_file.read_text(encoding="utf-8").splitlines() if skip_file.exists() else []
    if slug not in existing:
        with skip_file.open("a", encoding="utf-8") as f:
            f.write(f"{slug}\n")


def main(logger: logging.Logger) -> None:
    epic = sys.argv[1] if len(sys.argv) > 1 else ""
    slug = sys.argv[2] if len(sys.argv) > 2 else "story"
    attempts = sys.argv[3] if len(sys.argv) > 3 else "?"
    story_path_arg = sys.argv[4] if len(sys.argv) > 4 else ""
    run_dir_arg = sys.argv[5] if len(sys.argv) > 5 else ""

    root = find_repo_root()

    marker = f"[QA FAILED after {attempts} attempts — needs manual review]"
    # Deliberately does NOT say "QA passed": this is a give-up, not a pass, and the
    # status text is what a human (and select-next-story.py's fallback _is_done())
    # reads to judge whether the story's work is trustworthy. A give-up must never
    # claim to have passed — dependents of this story should stay blocked, since
    # they depend on work that did NOT actually pass (see select-next-story.py's
    # _next_from_json docstring: "A skipped story is NOT treated as done"). Both
    # story-selection paths already skip a given-up story WITHOUT needing the text
    # to say "passed": (1) ostler `next-story` (the PRIMARY selector) reads the
    # story.md FRONTMATTER `status:` field, which this sets to the same honest
    # value; (2) select-next-story.py's per-run skip set (record_skip below)
    # excludes it for the rest of THIS run regardless of the status text. A fresh
    # run (or an operator clearing the skip set) will legitimately retry it.
    new_status = f"QA give-up after {attempts} attempts — needs manual review"

    # Graph-first, story.md body as the fallback — see story_status.mark. Imported
    # fresh so a mid-run edit to ostler (an environment-fix loop landing a change
    # while QA nodes are still ahead in the graph) is not shadowed by the copy
    # cached in sys.modules from an earlier node.
    story_status = fresh_import("story_status", also_purge=("ostler",))
    story_status.mark(root, slug, new_status, epic=epic, story_path=story_path_arg, logger=logger)

    # Per-run skip set: record this story so select-next-story.py excludes it
    # for the REMAINDER OF THIS RUN even if the status marking above did not
    # take (ostler absent AND the story.md not found). The file lives inside the
    # run dir, so a fresh run starts with an empty set (the story is retried)
    # and an operator resets by clearing it.
    record_skip(run_dir_arg, slug)

    if scriptutil.commit_all(root, f"{epic}: {slug} {marker}"):
        committed = "yes"
    else:
        logger.info("nothing to commit for %s (no changes, or the commit failed)", slug)
        committed = "no"

    # Best-effort PR comment: only lands if the epic PR is already open (e.g. on
    # a resume after the PR exists). Otherwise the marker commit carries the flag.
    br = f"feat/{epic}"
    token = scriptutil.resolve_github_token(root)
    if token:
        repo, _ = scriptutil.resolve_repo(root, token)
        pr = scriptutil.find_open_pr(repo, br) if repo is not None else None
        if pr is not None:
            try:
                pr.create_issue_comment(
                    f"⚠️ Story `{slug}` did not pass automated QA after {attempts} rework attempts. "
                    f"It was committed behind the marker `{marker}` for manual review.",
                )
            except Exception as exc:
                logger.info("could not post PR comment for %s: %s", slug, exc)
        else:
            logger.info("epic PR for %s not open yet — relying on the marker commit to flag %s", br, slug)

    print(json.dumps({"qa_flagged": committed}))


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    main(logging.getLogger("flag-qa-failure"))
