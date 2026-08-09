"""The PR boundary: open it, merge it, and escalate when neither can be made to happen.

Ports `open-pr.py`, `gh-open-pr.py`, `merge-pr.py`, `flag-ci-failure.py`,
`flag-merge-failure.py` and story mode's `open-story-pr.py`.

**Two process layers collapse here, and that is the whole of what changes.** `open-pr.py`
was a seventeen-line `runpy.run_path` harness whose only job was to run `gh-open-pr.py`
in-process with a swapped `sys.argv` and stdout redirected to stderr, so that the helper's
prints could not corrupt the caller's JSON. `gh-open-pr.py` in turn spawned `push-epic.py`
as a **subprocess**, with `GH_TOKEN` injected into its environment so the child could
resolve the same credential the parent already held. Neither layer survives: the PR opener
is a plain function call below, and the push is `nodes.ci.push_epic_branch`, which resolves
its own token from the same repo root. No argv swap, no stdout redirect, no environment
mutation — the last of which also settles the "a node reads no environment variable" rule
for this group.

`gh-open-pr.py` does not become a node of its own. It never emitted anything: it is entirely
side effects (commit the prune, push, open the PR), and the workflow only ever reached it
through `open-pr.py`. A node whose output nothing reads is a node the run record cannot
explain, so it is `_open_epic_pr` here — a helper of the node that always called it.

The `[script-name]` log prefixes are gone as everywhere else, and the two give-up handlers'
stderr banners go to `logger.warning` instead of `print(file=sys.stderr)`. The banner is
operator-facing text, and the run record is where operator-facing text belongs now — a
`print` to stderr survives only as long as the terminal it scrolled past.

**The `main` default is not applied to a blank.** Each of these scripts read
`sys.argv[2] if len(sys.argv) > 2 else "main"`, and the YAML always passed the argument —
so an unrendered `base_branch` arrived as `""` and stayed `""`, not `"main"`. The parameter
defaults below reproduce that exactly: `"main"` when the caller omits the argument, `""`
when the caller passes an empty one. `open_story_pr` is the one that coerces (`base or
"main"`), because its script did, and that difference is preserved rather than smoothed.
"""
from __future__ import annotations

import logging
from pathlib import Path

from github import GithubException
from ostler import markdown, path as okf_path, registry
from workhorse_workflows.kit import find_repo_root, load_json
from workhorse_workflows.coder.shared import commits, paths
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.ci import push_epic_branch
from workhorse_workflows.coder.shared.queue import epics_set_aside
from workhorse_workflows.coder.shared.schemas.pr import (
    CiFlagged,
    MergeFlagged,
    MergeOutcome,
    PrGate,
    StoryPr,
)
from workhorse_workflows.kit import (
    branch_exists,
    checkout,
    commit_all,
    commit_paths,
    current_branch,
    find_open_pr,
    get_affected_repos,
    get_repo_config,
    is_ancestor,
    origin_url,
    push_branch,
    repo_full_name_from_url,
    resolve_github_token,
    resolve_repo,
    resolve_workspace,
    sync_to_origin,
)

#: Image suffixes counted as QA evidence when building a UI repo's PR body.
SCREENSHOT_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif")

#: The plan section quoted into a story PR's body. Where it stops is the parser's answer —
#: the next heading of the same level or shallower — not a lookahead for the next `## `,
#: which also stopped at a `## ` line inside a fenced code block.
PLAN_SUMMARY_HEADING = "1. Summary"

#: A repo whose QA runs a browser or a device driver gets screenshots in its PR body.
UI_QA_MODES = ("playwright", "maestro")


# ── The epic's PR ────────────────────────────────────────────────────────────────────


