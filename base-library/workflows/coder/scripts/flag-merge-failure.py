#!/usr/bin/env python3
"""Merge give-up handler (coder). An epic's PR could not be merged by the
automated conflict-resolution loop within the maximum number of attempts. We
escalate to the operator: leave the PR open and unmerged, post a comment
explaining the situation, and let the workflow route to the RESUMABLE
await_merge_operator gate so the run pauses for review rather than finishing
on an unmerged PR.

Args: <epic> <base_branch> <attempts>. Prints JSON: {"merge_flagged": "yes|no"}.
PR-comment auth reuses the GitHub token env var configured in agents.yml
(workflow.githubTokenEnv), then GH_TOKEN, then GITHUB_TOKEN — resolved by
workhorse.scriptutil.resolve_github_token.
Exits 0 (the *halt* is await_merge_operator, not a non-zero exit here — a
non-zero exit would be reported as a script crash).
"""
from __future__ import annotations

import json
import logging
import sys

from workhorse.scriptutil import find_open_pr, find_repo_root, resolve_github_token, resolve_repo


def main(logger: logging.Logger) -> None:
    epic = sys.argv[1] if len(sys.argv) > 1 else ""
    base = sys.argv[2] if len(sys.argv) > 2 else "main"
    attempts = sys.argv[3] if len(sys.argv) > 3 else "?"
    br = f"feat/{epic}"

    root = find_repo_root()

    print(
        "=" * 60 + "\n"
        "⛔ MERGE FAILED — operator input required (expected, NOT a crash).\n"
        f"The PR for epic '{epic}' (branch {br} → {base}) could not be merged after\n"
        f"{attempts} automated conflict-resolution attempts. The run is stopping so\n"
        "you can investigate (merge conflict, branch protection, required reviews, or\n"
        "required CI checks that have not run).\n"
        f"Resolve the merge on {br}, then re-run the workflow to resume.\n"
        + "=" * 60,
        file=sys.stderr,
    )

    flagged = "no"
    token = resolve_github_token(root)
    if epic and token:
        repo, _ = resolve_repo(root, token)
        pr = find_open_pr(repo, br) if repo is not None else None
        if pr is not None:
            try:
                pr.create_issue_comment(
                    f"⛔ This PR could not be merged after {attempts} automated conflict-resolution "
                    f"attempts. The coder run paused here for manual review (merge conflict, branch "
                    f"behind `{base}`, branch protection, or required checks that did not run).",
                )
                flagged = "yes"
            except Exception as exc:
                logger.info("could not post PR comment for %s: %s", br, exc)
        else:
            logger.info("PR for %s not open — nothing to comment on", br)

    print(json.dumps({"merge_flagged": flagged}))


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    main(logging.getLogger("flag-merge-failure"))
