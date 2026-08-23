"""The story spine: resolve a slug to paths, resolve the workspace, stamp the specs.

Ports `prepare-story.py`, `resolve-workspace-dirs.py` and `stamp-specs.py`.

These three sit at the top of `dev`, `review`, `docs` and `qa` and again at the top of the
main graph — in the YAML that is the same node declared in five graphs, and the reason they
are one module here rather than a copy per flow. `resolve_workspace_dirs` is also what
`fix_ci`'s `resolve_ci_workspace` was: the same body, differing only in a log line, so the
`ci` node is gone and its callers point here.

Two script exit codes become `WorkflowFailed`, which is the port rule and in both cases the
behavior the exit code was reaching for:

* `prepare-story.py` exits **2** when ostler can see the story in the graph and says it is
  not authored. That gate exists because an author run once produced 44 stubs and reported
  success; coder would have planned, implemented and QA'd against every one of them,
  inventing the requirements as it went.
* `stamp-specs.py` returns **1** when a spec doc is still untyped after stamping, so
  nothing downstream can silently accumulate `okf-missing-type` the way 347 docs once did.
"""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler, markdown, path as okf_path, registry
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.coder.shared import stubs
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.story import SpecsStamped, StoryPaths, WorkspaceDirs
from workhorse_workflows.kit import resolve_workspace


def _spec_dir_rel(okf: Ostler, slug: str) -> str:
    """Where this story's specs live, repo-relative, through ostler.

    Resolved rather than assumed so a repo with a custom specs doc root still works; the
    conventional layout is the fallback, not the rule.
    """
    try:
        return okf.spec_path(slug) or f"docs/specs/{slug}"
    except (OSError, ValueError, RuntimeError):
        return f"docs/specs/{slug}"


def _guard_authored(okf: Ostler, slug: str, logger: logging.Logger) -> None:
    """Fail the run if the graph knows this story and reports it unauthored.

    "Authored" is ostler's verdict (`Story.authored`), never a local re-derivation — the
    same fact `ostler doctor`'s `unwritten-story` finding and the author workflow's own
    gates read, so coder and author can never disagree about whether a story says anything.

    A graph that will not load, or a slug it does not know, is a *different* fault and is
    only logged: story mode can legitimately be pointed at a story outside the epics tree,
    and the path resolution below already tolerates an absent graph.
    """
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


@blueprint.node(stub=stubs.story_paths)
def prepare_story(
    logger: logging.Logger,
    docs_path: str = "",
    story: str = "",
    epic: str = "",
    repo_dir: str = "",
) -> StoryPaths:
    """Resolve a story slug and epic to the canonical absolute paths every flow uses.

    Story mode and epic mode both come through here, which is what makes `story_path`,
    `spec_dir`, `qa_dir` and `story_slug` mean the same thing whichever mode produced the
    slug. An absent epic is discovered by scanning the epics tree for a matching story
    folder.
    """
    if not story:
        logger.info("no story slug — nothing to resolve")
        return StoryPaths()

    docs_root = find_docs_root(docs_path, repo_dir)

    if not epic:
        epics_root = okf_path.epics_root_in(docs_root)
        matches = list(epics_root.glob(f"*/stories/{story}/story.md"))
        if matches:
            # epics/<epic>/stories/<slug>/story.md
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
        # The fallback is the last resort only, for a docs tree ostler could not read at
        # all; it is still ostler's layout rule being applied, just without a graph.
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
    )


@blueprint.node(aliases=("resolve_ci_workspace",))
def resolve_workspace_dirs(
    logger: logging.Logger, docs_path: str = "", repo_dir: str = "", workspace_file: str = ""
) -> WorkspaceDirs:
    """Every directory this run's agent turns may read: the workspace repos plus the docs.

    Agent turns run with one service repo as their cwd, and the story, plan and spec files
    they are working against live in the docs root — which is a separate concept that may
    not be a workspace folder at all. The docs root is prepended when the workspace does not
    already carry it, so a backend with a per-repo path sandbox can still reach them.

    `resolve_ci_workspace` is an alias rather than a second node: `fix_ci` called the same
    body under that name, and `self.output(node)` resolves against the run directory by
    node name, so an alias is what keeps an in-flight CI run resumable across the rename.
    """
    docs_root = find_docs_root(docs_path, repo_dir)
    repos = resolve_workspace(workspace_file, repo_dir)
    dirs = [r["path"] for r in repos.values() if Path(r["path"]).is_dir()]
    if str(docs_root) not in dirs:
        dirs = [str(docs_root), *dirs]
    logger.info("resolved %d workspace dir(s)", len(dirs))
    return WorkspaceDirs(dirs=dirs)


@blueprint.node
def stamp_specs(
    logger: logging.Logger, docs_path: str = "", story_slug: str = "", repo_dir: str = ""
) -> SpecsStamped:
    """Give every spec doc in the story's spec dir an OKF `type`, or fail the run.

    The coder's process artifacts (plan.md, qa.md, review.md, executive.md) are written as
    free-form markdown by agents, so the frontmatter that makes them Concepts is only as
    reliable as the model's memory. (`qa-report.md` is the exception: the runner renders it
    and stamps its type itself, so the idempotent pass below just leaves it alone.) The prompts ask for `ostler create spec` up front; this
    is the backstop that makes the guarantee model-independent. `create_spec` is idempotent
    — an already-typed doc is left untouched and a typed body is never rewritten — so
    running it after every writer phase is free.

    Only `<spec_dir>/*.md` is stamped: the spec EntityType's glob is one level deep, so a
    doc nested deeper is not a Concept and must not be given a type.
    """
    if not story_slug:
        logger.info("no story slug — nothing to stamp")
        return SpecsStamped()

    docs_root = find_docs_root(docs_path, repo_dir)
    okf = Ostler(docs_root)
    spec_dir = docs_root / _spec_dir_rel(okf, story_slug)
    if not spec_dir.is_dir():
        # Nothing written yet (an early phase, or a mode with no spec dir) is not a failure.
        logger.info("no spec dir at %s — nothing to stamp", spec_dir)
        return SpecsStamped()

    stamped = 0
    for path in sorted(spec_dir.glob("*.md")):
        res = okf.create_spec(story_slug, path.name)
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
    """`prepare_story` under a second node id, for the backlog drain nested in the main loop.

    Not a convenience and not a copy: the body is `prepare_story`'s, called directly. What
    differs is the *name*, and the name is the point. A node's output is recorded under its
    id, so the drain — which runs inside a story's own run, right after that story goes
    green — would otherwise overwrite the original story's `prepare_story` record. The main
    loop's commit reads that record to know which story it is committing, so the drain would
    have made it commit the fix item's identity instead. The YAML hit this and registered
    `prepare-story.py` a second time under `prepare_fix_story` for exactly this reason; the
    comment there is the bug report.
    """
    return prepare_story(logger, docs_path=docs_path, story=story, epic=epic, repo_dir=repo_dir)


__all__ = ["prepare_fix_story", "prepare_story", "resolve_workspace_dirs", "stamp_specs"]