def _inherited_set_aside_epic(root: Path, run_dir: str, branch: str, base: str) -> str:
    """The first epic set aside this run whose *unmerged* work `branch` carries, or `""`.

    `branch_epic` cuts every epic branch from HEAD, not from the base — deliberately, so an
    epic can build on the one before it, which is the only reason a story that depends on a
    previous epic's code compiles at all. The cost is that a *failed* epic rides along too:
    `flag_epic_blocked` promises its work "stays on its branch, unmerged … NOT merged", and
    then the next epic's branch is cut on top of it and its PR targets trunk. Merging that
    PR merges the set-aside epic, past the gate that set it aside, without anyone reviewing
    the failure the gate was raised for.

    So containment is the question, not order: an epic branch that contains a set-aside
    epic's commits is not independently shippable and must not become a PR. It stays on disk
    for the manual review the gate asked for, and the run advances as it does offline.

    Contributed commits, though, not mere containment. An epic set aside before it committed
    anything leaves `feat/<epic>` pointing at the base, which is an ancestor of every later
    branch — so a bare containment test would let one story's early failure wedge the entire
    remaining queue. A branch the base already contains has nothing to smuggle past a gate.
    """
    for blocked in epics_set_aside(root, run_dir):
        blocked_branch = f"feat/{blocked}"
        if is_ancestor(root, blocked_branch, base):
            continue  # built nothing the base does not already have
        if is_ancestor(root, blocked_branch, branch):
            return blocked
    return ""


@blueprint.node
def open_pr(
    logger: logging.Logger,
    epic: str = "",
    base_branch: str = "main",
    run_dir: str = "",
    repo_dir: str = "",
) -> PrGate:
    """Open the finished epic's PR, and say whether there is anything to gate CI on.

    With no epic there is nothing to PR and nothing to gate: the queue was already pruned
    and committed onto the epic branch, HEAD is still on that branch, and the caller's next
    selection reads the pruned queue and advances. That is the offline path too — every
    failure inside `_open_epic_pr` is best-effort and leaves the branch for a manual PR,
    which is why this node still reports `should_gate` from the *epic*, not from whether
    GitHub could be reached.

    The one case that reports no gate *with* an epic is a branch carrying a set-aside epic —
    see :func:`_inherited_set_aside_epic` for why that cannot become a PR. The queue prune is
    still committed there, because the epic itself did finish and the next selection has to
    see it gone.
    """
    if not epic:
        logger.info("no epic — nothing to PR")
        return PrGate(ci_base=base_branch)

    root = find_repo_root(repo_dir)
    branch = f"feat/{epic}"
    _commit_queue_prune(logger, root, epic, branch)

    inherited = _inherited_set_aside_epic(root, run_dir, branch, base_branch)
    if inherited:
        logger.warning(
            "not opening a PR for %s: its branch contains epic '%s', which was set aside this "
            "run and needs manual review — opening it would merge that work past its own gate. "
            "%s is left on disk; review and merge '%s' first.",
            branch, inherited, branch, inherited,
        )
        return PrGate(ci_base=base_branch)

    _open_epic_pr(logger, epic, base_branch, repo_dir)
    return PrGate(should_gate=True, ci_epic=epic, ci_base=base_branch)


def _commit_queue_prune(logger: logging.Logger, root: Path, epic: str, branch: str) -> None:
    """Commit the queue prune onto the epic branch, best-effort.

    Before pushing, so it rides into the base with this epic's own merge rather than being
    lost at the next checkout — `branch_epic` restores `index.md` from the base, so an
    uncommitted prune does not survive to the next epic. Where the queue lives is ostler's
    answer, not a literal here.
    """
    if not branch_exists(root, branch):
        return
    prune = commits.message(
        "chore",
        commits.scope(root.name),
        "prune completed epic from queue",
        epic=epic,
    )
    if commit_paths(root, prune, paths.epics_index(root)):
        logger.info("committed index.md prune onto %s", branch)


