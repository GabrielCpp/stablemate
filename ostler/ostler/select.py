"""`ostler next-epic` / `next-story` — selection over the markdown graph.

Replaces the workflows' select-next-epic / select-next-story scripts. ``next-epic`` returns the
first milestone-ordered epic that still has unfinished work; ``next-story`` returns the next
runnable story (dependencies satisfied, not yet done) in dependency order.
"""

from __future__ import annotations

from ostler import registry
from ostler.model import Epic, Graph, Story

_DONE_STATUSES = {"qa passed", "passed", "done", "merged", "complete"}

#: The openings of every status a coder run stamped when it gave up on a story. Each
#: carries a trailing explanation — `QA give-up after 3
#: attempts — needs manual review: docs/specs/x/qa.md` — so this is a prefix vocabulary,
#: not a set of whole values like :data:`_DONE_STATUSES`.
_BLOCKED_PREFIXES = ("blocked", "docs blocked", "qa give-up", "qa give up")


def is_done(status: str) -> bool:
    s = (status or "").strip().lower()
    return s in _DONE_STATUSES


def is_blocked(status: str) -> bool:
    """Whether a status is a give-up stamp — a story set aside for a human, not built.

    Distinct from the ``blocked`` *state* of :func:`next_story_report`, which is derived per
    run from the skip set and the dependency graph and owns no storage. This one is the mark
    that outlives the run, and it is why it needs a reader: nothing else in the graph
    distinguishes "not started" from "tried three times and gave up", so an agent that
    re-selects the story reads the stamp and believes the work is unsalvageable. (Observed:
    a planner handed a story whose code was green on every gate answered ``blocked`` and
    wrote no plan, because the status still said give-up.)

    A blocked story is emphatically NOT done — selection already retries it on the next run.
    Unblocking is about the label the next agent reads, not about eligibility.
    """
    s = (status or "").strip().lower()
    return not is_done(s) and s.startswith(_BLOCKED_PREFIXES)


def epic_by_name(graph: Graph, name: str) -> Epic | None:
    """The epic named by its directory (`0001-checkout-flow`) or by its bare slug.

    Both spellings are accepted for the same reason `path.epic_dir` accepts both: the
    number is creation order, not identity, and plenty of callers — older index lines,
    prompts, an operator on the command line — only ever knew the slug.
    """
    exact = next((e for e in graph.epics if e.name == name), None)
    if exact is not None or registry.epic_seq(name) is not None:
        return exact
    slug = registry.epic_slug(name)
    return next((e for e in graph.epics if registry.epic_slug(e.name) == slug), None)


def epic_done(epic: Epic) -> bool:
    return bool(epic.stories) and all(is_done(s.status) for s in epic.stories)


def epic_authored(epic: Epic) -> bool:
    """Whether every story in the epic has a written story.md — the *authoring* completion rule.

    Distinct from :func:`epic_done`, which is about building. An epic whose stories are all
    bare scaffolds is not authored, however many story.md files exist on disk: file presence
    was the test that let an author rerun skip nine epics of empty stories and report success.
    """
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
    """The epic's stories in dependency order (a dependency precedes its dependents).

    Ties and cycles keep declaration order, so a malformed DAG degrades to the file's own
    sequence rather than dropping stories.

    This is the *authoring* order (:func:`_author_report`). The build path does not need it:
    a story is only runnable once every dependency is done, so no two runnable stories can
    depend on each other and reordering them cannot change which comes first. It iterates the
    epic's declared order directly — see :func:`next_story_report` on what that order is.
    """
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
            "storyShape": story.story_shape, "authored": story.authored,
            "unwrittenSections": list(story.unwritten_sections)}


