"""The whole-run gates, and the git tail that ships what they passed.

Ported from `base-library/workflows/author/scripts/{reconcile-artifacts,ostler-doctor,
validate-artifacts,commit-author,open-author-pr}.py`.

Two divergences from the scripts, both recorded rather than absorbed:

* `open_author_pr` resolves the GitHub token by calling `kit.github.resolve_github_token`
  directly, where the script spawned `gh-token.py` as a subprocess and read its stdout.
  `gh-token.py` *is* a one-line wrapper over that function, so the resolution order is
  identical — the subprocess was the only way a YAML script could share code with another
  script's process. It joins the deletion list.
* `open_author_pr` uses `kit.github.find_open_pr` instead of the script's private copy.
  The kit version swallows a `GithubException` while listing, so an API error there now
  reads as "no PR is open" and the failure surfaces one step later, from `create_pull`,
  with its own message. Both paths still fail the node.

The two YAML nodes `commit_author` and `commit_incomplete` ran the *same* script with a
different first argument, so they are one node here, called with `mode="incomplete"` on
the failure edge. They sit on mutually exclusive paths, so `self.output(commit_author)`
still names exactly one commit.
"""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler, markdown, registry, select
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.kit import find_repo_root
from workhorse_workflows.author.main.nodes._blueprint import blueprint
from workhorse_workflows.author.main.nodes import _stubs
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.paths import launch_repo_root, survey_repo_root
from workhorse_workflows.author.shared.schemas.main import Committed, Defects, PullRequest, VerifyReport
from workhorse_workflows.kit import branch_exists, commit_paths, remote_urls, show_file
from workhorse_workflows.kit import github as github_kit

# ── reconciliation: what this run silently dropped ──────────────────────────


def _subsection_ids(text: str, heading: str) -> set[str]:
    """The `### <id>` titles directly under the `## <heading>` section of an epic.md.

    Read off the parsed heading tree, so a `##`-looking line inside a fenced example is not a
    section and the nesting is the parser's rather than a "still inside it" flag.
    """
    ids: set[str] = set()
    for root in markdown.split(text or "").sections:
        for section in root.walk():
            if section.level == 2 and section.title.strip().lower() == heading.lower():
                ids.update(c.title.strip() for c in section.children if c.level == 3)
    return ids


@blueprint.node(stub=_stubs.holds)
def verify_reconcile(
    logger: logging.Logger,
    epics_dir: str = "",
    ref: str = "HEAD",
    repo_dir: str = "",
) -> VerifyReport:
    """Scope this run silently dropped, measured against the last committed epics.

    `ostler doctor` catches *dangling* references; it does not catch a **clean removal** —
    an IDed entity deleted along with every reference to it. That is the "dropped scope"
    failure: a re-run re-derives an epic and quietly omits a seed item a prior run
    committed, leaving nothing dangling to find. So this compares the parsed `epic.md`
    subsection ids on both sides.

    **Removals block, additions don't**, and it is fail-open on infrastructure: no git, no
    epics dir, or no epic with a committed baseline is a clean `skipped`, never a block.
    """
    ref = ref.strip() or "HEAD"
    root = launch_repo_root(repo_dir)
    epics_rel = paths.epics_dir(root, epics_dir)
    epics_path = root / epics_rel

    if show_file(root, ref, epics_rel) is None and not (root / ".git").exists():
        logger.info("not a git repo at %s — reconciliation gate skipped", root)
        return VerifyReport(skipped=True, report="not a git repo — reconciliation gate skipped")
    if not epics_path.is_dir():
        logger.info("no epics dir at %s — skipped", epics_path)
        return VerifyReport(skipped=True, report=f"no epics dir at {epics_rel} — skipped")

    drops: list[str] = []
    checked = 0
    for epic_md in sorted(epics_path.glob("*/epic.md")):
        epic = epic_md.parent.name
        base = show_file(root, ref, str(epic_md.relative_to(root)))
        if base is None:
            continue  # brand-new epic (no committed baseline) — nothing to reconcile
        checked += 1
        now = epic_md.read_text(encoding="utf-8")

        for sid in sorted(_subsection_ids(base, "Seeds") - _subsection_ids(now, "Seeds")):
            drops.append(
                f"  - [dropped-seed] ({epic}) seed item '{sid}' was committed but is "
                f"absent now — confirm it was intentionally dropped (record the reason), "
                f"or restore it"
            )
        for slug in sorted(_subsection_ids(base, "Stories") - _subsection_ids(now, "Stories")):
            drops.append(
                f"  - [dropped-story] ({epic}) story '{slug}' was committed but is "
                f"absent now — confirm intentional, or restore it"
            )

    if checked == 0:
        logger.info("no epics with a committed baseline at %s — skipped", ref)
        return VerifyReport(
            skipped=True, report=f"no epics with a committed baseline at {ref} — skipped"
        )

    summary = f"reconcile vs {ref}: {checked} epic(s) checked, {len(drops)} silent drop(s)"
    logger.info(summary)
    if not drops:
        return VerifyReport(holds=True, report=summary)

    lines = [
        "This run silently removed planning entities that a prior run committed.",
        "Each is a scope drop with no dangling reference left for `ostler doctor` to catch.",
        "Confirm each was intentional (record the disposition/reason) or restore it — a silent",
        "removal of prior scope is a regression, not a clean re-derivation.",
        "",
        *drops,
    ]
    return VerifyReport(errors="\n".join(lines), report=summary)


