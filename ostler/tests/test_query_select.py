from __future__ import annotations

from pathlib import Path

from ostler import backlog, crud, query, select, todo
from ostler.model import load

from conftest import write


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
    ne = select.next_epic(g)
    assert ne["name"] == "epic-a"
    ns = select.next_story(g, "epic-a")
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
    assert select.next_story(load(tmp_path), "e")["slug"] == "a"
    crud.set_status(load(tmp_path), "a", "done")
    assert select.next_story(load(tmp_path), "e")["slug"] == "b"


def test_todo_queue(tmp_path: Path):
    g = load(tmp_path)
    crud.create_epic(g, "one", "One", prefix="x")
    crud.create_epic(load(tmp_path), "two", "Two", prefix="x")
    todo.add(load(tmp_path), "one")
    todo.add(load(tmp_path), "two")
    assert todo.list_epics(load(tmp_path)) == ["one", "two"]
    todo.reorder(load(tmp_path), ["two", "one"])
    assert todo.list_epics(load(tmp_path)) == ["two", "one"]
    todo.prune(load(tmp_path), "two")
    assert todo.list_epics(load(tmp_path)) == ["one"]


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