def _epic_pr_title(root: Path, epic: str) -> str:
    """The epic PR's title: a Conventional Commit subject, because a squash merge makes it one.

    Under squash-merge — the default on most repos, and what a bot-authored epic branch
    usually gets — GitHub uses the PR title as the merge commit's subject, so this string is
    what release-please parses for the whole epic. `Epic: checkout` parses as nothing and
    releases nothing.

    The epic's own `# ` heading is the description where there is one; the epic name is the
    fallback, minus the sequence prefix that orders its folder.
    """
    name = registry.epic_slug(epic) or epic
    try:
        epic_md = okf_path.epic_dir_in(root, epic) / "epic.md"
        description = commits.story_description(root, str(epic_md.relative_to(root)), name)
    except (OSError, ValueError, RuntimeError):
        description = commits.describe(name)
    return commits.subject("feat", commits.scope(root.name), description)


def _open_epic_pr(logger: logging.Logger, epic: str, base: str, repo_dir: str = "") -> None:
    """Push the epic branch and open its PR. Best-effort throughout.

    Every early return leaves the branch unpushed or the PR unopened for a manual
    follow-up, and none of them is an error: an offline run, a token-less run and a
    non-github origin all reach the end of the epic and advance the queue.
    """
    branch = f"feat/{epic}"
    root = find_repo_root(repo_dir)

    if not branch_exists(root, branch):
        logger.info("no branch %s to PR", branch)
        return

    token = resolve_github_token(root)
    if not token:
        logger.info(
            "no GitHub token (set workflow.githubTokenEnv in agents.yml) — "
            "leaving %s for a manual PR",
            branch,
        )
        return
    if not origin_url(root):
        logger.info("no 'origin' remote — leaving %s for a manual PR", branch)
        return

    repo, slug = resolve_repo(root, token)
    if repo is None:
        logger.info(
            "origin is not a reachable github.com repo (%s) — leaving %s for a manual PR",
            slug, branch,
        )
        return

    push_epic_branch(logger, root, branch)

    if find_open_pr(repo, branch) is not None:
        logger.info("PR already open for %s", branch)
        return

    try:
        repo.create_pull(
            base=base,
            head=branch,
            title=_epic_pr_title(root, epic),
            body=(
                f"Automated epic PR for `{epic}`, generated by the coder workflow. "
                "One PR per epic; one commit per completed story.\n\n"
                "The title is a Conventional Commit subject on purpose: a squash merge "
                "makes it the only line release-please reads for this epic."
            ),
        )
    except Exception as exc:  # noqa: BLE001 - an unopened PR is a manual follow-up, not a failure
        logger.info("PR create failed for %s: %s", branch, exc)