# ── referential integrity of the whole graph ────────────────────────────────


@blueprint.node(stub=_stubs.holds)
def verify_integrity(
    logger: logging.Logger,
    epic: str = "",
    epics_dir: str = "",
    repo_dir: str = "",
) -> VerifyReport:
    """`ostler doctor` over the whole graph, as a blocking gate.

    The per-epic coverage validator proves seeds map to stories *within* an epic; story
    grounding proves one story rests on real seeds. Neither catches the cross-run drift
    here: a story referencing another epic's seed, a reference resolving to nothing.
    ostler *computes* those facts; this turns its error-level findings into a gate.

    **Errors block, warnings don't**, and an unloadable graph is a `skipped` — the same
    opt-in-by-presence stance the other author gates take. `epic` blank means the whole
    graph, which is what the final gate wants.
    """
    okf = Ostler(launch_repo_root(repo_dir), doc_roots={"epics": epics_dir} if epics_dir else {})

    outcome = okf.doctor(epic=epic.strip() or None)
    if outcome.status == "invalid":
        logger.warning("%s — skipped", outcome.message)
        return VerifyReport(skipped=True, report=f"{outcome.message} — skipped")

    report = outcome.data
    findings = report.get("findings", [])
    errors = [f for f in findings if f.get("severity") == "error"]
    warns = [f for f in findings if f.get("severity") == "warn"]
    summary = (
        f"ostler doctor [{report.get('org', '?')}/{report.get('profile', '?')}]: "
        f"{len(errors)} error(s), {len(warns)} warning(s)"
    )
    logger.info(summary)

    if not errors:
        return VerifyReport(holds=True, report=summary)

    lines = [
        "ostler doctor found referential-integrity errors in the planning-doc graph.",
        "Each is a graph break (a reference that resolves to nothing, or to the wrong epic).",
        "Reconcile each with `ostler edit` (relink / rename) or escalate — never",
        "delete a reference or fabricate an entity to silence the check.",
        "",
    ]
    for f in errors:
        scope = f.get("epic") or f.get("ref") or ""
        scope = f" ({scope})" if scope else ""
        lines.append(f"  - [{f.get('code', '?')}]{scope} {f.get('message', '')}")
    return VerifyReport(errors="\n".join(lines), report=summary)


# ── the last gate before the run may report success ─────────────────────────


def _is_done(status: str) -> bool:
    return select.is_done(status)


