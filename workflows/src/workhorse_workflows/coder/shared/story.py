"""The story spine: resolve a story handle to its id and paths, resolve the workspace, stamp the specs."""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler, markdown, path as okf_path, registry
from ostler.model import Epic, Story
from workhorse.pyflow import Workflow, WorkflowFailed
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.coder.shared import stubs
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.story import SpecsStamped, StoryPaths, WorkspaceDirs
from workhorse_workflows.kit import resolve_workspace


def _resolve(okf: Ostler, ref: str) -> tuple[Epic, Story]:
    """The story a launch handle names: its id, or the slug a worklist or fix seed carries."""
    try:
        found = okf.graph.find_story(ref) or okf.graph.story_by_slug(ref)
        if found is None:
            raise WorkflowFailed(okf.graph.no_story(ref))
        if not found[1].eid:
            raise WorkflowFailed(okf.graph.no_story(found[1].slug))
    except (OSError, ValueError, RuntimeError) as exc:
        raise WorkflowFailed(str(exc)) from exc
    return found


def _spec_dir(okf: Ostler, story_id: str) -> Path:
    """Where this story's specs live (absolute, outside the repo by default), through ostler."""
    try:
        return Path(okf.spec_path(story_id))
    except ValueError as exc:
        raise WorkflowFailed(str(exc)) from exc


def _guard_authored(epic: Epic, story: Story, logger: logging.Logger) -> None:
    """Fail the run if the resolved story is unauthored."""
    del logger
    if story.authored:
        return
    detail = (
        "story.md is missing"
        if story.story_md is None
        else "story.md is still a bare scaffold — " + ", ".join(story.unwritten_detail)
    )
    raise WorkflowFailed(
        f"story '{story.slug}' is not authored ({detail}); refusing to plan against it. "
        f"Run the author workflow for epic '{epic.name}' first."
    )


@blueprint.node
def guard_story_file(logger: logging.Logger, story: StoryPaths) -> None:
    """Fail the run when the story a lane was pointed at is not a file it can read."""
    del logger
    if not story.story_path:
        raise WorkflowFailed(
            f"no story path for {story.story_slug or '(no slug)'!r} — the story handle did not "
            "resolve to a story file, so there is nothing to work against."
        )
    if not story.spec_dir:
        raise WorkflowFailed(
            f"no spec dir for {story.story_slug or '(no slug)'!r} — the story handle resolved to a "
            "story but to no place to keep its plan, evidence and QA report."
        )
    try:
        Path(story.story_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise WorkflowFailed(
            f"story file '{story.story_path}' is not readable ({exc.strerror or exc}); "
            "refusing to work against a story nobody wrote."
        ) from exc


@blueprint.node(stub=stubs.story_paths)
def prepare_story(
    logger: logging.Logger,
    story: str = "",
    epic: str = "",
    repo_dir: str = "",
) -> StoryPaths:
    """Resolve a story handle (id or slug) and epic to the canonical absolute paths every flow uses."""
    if not story:
        logger.info("no story handle — nothing to resolve")
        return StoryPaths()

    docs_root = find_docs_root(repo_dir)
    okf = Ostler(docs_root)
    found_epic, found = _resolve(okf, story)
    slug = found.slug
    story_id = found.eid
    epic = epic or found_epic.name
    _guard_authored(found_epic, found, logger)

    spec_dir = str(_spec_dir(okf, story_id).resolve())

    try:
        story_path_rel = okf.story_path(story_id)
    except (OSError, ValueError, RuntimeError):
        story_path_rel = ""
    story_path = str(
        (docs_root / story_path_rel).resolve() if story_path_rel
        else okf_path.story_dir_in(docs_root, epic, slug) / "story.md"
    )

    return StoryPaths(
        story_path=story_path,
        spec_dir=spec_dir,
        qa_dir=spec_dir + "/qa",
        story_slug=slug,
        story_epic=epic,
        story_id=story_id,
        story_services=list(found.services),
    )


@blueprint.node(aliases=("resolve_ci_workspace",))
def resolve_workspace_dirs(
    logger: logging.Logger, repo_dir: str = "", workspace: str = ""
) -> WorkspaceDirs:
    """Every directory this run's agent turns may read: the workspace repos plus the docs."""
    docs_root = find_docs_root(repo_dir)
    repos = resolve_workspace(workspace, repo_dir)
    dirs = [r["path"] for r in repos.values() if Path(r["path"]).is_dir()]
    if str(docs_root) not in dirs:
        dirs = [str(docs_root), *dirs]
    logger.info("resolved %d workspace dir(s)", len(dirs))
    return WorkspaceDirs(dirs=dirs)


def workspace_dirs(flow: Workflow) -> list[str]:
    """Every directory this run's agent turns may read, off the recorded `setup` output."""
    return list(flow.output(resolve_workspace_dirs).dirs)


@blueprint.node
def stamp_specs(
    logger: logging.Logger, story_id: str = "", repo_dir: str = ""
) -> SpecsStamped:
    """Give every spec doc in the story's spec dir an OKF `type`, or fail the run."""
    if not story_id:
        logger.info("no story id — nothing to stamp")
        return SpecsStamped()

    docs_root = find_docs_root(repo_dir)
    okf = Ostler(docs_root)
    spec_dir = _spec_dir(okf, story_id)
    if not spec_dir.is_dir():
        logger.info("no spec dir at %s — nothing to stamp", spec_dir)
        return SpecsStamped()

    stamped = 0
    for path in sorted(spec_dir.glob("*.md")):
        res = okf.create_spec(story_id, path.name)
        if not res.ok:
            logger.info("skipped %s: %s", path.name, res.message)
            continue
        if res.message.startswith("stamped"):
            logger.info("%s", res.message)
            stamped += 1

    untyped = [
        p.name
        for p in sorted(spec_dir.glob("*.md"))
        if p.name not in registry.RESERVED_FILES
        and not registry.type_of(markdown.split(p.read_text(encoding="utf-8")).frontmatter)
    ]
    if untyped:
        raise WorkflowFailed("still untyped after stamping: " + ", ".join(untyped))

    logger.info("stamped %d doc(s) in %s", stamped, story_id)
    return SpecsStamped(stamped=stamped)


@blueprint.node
def prepare_fix_story(
    logger: logging.Logger,
    story: str = "",
    epic: str = "",
    repo_dir: str = "",
) -> StoryPaths:
    """`prepare_story` under a second node id, for the backlog drain nested in the main loop."""
    return prepare_story(logger, story=story, epic=epic, repo_dir=repo_dir)


__all__ = [
    "guard_story_file",
    "prepare_fix_story",
    "prepare_story",
    "resolve_workspace_dirs",
    "stamp_specs",
    "workspace_dirs",
]