@blueprint.node
def merge_pr(
    logger: logging.Logger, epic: str = "", base_branch: str = "main", repo_dir: str = ""
) -> MergeOutcome:
    """Merge the epic's PR into its base, then move the local checkout to the merged tip.

    Syncing the checkout is the load-bearing half: the next epic branches from whatever
    HEAD is on, so a merge that landed remotely but left the local base behind would branch
    the next epic off a tip missing this epic's work — including the queue prune that rode
    in with the PR.

    A resume after the merge already landed finds no *open* PR and would otherwise report
    `unavailable` and re-offer the same epic forever; `_find_merged_pr` is what makes that
    case report `merged` and sync, exactly as the first pass would have.
    """
    branch = f"feat/{epic}"

    if not epic:
        logger.info("no epic given — nothing to merge")
        return MergeOutcome(merge_status="unavailable", base_branch=base_branch)

    root = find_repo_root(repo_dir)

    token = resolve_github_token(root)
    if not token:
        logger.info(
            "no GitHub token (set workflow.githubTokenEnv in agents.yml) — leaving %s unmerged",
            branch,
        )
        return MergeOutcome(merge_status="unavailable", base_branch=base_branch)

    url = origin_url(root)
    if not url:
        logger.info("no 'origin' remote — leaving %s unmerged", branch)
        return MergeOutcome(merge_status="unavailable", base_branch=base_branch)

    repo_path = repo_full_name_from_url(url)
    if not repo_path:
        logger.info("origin '%s' is not a github.com remote — leaving %s unmerged", url, branch)
        return MergeOutcome(merge_status="unavailable", base_branch=base_branch)

    repo, _ = resolve_repo(root, token)
    if repo is None:
        logger.info("cannot reach github.com repo %s — leaving %s unmerged", repo_path, branch)
        return MergeOutcome(merge_status="unavailable", base_branch=base_branch)

    pr = find_open_pr(repo, branch)
    if pr is None:
        # No open PR. If one was already merged (e.g. a resume after the merge landed),
        # sync the base and report merged; otherwise there is nothing to do.
        if _find_merged_pr(repo, branch) is not None:
            logger.info("PR for %s already merged into %s", branch, base_branch)
            _sync_base(logger, root, base_branch, token)
            return MergeOutcome(merge_status="merged", base_branch=base_branch)
        logger.info("no open PR for %s — nothing to merge", branch)
        return MergeOutcome(merge_status="unavailable", base_branch=base_branch)

    method = _pick_merge_method(repo)
    logger.info("merging %s into %s with --%s", branch, base_branch, method)
    try:
        pr.merge(merge_method=method)
    except Exception as exc:  # noqa: BLE001 - conflict, protection or not-mergeable all read the same
        logger.info(
            "merge (--%s) failed for %s (merge conflict, branch protection, or not mergeable): "
            "%s — leaving PR open; next epic will branch from its tip",
            method, branch, exc,
        )
        return MergeOutcome(merge_status="failed", base_branch=base_branch)

    logger.info("merged %s into %s (--%s)", branch, base_branch, method)
    _sync_base(logger, root, base_branch, token)
    return MergeOutcome(merge_status="merged", base_branch=base_branch)


def _sync_base(logger: logging.Logger, root: Path, base: str, token: str) -> None:
    """Return the local checkout to `base` and pull it to the merged tip."""
    head = sync_to_origin(root, token, base)
    if head is None:
        logger.warning(
            "merged but could not sync local '%s' to the merged tip — leaving HEAD as-is; "
            "the next epic will branch from its current tip",
            base,
        )
        return
    logger.info("synced local '%s' to the merged tip (%s)", base, head)


def _pick_merge_method(repo) -> str:
    """The first merge method the repo allows, defaulting to a merge commit.

    The default is deliberately the one that may be rejected: guessing `squash` at a repo
    that forbids it produces a `failed` the merge gate can act on, whereas assuming nothing
    would need a fourth status nobody routes.
    """
    try:
        if repo.allow_merge_commit:
            return "merge"
        if repo.allow_squash_merge:
            return "squash"
        if repo.allow_rebase_merge:
            return "rebase"
    except Exception:  # noqa: BLE001 - an unreadable settings blob just means "assume merge"
        pass
    return "merge"


def _find_merged_pr(repo, branch: str):
    """The most recent MERGED PR for `branch` (the resume-after-merge case), else `None`."""
    owner = repo.owner.login
    for pr in repo.get_pulls(state="closed", head=f"{owner}:{branch}"):
        if pr.merged:
            return pr
    return None


# ── The two give-up handlers ─────────────────────────────────────────────────────────