def _canonical_epic_names(okf: Ostler, names: list[str]) -> list[str]:
    resolved: list[str] = []
    seen: set[str] = set()
    for name in names:
        try:
            epic = Path(okf.epic_path(name)).name
        except (OSError, ValueError, RuntimeError):
            epic = name
        if epic not in seen:
            resolved.append(epic)
            seen.add(epic)
    return resolved


@blueprint.node(stub=_stubs.clean)
def validate_artifacts(logger: logging.Logger, repo_dir: str = "") -> Defects:
    """Can the coder engine actually walk what this run produced?

    A valid epics queue, every queued epic loadable with at least one story, every story
    **authored** by ostler's verdict, and at least one story still selectable — otherwise
    the coder has nothing to run.

    This gate used to accept a `story.md` that merely existed and carried a
    `- **Status**:` line, both of which `ostler create story` writes into the scaffold. A
    queue of 44 empty stubs passed here, the run reported success and opened a PR. An
    unauthored story is now an error that names the epic, the slug and the empty sections,
    and it does not count toward `selectable`.

    The YAML passed `epics_dir` here for the node's contract and the script never read it:
    ostler discovers the graph's doc roots itself. This takes no arguments.
    """
    okf = Ostler(survey_repo_root(repo_dir))

    try:
        queue = okf.todo()
    except (OSError, ValueError, RuntimeError):
        reason = "could not read the epics index via ostler's in-process API"
        logger.warning(reason)
        return Defects(errors=reason)
    if not queue:
        seen: set[str] = set()
        for milestone in okf.graph.milestones:
            for epic in milestone.epics:
                name = str(epic).strip()
                if name and name not in seen:
                    queue.append(name)
                    seen.add(name)
    if not queue:
        queue = [epic.name for epic in okf.graph.epics]
    queue = _canonical_epic_names(okf, queue)
    if not queue:
        logger.info("no epics found in todo, milestones, or graph")
        return Defects(errors="no epics found in todo, milestones, or graph")

    by_epic: dict[str, list[dict]] = {}
    for s in okf.list("story"):
        by_epic.setdefault(str(s.get("epic", "")), []).append(s)

    # An epic ostler could not load has no epic.md — the graph's own answer, so this node
    # never stats a file and never gets a second opinion about what a document must contain.
    loadable = {e.name for e in okf.graph.epics}

    errors: list[str] = []
    selectable = 0
    for raw_epic in queue:
        epic = str(raw_epic)
        if epic not in loadable:
            errors.append(f"epic '{epic}': epic.md missing (ostler cannot load the epic)")
        stories = by_epic.get(epic, [])
        if not stories:
            errors.append(f"epic '{epic}': lists no stories in `## Stories`")
            continue
        for s in stories:
            slug = s.get("slug", "?")
            path = s.get("path", "")
            if not s.get("hasStoryMd"):
                errors.append(
                    f"epic '{epic}' story '{slug}': story.md missing at {path or '<no path>'}"
                )
            elif not s.get("authored"):
                empty = ", ".join(s.get("unwrittenSections") or []) or "its required sections"
                errors.append(
                    f"epic '{epic}' story '{slug}': story.md is still a bare scaffold "
                    f"({empty} empty) at {path}"
                )
            elif not _is_done(str(s.get("status", ""))):
                selectable += 1

    if selectable == 0 and not errors:
        errors.append("no selectable story (coder would have nothing to run)")

    logger.info(
        "artifacts validation: %d error(s), %d selectable stor(y/ies)", len(errors), selectable
    )
    return Defects(ok=not errors, errors="\n".join(errors))


# ── git: keep the work, and ship it ─────────────────────────────────────────


