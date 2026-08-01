from __future__ import annotations

from pathlib import Path

import pytest

from ostler import backlog, crud, query, select, todo
from ostler.model import load

from conftest import present, write


def test_list_by_type(repo: Path):
    g = load(repo)
    assert {r["name"] for r in query.list_entities(g, "epic")} == {"epic-a", "epic-b"}
    assert {r["slug"] for r in query.list_entities(g, "story")} == {"01-foo", "01-bar"}
    assert {r["id"] for r in query.list_entities(g, "seed")} == {"seed-a1", "seed-a2", "seed-b1"}
    assert {r["surface"] for r in query.list_entities(g, "knowledge")} == {"area/rec", "area/rec2"}


def test_list_filters(repo: Path):
    g = load(repo)
    rows = query.list_entities(g, "seed", epic="epic-a")
    assert {r["id"] for r in rows} == {"seed-a1", "seed-a2"}
    rows = query.list_entities(g, "seed", status="resolved")
    assert {r["id"] for r in rows} == {"seed-a2"}


def test_search_hits_body(repo: Path):
    g = load(repo)
    hits = query.search(g, "thing works", etype="story")
    assert any(h["slug"] == "01-foo" for h in hits)


def test_query_reverse_indexes(repo: Path):
    g = load(repo)
    covers = query.query(g, "stories-covering-seed", "seed-a1")
    assert {x["slug"] for x in covers} == {"01-foo"}
    refs = query.query(g, "surfaces-referenced-by-story", "01-foo")
    assert any("rec.md" in x["path"] for x in refs)


def test_next_epic_and_story(repo: Path):
    g = load(repo)
    # both epics have un-done stories; no index → graph order, first is epic-a
    ne = present(select.next_epic(g))
    assert ne["name"] == "epic-a"
    ns = present(select.next_story(g, "epic-a"))
    assert ns["slug"] == "01-foo"
    # mark 01-foo done → no runnable story left in epic-a
    crud.set_status(load(repo), "01-foo", "QA passed")
    assert select.next_story(load(repo), "epic-a") is None


def test_next_story_respects_dependencies(tmp_path: Path):
    g = load(tmp_path)
    crud.create_epic(g, "e", "E", prefix="x")
    crud.create_story(load(tmp_path), "e", "a", "A")
    crud.create_story(load(tmp_path), "e", "b", "B", depends=["a"])
    # b depends on a (not done) → next is a
    assert present(select.next_story(load(tmp_path), "e"))["slug"] == "a"
    crud.set_status(load(tmp_path), "a", "done")
    assert present(select.next_story(load(tmp_path), "e"))["slug"] == "b"


def test_todo_queue(tmp_path: Path):
    """The queue names the directories that exist; every operation still takes a bare slug.

    A caller queues, reorders and prunes by the slug it knows — the numbering is ostler's,
    minted at creation, and a workflow prompt holding `two` must not have to learn that the
    folder is `0002-two` before it can touch the queue.
    """
    g = load(tmp_path)
    crud.create_epic(g, "one", "One", prefix="x")
    crud.create_epic(load(tmp_path), "two", "Two", prefix="x")
    todo.add(load(tmp_path), "one")
    todo.add(load(tmp_path), "two")
    assert todo.list_epics(load(tmp_path)) == ["0001-one", "0002-two"]
    todo.reorder(load(tmp_path), ["two", "one"])
    assert todo.list_epics(load(tmp_path)) == ["0002-two", "0001-one"]
    todo.prune(load(tmp_path), "two")
    assert todo.list_epics(load(tmp_path)) == ["0001-one"]
    # And a slug already queued under its numbered name is not queued twice.
    assert not todo.add(load(tmp_path), "one").ok


def test_todo_add_warns_when_the_epic_has_no_doc(tmp_path: Path):
    """Queueing a name with no epic.md still succeeds (queue-ahead is legitimate), but says
    so: selection silently skips such a name and then reports "every epic is fully authored",
    which is a no-work run indistinguishable from a successful one."""
    write(tmp_path / "docs/epics/.keep", "")
    res = todo.add(load(tmp_path), "ghost")
    assert res.ok
    assert "WARNING" in res.message and "ghost" in res.message
    assert todo.list_epics(load(tmp_path)) == ["ghost"]


def test_todo_add_does_not_warn_for_a_real_epic(tmp_path: Path):
    crud.create_epic(load(tmp_path), "real", "Real", prefix="x")
    res = todo.add(load(tmp_path), "real")
    assert res.ok and "WARNING" not in res.message