@blueprint.node
def flag_ci_failure(
    logger: logging.Logger,
    epic: str = "",
    attempts: str = "?",
    summary: str = "",
    repo_dir: str = "",
) -> CiFlagged:
    """CI could not be turned green within the fix budget. Leave it red and say so.

    The PR stays open and red on purpose: the branch carries the epic's work, and closing
    or reverting it would throw away everything the run built to protect a clean queue.
    This node does not halt anything — the operator gate the flow routes to next does, and
    it is a *resumable* one, so re-running the workflow resets the fix counter and
    re-attempts the loop rather than dying in a terminal.
    """
    branch = f"feat/{epic}"
    root = find_repo_root(repo_dir)

    logger.warning(
        "%s\n"
        "⛔ CI FAILED — operator input required (expected, NOT a crash).\n"
        "The PR for epic '%s' (branch %s) is still red after %s\n"
        "automated fix attempts. The run is stopping so you can investigate.\n"
        "  Last CI summary: %s\n"
        "Fix CI on %s, then re-run the workflow to resume.\n"
        "%s",
        "=" * 60, epic, branch, attempts, summary or "<none captured>", branch, "=" * 60,
    )

    return CiFlagged(
        ci_flagged=_comment_on_pr(
            logger,
            root,
            epic,
            branch,
            f"⛔ CI did not pass for this epic after {attempts} automated fix attempts. "
            f"The coder run stopped here for manual review. Last summary: "
            f"`{summary or 'none'}`.",
        )
    )


@blueprint.node
def flag_merge_failure(
    logger: logging.Logger,
    epic: str = "",
    base_branch: str = "main",
    attempts: str = "?",
    repo_dir: str = "",
) -> MergeFlagged:
    """The PR could not be merged within the conflict-resolution budget. Say so and pause.

    The merge-side twin of `flag_ci_failure`, and pausing rather than finishing is the
    point: the failure mode this replaced was a run that reported success with the epic's
    PR left open and unmerged.
    """
    branch = f"feat/{epic}"
    root = find_repo_root(repo_dir)

    logger.warning(
        "%s\n"
        "⛔ MERGE FAILED — operator input required (expected, NOT a crash).\n"
        "The PR for epic '%s' (branch %s → %s) could not be merged after\n"
        "%s automated conflict-resolution attempts. The run is stopping so\n"
        "you can investigate (merge conflict, branch protection, required reviews, or\n"
        "required CI checks that have not run).\n"
        "Resolve the merge on %s, then re-run the workflow to resume.\n"
        "%s",
        "=" * 60, epic, branch, base_branch, attempts, branch, "=" * 60,
    )

    return MergeFlagged(
        merge_flagged=_comment_on_pr(
            logger,
            root,
            epic,
            branch,
            f"⛔ This PR could not be merged after {attempts} automated conflict-resolution "
            f"attempts. The coder run paused here for manual review (merge conflict, branch "
            f"behind `{base_branch}`, branch protection, or required checks that did not run).",
        )
    )


def _comment_on_pr(
    logger: logging.Logger, root: Path, epic: str, branch: str, body: str
) -> bool:
    """Post the give-up note on the epic's open PR. False whenever there is nowhere to post.

    Shared by both handlers because they differ only in their text. Comment auth is the
    workflow's ordinary GitHub token — the env var configured as `workflow.githubTokenEnv`
    in agents.yml, then `GH_TOKEN`, then `GITHUB_TOKEN` — resolved by the kit.
    """
    token = resolve_github_token(root)
    if not epic or not token:
        return False
    repo, _ = resolve_repo(root, token)
    pr = find_open_pr(repo, branch) if repo is not None else None
    if pr is None:
        logger.info("PR for %s not open — nothing to comment on", branch)
        return False
    try:
        pr.create_issue_comment(body)
    except Exception as exc:  # noqa: BLE001 - a note that did not land is never worth failing on
        logger.info("could not post PR comment for %s: %s", branch, exc)
        return False
    return True


# ── Story mode's PRs ─────────────────────────────────────────────────────────────────