def _commit_message(mode: str, epic: str, bullet: str) -> str:
    if mode == "incomplete":
        # The failure edge of the final gate. The partial prose is worth keeping — it is what
        # a rerun resumes from — but it must never look like a finished run, and the workflow
        # ends red right after this so no PR is opened on it. The message is the marker a
        # human (or a `git log` skim) needs to spot the branch as unfinished.
        if epic:
            return f"author: INCOMPLETE — unwritten stories, do not merge ({epic})"
        return "author: INCOMPLETE — unwritten stories, do not merge"
    if mode == "survey":
        return "author: survey intake and epic backlog authoring"
    if mode == "story" and epic:
        trimmed = bullet.strip().splitlines()[0][:72] if bullet.strip() else ""
        return f"author: {epic} — {trimmed}" if trimmed else f"author: {epic}"
    if mode == "epic-edit" and epic:
        trimmed = bullet.strip().splitlines()[0][:72] if bullet.strip() else ""
        epic = registry.epic_slug(epic)
        return f"author: {epic} — {trimmed}" if trimmed else f"author: {epic}"
    return "author: epic backlog authoring"


@blueprint.node
def commit_author(
    logger: logging.Logger,
    mode: str = "epic",
    epic: str = "",
    bullet: str = "",
    repo_dir: str = "",
    docs_dir: str = "docs",
    id_registry: str = ".agents/ids.json",
) -> Committed:
    """Commit the epic/story docs this run wrote, in the one repo it wrote them in.

    Author only ever writes into the docs repo running the workflow — unlike coder there
    is no affected-repos resolution, so this always commits at the repo root.
    `mode="incomplete"` is the failure edge and only changes the message.

    **Scoped to what this workflow writes, not to the whole tree.** The repo author runs
    in is routinely a checkout somebody is *also* working in — `repo_dir` defaults to the
    directory the run was launched from, so it points straight at their working tree. A
    `git add -A` here commits their in-flight edits under an `author:` subject, which is
    how a run ends up owning changes it never made.

    Two scopes, because the run writes in two places: `docs_dir` for the prose, and
    `id_registry` for ostler's id ledger, which lives outside the docs tree and *must*
    travel with the documents it numbers — an id minted but left uncommitted is reminted
    for a different entity by the next run. A scope that does not exist is dropped rather
    than passed to git, which would fail the whole commit on an unmatched pathspec.
    """
    repo_root = find_repo_root(repo_dir)
    if not (repo_root / ".git").exists():
        logger.info("no .git at %s — nothing to commit", repo_root)
        return Committed()

    scope = [
        rel for rel in (docs_dir.strip(), id_registry.strip()) if rel and (repo_root / rel).exists()
    ]
    if not scope:
        logger.info("nothing author writes exists under %s — nothing to commit", repo_root)
        return Committed()

    committed = commit_paths(repo_root, _commit_message(mode, epic, bullet), *scope)
    if committed:
        logger.info("committed %s in %s", " ".join(scope), repo_root)
    return Committed(committed=committed)


def _pr_title(mode: str, epic: str, bullet: str) -> str:
    if mode == "survey":
        return "Author: survey intake and epic/story backlog authoring"
    if mode == "story" and epic:
        trimmed = bullet.strip().splitlines()[0][:72] if bullet.strip() else ""
        return f"Author: {epic} — {trimmed}" if trimmed else f"Author: {epic}"
    return "Author: epic/story backlog authoring"


def _pr_body(mode: str) -> str:
    label = "survey mode" if mode == "survey" else "story mode" if mode == "story" else "epic mode"
    return "\n".join(
        [
            "## Summary",
            "",
            f"Automated epic/story docs authored by the `author` workflow ({label}).",
            "",
            "---",
            "*Automated author PR. Left open for review — not auto-merged.*",
        ]
    )


def _github_slug(url: str) -> str:
    """`owner/repo` for a supported GitHub remote URL, or `""`."""
    for prefix in ("git@github.com:", "ssh://git@github.com/", "https://github.com/"):
        if url.startswith(prefix):
            return url.removeprefix(prefix).removesuffix(".git")
    return ""