def test_backlog(tmp_path: Path):
    write(tmp_path / "docs/knowledge/.keep", "")  # make it a repo root with docs/
    g = load(tmp_path)
    assert backlog.add(g, "b1", "do a thing").ok
    assert backlog.add(load(tmp_path), "b2", "do another", section="Filed by coder").ok
    items = dict(backlog.items(load(tmp_path)))
    assert items == {"b1": "do a thing", "b2": "do another"}
    assert backlog.prune(load(tmp_path), "b1").ok
    assert dict(backlog.items(load(tmp_path))) == {"b2": "do another"}


def test_next_story_skips_given_up_without_stranding_the_epic(tmp_path: Path):
    """The premature-epic-completion bug: a story that gave up on QA is not "done", so it
    stays first-runnable forever and the selector keeps returning it. The caller rejects it
    and, finding nothing else, prunes the whole epic — while independent stories sit unbuilt.
    Observed live: an epic merged with 20 of 21 stories "Not started" after one gave up.

    Skip-aware selection must exclude the given-up story WITHOUT counting it as done, then
    return the next independent runnable story."""
    g = load(tmp_path)
    crud.create_epic(g, "e", "E", prefix="x")
    crud.create_story(load(tmp_path), "e", "first", "First")      # gives up
    crud.create_story(load(tmp_path), "e", "independent", "Indep")  # no deps — must still run
    crud.create_story(load(tmp_path), "e", "dependent", "Dep", depends=["first"])

    # Without a skip set, selection returns the first story.
    assert present(select.next_story(load(tmp_path), "e"))["slug"] == "first"

    # With 'first' given up: it is excluded, and the next INDEPENDENT story runs.
    nxt = select.next_story(load(tmp_path), "e", skip={"first"})
    assert nxt is not None, "epic must not be treated as complete — 2 stories remain runnable"
    assert nxt["slug"] == "independent"


def test_next_story_keeps_dependents_of_a_given_up_story_blocked(tmp_path: Path):
    """A skipped story is not 'done', so its dependents stay blocked — you don't build on
    unverified work. Only the skipped story and its dependents are excluded; nothing else."""
    g = load(tmp_path)
    crud.create_epic(g, "e", "E", prefix="x")
    crud.create_story(load(tmp_path), "e", "base", "Base")            # gives up
    crud.create_story(load(tmp_path), "e", "onbase", "OnBase", depends=["base"])

    # base skipped, onbase depends on it → nothing runnable → None (genuinely no work now).
    assert select.next_story(load(tmp_path), "e", skip={"base"}) is None


def test_next_story_skip_is_backward_compatible(tmp_path: Path):
    """Existing callers pass no skip set; behaviour is unchanged."""
    g = load(tmp_path)
    crud.create_epic(g, "e", "E", prefix="x")
    crud.create_story(load(tmp_path), "e", "only", "Only")
    assert present(select.next_story(load(tmp_path), "e"))["slug"] == "only"
    assert present(select.next_story(load(tmp_path), "e", skip=set()))["slug"] == "only"


def test_report_separates_done_from_blocked(tmp_path: Path):
    """The four ``None`` cases must be four distinct states — that split is the whole point.

    ``done`` is the only one that means "prune and merge the epic"; the caller reads
    ``state``, so a blocked epic reporting anything but ``blocked`` ships unbuilt scope.
    """
    g = load(tmp_path)
    crud.create_epic(g, "e", "E", prefix="x")
    crud.create_story(load(tmp_path), "e", "a", "A")
    crud.create_story(load(tmp_path), "e", "b", "B", depends=["a"])

    ready = select.next_story_report(load(tmp_path), "e")
    assert ready["state"] == "ready" and ready["story"]["slug"] == "a"

    # 'a' given up → 'b' depends on it → nothing runnable, but the epic is NOT finished.
    blocked = select.next_story_report(load(tmp_path), "e", skip={"a"})
    assert blocked["state"] == "blocked"
    assert blocked["story"] is None
    assert set(blocked["remaining"]) == {"a", "b"}
    assert blocked["skipped"] == ["a"]
    assert blocked["waiting_on"] == {"b": ["a"]}
    assert "given up this run: a" in blocked["detail"]

    crud.set_status(load(tmp_path), "a", "QA passed")
    crud.set_status(load(tmp_path), "b", "QA passed")
    finished = select.next_story_report(load(tmp_path), "e")
    assert finished["state"] == "done"
    assert finished["done"] == finished["total"] == 2


