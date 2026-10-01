"""The story spine: resolve a slug to paths, resolve the workspace, stamp the specs."""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler, markdown, path as okf_path, registry
from workhorse.pyflow import Workflow, WorkflowFailed
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.coder.shared import stubs
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.story import SpecsStamped, StoryPaths, WorkspaceDirs
from workhorse_workflows.kit import resolve_workspace


def _spec_dir_rel(okf: Ostler, slug: str) -> str:
    """Where this story's specs live, repo-relative, through ostler."""
    try:
        return okf.spec_path(slug) or f"docs/specs/{slug}"
    except (OSError, ValueError, RuntimeError):
        return f"docs/specs/{slug}"


def _story_id(okf: Ostler, slug: str) -> str:
    """The story's minted id (`ACME-01H…`), or empty on a book that predates them."""
    try:
        found = okf.graph.find_story(slug)
    except (OSError, ValueError, RuntimeError):
        return ""
    return found[1].eid if found is not None else ""


def _guard_authored(okf: Ostler, slug: str, logger: logging.Logger) -> None:
    """Fail the run if the graph knows this story and reports it unauthored."""
    try:
        found = okf.graph.find_story(slug)
    except (OSError, ValueError, RuntimeError) as exc:
        logger.info("could not load the doc graph to check '%s' is authored (%s)", slug, exc)
        return
    if found is None:
        logger.info("story '%s' is not in the doc graph — cannot check it is authored", slug)
        return
    epic, story = found
    if story.authored:
        return
    detail = (
        "story.md is missing"
        if story.story_md is None
        else "story.md is still a bare scaffold — " + ", ".join(story.unwritten_detail)
    )
    raise WorkflowFailed(
        f"story '{slug}' is not authored ({detail}); refusing to plan against it. "
        f"Run the author workflow for epic '{epic.name}' first."
    )


def guard_story_file(story: StoryPaths) -> None:
    """Fail the run when the story a lane was pointed at is not a file it can read."""
    if not story.story_path:
        raise WorkflowFailed(
            f"no story path for {story.story_slug or '(no slug)'!r} — the slug did not "
            "resolve to a story file, so there is nothing to work against."
        )
    if not story.spec_dir:
        raise WorkflowFailed(
            f"no spec dir for {story.story_slug or '(no slug)'!r} — the slug resolved to a "
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
    docs_path: str = "",
    story: str = "",
    epic: str = "",
    repo_dir: str = "",
) -> StoryPaths:
    """Resolve a story slug and epic to the canonical absolute paths every flow uses."""
    if not story:
        logger.info("no story slug — nothing to resolve")
        return StoryPaths()

    docs_root = find_docs_root(docs_path, repo_dir)

    if not epic:
        epics_root = okf_path.epics_root_in(docs_root)
        matches = list(epics_root.glob(f"*/stories/{story}/story.md"))
        if matches:
            epic = matches[0].parent.parent.parent.name
        else:
            logger.warning("no epic given and no matching story folder found for '%s'", story)

    okf = Ostler(docs_root)
    _guard_authored(okf, story, logger)

    spec_dir = str((docs_root / _spec_dir_rel(okf, story)).resolve())

    story_path = ""
    if epic:
        try:
            story_path_rel = okf.story_path(epic, story)
        except (OSError, ValueError, RuntimeError):
            story_path_rel = ""
        story_path = str(
            (docs_root / story_path_rel).resolve() if story_path_rel
            else okf_path.story_dir_in(docs_root, epic, story) / "story.md"
        )

    return StoryPaths(
        story_path=story_path,
        spec_dir=spec_dir,
        qa_dir=spec_dir + "/qa",
        story_slug=story,
        story_epic=epic,
        story_id=_story_id(okf, story),
    )


@blueprint.node(aliases=("resolve_ci_workspace",))
def resolve_workspace_dirs(
    logger: logging.Logger, docs_path: str = "", repo_dir: str = "", workspace_file: str = ""
) -> WorkspaceDirs:
    """Every directory this run's agent turns may read: the workspace repos plus the docs."""
    docs_root = find_docs_root(docs_path, repo_dir)
    repos = resolve_workspace(workspace_file, repo_dir)
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
    logger: logging.Logger, docs_path: str = "", story_slug: str = "", repo_dir: str = ""
) -> SpecsStamped:
    """Give every spec doc in the story's spec dir an OKF `type`, or fail the run."""
    if not story_slug:
        logger.info("no story slug — nothing to stamp")
        return SpecsStamped()

    docs_root = find_docs_root(docs_path, repo_dir)
    okf = Ostler(docs_root)
    spec_rel = _spec_dir_rel(okf, story_slug)
    spec_dir = docs_root / spec_rel
    if not spec_dir.is_dir():
        logger.info("no spec dir at %s — nothing to stamp", spec_dir)
        return SpecsStamped()

    spec_key = Path(spec_rel).name
    stamped = 0
    for path in sorted(spec_dir.glob("*.md")):
        res = okf.create_spec(spec_key, path.name)
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

    logger.info("stamped %d doc(s) in %s", stamped, story_slug)
    return SpecsStamped(stamped=stamped)


@blueprint.node
def prepare_fix_story(
    logger: logging.Logger,
    docs_path: str = "",
    story: str = "",
    epic: str = "",
    repo_dir: str = "",
) -> StoryPaths:
    """`prepare_story` under a second node id, for the backlog drain nested in the main loop."""
    return prepare_story(logger, docs_path=docs_path, story=story, epic=epic, repo_dir=repo_dir)


__all__ = [
    "guard_story_file",
    "prepare_fix_story",
    "prepare_story",
    "resolve_workspace_dirs",
    "stamp_specs",
    "workspace_dirs",
]