def _resolve_github_slug(repo_path: Path) -> str:
    """Resolve GitHub even when this checkout was cloned from a local bind mount.

    Container runs clone the host working tree from paths such as `/mnt/repo-src`. In that
    case the clone's origin is local, but the mounted source repository still carries the
    real GitHub origin.
    """
    origins = remote_urls(repo_path)
    for url in origins:
        slug = _github_slug(url)
        if slug:
            return slug

    for url in origins:
        source = Path(url.removeprefix("file://") if url.startswith("file://") else url)
        if not source.is_absolute():
            source = (repo_path / source).resolve()
        if not source.exists():
            continue
        for source_origin in remote_urls(source):
            slug = _github_slug(source_origin)
            if slug:
                return slug
    return ""


def _base_branch(repo_path: Path, declared: str, fallback: str = "main") -> str:
    if declared:
        return declared
    for candidate in ("develop", "main", "master"):
        if branch_exists(repo_path, candidate):
            return candidate
    return fallback


def _skipped(logger: logging.Logger, reason: str) -> PullRequest:
    """PR delivery is not configured — a supported state, not a failure."""
    logger.info("PR delivery not configured (%s) — skipping", reason)
    return PullRequest(author_pr="skipped", pr_skip_reason=reason)


@blueprint.node
def open_author_pr(
    logger: logging.Logger,
    base_branch: str = "main",
    author_branch: str = "",
    mode: str = "epic",
    epic: str = "",
    bullet: str = "",
    repo_dir: str = "",
) -> PullRequest:
    """Push the run's branch and open one PR in the docs repo.

    Two outcomes are deliberately not conflated. **PR delivery is not configured** — no
    `.git`, no token, or an `origin` that is not a github.com repository — is a legitimate
    configuration (a `git init` with no remote, the greenfield case), so it is a `skipped`
    and the run still passes. **PR delivery was attempted and failed** — a push error, an
    unreachable repository, a create error — still fails the run: wherever a remote *is*
    configured, "a PR is required" remains true.
    """
    if not author_branch:
        raise WorkflowFailed("no author branch was provided")

    repo_root = find_repo_root(repo_dir)
    if not (repo_root / ".git").exists():
        return _skipped(logger, f"no .git at {repo_root}")

    token = github_kit.resolve_github_token(repo_root)
    if not token:
        return _skipped(logger, "no GitHub token is configured")

    if not branch_exists(repo_root, author_branch):
        raise WorkflowFailed(f"no branch {author_branch} in {repo_root}")

    slug = _resolve_github_slug(repo_root)
    if not slug:
        # Not configured, not broken: a local-only repo has no forge to deliver to.
        origins = ", ".join(remote_urls(repo_root)) or "<no remote>"
        return _skipped(logger, f"origin does not resolve to a github.com repository: {origins}")

    # push_branch targets the resolved slug explicitly (the origin may be a local
    # bind-mount path in container runs, so we can't let it re-derive from origin).
    if not github_kit.push_branch(repo_root, token, author_branch, slug=slug, verify=False):
        raise WorkflowFailed(f"push failed for {author_branch}")

    try:
        gh_repo = github_kit.github_client(token).get_repo(slug)
    except Exception as exc:
        raise WorkflowFailed(f"cannot access github.com repository {slug}: {exc}") from exc

    existing = github_kit.find_open_pr(gh_repo, author_branch)
    if existing is not None:
        logger.info("PR already open for %s", author_branch)
        return PullRequest(author_pr="exists", pr_url=existing.html_url)

    base = _base_branch(repo_root, base_branch)
    try:
        pr = gh_repo.create_pull(
            base=base,
            head=author_branch,
            title=_pr_title(mode, epic, bullet),
            body=_pr_body(mode),
        )
    except Exception as exc:
        raise WorkflowFailed(f"PR create failed for {author_branch}: {exc}") from exc

    logger.info("opened PR for %s -> %s", author_branch, base)
    return PullRequest(author_pr="opened", pr_url=pr.html_url)


__all__ = [
    "commit_author",
    "open_author_pr",
    "validate_artifacts",
    "verify_integrity",
    "verify_reconcile",
]
