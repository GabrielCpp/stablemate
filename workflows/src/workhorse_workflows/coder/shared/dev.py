"""The dev flow's deterministic work: read the story's status and sources, and the operator's answer."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from ostler.provenance import story_commits
from workhorse import gates
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared import story_status
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.dev import (
    ChangedFiles,
    DispatchEntry,
    OperatorAnswer,
    StoryStatusCheck,
    StorySource,
    StorySources,
)
from ostler.select import is_done

AWAITING = "AWAITING_OPERATOR"
ANSWERED = "ANSWERED"
CONSUMED = "CONSUMED"


@blueprint.node
def check_story_status(
    logger: logging.Logger,
    docs_path: str = "",
    slug: str = "",
    epic: str = "",
    story_path: str = "",
    repo_dir: str = "",
) -> StoryStatusCheck:
    """Whether the turn just taken stamped the story finished."""
    root = find_docs_root(docs_path, repo_dir)
    written = story_status.current(root, slug, epic=epic, story_path=story_path).strip()
    if not is_done(written):
        return StoryStatusCheck(status="clean", written=written)
    logger.warning(
        "the story's Status reads %r, which marks it finished, before QA has run", written
    )
    return StoryStatusCheck(status="dirty", written=written)


@blueprint.node
def changed_files(
    logger: logging.Logger, cwd: str = "", story_slug: str = "", story_id: str = ""
) -> ChangedFiles:
    """Which files this story has already written in one service checkout."""
    if not cwd or not Path(cwd).expanduser().is_dir():
        return ChangedFiles()
    commands = [["diff", "--name-only", "HEAD"], ["ls-files", "--others", "--exclude-standard"]]
    if story_slug or story_id:
        greps = [
            f"--grep=Story: {ref}" for ref in dict.fromkeys((story_id, story_slug)) if ref
        ]
        commands.append(["log", "--name-only", "--pretty=format:", *greps])
    found: list[str] = []
    for args in commands:
        try:
            done = subprocess.run(
                ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.info("could not list changed files in %s: %s", cwd, exc)
            break
        if done.returncode == 0:
            found += [line.strip() for line in done.stdout.splitlines() if line.strip()]
    return ChangedFiles(paths=sorted(set(found)))


def _story_base(cwd: str, refs: tuple[str, ...]) -> str:
    matching = story_commits(Path(cwd), refs)
    if not matching:
        raise ValueError("no commit carries an exact Story trailer for this story")
    parent = matching[0].get("parent")
    if not parent:
        raise ValueError("the story's earliest commit is the repository root")
    return str(parent)


@blueprint.node
def resolve_story_sources(
    logger: logging.Logger,
    dispatch: tuple[DispatchEntry, ...],
    story_slug: str = "",
    story_id: str = "",
    docs_path: str = "",
    repo_dir: str = "",
) -> StorySources:
    """Resolve each implementation repository to the parent before this story began."""
    docs_root = Path(find_docs_root(docs_path, repo_dir)).resolve()
    dispatch_roots = {
        Path(entry.cwd).resolve() for entry in dispatch if entry.cwd
    }
    if not dispatch_roots or dispatch_roots == {docs_root}:
        return StorySources()
    refs = tuple(dict.fromkeys(ref for ref in (story_id, story_slug) if ref))
    if not refs:
        return StorySources(status="invalid", errors=("the story has no identity",))
    bases: dict[str, tuple[str, str]] = {}
    sources: list[StorySource] = []
    errors: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in dispatch:
        cwd = str(Path(entry.cwd).resolve()) if entry.cwd else ""
        repo_name = (entry.repo or Path(cwd).name).strip()
        surface = (entry.repo or entry.service).strip()
        root = entry.service_path.strip().replace("\\", "/").strip("/") or "."
        if not cwd or not repo_name or not surface:
            errors.append(f"implementation entry {entry.service!r} has no source repository")
            continue
        existing = bases.get(repo_name)
        if existing is not None and existing[0] != cwd:
            errors.append(f"source repository {repo_name!r} resolves to multiple checkouts")
            continue
        if existing is None:
            try:
                base = _story_base(cwd, refs)
            except (OSError, ValueError) as exc:
                errors.append(f"source repository {repo_name!r}: {exc}")
                continue
            bases[repo_name] = (cwd, base)
        else:
            base = existing[1]
        key = (repo_name, surface, root)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            StorySource(
                repo=repo_name,
                checkout=cwd,
                surface=surface,
                root=root,
                base=base,
            )
        )
    if errors:
        logger.warning("story source provenance is invalid: %s", "; ".join(errors))
        return StorySources(status="invalid", errors=tuple(errors))
    return StorySources(sources=tuple(sources))


@blueprint.node
def read_operator_context(logger: logging.Logger, story_path: str = "") -> OperatorAnswer:
    """Take the operator's answer off `<story-folder>/context.md` and consume it."""
    ctx = paths.story_context_path(story_path)
    if not ctx.exists():
        logger.warning("no operator context at %s — treating the block as unanswered", ctx)
        return OperatorAnswer()

    content = ctx.read_text(encoding="utf-8")
    if gates.status_of(content) == ANSWERED:
        ctx.write_text(gates.set_status(content, CONSUMED), encoding="utf-8")
        logger.info("consumed the operator's answer in %s", ctx)

    scope = "epic" if gates.scope_of(content) == "epic" else "story"
    return OperatorAnswer(answered=True, scope=scope, content=content)


__all__ = [
    "changed_files",
    "check_story_status",
    "read_operator_context",
]
