"""The clean-tree check, the commit that records a passed story, and its stamp."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from ostler import coverage, model, registry
from ostler import graph as graph_mod
from ostler.qa.plan import scenario_covers
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.coder.shared import commits, paths, story_status
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.plan import get_affected_repos, load_plan_context
from workhorse_workflows.coder.shared.proof_scope import inert_paths, scope
from workhorse_workflows.coder.shared.schemas.queue import (
    ProofScope,
    StoryCommitted,
    StoryStamped,
    WorktreeCleanliness,
)
from workhorse_workflows.coder.shared.worktree import untouched_since
from workhorse_workflows.kit.agent_files import render_agent_files_returning_failure
from workhorse_workflows.kit import (
    GitError,
    commit_paths,
    find_docs_root,
    find_repo_root,
    open_repo,
    resolve_workspace,
)

DONE_STATUS = "QA passed"

_COVERED_PAGE = re.compile(r"^okf:(.+?\.md)(?::|$)")


def _stamp_status(
    logger: logging.Logger, root: Path, epic: str, slug: str, story_path: str
) -> tuple[bool, bool]:
    """Record `QA passed` on the story and commit just that change."""
    before = story_status.current(root, slug, epic=epic, story_path=story_path)
    written = story_status.mark(root, slug, DONE_STATUS, epic=epic, story_path=story_path, logger=logger)
    if not written:
        logger.warning(
            "status '%s' NOT recorded for %s — it will be re-selected on the next loop",
            DONE_STATUS,
            slug,
        )
        return False, False
    prior = before.strip()
    superseded = bool(prior) and prior not in (registry.DEFAULT_STORY_STATUS, DONE_STATUS)

    specs: list[str] = []
    for path in written:
        try:
            specs.append(str(path.resolve().relative_to(root.resolve())))
        except ValueError:
            logger.info("status file %s is outside %s — not committing it here", path, root)
    stamp = commits.message(
        "docs",
        commits.scope(root.name),
        f"mark {slug} {DONE_STATUS}",
        epic=epic,
        story=slug,
    )
    if specs and commit_paths(root, stamp, *specs, verify=False):
        logger.info("recorded %s for %s", DONE_STATUS, slug)
    return True, superseded


def _commit_roots(
    logger: logging.Logger,
    root: Path,
    spec_dir: str,
    workspace: str,
    repo_dir: str,
    roots: list[str] | None,
) -> list[tuple[str, Path]]:
    """Which checkouts this story's commit covers — the caller's list, or the plan's."""
    if roots:
        return [(Path(p).name, Path(p)) for p in roots]
    return _affected_roots(logger, root, spec_dir, workspace, repo_dir)


def _affected_roots(
    logger: logging.Logger, root: Path, spec_dir: str, workspace: str, repo_dir: str
) -> list[tuple[str, Path]]:
    """The repos this story's plan says it touched, as `(package name, checkout)` pairs."""
    repos = resolve_workspace(workspace, repo_dir)
    plan_ctx = load_plan_context(root, spec_dir, logger)
    affected = get_affected_repos(plan_ctx, repos)
    if not affected:
        logger.info("no affected repos resolved from plan-context — falling back to the repo root")
        return [(root.name, root)]

    found: list[tuple[str, Path]] = []
    for name in affected:
        repo_path = Path(repos.get(name, {}).get("path", ""))
        if not repo_path.is_dir():
            logger.warning("repo %s path not found: %s", name, repo_path)
            continue
        if not (repo_path / ".git").exists():
            logger.warning("repo %s is not a git repo — skipping", name)
            continue
        found.append((name, repo_path))
    return found


def _uncommitted(root: Path) -> list[str]:
    """Every path in *root* holding work that is not in a commit yet."""
    try:
        repo = open_repo(root)
        dirty = {item.a_path for item in repo.index.diff(None) if item.a_path}
        dirty |= set(repo.untracked_files)
        try:
            staged = repo.index.diff("HEAD")
            dirty |= {path for item in staged for path in (item.a_path, item.b_path) if path}
        except (GitError, OSError, TypeError, ValueError, KeyError):
            pass
    except (GitError, OSError, TypeError, ValueError, RuntimeError):
        return []
    return sorted(dirty)


@blueprint.node
def check_repos_clean(
    logger: logging.Logger,
    story_slug: str = "",
    spec_dir: str = "",
    preexisting: list[str] | None = None,
    repo_dir: str = "",
    workspace: str = "",
    roots: list[str] | None = None,
) -> WorktreeCleanliness:
    """Did the agent commit its own work in every repo the story touched?"""
    root = find_repo_root(repo_dir)
    snapshot = tuple(preexisting or ())
    dirty: list[str] = []
    names: list[str] = []
    for name, repo_path in _commit_roots(logger, root, spec_dir, workspace, repo_dir, roots):
        names.append(name)
        excused = untouched_since(repo_path, snapshot)
        dirty.extend(
            f"{name}:{rel}"
            for rel in _uncommitted(repo_path)
            if rel not in excused and not paths.is_gate_context(rel)
        )

    slug = story_slug or "story"
    if dirty:
        logger.info(
            "%s left %d uncommitted path(s) behind: %s",
            slug, len(dirty), ", ".join(dirty[:10]) + (" …" if len(dirty) > 10 else ""),
        )
    else:
        logger.info("%s left nothing uncommitted in %s", slug, ", ".join(names) or "the repo root")
    return WorktreeCleanliness(clean=not dirty, dirty=dirty, repos=names)