def test_a_ready_report_counts_the_work_left_like_every_other_state(tmp_path: Path):
    """`ready` is where a run spends the whole build, and it must not be the blind state.

    The census (`done`/`total`/`remaining`) used to be filled only on the paths that come
    after the `ready` return, so the one state a progress reader is ever in answered
    `done=0, remaining=[]`. The coder derives its `progress` label from exactly those two
    fields and rendered "0/3" as "0/0" for every story of every epic — a queue that looks
    empty while it is being built.

    The story being handed back is itself unfinished, so it counts as remaining: `remaining`
    is "not done", not "not selected".
    """
    g = load(tmp_path)
    crud.create_epic(g, "e", "E", prefix="x")
    for slug in ("a", "b", "c"):
        crud.create_story(load(tmp_path), "e", slug, slug.upper())
    crud.set_status(load(tmp_path), "a", "QA passed")

    ready = select.next_story_report(load(tmp_path), "e")

    assert ready["state"] == "ready" and ready["story"]["slug"] == "b"
    assert (ready["done"], ready["total"]) == (1, 3)  # the "1/3" the run's progress reads
    assert ready["remaining"] == ["b", "c"]
    # Nothing is skipped or waiting, and the census says so rather than staying silent.
    assert ready["skipped"] == [] and ready["waiting_on"] == {}


def test_declared_order_wins_over_the_slugs_numeric_prefix(tmp_path: Path):
    """A story numbered `02` declared after `03` does not jump the queue — and must not.

    Real epics are written this way: the author appends each story as it decides on it, so
    `## Stories` ends up listing `01, 03, 04, 02, …` while the prefixes track milestones. A
    coder run then builds `01` and picks `03`, which reads as *skipping* `02` and cost a
    session's diagnosis. It is correct: `02` states its sequence with `depends on:`, which is
    honoured, and having no unmet dependency is exactly what makes `03` parallel to it. Sorting
    on the prefix instead would invent an ordering contract ostler does not offer — it never
    mints the slug — and would serialise work the author declared independent.
    """
    g = load(tmp_path)
    crud.create_epic(g, "e", "E", prefix="x")
    crud.create_story(load(tmp_path), "e", "01-first", "First")
    crud.create_story(load(tmp_path), "e", "03-independent", "Independent")
    crud.create_story(load(tmp_path), "e", "02-after-first", "After first", depends=["01-first"])

    assert present(select.next_story(load(tmp_path), "e"))["slug"] == "01-first"

    # '01' done unblocks '02', but '03' is declared first and is runnable, so '03' is next.
    crud.set_status(load(tmp_path), "01-first", "QA passed")
    report = select.next_story_report(load(tmp_path), "e")
    assert report["state"] == "ready"
    assert report["story"]["slug"] == "03-independent"

    # The dependency itself is still a real gate: '02' is only passed over, never lost.
    crud.set_status(load(tmp_path), "03-independent", "QA passed")
    assert present(select.next_story(load(tmp_path), "e"))["slug"] == "02-after-first"


def test_report_distinguishes_an_unwritten_epic_from_a_finished_one(tmp_path: Path):
    """An epic that lists no stories at all is ``no-stories``, never ``done``.

    Zero stories done out of zero is arithmetically "all done", and calling it that drops
    unwritten scope out of the queue silently. Absent epics get their own state too, so a
    typo'd name cannot be read as completion either.
    """
    g = load(tmp_path)
    crud.create_epic(g, "empty", "Empty", prefix="x")

    empty = select.next_story_report(load(tmp_path), "empty")
    assert empty["state"] == "no-stories"
    assert empty["story"] is None

    missing = select.next_story_report(load(tmp_path), "nope")
    assert missing["state"] == "no-epic"
    assert missing["story"] is None


# --------------------------------------------------------------------------- #
# next_story_report(need="author")                                            #
# --------------------------------------------------------------------------- #
#
# The author workflow's selection question — "which story still has nothing in it?" — answered
# by the same DAG walk the coder builds with, instead of by a script scanning for the presence
# of a file. Presence was the whole defect: every scaffold existed, so every epic read as
# finished and the author run wrote nothing and said it was done.

def _authored(root: Path, slug: str) -> None:
    """Fill a scaffold's required sections, the way a write_story node does."""
    _, story = present(load(root).find_story(slug))
    story_md = present(story.story_md)
    story_md.write_text(
        story_md.read_text(encoding="utf-8")
        .replace("## Context\n", "## Context\n\n- why this matters\n")
        .replace("## Acceptance Criteria\n", "## Acceptance Criteria\n\n- The thing works.\n"),
        encoding="utf-8",
    )


def _epic_of_scaffolds(root: Path, stories: list[tuple[str, list[str]]]) -> None:
    crud.create_epic(load(root), "e", "E", prefix="x")
    for slug, depends in stories:
        crud.create_story(load(root), "e", slug, slug.upper(), depends=depends)


