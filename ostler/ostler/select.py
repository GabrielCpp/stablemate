"""`ostler next-epic` / `next-story` — selection over the markdown graph + epics index.

Replaces the workflows' select-next-epic / select-next-story scripts. ``next-epic`` returns the
front of the epics queue that still has unfinished work; ``next-story`` returns the next runnable
story (dependencies satisfied, not yet done) in dependency order.
"""

from __future__ import annotations

from ostler import todo
from ostler.model import Epic, Graph, Story

_DONE_TOKENS = ("qa passed", "passed", "done", "merged", "complete")


def is_done(status: str) -> bool:
    s = (status or "").strip().lower()
    return any(tok in s for tok in _DONE_TOKENS)


def _epic_by_name(graph: Graph, name: str) -> Epic | None:
    return next((e for e in graph.epics if e.name == name), None)


def epic_done(epic: Epic) -> bool:
    return bool(epic.stories) and all(is_done(s.status) for s in epic.stories)


def next_epic(graph: Graph) -> dict | None:
    """First queued epic with unfinished work; falls back to graph order if no index."""
    order = todo.list_epics(graph) or [e.name for e in graph.epics]
    for name in order:
        epic = _epic_by_name(graph, name)
        if epic is None:
            continue
        if not epic_done(epic):
            return {"name": epic.name, "id": epic.eid, "title": epic.title,
                    "stories": len(epic.stories)}
    return None


def _runnable(epic: Epic, story: Story, done: set[str], skip: frozenset[str]) -> bool:
    if is_done(story.status) or story.slug in skip:
        return False
    return all(dep in done for dep in story.dependencies)


def next_story(graph: Graph, epic_name: str,
               skip: frozenset[str] | set[str] | None = None) -> dict | None:
    """The next runnable story in ``epic_name`` — not done, not skipped, all deps done.

    ``skip`` is a set of story slugs to treat as ineligible without treating them as *done*:
    a story the caller has given up on this run. Excluding it is essential — otherwise, since
    a given-up story is not "done", it stays first-runnable forever and the selector keeps
    returning it. The caller then rejects it and, finding nothing else, prunes the whole epic
    while other independent stories sit "Not started". (Observed: an epic merged with 20 of 21
    stories unbuilt after one story gave up on QA.) A skipped story is NOT added to ``done``,
    so its dependents stay blocked — you don't build on unverified work — but every story that
    does not depend on it remains selectable.
    """
    epic = _epic_by_name(graph, epic_name)
    if epic is None:
        return None
    skip = frozenset(skip or ())
    done = {s.slug for s in epic.stories if is_done(s.status)}
    # dependency order: a story is eligible once its deps are done; iterate to a fixpoint pick
    for story in epic.stories:
        if _runnable(epic, story, done, skip):
            return {"slug": story.slug, "epic": epic.name, "title": story.title,
                    "status": story.status, "path": story.path,
                    "covers": story.seed_items, "dependsOn": story.dependencies}
    return None