def leftover_text(dirty: list[str]) -> str:
    """The report an owner turn gets back when it left uncommitted paths behind."""
    listing = "\n".join(f"- `{path}`" for path in dirty[:40])
    elided = f"\n- … and {len(dirty) - 40} more" if len(dirty) > 40 else ""
    return (
        "Uncommitted work: these paths changed since the story began and are not "
        f"committed.\n\n{listing}{elided}\n\n"
        "Commit what this story wrote. Delete what a tool generated during the turn that is "
        "not evidence, such as a test runner's failure screenshot or report. Leave alone what "
        "the story did not write, and report `blocked` naming those paths, so the operator "
        "decides what happens to them."
    )


def _key_of(roots: list[tuple[str, Path]], absolute: Path) -> str | None:
    """The `<repo name>:<repo-relative path>` key of *absolute* in the deepest checkout holding it."""
    held = [
        (name, repo_path.resolve())
        for name, repo_path in roots
        if absolute.is_relative_to(repo_path.resolve())
    ]
    if not held:
        return None
    name, repo_path = max(held, key=lambda pair: len(pair[1].parts))
    return f"{name}:{absolute.relative_to(repo_path).as_posix()}"


def _page_key(roots: list[tuple[str, Path]], docs_root: Path, page: str) -> str:
    """The key of a book page named by its docs-root-relative path."""
    return _key_of(roots, (docs_root / page).resolve()) or f"{docs_root.name}:{page}"


def _citations_by_key(
    roots: list[tuple[str, Path]], docs_root: Path
) -> tuple[dict[str, set[str]], set[str]]:
    """The book's code citations and its pages, both in the key form `check_repos_clean` reports."""
    graph = model.load(docs_root)
    cited: dict[str, set[str]] = {}
    for target, nodes in coverage.citations(graph).items():
        key = _key_of(roots, (docs_root / target.partition("::")[0]).resolve())
        if key is not None:
            cited.setdefault(key, set()).update(
                _page_key(roots, docs_root, node.partition("#")[0]) for node in nodes
            )
    pages = {
        _page_key(roots, docs_root, str(node["id"]).partition("#")[0])
        for node in graph_mod.build(graph)["nodes"]
    }
    return cited, pages


@blueprint.node
def proof_scope(
    logger: logging.Logger,
    story_slug: str = "",
    spec_dir: str = "",
    story_path: str = "",
    dirty: list[str] | None = None,
    repo_dir: str = "",
    workspace: str = "",
) -> ProofScope:
    """How much of the story's proof the paths it left uncommitted reopen."""
    root = find_repo_root(repo_dir)
    roots = _affected_roots(logger, root, spec_dir, workspace, repo_dir)
    changed = list(dirty or [])
    inert: set[str] = set()
    for name, repo_path in roots:
        inert |= inert_paths(name, repo_path, story_path, changed)
    docs_root = find_docs_root(repo_dir)
    cited: dict[str, set[str]] = {}
    pages: set[str] = set()
    if any(path not in inert for path in changed):
        cited, pages = _citations_by_key(roots, docs_root)
    plan = root / spec_dir / "qa_plan.py"
    covers: dict[str, set[str]] = {}
    for scenario_id, ids in scenario_covers(plan).items():
        matched = (_COVERED_PAGE.match(text) for text in ids)
        covers[scenario_id] = {_page_key(roots, docs_root, m.group(1)) for m in matched if m}
    decided = scope(changed, inert, cited, covers, pages)
    logger.info(
        "%s: the leftovers reopen %s of the proof (%d scenario(s))%s",
        story_slug or "story",
        decided.kind,
        len(decided.scenarios),
        "".join(f"\n  {reason}" for reason in decided.reasons),
    )
    return decided


