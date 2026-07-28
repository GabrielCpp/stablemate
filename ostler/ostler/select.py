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


def _story_dict(epic: Epic, story: Story) -> dict:
    return {"slug": story.slug, "epic": epic.name, "title": story.title,
            "status": story.status, "path": story.path,
            "covers": story.seed_items, "dependsOn": story.dependencies}


def next_story_report(graph: Graph, epic_name: str,
                      skip: frozenset[str] | set[str] | None = None) -> dict:
    """Why there is (or is not) a next story in ``epic_name`` — not just whether there is one.

    ``next_story`` answers with a story or ``None``, and that ``None`` covers four different
    situations: the epic does not exist, every story is done, every remaining story was given
    up on this run, or every remaining story is waiting on a dependency that will never be
    satisfied. Callers cannot tell them apart — and the coder workflow's caller treats all of
    them as "epic finished", opens a PR and merges it. Only the first two of the four are
    finished; the other two merge an epic with unbuilt scope in it. That is the bug this
    function exists to make impossible: the caller gets a ``state``, not an absence.

    ``state`` is one of:

    ``ready``       a runnable story — ``story`` holds it.
    ``done``        every story in the epic is done. The only state that means "prune it".
    ``blocked``     stories remain but none is runnable: each is either in ``skip`` or waiting
                    on an unmet dependency (``waiting_on`` names which). Not finished.
    ``no-stories``  the epic exists but has no authored stories. Deliberately NOT ``done`` —
                    an empty epic is unwritten scope, and treating it as complete drops it
                    from the queue silently.
    ``no-epic``     no epic by that name in the graph.

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
        return {"state": "no-epic", "story": None, "epic": epic_name, "total": 0, "done": 0,
                "remaining": [], "skipped": [], "waiting_on": {},
                "detail": f"no epic named '{epic_name}' in the graph"}

    skip = frozenset(skip or ())
    done = {s.slug for s in epic.stories if is_done(s.status)}
    report = {"state": "", "story": None, "epic": epic.name, "total": len(epic.stories),
              "done": len(done), "remaining": [], "skipped": [], "waiting_on": {},
              "detail": ""}

    if not epic.stories:
        report["state"] = "no-stories"
        report["detail"] = f"epic '{epic.name}' has no authored stories"
        return report

    # dependency order: a story is eligible once its deps are done; iterate to a fixpoint pick
    for story in epic.stories:
        if _runnable(epic, story, done, skip):
            report["state"] = "ready"
            report["story"] = _story_dict(epic, story)
            report["detail"] = f"{story.slug} is runnable"
            return report

    # Nothing runnable. Say why — per story, since the reasons differ within one epic.
    for story in epic.stories:
        if story.slug in done:
            continue
        report["remaining"].append(story.slug)
        if story.slug in skip:
            report["skipped"].append(story.slug)
            continue
        unmet = [dep for dep in story.dependencies if dep not in done]
        if unmet:
            report["waiting_on"][story.slug] = unmet

    if not report["remaining"]:
        report["state"] = "done"
        report["detail"] = f"all {len(epic.stories)} stories in '{epic.name}' are done"
        return report

    report["state"] = "blocked"
    parts = []
    if report["skipped"]:
        parts.append(f"given up this run: {', '.join(report['skipped'])}")
    if report["waiting_on"]:
        parts.append("waiting on unmet dependencies: " + "; ".join(
            f"{slug} needs {', '.join(deps)}" for slug, deps in report["waiting_on"].items()))
    report["detail"] = (
        f"{len(report['remaining'])} of {len(epic.stories)} stories in '{epic.name}' are not "
        f"done and none is runnable" + (f" ({'; '.join(parts)})" if parts else ""))
    return report


def next_story(graph: Graph, epic_name: str,
               skip: frozenset[str] | set[str] | None = None) -> dict | None:
    """The next runnable story in ``epic_name`` — not done, not skipped, all deps done.

    Thin wrapper over :func:`next_story_report` for callers that only need the story (the
    ``ostler next-story`` CLI). Anything that decides what to do when there *is* no story
    should call the report instead — see its docstring for why ``None`` is not enough.
    """
    return next_story_report(graph, epic_name, skip=skip)["story"]
