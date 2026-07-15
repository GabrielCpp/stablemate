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
else GH_TOKEN, else GITHUB_TOKEN — resolved by gh-token.py. The token is
supplied to `git push` via an inline credential helper that reads it from the
environment — it is never written into a remote URL, git config, or the
logs. Shared by gh-open-pr.py (initial PR push) and the CI fix loop
(re-push after a fix) so the secret-handling lives in exactly one place.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from workhorse.scriptutil import find_repo_root

from lib import ghutil

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
    scripts_dir = Path(__file__).resolve().parent

    if not ghutil.branch_exists(br, root):
        logger.info("no branch %s to push", br)
        return UNAVAILABLE

    token = ghutil.resolve_gh_token(scripts_dir)
    if not token:
        logger.info("no GitHub token (set workflow.githubTokenEnv in agents.yml) — leaving %s unpushed", br)
        return UNAVAILABLE

    url = ghutil.origin_url(root)
    if not url:
        logger.info("no 'origin' remote — leaving %s unpushed", br)
        return UNAVAILABLE

    repo_path = ghutil.repo_path_from_url(url)
    if not repo_path:
        logger.info("origin '%s' is not a github.com remote — leaving %s unpushed", url, br)
        return UNAVAILABLE
    push_url = f"https://github.com/{repo_path}.git"

    env = {**os.environ, "GH_TOKEN": token}
    push = ghutil.run(
        ["git", "-c", f"credential.helper={ghutil.CRED_HELPER}", "push", push_url, f"{br}:{br}"],
        root, env=env, timeout=120, echo=True,
    )
    if push.returncode != 0:
        logger.info(
            "push failed for %s (auth/permission/network/non-fast-forward) — NOT silently ignored; surfacing as a failure",
            br,
        )
        return FAILED

    # Verify the remote head actually advanced to the local head. A push can
    # report success while leaving the remote unchanged (e.g. an
    # "Everything up-to-date" that really points at a stale ref) — an
    # unverified push is exactly what let the CI fix loop spin against an
    # unmoved PR head until its attempts ran out.
    local_head = ghutil.run(["git", "rev-parse", br], root).stdout.strip()
    ls_remote = ghutil.run(
        ["git", "-c", f"credential.helper={ghutil.CRED_HELPER}", "ls-remote", push_url, f"refs/heads/{br}"],
        root, env=env, timeout=60,
    )
    remote_head = ls_remote.stdout.split()[0] if ls_remote.stdout.split() else ""
    if not remote_head or remote_head != local_head:
        logger.info(
            "remote %s head (%s) does not match local (%s) after push — treating as failed",
            br, remote_head, local_head,
        )
        return FAILED

    logger.info("pushed %s (remote head verified at %s)", br, local_head)
    return 0


if __name__ == "__main__":
    sys.exit(main())
