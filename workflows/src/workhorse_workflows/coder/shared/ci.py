"""The CI fix loop's deterministic work: the repo pick, the poll, the push.

Ports `select-ci-fix-repo.py`, `await-pr-checks.py`, `push-ci.py` and `push-epic.py`.
`resolve-workspace-dirs.py` was ported here too while `fix_ci` was the only flow that had
it; it now lives in `shared/story.py` as `resolve_workspace_dirs`, because `dev`, `review`,
`docs` and `qa` all run the same forty lines and one of them had to be the definition. The
old node name survives as an alias on it, so an in-flight CI run still resumes.

**The repo a node works on is a parameter now, not the process's cwd.** Every node in the
YAML's `fix_ci` graph carried `cwd: {{ current_repo_cwd }}`, and `await-pr-checks.py` has a
long note explaining that it must therefore use `Path.cwd()` and specifically *not*
`find_repo_root()`, because the launch checkout would override the per-node cwd. A node
here runs in the engine's own process, so there is no per-node cwd to inherit from — the
directory arrives as `repo_dir` instead, which is what the flow always meant and what the
`cwd:` field was a mechanism for.

That surfaces a latent defect in the YAML rather than creating one: `push-ci.py` ran
`push-epic.py`, which resolves with `find_repo_root()` and so *did* prefer the launch
checkout. In a multi-repo workspace the CI loop polled one repo's PR and pushed a
different repo's branch. It is recorded as a finding in the progress
ledger; `push_ci_fix` takes `repo_dir` like its neighbours and only falls back to
`find_repo_root()` when handed nothing, which is the single-repo case the YAML got right.

Two subprocess artifacts are gone. `push-ci.py` was fifty lines of `runpy.run_path`,
`sys.argv` swapping and `redirect_stdout` whose entire purpose was to reuse another
script's **exit code** from inside a third process; `push_epic_branch` below is that
script's body, returning the status string directly. And the `[script-name]` log prefixes
are gone, as everywhere else in the port.
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from github import GithubException
from workhorse_workflows.kit import find_repo_root
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.ci import CiChecks, CiRepoPick, PushOutcome
from workhorse_workflows.kit import (
    branch_exists,
    find_open_pr,
    origin_url,
    push_branch,
    repo_full_name_from_url,
    resolve_github_token,
    resolve_repo,
    resolve_workspace,
)

def epic_branch(epic: str) -> str:
    """The branch an epic's work lives on — the one its PR is opened from.

    A helper rather than a literal because the CI gate is handed the *epic* and every
    GitHub lookup needs the *branch*. Passing the bare epic name to `poll_pr_checks` finds
    no PR (its head is `feat/<epic>`, never `<epic>`), and the gate reports `unavailable`,
    which the flow passes through by design — so a whole epic merges with CI never
    consulted and nothing in the log distinguishes that from an offline run.
    """
    return f"feat/{epic}" if epic else ""


#: An Actions run in any of these states is red. `cancelled` and `stale` are included
#: deliberately: neither is evidence the branch is good, and treating them as green is how
#: a broken pipeline reads as a passing one.
FAIL_CONCLUSIONS = frozenset(
    {"failure", "timed_out", "cancelled", "startup_failure", "action_required", "stale"}
)

#: What a GitHub error message looks like when the token cannot read what was asked for,
#: as opposed to a transient outage. The status code is checked first; this catches the
#: cases GitHub reports with a 200 and an explanatory body.
AUTH_RE = re.compile(
    r"resource not accessible|bad credentials|HTTP 40[13]|requires authentication"
    r"|gh auth login|must authenticate|SAML",
    re.IGNORECASE,
)

#: Consecutive polls that find no Actions runs at all before the repo is called CI-less.
#: Not one poll: a run takes a moment to be queued after a push.
NO_RUNS_POLL_LIMIT = 6


@blueprint.node
def select_ci_repo(
    logger: logging.Logger,
    repo: str = "",
    processed: list[str] | None = None,
    workspace_file: str = "",
    launch_dir: str = "",
) -> CiRepoPick:
    """The next repo whose CI has not been looked at yet, or "none left".

    `processed` is what makes the loop terminate, and a repo joins it the moment it is
    *picked* rather than when its CI settles — so a repo whose CI fails and exhausts the
    fix budget is still not revisited.

    A named `repo` pins the loop to that one repo; a repo named but absent from the
    workspace is a warning and an empty pick, not a failure, because a workspace that does
    not carry it is a configuration difference rather than a broken run.
    """
    seen = list(processed or [])
    repos = resolve_workspace(workspace_file, launch_dir)

    if repo:
        if repo in seen:
            return CiRepoPick(processed=seen)
        if repo not in repos:
            logger.warning("repo '%s' not found in workspace — skipping", repo)
            return CiRepoPick(processed=seen)
        return _picked(repo, repos[repo], seen, launch_dir)

    for name, info in repos.items():
        if name not in seen:
            return _picked(name, info, seen, launch_dir)
    return CiRepoPick(processed=seen)


def _picked(name: str, info: dict, processed: list[str], launch_dir: str = "") -> CiRepoPick:
    """`name` chosen, and appended to the processed list the caller carries onward."""
    return CiRepoPick(
        has_repo=True,
        repo=name,
        repo_cwd=str(info.get("path", find_repo_root(launch_dir))),
        processed=[*processed, name],
    )


@blueprint.node
def poll_pr_checks(
    logger: logging.Logger,
    repo_dir: str,
    branch: str,
    pr_number: str = "",
    watch_timeout: int = 1200,
    poll_interval: int = 30,
) -> CiChecks:
    """Block until the PR's Actions runs settle, then report `passed`/`failed`/`unavailable`.

    CI state is read from the **Actions runs** API rather than the check-runs resource. A
    fine-grained PAT cannot access check-runs at all ("Resource not accessible by personal
    access token", HTTP 403) even with Actions:Read granted — there is no fine-grained
    "Checks" permission for user tokens — while the Actions runs/jobs/logs REST API is
    readable with it. Gating on Actions is what keeps a least-privilege token working, with
    no classic PAT and no GitHub App.

    Every way of *not knowing* is `unavailable`, and the flow treats that as a pass-through
    so offline, CI-less and read-blocked runs still complete. It is logged loudly at each
    site so it is never silent.

    The verdict is judged on the PR **head commit**, so stale runs on earlier commits of
    the branch cannot pollute it. `watch_timeout` (1200s) bounds the wait and
    `poll_interval` (30s) sets the cadence; a never-settling pipeline reports `failed`
    rather than hanging the run. Both are arguments rather than environment, so a flow that
    wants a different cadence says so where the node is called.
    """
    if not branch:
        logger.info("no branch given — nothing to gate")
        return CiChecks(status="unavailable", summary="no branch given")

    root = Path(repo_dir) if repo_dir else find_repo_root()
    # An explicit PR number wins over the branch lookup: a branch that has carried more
    # than one PR can resolve to a closed one.
    pr_ref = pr_number or branch

    token = resolve_github_token(root)
    if not token:
        logger.info(
            "no GitHub token (set workflow.githubTokenEnv in agents.yml) — cannot query CI for %s",
            branch,
        )
        return CiChecks(status="unavailable", summary="no GitHub token")
    if not origin_url(root):
        logger.info("no 'origin' remote — cannot query CI for %s", branch)
        return CiChecks(status="unavailable", summary="no origin remote")

    repo, slug = resolve_repo(root, token)
    if repo is None:
        logger.info(
            "origin '%s' is not a reachable github.com repo — cannot query CI for %s", slug, branch
        )
        return CiChecks(status="unavailable", summary="origin not a reachable github.com remote")

    pr = _resolve_pr(repo, pr_ref)
    if pr is None:
        logger.info("no open PR for %s — cannot gate on CI", pr_ref)
        return CiChecks(status="unavailable", summary=f"no open PR for {pr_ref}")

    try:
        head_sha = pr.head.sha
    except GithubException:
        head_sha = ""
    if not head_sha:
        logger.info("could not resolve head SHA for %s — cannot gate on CI", pr_ref)
        return CiChecks(
            status="unavailable", summary=f"could not resolve head SHA for {pr_ref}"
        )

    return _watch(logger, repo, branch, head_sha, watch_timeout, poll_interval)


def _resolve_pr(repo, pr_ref: str):
    """The PR by explicit number, else the open one whose head is that branch."""
    if pr_ref.isdigit():
        try:
            return repo.get_pull(int(pr_ref))
        except GithubException:
            return None
    return find_open_pr(repo, pr_ref)


def _poll_runs(repo, head_sha: str) -> tuple[int, int, int, str]:
    """`(total, pending, failed, failing_names)` for the Actions runs on `head_sha`.

    The failing entries carry the run **id** as well as the name, because that is what
    lets the fixer agent pull the job logs rather than guess from a workflow name.
    """
    total = pending = failed = 0
    failing: list[str] = []
    for wr in repo.get_workflow_runs(head_sha=head_sha):
        total += 1
        if wr.status != "completed":
            pending += 1
        if wr.conclusion in FAIL_CONCLUSIONS:
            failed += 1
            failing.append(f"{wr.name}#{wr.id}({wr.conclusion})")
    return total, pending, failed, ", ".join(failing)


def _watch(
    logger: logging.Logger,
    repo,
    branch: str,
    head_sha: str,
    watch_timeout: int = 1200,
    poll_interval: int = 30,
) -> CiChecks:
    """The poll loop, until the runs settle or the wall-clock ceiling is reached."""
    start = time.monotonic()
    no_runs_polls = 0

    while True:
        try:
            total, pending, failed, names = _poll_runs(repo, head_sha)
        except GithubException as exc:
            settled = _auth_failure(logger, exc, branch)
            if settled is not None:
                return settled
            logger.info(
                "transient error querying Actions runs for %s (%s) — retrying", branch, exc
            )
        else:
            if total == 0:
                no_runs_polls += 1
                if no_runs_polls >= NO_RUNS_POLL_LIMIT:
                    logger.info(
                        "no Actions runs for %s@%s after %d polls — treating as no CI configured",
                        branch, head_sha, no_runs_polls,
                    )
                    return CiChecks(
                        status="unavailable", summary=f"no Actions runs for {branch}"
                    )
                logger.info(
                    "no Actions runs for %s@%s yet (poll %d) — waiting",
                    branch, head_sha, no_runs_polls,
                )
            elif pending > 0:
                logger.info(
                    "%d/%d run(s) still in progress for %s — waiting", pending, total, branch
                )
            elif failed > 0:
                # Settled, and at least one is not green. The summary names the failing
                # workflows and their run ids so the fixer can pull the job logs.
                names = names or f"{failed} of {total} run(s) failed"
                logger.info("CI not green for %s@%s: %s", branch, head_sha, names)
                return CiChecks(status="failed", summary=names.replace('"', "")[:300])
            else:
                logger.info(
                    "CI passed for %s@%s (%d run(s) succeeded)", branch, head_sha, total
                )
                return CiChecks(
                    status="passed", summary=f"all {total} Actions run(s) succeeded"
                )

        if time.monotonic() - start >= watch_timeout:
            logger.info(
                "CI watch timed out after %ds for %s (runs never settled)", watch_timeout, branch
            )
            return CiChecks(
                status="failed",
                summary=f"watch timed out after {watch_timeout}s (Actions runs never settled)",
            )

        time.sleep(poll_interval)


def _auth_failure(logger: logging.Logger, exc: GithubException, branch: str) -> CiChecks | None:
    """`unavailable` when the token cannot read Actions, `None` when it is worth retrying."""
    err = str(getattr(exc, "data", "") or exc)
    if getattr(exc, "status", None) not in (401, 403) and not AUTH_RE.search(err):
        return None
    reason = err.replace('"', "").strip()[:200] or "GitHub auth/permission error"
    logger.info(
        "cannot read Actions runs for %s — auth/permission error; treating as unavailable "
        "(pass-through). Grant the token Actions:Read.",
        branch,
    )
    logger.info("%s", err)
    return CiChecks(status="unavailable", summary=f"CI unreadable: {reason}")


def push_epic_branch(logger: logging.Logger, root: Path, branch: str) -> str:
    """Push `branch` from `root` over HTTPS: `pushed`, `unavailable` or `failed`.

    `push-epic.py`'s body, with its exit-code contract as a return value. The three
    outcomes are distinct on purpose:

    * `unavailable` — nothing to push, or no way to push it (no branch, no token, no
      origin, a non-github remote). Tolerated, so offline and CI-less runs still complete;
      the branch is left for a manual push.
    * `failed` — a push was **attempted** and did not land, or landed without the remote
      head advancing. `push_branch` verifies that head, because a push can report success
      while leaving the ref unmoved, and an unverified push is exactly what let the CI fix
      loop spin against an unmoved PR head until its attempts ran out.
    * `pushed` — the push landed and the remote head was verified equal to the local one.

    Not a node: two callers reach it, this module's `push_ci_fix` and the main graph's
    PR step, and both want the status rather than a recorded node output.
    """
    if not branch:
        logger.info("no branch given — nothing to push")
        return "unavailable"
    if not branch_exists(root, branch):
        logger.info("no branch %s to push", branch)
        return "unavailable"

    token = resolve_github_token(root)
    if not token:
        logger.info(
            "no GitHub token (set workflow.githubTokenEnv in agents.yml) — leaving %s unpushed",
            branch,
        )
        return "unavailable"

    url = origin_url(root)
    if not url:
        logger.info("no 'origin' remote — leaving %s unpushed", branch)
        return "unavailable"
    if not repo_full_name_from_url(url):
        logger.info("origin '%s' is not a github.com remote — leaving %s unpushed", url, branch)
        return "unavailable"

    if not push_branch(root, token, branch):
        logger.info(
            "push failed or unverified for %s (auth/permission/network/non-fast-forward, "
            "or the remote head did not advance) — NOT silently ignored; surfacing as a failure",
            branch,
        )
        return "failed"

    logger.info("pushed %s (remote head verified)", branch)
    return "pushed"


@blueprint.node
def push_ci_fix(logger: logging.Logger, repo_dir: str, branch: str) -> PushOutcome:
    """Push the CI fix, so the next poll has a new head to judge.

    `repo_dir` is the repo the loop picked. It falls back to `find_repo_root()` only when
    handed nothing, which is the single-repo case; see the module docstring for why the
    YAML's resolution could pick the wrong repo here.
    """
    root = Path(repo_dir) if repo_dir else find_repo_root()
    status = push_epic_branch(logger, root, branch)
    return PushOutcome(status=status, notes=f"{status} {branch} from {root}")


__all__ = [
    "epic_branch",
    "poll_pr_checks",
    "push_ci_fix",
    "push_epic_branch",
    "select_ci_repo",
]
