#!/usr/bin/env python3
"""CI give-up handler (coder). An epic's PR could not be turned green by the
automated fix loop within the maximum number of attempts. We escalate to the
operator: leave the PR open and red, post a comment explaining the situation,
and let the workflow route to its `fail` terminal so the run STOPS rather than
moving on to the next epic with a broken PR behind it.

Args: <epic> <attempts> <last_summary>. Prints JSON: {"ci_flagged": "yes|no"}.
PR-comment auth reuses the GitHub token env var configured in agents.yml
(workflow.githubTokenEnv), then GH_TOKEN, then GITHUB_TOKEN — resolved by
workhorse.scriptutil.resolve_github_token.
Exits 0 (the *halt* is the `fail` terminal the workflow routes to next, not a
non-zero exit here — a non-zero exit would be reported as a script crash).
"""
from __future__ import annotations

import json
import logging
import sys

from workhorse.scriptutil import find_open_pr, find_repo_root, resolve_github_token, resolve_repo


def main(logger: logging.Logger) -> None:
    epic = sys.argv[1] if len(sys.argv) > 1 else ""
    attempts = sys.argv[2] if len(sys.argv) > 2 else "?"
    summary = sys.argv[3] if len(sys.argv) > 3 else ""
    br = f"feat/{epic}"

    root = find_repo_root()

    print(
        "=" * 60 + "\n"
        "⛔ CI FAILED — operator input required (expected, NOT a crash).\n"
        f"The PR for epic '{epic}' (branch {br}) is still red after {attempts}\n"
        "automated fix attempts. The run is stopping so you can investigate.\n"
        f"  Last CI summary: {summary or '<none captured>'}\n"
        f"Fix CI on {br}, then re-run the workflow to resume.\n"
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
                    f"⛔ CI did not pass for this epic after {attempts} automated fix attempts. "
                    f"The coder run stopped here for manual review. Last summary: `{summary or 'none'}`.",
                )
                flagged = "yes"
            except Exception as exc:
                logger.info("could not post PR comment for %s: %s", br, exc)
        else:
            logger.info("PR for %s not open — nothing to comment on", br)

    print(json.dumps({"ci_flagged": flagged}))


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    main(logging.getLogger("flag-ci-failure"))