@blueprint.node
def open_story_pr(
    logger: logging.Logger,
    story_slug: str = "",
    base_branch: str = "main",
    story_path: str = "",
    spec_dir: str = "",
    story_branch: str = "",
    repo_dir: str = "",
    workspace_file: str = "",
) -> StoryPr:
    """Story mode's terminal: one PR per affected **code** repo, none in the docs repo.

    Each PR carries the story's own heading as its title — as a Conventional Commit subject
    scoped to that repo, since a squash merge makes the title the released subject — and the
    plan's summary as its body,
    plus the QA screenshots for a repo whose QA drives a browser or a device. The
    PRs are left open for review and never auto-merged — epic mode's merge gate has no
    counterpart here.

    `story_branch` comes from the node that cut the branch, and is only re-derived from the
    slug for a hand invocation with nothing to read. The two drifted once: this script kept
    a `story/` prefix after the branching node dropped it, so every PR targeted a branch
    that had never been cut.

    **`base_branch` reaches nothing, and that is preserved rather than repaired.** The
    script read it, coerced it (`base = base or "main"`), and then never passed it anywhere:
    each PR's base comes from `_repo_base_branch`, whose own fallback is a separate literal
    `"main"`. So a run configured with a non-`main` base opened its story PRs against
    whatever each repo declared or probed to, never against the configured value. Wiring the
    parameter through would change behavior, and this port does not change behavior — the
    parameter stays, inert, and the defect is recorded in the progress ledger.

    Best-effort per repo, exactly as before: a missing path, a non-git directory, an
    unreachable origin or a failed push each skip that repo and are logged, and the node
    still reports whatever the other repos managed.
    """
    if not story_slug:
        logger.info("no story slug — nothing to PR")
        return StoryPr()

    branch = story_branch or story_slug
    root = find_repo_root(repo_dir)
    repos = resolve_workspace(workspace_file, repo_dir)

    spec = root / spec_dir if spec_dir else None
    plan_ctx = (
        load_json(spec / "plan-context.json", "plan-context.json", logger)
        if spec and spec.exists()
        else {}
    )
    affected = get_affected_repos(plan_ctx, repos)
    if not affected:
        logger.info("no affected repos resolved — nothing to PR")
        return StoryPr()

    description = commits.story_description(root, story_path, story_slug)
    summary = _plan_summary(spec) if spec else ""
    screenshots = _qa_screenshots(root, story_path)

    token = resolve_github_token(root)
    if not token:
        logger.info("no GitHub token — leaving %s for manual PRs", branch)
        return StoryPr()

    results: list[str] = []
    pr_urls: list[str] = []
    for name in affected:
        info = repos.get(name, {})
        repo_path = Path(info.get("path", ""))
        if not repo_path.is_dir():
            logger.warning("repo %s path not found: %s", name, repo_path)
            results.append("skipped")
            continue
        if not (repo_path / ".git").exists():
            logger.warning("repo %s is not a git repo — skipping", name)
            results.append("skipped")
            continue

        # Each code repo has its own default branch; the docs repo's base is not it.
        repo_base = _repo_base_branch(repo_path, name, repos)
        # Scoped to the repo it lands in, so a squash merge — which turns this title into
        # the merge commit's subject — releases that repo's package and no other.
        title = commits.subject("feat", commits.scope(name), description)
        _commit_in_repo(
            logger,
            repo_path,
            branch,
            commits.message("feat", commits.scope(name), description, story=story_slug),
        )

        body = _pr_body(summary, screenshots, _is_ui_repo(info))
        result, pr_url = _push_and_pr(logger, repo_path, branch, repo_base, title, body, token)
        results.append(result)
        if result in ("opened", "exists") and pr_url:
            pr_urls.append(pr_url)

    # Overall status: the best result across the repos wins.
    if "opened" in results:
        status = "opened"
    elif "exists" in results:
        status = "exists"
    else:
        status = "skipped"

    return StoryPr(story_pr=status, pr_urls=pr_urls)


def _plan_summary(spec_dir: Path) -> str:
    """The plan's `## 1. Summary`, trimmed to its first two paragraphs."""
    plan_file = spec_dir / "plan.md"
    if not plan_file.exists():
        return ""
    try:
        text = plan_file.read_text(encoding="utf-8")
    except OSError:
        return ""
    section = markdown.split(text).find_section(PLAN_SUMMARY_HEADING)
    if section is None:
        return ""
    paragraphs = [p.strip() for p in section.body.strip().split("\n\n") if p.strip()]
    return "\n\n".join(paragraphs[:2])