def test_author_report_selects_the_first_unwritten_story_in_dag_order(tmp_path: Path):
    """Declaration order does not decide; dependency order does — the order coder will build in.

    Writing a dependent before its dependency is how a story ends up specified against
    requirements that do not exist yet, so the author walks the DAG even though, unlike the
    build path, nothing here is *blocked* by an unwritten dependency.
    """
    _epic_of_scaffolds(tmp_path, [("b", ["a"]), ("a", [])])

    report = select.next_story_report(load(tmp_path), "e", need="author")

    assert report["state"] == "ready"
    assert report["story"]["slug"] == "a"
    assert report["story"]["authored"] is False
    assert report["story"]["unwrittenSections"] == ["Context", "Acceptance Criteria"]
    assert "a is unwritten" in report["detail"]


def test_author_report_counts_authored_stories_and_resumes_at_the_first_gap(tmp_path: Path):
    """A rerun picks up where the last one stopped: written stories are counted, not rewritten.

    This is the self-correction property. The failed run left every story a stub; with
    presence-based selection a rerun had nothing to select and ended immediately, so there was
    no way to make the workflow finish its own work short of deleting the stubs by hand.
    """
    _epic_of_scaffolds(tmp_path, [("a", []), ("b", ["a"]), ("c", ["b"])])
    _authored(tmp_path, "a")

    report = select.next_story_report(load(tmp_path), "e", need="author")

    assert report["state"] == "ready"
    assert report["story"]["slug"] == "b"
    assert (report["done"], report["total"]) == (1, 3)   # the "1/3" the run's progress reads
    assert report["remaining"] == ["b", "c"]


def test_author_report_is_done_only_when_every_story_is_written(tmp_path: Path):
    _epic_of_scaffolds(tmp_path, [("a", []), ("b", ["a"])])
    _authored(tmp_path, "a")
    assert select.next_story_report(load(tmp_path), "e", need="author")["state"] == "ready"

    _authored(tmp_path, "b")
    report = select.next_story_report(load(tmp_path), "e", need="author")

    assert report["state"] == "done"
    assert report["story"] is None
    assert report["done"] == report["total"] == 2
    assert report["remaining"] == []


def test_author_and_build_are_separate_axes(tmp_path: Path):
    """A story can be unwritten and "not done", or written and done — the two never substitute.

    ``need`` exists because the same epic answers both questions differently, and a caller that
    read the wrong one either rewrites finished stories or plans against empty ones.
    """
    _epic_of_scaffolds(tmp_path, [("a", [])])
    _authored(tmp_path, "a")
    crud.set_status(load(tmp_path), "a", "QA passed")

    g = load(tmp_path)
    assert select.next_story_report(g, "e", need="author")["state"] == "done"
    assert select.next_story_report(g, "e", need="build")["state"] == "done"

    # Now the reverse: written, but nowhere near built.
    crud.set_status(load(tmp_path), "a", "In progress")
    g = load(tmp_path)
    assert select.next_story_report(g, "e", need="author")["state"] == "done"
    assert select.next_story_report(g, "e", need="build")["state"] == "ready"


def test_epic_authored_needs_stories_a_doc_and_content(tmp_path: Path):
    """``epic_authored`` is the fact ``select-epic.py`` got wrong — pin all three of its parts."""
    _epic_of_scaffolds(tmp_path, [("a", []), ("b", [])])
    epic = present(select.epic_by_name(load(tmp_path), "e"))
    assert not select.epic_authored(epic), "an epic of bare scaffolds is not authored"

    _authored(tmp_path, "a")
    epic = present(select.epic_by_name(load(tmp_path), "e"))
    assert not select.epic_authored(epic), "one written story does not finish the epic"

    _authored(tmp_path, "b")
    epic = present(select.epic_by_name(load(tmp_path), "e"))
    assert select.epic_authored(epic)


def test_epic_with_no_stories_is_not_authored(tmp_path: Path):
    # Zero of zero is arithmetically "all", and calling it authored drops unwritten scope out
    # of the queue silently — the same trap `no-stories` exists to keep out of `done`.
    crud.create_epic(load(tmp_path), "empty", "Empty", prefix="x")
    epic = select.epic_by_name(load(tmp_path), "empty")
    assert epic is not None and not select.epic_authored(epic)


def test_an_unknown_need_is_rejected(tmp_path: Path):
    """A typo'd ``need`` must not silently fall through to the build answer.

    The two axes disagree constantly, so a caller that meant "author" and got "build" would
    read an epic of empty stories as ready to select — the original failure, reintroduced.
    """
    _epic_of_scaffolds(tmp_path, [("a", [])])
    with pytest.raises(ValueError, match="unknown need"):
        select.next_story_report(load(tmp_path), "e", need="authored")