@blueprint.node
def commit_leftovers(
    logger: logging.Logger,
    epic: str = "",
    story_slug: str = "",
    spec_dir: str = "",
    dirty: list[str] | None = None,
    repo_dir: str = "",
    workspace: str = "",
) -> StoryCommitted:
    """Commit exactly the paths a passed story left uncommitted, and nothing else in the tree."""
    slug = story_slug or "story"
    root = find_repo_root(repo_dir)
    epic_name = registry.epic_slug(epic) or epic
    committed = False
    for name, repo_path in _affected_roots(logger, root, spec_dir, workspace, repo_dir):
        prefix = f"{name}:"
        keyed = [key[len(prefix):] for key in dirty or [] if key.startswith(prefix)]
        generated = [rel for rel in keyed if paths.is_tool_output(rel)]
        if generated:
            logger.info(
                "left %d tool-generated path(s) in %s out of the commit: %s",
                len(generated), name, ", ".join(generated[:10]),
            )
        rels = [rel for rel in keyed if rel not in generated]
        if not rels:
            continue
        kind = "docs" if all(rel.endswith(".md") for rel in rels) else "fix"
        message = commits.message(
            kind,
            commits.scope(name),
            f"commit what {slug} left uncommitted",
            epic=epic_name,
            story=slug,
        )
        try:
            landed = commit_paths(repo_path, message, *rels, verify=False)
        except GitError as exc:
            raise WorkflowFailed(
                f"git refused the commit for {slug} in {repo_path}: {exc}"
            ) from exc
        if landed:
            logger.info("committed %d leftover path(s) in %s", len(rels), name)
        committed = committed or landed
    return StoryCommitted(committed=committed)


@blueprint.node
def stamp_story_passed(
    logger: logging.Logger,
    epic: str = "",
    story_slug: str = "",
    story_path: str = "",
    repo_dir: str = "",
) -> StoryStamped:
    """Record the story's passing outcome, and commit that one line."""
    slug = story_slug or "story"
    root = find_repo_root(repo_dir)
    stamped, superseded = _stamp_status(logger, root, epic, slug, story_path)
    return StoryStamped(stamped=stamped, superseded_outcome=superseded)


@blueprint.node
def commit_plan_record(
    logger: logging.Logger,
    epic: str = "",
    story_slug: str = "",
    spec_dir: str = "",
    repo_dir: str = "",
) -> StoryCommitted:
    """Commit what the run itself wrote into the spec dir: the plan projection and the spec stamps."""
    slug = story_slug or "story"
    root = find_repo_root(repo_dir)
    spec = Path(spec_dir) if Path(spec_dir).is_absolute() else root / spec_dir
    try:
        rel = str(spec.resolve().relative_to(root.resolve()))
    except ValueError:
        logger.info("spec dir %s is outside %s, so the run commits no plan record", spec, root)
        return StoryCommitted()
    message = commits.message(
        "docs",
        commits.scope(root.name),
        f"record the plan of {slug}",
        epic=registry.epic_slug(epic) or epic,
        story=slug,
    )
    committed = bool(spec_dir) and commit_paths(root, message, rel, verify=False)
    if committed:
        logger.info("recorded the plan of %s", slug)
    return StoryCommitted(committed=committed)


@blueprint.node
def commit_story(
    logger: logging.Logger,
    epic: str = "",
    story_slug: str = "",
    spec_dir: str = "",
    story_path: str = "",
    repo_dir: str = "",
    workspace: str = "",
    kind: str = "feat",
    roots: list[str] | None = None,
    story_id: str = "",
    preexisting: list[str] | None = None,
) -> StoryCommitted:
    """Commit what a completed story changed in each affected code repo, then stamp it passed."""
    slug = story_slug or "story"
    root = find_repo_root(repo_dir)

    epic_name = registry.epic_slug(epic) or epic
    description = commits.story_description(root, story_path, slug)

    def _story_message(package: str) -> str:
        return commits.message(
            kind, commits.scope(package), description, epic=epic_name, story=story_id or slug
        )

    snapshot = tuple(preexisting or ())

    def _commit_in(repo_path: Path, package: str) -> bool:
        """Commit the dirty paths that were not dirty and untouched at story start, with a git refusal turned into a halt rather than a False."""
        dirty = _uncommitted(repo_path)
        excused = untouched_since(repo_path, snapshot)
        rels = [rel for rel in dirty if rel not in excused]
        if len(rels) < len(dirty):
            logger.info(
                "left %d pre-existing dirty path(s) in %s out of the commit",
                len(dirty) - len(rels), package,
            )
        try:
            return commit_paths(repo_path, _story_message(package), *rels)
        except GitError as exc:
            raise WorkflowFailed(
                f"git refused the commit for {slug} in {repo_path}: {exc}"
            ) from exc

    any_committed = False
    for name, repo_path in _commit_roots(logger, root, spec_dir, workspace, repo_dir, roots):
        failure = render_agent_files_returning_failure(repo_path)
        if failure:
            logger.warning("agent files of %s not rendered: %s", repo_path.name, failure)
        if _commit_in(repo_path, name):
            logger.info("committed in %s", repo_path.name)
            any_committed = True

    _, superseded = _stamp_status(logger, root, epic, slug, story_path)
    return StoryCommitted(committed=any_committed, superseded_outcome=superseded)


__all__ = [
    "check_repos_clean",
    "commit_leftovers",
    "commit_plan_record",
    "commit_story",
    "leftover_text",
    "proof_scope",
    "stamp_story_passed",
]
