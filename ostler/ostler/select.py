"""`ostler next-epic` / `next-story` — selection over the markdown graph."""

from __future__ import annotations

from ostler import registry
from ostler.model import Epic, Graph, Story

_DONE_STATUSES = {"qa passed", "passed", "done", "merged", "complete"}

_BLOCKED_PREFIXES = ("blocked", "docs blocked", "qa give-up", "qa give up")


def is_done(status: str) -> bool:
    s = (status or "").strip().lower()
    return s in _DONE_STATUSES


def is_blocked(status: str) -> bool:
    """Whether a status is a give-up stamp — a story set aside for a human, not built."""
    s = (status or "").strip().lower()
    return not is_done(s) and s.startswith(_BLOCKED_PREFIXES)


def epic_by_name(graph: Graph, name: str) -> Epic | None:
    """The epic named by its directory (`0001-checkout-flow`) or by its bare slug."""
    exact = next((e for e in graph.epics if e.name == name), None)
    if exact is not None or registry.epic_seq(name) is not None:
        return exact
    slug = registry.epic_slug(name)
    return next((e for e in graph.epics if registry.epic_slug(e.name) == slug), None)


def epic_done(epic: Epic) -> bool:
    return bool(epic.stories) and all(is_done(s.status) for s in epic.stories)


def epic_authored(epic: Epic) -> bool:
    """Whether every story in the epic has a written story.md — the *authoring* completion rule."""
    return (epic.epic_md is not None and bool(epic.stories)
            and all(s.authored for s in epic.stories))


def _milestone_epic_order(graph: Graph) -> list[str]:
    order: list[str] = []
    visited: set[str] = set()
    by_name = {m.name: m for m in graph.milestones}
    by_name.update({m.eid: m for m in graph.milestones if m.eid})

    def visit(name: str) -> None:
        milestone = by_name.get(name)
        if milestone is None or milestone.name in visited:
            return
        visited.add(milestone.name)
        for dep in milestone.depends_on:
            visit(dep)
        order.extend(milestone.epics)

    for milestone in graph.milestones:
        visit(milestone.name)
    return order


def dag_order(epic: Epic) -> list[Story]:
    """The epic's stories in dependency order (a dependency precedes its dependents)."""
    by_slug = {s.slug: s for s in epic.stories if s.slug}
    order: list[Story] = []
    seen: set[str] = set()
    walking: set[str] = set()

    def visit(slug: str) -> None:
        if slug in seen or slug in walking:
            return
        walking.add(slug)
        for dep in by_slug[slug].dependencies:
            if dep in by_slug:
                visit(dep)
        walking.discard(slug)
        seen.add(slug)
        order.append(by_slug[slug])

    for story in epic.stories:
        if story.slug:
            visit(story.slug)
    return order


def next_epic(graph: Graph) -> dict | None:
    """First milestone-ordered epic with unfinished work; falls back to graph order."""
    order = _milestone_epic_order(graph) or [e.name for e in graph.epics]
    for name in order:
        epic = epic_by_name(graph, name)
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
    return {"slug": story.slug, "id": story.eid, "externalKey": story.external_key,
            "aliases": list(story.aliases), "epic": epic.name, "title": story.title,
            "status": story.status, "path": story.path,
            "covers": story.seed_items, "dependsOn": story.dependencies,
            "authored": story.authored,
            "unwrittenSections": list(story.unwritten_sections)}


def _author_report(epic: Epic, skip: frozenset[str] = frozenset()) -> dict:
    """``need="author"`` — the first story in DAG order that still has no written story.md."""
    ordered = dag_order(epic)
    authored = [s.slug for s in ordered if s.authored]
    pending = [s for s in ordered if not s.authored]
    report = {"state": "", "story": None, "epic": epic.name, "total": len(ordered),
              "done": len(authored), "remaining": [s.slug for s in pending],
              "skipped": [s.slug for s in pending if s.slug in skip],
              "waiting_on": {}, "detail": ""}
    for story in pending:
        if story.slug in skip:
            continue
        report["state"] = "ready"
        report["story"] = _story_dict(epic, story)
        empty = ", ".join(story.unwritten_detail) or "no story.md"
        report["detail"] = f"{story.slug} is unwritten ({empty})"
        return report
    if pending:
        report["state"] = "blocked"
        report["detail"] = (f"all {len(pending)} unauthored stories in '{epic.name}' were parked "
                            f"this run: {', '.join(report['skipped'])}")
        return report
    report["state"] = "done"
    report["detail"] = f"all {len(ordered)} stories in '{epic.name}' are authored"
    return report


def next_story_report(graph: Graph, epic_name: str,
                      skip: frozenset[str] | set[str] | None = None,
                      need: str = "build") -> dict:
    """Why there is (or is not) a next story in ``epic_name`` — not just whether there is one."""
    epic = epic_by_name(graph, epic_name)
    if epic is None:
        return {"state": "no-epic", "story": None, "epic": epic_name, "total": 0, "done": 0,
                "remaining": [], "skipped": [], "waiting_on": {},
                "detail": f"no epic named '{epic_name}' in the graph"}
    if need not in ("build", "author"):
        raise ValueError(f"unknown need '{need}' (expected 'build' or 'author')")
    skip = frozenset(skip or ())
    if need == "author" and epic.stories:
        return _author_report(epic, skip)

    done = {s.slug for s in epic.stories if is_done(s.status)}
    report = {"state": "", "story": None, "epic": epic.name, "total": len(epic.stories),
              "done": len(done), "remaining": [], "skipped": [], "waiting_on": {},
              "detail": ""}

    if not epic.stories:
        report["state"] = "no-stories"
        report["detail"] = f"epic '{epic.name}' lists no stories in `## {registry.STORIES_HEADING}`"
        return report

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

    for story in epic.stories:
        if _runnable(epic, story, done, skip):
            report["state"] = "ready"
            report["story"] = _story_dict(epic, story)
            report["detail"] = f"{story.slug} is runnable"
            return report

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
               skip: frozenset[str] | set[str] | None = None,
               need: str = "build") -> dict | None:
    """The next runnable story in ``epic_name`` — not done, not skipped, all deps done."""
    return next_story_report(graph, epic_name, skip=skip, need=need)["story"]