def _qa_screenshots(root: Path, story_path: str) -> list[str]:
    """The images under the story's `qa/` dir, repo-relative."""
    if not story_path:
        return []
    qa_dir = root / Path(story_path).parent / "qa"
    if not qa_dir.is_dir():
        return []
    return [
        str(f.relative_to(root))
        for f in sorted(qa_dir.rglob("*"))
        if f.suffix.lower() in SCREENSHOT_SUFFIXES
    ]


def _is_ui_repo(info: dict) -> bool:
    """Does this repo's QA drive a browser or a device? Then screenshots belong in its PR."""
    return info.get("qa_mode", "") in UI_QA_MODES


def _pr_body(summary: str, screenshots: list[str], is_ui: bool) -> str:
    """The PR description: the plan summary, the QA evidence, and the provenance note."""
    parts = []
    if summary:
        parts.append(f"## Summary\n\n{summary}")
    if is_ui and screenshots:
        parts.append("## QA Evidence\n")
        parts.append("Screenshots captured during QA (in the docs repo `qa/` dir):\n")
        for shot in screenshots[:6]:
            name = Path(shot).stem.replace("-", " ").replace("_", " ")
            parts.append(f"- `{shot}` — {name}")
    parts.append(
        "\n---\n*Automated story PR generated by the coder workflow (story mode). "
        "Left open for review — not auto-merged.*"
    )
    return "\n\n".join(parts)


def _repo_base_branch(repo_path: Path, name: str, repos: dict, fallback: str = "main") -> str:
    """The repo's declared base branch, else the first of develop/main/master it has."""
    declared = get_repo_config(name, "base_branch", repos=repos)
    if declared:
        return declared
    for candidate in ("develop", "main", "master"):
        if branch_exists(repo_path, candidate):
            return candidate
    return fallback


def _commit_in_repo(logger: logging.Logger, repo_path: Path, branch: str, message: str) -> None:
    """Commit whatever is pending in a code repo, on the story branch.

    A false `commit_all` here just means nothing was staged — the branch may already carry
    the story's commits ahead of base, which is fine and not worth surfacing.
    """
    if current_branch(repo_path) != branch and not (
        checkout(repo_path, branch) or checkout(repo_path, branch, create=True)
    ):
        logger.warning("cannot checkout %s in %s", branch, repo_path.name)
        return
    commit_all(repo_path, message)


def _push_and_pr(
    logger: logging.Logger,
    repo_path: Path,
    branch: str,
    base: str,
    title: str,
    body: str,
    token: str,
) -> tuple[str, str]:
    """Push one repo's story branch and open its PR: `(opened|exists|skipped, url)`."""
    if not branch_exists(repo_path, branch):
        logger.warning("no branch %s in %s", branch, repo_path.name)
        return "skipped", ""

    gh_repo, slug = resolve_repo(repo_path, token)
    if gh_repo is None:
        logger.warning(
            "%s: origin %s not a reachable github.com repo — skipping", repo_path.name, slug
        )
        return "skipped", ""

    if not push_branch(repo_path, token, branch, verify=False):
        logger.warning("push failed for %s in %s", branch, repo_path.name)
        return "skipped", ""

    existing = find_open_pr(gh_repo, branch)
    if existing is not None:
        logger.info("PR already open for %s in %s", branch, repo_path.name)
        return "exists", existing.html_url

    try:
        pr = gh_repo.create_pull(base=base, head=branch, title=title, body=body)
    except GithubException as exc:
        logger.warning("PR create failed in %s: %s", repo_path.name, exc)
        return "skipped", ""

    logger.info("opened PR for %s → %s in %s", branch, base, repo_path.name)
    return "opened", pr.html_url


__all__ = [
    "flag_ci_failure",
    "flag_merge_failure",
    "merge_pr",
    "open_pr",
    "open_story_pr",
]