def _author_report(epic: Epic, skip: frozenset[str] = frozenset(), *,
                   require_current_shape: bool = False) -> dict:
    """``need="author"`` — the first story in DAG order that still has no written story.md.

    Dependencies order the work but do not gate it: an unauthored dependency is a reason to
    write it *first*, not a reason to stall, so on this axis nothing ever waits on a
    dependency. Stories already authored are counted, not re-selected, which is what lets a
    rerun resume mid-epic instead of starting over or (as it did) skipping the epic entirely.

    ``skip`` is the author's own give-up set — a story the run parked because it exhausted its
    rework budget. It is excluded from selection but never counted as authored, exactly as on
    the build axis: otherwise a story nothing can fix stays first-unauthored forever and the
    epic's other 100 stories never get written. When every unauthored story is parked the state
    is ``blocked``, not ``done`` — the epic has unwritten scope in it and a caller that reads
    ``done`` would prune it.
    """
    ordered = dag_order(epic)
    def complete(story: Story) -> bool:
        return story.authored and (
            not require_current_shape
            or story.story_shape == registry.CURRENT_STORY_SHAPE
        )

    authored = [s.slug for s in ordered if complete(s)]
    pending = [s for s in ordered if not complete(s)]
    report = {"state": "", "story": None, "epic": epic.name, "total": len(ordered),
              "done": len(authored), "remaining": [s.slug for s in pending],
              "skipped": [s.slug for s in pending if s.slug in skip],
              "waiting_on": {}, "detail": ""}
    for story in pending:
        if story.slug in skip:
            continue
        report["state"] = "ready"
        report["story"] = _story_dict(epic, story)
        if story.authored and require_current_shape:
            report["detail"] = (
                f"{story.slug} uses story shape {story.story_shape!r}, "
                f"not current shape {registry.CURRENT_STORY_SHAPE}"
            )
        else:
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
    """Why there is (or is not) a next story in ``epic_name`` — not just whether there is one.

    ``next_story`` answers with a story or ``None``, and that ``None`` covers four different
    situations: the epic does not exist, every story is done, every remaining story was given
    up on this run, or every remaining story is waiting on a dependency that will never be
    satisfied. Callers cannot tell them apart — and the coder workflow's caller treats all of
    them as "epic finished", opens a PR and merges it. Only the first two of the four are
    finished; the other two merge an epic with unbuilt scope in it. That is the bug this
    function exists to make impossible: the caller gets a ``state``, not an absence.

    ``state`` is one of:

    ``ready``       a runnable story — ``story`` holds it. When several are runnable it is the
                    first in the epic's **declared** order, i.e. the order `## Stories` lists
                    them in, which is the order they were created in. A slug's numeric prefix
                    is *not* an ordering contract — ostler never mints it and never sorts on
                    it — so an epic that declares `03` before `02` builds `03` first, and that
                    is correct: a story's own `## Dependencies` section is where sequence is
                    stated, and a story with no
                    unmet dependency is by definition parallel to the ones around it. (Reading
                    the prefix as the queue is what made a run look like it *skipped* a story.)
    ``done``        every story in the epic is done. The only state that means "prune it".
    ``blocked``     stories remain but none is runnable: each is either in ``skip`` or waiting
                    on an unmet dependency (``waiting_on`` names which). Not finished.
    ``no-stories``  the epic exists but lists no stories at all. Deliberately NOT ``done`` —
                    an empty epic is unwritten scope, and treating it as complete drops it
                    from the queue silently. Distinct from stories that exist and are
                    unauthored, which is what ``Story.authored`` reports.
    ``no-epic``     no epic by that name in the graph.

    ``done``/``total``/``remaining``/``skipped``/``waiting_on`` are the census, and they are
    filled the same way whatever the state — including ``ready``, which is where a caller
    tracking progress spends the entire build. They are not a description of why the epic
    stalled; ``detail`` is.

    ``skip`` is a set of story slugs to treat as ineligible without treating them as *done*:
    a story the caller has given up on this run. Excluding it is essential — otherwise, since
    a given-up story is not "done", it stays first-runnable forever and the selector keeps
    returning it. The caller then rejects it and, finding nothing else, prunes the whole epic
    while other independent stories sit "Not started". (Observed: an epic merged with 20 of 21
    stories unbuilt after one story gave up on QA.) A skipped story is NOT added to ``done``,
    so its dependents stay blocked — you don't build on unverified work — but every story that
    does not depend on it remains selectable.

    ``need`` picks which question is being asked. ``"build"`` (the default, everything above)
    is the coder's: which story can be implemented next. ``"author"`` is the author's existing
    question: which story still has no written story.md. ``"author-current"`` additionally treats
    an authored legacy/unversioned story as pending until its persisted shape is current. On both
    authoring modes ``skip`` applies exactly as above and only the dependency machinery does not
    (see :func:`_author_report`). These are separate axes and a story is routinely finished on one
    and untouched on another, so a caller must say which it means; the report shape is identical.
    """
    epic = epic_by_name(graph, epic_name)
    if epic is None:
        return {"state": "no-epic", "story": None, "epic": epic_name, "total": 0, "done": 0,
                "remaining": [], "skipped": [], "waiting_on": {},
                "detail": f"no epic named '{epic_name}' in the graph"}
    if need not in ("build", "author", "author-current"):
        raise ValueError(
            f"unknown need '{need}' (expected 'build', 'author', or 'author-current')"
        )
    skip = frozenset(skip or ())
    if need in ("author", "author-current") and epic.stories:
        return _author_report(epic, skip, require_current_shape=need == "author-current")

    done = {s.slug for s in epic.stories if is_done(s.status)}
    report = {"state": "", "story": None, "epic": epic.name, "total": len(epic.stories),
              "done": len(done), "remaining": [], "skipped": [], "waiting_on": {},
              "detail": ""}

    if not epic.stories:
        report["state"] = "no-stories"
        report["detail"] = f"epic '{epic.name}' lists no stories in `## {registry.STORIES_HEADING}`"
        return report

    # The not-done stories, and why each is not runnable — per story, since the reasons
    # differ within one epic. Counted *before* selection so `remaining` means the same
    # thing in every state, as it already does on the `author` path. It used to be filled
    # only after the `ready` return below, which left `ready` — the one state a caller
    # reading progress is actually in — reporting `done=0, remaining=[]`. The coder's
    # labels rendered that as "0/0" for the whole of every epic it was building.
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

    # First runnable in the epic's declared order — see the docstring on why that is the order.
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
    """The next runnable story in ``epic_name`` — not done, not skipped, all deps done.

    Thin wrapper over :func:`next_story_report` for callers that only need the story (the
    ``ostler next-story`` CLI). Anything that decides what to do when there *is* no story
    should call the report instead — see its docstring for why ``None`` is not enough.
    """
    return next_story_report(graph, epic_name, skip=skip, need=need)["story"]
