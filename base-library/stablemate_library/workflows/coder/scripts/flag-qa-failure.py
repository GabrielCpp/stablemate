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
PR-comment auth uses the configured GitHub token (see gh-token.py / agents.yml).
All git/gh chatter goes to stderr so stdout stays valid JSON.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from workhorse.scriptutil import find_repo_root

from lib import ghutil

logger = logging.getLogger(__name__)

STATUS_LINE_RE = re.compile(r"^- \*\*Status\*\*:.*$", re.MULTILINE)


def mark_via_ostler(root: Path, slug: str, new_status: str) -> bool:
    if not slug or not shutil.which("ostler"):
        return False
    result = subprocess.run(
        ["ostler", "-C", str(root), "set-status", slug, new_status],
        stdout=sys.stderr, stderr=sys.stderr, text=True, check=False,
    )
    if result.returncode != 0:
        logger.info("ostler set-status failed for %s — falling back to story.md edit", slug)
        return False
    return True


def resolve_story_path(root: Path, epic: str, slug: str, story_path_arg: str) -> Path:
    if story_path_arg and Path(story_path_arg).is_file():
        return Path(story_path_arg)
    return root / "docs" / "epics" / epic / "stories" / slug / "story.md"


def rewrite_status(story_md: Path, new_status: str) -> None:
    text = story_md.read_text(encoding="utf-8")
    if STATUS_LINE_RE.search(text):
        # Rewrite via a temp file + os.replace rather than editing in place, so a
        # write failure can't leave story.md half-written (portable equivalent of
        # the bash original's mktemp+mv, which existed to dodge GNU/BSD `sed -i`
        # incompatibilities entirely).
        new_text = STATUS_LINE_RE.sub(f"- **Status**: {new_status}", text, count=1)
        fd, tmp_name = tempfile.mkstemp(dir=story_md.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(new_text)
            os.replace(tmp_name, story_md)
        except OSError:
            os.unlink(tmp_name)
            logger.warning("WARNING: could not rewrite Status in %s", story_md)
    else:
        with story_md.open("a", encoding="utf-8") as f:
            f.write(f"- **Status**: {new_status}\n")


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


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    epic = sys.argv[1] if len(sys.argv) > 1 else ""
    slug = sys.argv[2] if len(sys.argv) > 2 else "story"
    attempts = sys.argv[3] if len(sys.argv) > 3 else "?"
    story_path_arg = sys.argv[4] if len(sys.argv) > 4 else ""
    run_dir_arg = sys.argv[5] if len(sys.argv) > 5 else ""

    root = find_repo_root()
    scripts_dir = Path(__file__).resolve().parent

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

    # `ostler set-status` updates BOTH the frontmatter and the body; fall back to
    # a body edit only when ostler is unavailable or can't resolve the slug (e.g.
    # non-standard test layouts).
    marked = mark_via_ostler(root, slug, new_status)

    story_md = resolve_story_path(root, epic, slug, story_path_arg)
    if not marked and story_md.is_file():
        rewrite_status(story_md, new_status)

    # Per-run skip set: record this story so select-next-story.py excludes it
    # for the REMAINDER OF THIS RUN even if the status marking above did not
    # take (ostler absent AND the story.md not found). The file lives inside the
    # run dir, so a fresh run starts with an empty set (the story is retried)
    # and an operator resets by clearing it.
    record_skip(run_dir_arg, slug)

    subprocess.run(["git", "add", "-A"], cwd=str(root), stdout=sys.stderr, stderr=sys.stderr, text=True, check=False)
    diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=str(root), capture_output=True, text=True, check=False,
    )
    if diff.returncode == 0:
        logger.info("no changes to commit for %s", slug)
        committed = "no"
    else:
        commit = subprocess.run(
            ["git", "commit", "-m", f"{epic}: {slug} {marker}"],
            cwd=str(root), stdout=sys.stderr, stderr=sys.stderr, text=True, check=False,
        )
        if commit.returncode == 0:
            committed = "yes"
        else:
            logger.info("commit failed for %s", slug)
            committed = "no"

    # Best-effort PR comment: only lands if the epic PR is already open (e.g. on
    # a resume after the PR exists). Otherwise the marker commit carries the flag.
    br = f"feat/{epic}"
    token = ghutil.resolve_gh_token(scripts_dir)
    if token and ghutil.gh_available():
        env = {**os.environ, "GH_TOKEN": token}
        if ghutil.run(["gh", "pr", "view", br, "--json", "number"], root, env=env).returncode == 0:
            comment = ghutil.run(
                [
                    "gh", "pr", "comment", br, "--body",
                    f"⚠️ Story `{slug}` did not pass automated QA after {attempts} rework attempts. "
                    f"It was committed behind the marker `{marker}` for manual review.",
                ],
                root, env=env, timeout=60, echo=True,
            )
            if comment.returncode != 0:
                logger.info("could not post PR comment for %s", slug)
        else:
            logger.info("epic PR for %s not open yet — relying on the marker commit to flag %s", br, slug)

    print(json.dumps({"qa_flagged": committed}))


if __name__ == "__main__":
    main()
