#!/usr/bin/env python3
"""Push an epic branch to GitHub over HTTPS, authenticating with a token.

Args: <epic>. Writes only to stderr (no stdout) so callers that emit JSON on
stdout (gh-open-pr.py -> open-pr.py) stay clean.

Exit code is the contract (the CI loop's push-ci.py maps it to a push_status):
  0   pushed      — the push succeeded AND the remote branch head now equals
                   the local head (verified, so a silent no-op can't
                   masquerade as a successful push and burn the fix loop
                   against a stale remote).
  10  unavailable — nothing to push or no way to push (no epic / no branch /
                   no token / no origin / non-github remote). Tolerated:
                   offline and CI-less runs still complete; the branch is
                   left for a manual push.
  20  failed      — a push was ATTEMPTED but did not land (auth/permission
                   denied, rejected non-fast-forward, network, or the remote
                   head did not advance). The caller surfaces this instead of
                   silently looping.

gh-open-pr.py calls this best-effort and ignores the exit code (offline
PR-open must not halt); the CI fix loop branches on it.

Auth: the GitHub token env var configured in agents.yml (workflow.githubTokenEnv),
else GH_TOKEN, else GITHUB_TOKEN — resolved by workhorse.scriptutil.resolve_github_token. The token is
supplied to `git push` via an inline credential helper that reads it from the
environment — it is never written into a remote URL, git config, or the
logs. Shared by gh-open-pr.py (initial PR push) and the CI fix loop
(re-push after a fix) so the secret-handling lives in exactly one place.
"""
from __future__ import annotations

import logging
import sys

from workhorse.scriptutil import (
    branch_exists,
    find_repo_root,
    origin_url,
    push_branch,
    repo_full_name_from_url,
    resolve_github_token,
)

logger = logging.getLogger(__name__)

UNAVAILABLE = 10
FAILED = 20


def main() -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    epic = sys.argv[1] if len(sys.argv) > 1 else ""
    if not epic:
        logger.info("no branch given — nothing to push")
        return UNAVAILABLE
    br = epic

    # Script nodes run with cwd = the workflow definition's own directory (the
    # prompt-library checkout), NOT the consuming repo — AGENT_REPO_DIR is
    # pinned by the Makefile/workhorse to the actual repo root and is
    # inherited by every script-node subprocess, so resolve through it first.
    root = find_repo_root()

    if not branch_exists(root, br):
        logger.info("no branch %s to push", br)
        return UNAVAILABLE

    token = resolve_github_token(root)
    if not token:
        logger.info("no GitHub token (set workflow.githubTokenEnv in agents.yml) — leaving %s unpushed", br)
        return UNAVAILABLE

    url = origin_url(root)
    if not url:
        logger.info("no 'origin' remote — leaving %s unpushed", br)
        return UNAVAILABLE

    if not repo_full_name_from_url(url):
        logger.info("origin '%s' is not a github.com remote — leaving %s unpushed", url, br)
        return UNAVAILABLE

    # push_branch pushes over HTTPS with the token in a transient credential helper,
    # then VERIFIES the remote branch head advanced to the local head. A push can
    # report success while leaving the remote unchanged (an "Everything up-to-date"
    # pointing at a stale ref) — an unverified push is exactly what let the CI fix
    # loop spin against an unmoved PR head until its attempts ran out. A False here
    # therefore means the push was attempted but did not land (or did not verify).
    if not push_branch(root, token, br):
        logger.info(
            "push failed or unverified for %s (auth/permission/network/non-fast-forward, "
            "or the remote head did not advance) — NOT silently ignored; surfacing as a failure",
            br,
        )
        return FAILED

    logger.info("pushed %s (remote head verified)", br)
    return 0


if __name__ == "__main__":
    sys.exit(main())
