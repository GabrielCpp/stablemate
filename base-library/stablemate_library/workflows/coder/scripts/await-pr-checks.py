#!/usr/bin/env python3
"""Wait for the GitHub PR checks on an epic branch to finish, then report the
outcome so the workflow can gate on a green PR before moving on.

Args: <epic> [<base_branch>=main] [<pr_number>]

Always exits 0 (the *outcome* is in the JSON, not the exit code) — a non-zero
exit would halt the whole run, but a red CI is a normal, handled state here
(it drives the fix loop).

Auth: the GitHub token env var configured in agents.yml (workflow.githubTokenEnv),
else GH_TOKEN, else GITHUB_TOKEN — resolved by gh-token.py. All git/gh chatter
goes to stderr so stdout stays valid JSON.

CI state is read from the GitHub Actions runs API (gh api .../actions/runs),
NOT `gh pr checks` — see the long comment by the poll loop for why (fine-grained
PATs can't read the check-runs resource, but CAN read Actions runs).

Outputs JSON: {"ci_status": "passed|failed|unavailable", "ci_summary": "<text>"}
  passed      — every Actions run on the PR head commit concluded successfully.
  failed      — at least one run did not succeed, or the watch timed out pending.
  unavailable — CI could not be queried (no token / gh / origin / open PR / no
                Actions runs / auth or permission error). Treated as a pass-through
                by the workflow so offline, CI-less, and read-blocked runs keep
                working (best-effort) — loudly logged so it is never silent.

A wall-clock ceiling is enforced (CI_WATCH_TIMEOUT, default 1200s; poll cadence
CI_POLL_INTERVAL, default 30s) so a never-settling pipeline can't hang the run.

NOTE: this script deliberately does NOT use workhorse.scriptutil.find_repo_root()
or AGENT_REPO_DIR. workhorse sets cwd: on the node to the repo root already;
AGENT_REPO_DIR is set by workhorse to the launch dir (the prompt-library
checkout), so using it here would override the per-node cwd and point at the
wrong repo. Operate on Path.cwd() directly.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from pathlib import Path

from lib import ghutil

logger = logging.getLogger(__name__)

FAIL_CONCLUSIONS = '"failure","timed_out","cancelled","startup_failure","action_required","stale"'
AUTH_RE = re.compile(
    r"resource not accessible|bad credentials|HTTP 40[13]|requires authentication|gh auth login|must authenticate|SAML",
    re.IGNORECASE,
)
NO_RUNS_POLL_LIMIT = 6


def emit(status: str, summary: str) -> None:
    print(json.dumps({"ci_status": status, "ci_summary": summary}))


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    epic = sys.argv[1] if len(sys.argv) > 1 else ""
    # base (argv[2]) accepted for symmetry with the other PR scripts; not used here.
    pr_number = sys.argv[3] if len(sys.argv) > 3 else ""
    br = epic
    # Use the explicit PR number when given — branch name lookup can resolve to a
    # previously-closed PR when multiple PRs have been opened on the same branch.
    pr_ref = pr_number or br

    if not epic:
        logger.info("no branch given — nothing to gate")
        emit("unavailable", "no branch given")
        return

    root = Path.cwd()
    scripts_dir = Path(__file__).resolve().parent

    token = ghutil.resolve_gh_token(scripts_dir)
    if not token:
        logger.info("no GitHub token (set workflow.githubTokenEnv in agents.yml) — cannot query CI for %s", br)
        emit("unavailable", "no GitHub token")
        return
    if not ghutil.gh_available():
        logger.info("gh CLI not found — cannot query CI for %s", br)
        emit("unavailable", "gh CLI not found")
        return
    if not ghutil.origin_url(root):
        logger.info("no 'origin' remote — cannot query CI for %s", br)
        emit("unavailable", "no origin remote")
        return

    env = {**os.environ, "GH_TOKEN": token}

    # Existence check via --json: the default `gh pr view` query pulls
    # `projectCards`, which now errors out with a "Projects (classic) is being
    # deprecated" GraphQL message and a non-zero exit even when the PR exists —
    # which would make us bail as if there were no PR. Restricting to a single
    # JSON field avoids that field.
    if ghutil.run(["gh", "pr", "view", pr_ref, "--json", "number"], root, env=env).returncode != 0:
        logger.info("no open PR for %s — cannot gate on CI", pr_ref)
        emit("unavailable", f"no open PR for {pr_ref}")
        return

    # Gate on the GitHub Actions runs API rather than `gh pr checks` / `gh run
    # view`. Those porcelain commands read the *check-runs* (and annotations)
    # resources, which a fine-grained PAT CANNOT access ("Resource not
    # accessible by personal access token", HTTP 403) even with Actions:Read
    # granted — there is no fine-grained "Checks" permission for user tokens.
    # The Actions runs/jobs/logs REST API, by contrast, IS readable with
    # Actions:Read, so the gate (and the fix-ci agent) use it. This keeps a
    # least-privilege fine-grained token working — no classic PAT (which would
    # grant access to everything) and no GitHub App required.
    origin_url = ghutil.origin_url(root) or ""
    repo_path = ghutil.repo_path_from_url(origin_url)
    if not repo_path:
        logger.info("origin '%s' is not a github.com remote — cannot query CI for %s", origin_url, br)
        emit("unavailable", "origin not a github.com remote")
        return

    # Judge the PR head commit specifically, so stale runs on earlier commits of
    # the branch don't pollute the verdict. (headRefOid avoids the projectCards
    # field.)
    head_sha = ghutil.run(
        ["gh", "pr", "view", pr_ref, "--json", "headRefOid", "-q", ".headRefOid"], root, env=env, timeout=60,
    ).stdout.strip()
    if not head_sha:
        logger.info("could not resolve head SHA for %s — cannot gate on CI", pr_ref)
        emit("unavailable", f"could not resolve head SHA for {pr_ref}")
        return

    runs_api = f"repos/{repo_path}/actions/runs?head_sha={head_sha}&per_page=100"
    counts_jq = (
        '"\\(.workflow_runs|length) '
        '\\([.workflow_runs[]|select(.status!="completed")]|length) '
        f'\\([.workflow_runs[]|select(.conclusion|IN({FAIL_CONCLUSIONS}))]|length)"'
    )
    names_jq = (
        f'[.workflow_runs[]|select(.conclusion|IN({FAIL_CONCLUSIONS}))'
        '|"\\(.name)#\\(.id)(\\(.conclusion))"]|join(", ")'
    )

    watch_timeout = int(os.environ.get("CI_WATCH_TIMEOUT", "1200"))
    poll_interval = int(os.environ.get("CI_POLL_INTERVAL", "30"))
    start = time.monotonic()
    no_runs_polls = 0

    while True:
        result = ghutil.run(["gh", "api", runs_api, "--jq", counts_jq], root, env=env, timeout=60)
        counts = result.stdout.strip()

        if result.returncode != 0 or not counts:
            err = result.stderr or ""
            match = AUTH_RE.search(err)
            if match:
                reason_line = next((line for line in err.splitlines() if AUTH_RE.search(line)), "")
                reason = reason_line.replace('"', "").strip()[:200] or "GitHub auth/permission error"
                logger.info(
                    "cannot read Actions runs for %s — auth/permission error; treating as unavailable "
                    "(pass-through). Grant the token Actions:Read.",
                    br,
                )
                logger.info("%s", err)
                emit("unavailable", f"CI unreadable: {reason}")
                return
            logger.info("transient error querying Actions runs for %s (gh exit %s) — retrying", br, result.returncode)
            logger.info("%s", err)
        else:
            parts = counts.split()
            total = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
            pending = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            failed = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

            if total == 0:
                no_runs_polls += 1
                if no_runs_polls >= NO_RUNS_POLL_LIMIT:
                    logger.info(
                        "no Actions runs for %s@%s after %d polls — treating as no CI configured",
                        br, head_sha, no_runs_polls,
                    )
                    emit("unavailable", f"no Actions runs for {br}")
                    return
                logger.info("no Actions runs for %s@%s yet (poll %d) — waiting", br, head_sha, no_runs_polls)
            elif pending > 0:
                logger.info("%d/%d run(s) still in progress for %s — waiting", pending, total, br)
            elif failed > 0:
                # All runs settled, at least one not green → red CI. Summarize the
                # failing workflow(s) + run ids so the fix-ci agent can pull their
                # job logs.
                names = ghutil.run(["gh", "api", runs_api, "--jq", names_jq], root, env=env, timeout=60).stdout.strip()
                if not names:
                    names = f"{failed} of {total} run(s) failed"
                logger.info("CI not green for %s@%s: %s", br, head_sha, names)
                emit("failed", names.replace('"', "")[:300])
                return
            else:
                logger.info("CI passed for %s@%s (%d run(s) succeeded)", br, head_sha, total)
                emit("passed", f"all {total} Actions run(s) succeeded")
                return

        if time.monotonic() - start >= watch_timeout:
            logger.info("CI watch timed out after %ds for %s (runs never settled)", watch_timeout, br)
            emit("failed", f"watch timed out after {watch_timeout}s (Actions runs never settled)")
            return

        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
