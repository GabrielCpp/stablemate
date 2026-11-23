"""The whole-graph snapshot cache: it may save a load, and it may never change an answer."""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler import api, model, index
from ostler.api import Ostler

from conftest import BAR_STORY, FOO_ID, EPIC_A, EPIC_B, FOO_STORY, epic_md, story_md, write, epics_root


def loads(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """A one-element counter of how many times `api.load` actually ran."""
    counter = [0]
    real = api.load

    def spy(*args, **kwargs):
        counter[0] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(api, "load", spy)
    return counter


def drop_snapshot(directory: Path, key: str | None) -> None:
    """Delete just the snapshot entry, leaving the parse products warm."""
    assert key is not None
    entry = directory / key[:2] / key
    entry.unlink()


def entries(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*") if p.is_file() and p.name != index.PRUNE_STAMP_NAME)


def test_a_second_instance_over_an_unmoved_book_does_not_load(repo, index_home, monkeypatch):
    counter = loads(monkeypatch)
    first = Ostler(repo).graph

    second = Ostler(repo)
    graph = second.graph

    assert counter == [1], "the second construction must be served the stored snapshot"
    assert second.snapshot_stats() == {"hits": 1, "misses": 0}
    assert [e.name for e in graph.epics] == [e.name for e in first.epics]
    assert {s.slug for e in graph.epics for s in e.stories} == {"01-foo", "01-bar"}


def test_a_hit_serves_no_document_from_the_parse_index(repo, index_home):
    """The saving is a different one: a snapshot hit reads no document at all."""
    Ostler(repo).graph

    second = Ostler(repo)
    second.graph

    assert second.snapshot_stats()["hits"] == 1
    assert second.index_stats()["hits"] == 0


def test_writing_into_the_spec_root_does_not_invalidate(repo, index_home, monkeypatch):
    """The case a key over the whole tree would get wrong."""
    Ostler(repo).graph
    counter = loads(monkeypatch)
    write(repo / "docs/specs/01-foo/qa.md", "# QA plan\n")

    okf = Ostler(repo)
    okf.graph

    assert okf.snapshot_stats()["hits"] == 1
    assert counter == [0]


def test_editing_a_story_invalidates(repo, index_home):
    Ostler(repo).graph
    write(epics_root() / FOO_STORY,
          story_md("01-foo", "Foo", "QA passed", eid=FOO_ID))

    okf = Ostler(repo)
    story = next(s for e in okf.graph.epics for s in e.stories if s.slug == "01-foo")

    assert okf.snapshot_stats() == {"hits": 0, "misses": 1}
    assert story.status == "QA passed"


def test_a_new_document_invalidates(repo, index_home):
    """The listing half: a per-file digest can only speak for files that already existed."""
    Ostler(repo).graph
    write(epics_root() / "t-3/epic.md", epic_md(
        "t-3", "epic-c", seeds=[("seed-c1", "researched", "see")],
        stories=[("01-baz", "Baz", ["seed-c1"], "t-03baz")], slug="epic-c"))

    okf = Ostler(repo)
    names = {e.name for e in okf.graph.epics}

    assert okf.snapshot_stats()["misses"] == 1
    assert "t-3" in names


def test_a_deleted_document_invalidates(repo, index_home):
    Ostler(repo).graph
    (epics_root() / BAR_STORY).unlink()

    okf = Ostler(repo)
    story = next(s for e in okf.graph.epics if e.name == EPIC_B for s in e.stories)

    assert okf.snapshot_stats()["misses"] == 1
    assert story.story_md is None


def test_a_story_file_appearing_where_none_was_invalidates(repo, index_home):
    """The negative half: a graph is a function of what was *not* found, too."""
    write(epics_root() / "t-3/epic.md", epic_md(
        "t-3", "epic-c", seeds=[("seed-c1", "researched", "see")],
        stories=[("01-baz", "Baz", ["seed-c1"], "t-03baz")], slug="epic-c"))
    first = Ostler(repo)
    story = next(s for e in first.graph.epics if e.name == "t-3" for s in e.stories)
    assert story.story_md is None

    write(epics_root() / "t-3/stories/t-03baz/story.md", story_md("01-baz", "Baz", "Not started", eid="t-03baz"))
    okf = Ostler(repo)
    grown = next(s for e in okf.graph.epics if e.name == "t-3" for s in e.stories)

    assert okf.snapshot_stats()["misses"] == 1

    assert grown.story_md is not None


def test_a_different_book_gets_a_different_snapshot(repo, tmp_path, index_home):
    other = tmp_path / "other"
    (other / ".git").mkdir(parents=True)
    Ostler(repo).graph

    okf = Ostler(other)
    _ = okf.graph

    assert okf.snapshot_stats()["misses"] == 1


def test_a_corrupt_entry_is_a_miss_not_a_failure(repo, index_home):
    Ostler(repo).graph
    written = entries(index_home)
    assert written, "the first construction must have stored something"
    for entry in written:
        entry.write_bytes(b"\x80\x04not-a-pickle")

    okf = Ostler(repo)
    names = {e.name for e in okf.graph.epics}

    assert okf.snapshot_stats()["misses"] == 1
    assert names == {EPIC_A, EPIC_B}


def test_a_truncated_entry_is_a_miss_not_a_failure(repo, index_home):
    Ostler(repo).graph
    for entry in entries(index_home):
        entry.write_bytes(entry.read_bytes()[: max(1, len(entry.read_bytes()) // 3)])

    okf = Ostler(repo)
    names = {e.name for e in okf.graph.epics}

    assert okf.snapshot_stats()["misses"] == 1
    assert names == {EPIC_A, EPIC_B}


def test_a_payload_that_is_not_a_snapshot_is_a_miss(repo, index_home, monkeypatch):
    """A stored value of the wrong shape — an older layout, another product — recomputes."""
    okf = Ostler(repo)
    okf.graph
    key = okf._snapshot_key()
    okf.index.put_key(key, {"graph": "not a Snapshot"})

    fresh = Ostler(repo)
    names = {e.name for e in fresh.graph.epics}

    assert fresh.snapshot_stats()["misses"] == 1
    assert names == {EPIC_A, EPIC_B}


def test_no_index_stores_and_serves_no_snapshot(repo, tmp_path, index_home, monkeypatch):
    explicit = tmp_path / "off"
    counter = loads(monkeypatch)

    Ostler(repo, use_index=False, index_dir=explicit).graph
    second = Ostler(repo, use_index=False, index_dir=explicit)
    second.graph

    assert counter == [2], "--no-index must force the uncached path both ways"
    assert second.snapshot_stats() == {"hits": 0, "misses": 0}
    assert entries(explicit) == []
    assert entries(index_home) == []


def test_the_probe_order_matches_the_loader(repo, index_home):
    """`_story_candidates` repeats `model._attach_story_md`'s list; a drift is a stale hit."""
    okf = Ostler(repo)
    epic = next(e for e in okf.graph.epics if e.name == EPIC_A)
    story = next(s for s in epic.stories if s.slug == "01-foo")
    candidates = api._story_candidates(okf.graph, epic, story)

    assert candidates == [okf.graph.root / story.path,
                          epic.directory / "stories" / story.slug / "story.md"]
    loader = model._attach_story_md.__code__
    assert {"stories", "story.md"} <= set(loader.co_consts)
    assert {"root", "path", "directory", "slug"} <= set(loader.co_names)

    snapshot = api._snapshot_of(okf.graph, okf._loaded_doc_roots())
    assert str(story.story_md) in snapshot.files


def big_book(root: Path, milestones: int = 400, epics: int = 4, stories: int = 8) -> Path:
    """A book of a few hundred documents — the scale the saving is actually about."""
    for i in range(milestones):
        write(root / f"docs/milestones/m{i}/milestone.md",
              f"---\ntype: milestone\nid: m{i}\ntitle: M {i}\nstatus: proposed\ndependsOn: []\nepics: []\n---\n# M {i}\n")
    for e in range(epics):
        write(epics_root() / f"t-{e}/epic.md", epic_md(
            f"t-{e}", f"epic-{e}", seeds=[(f"seed-{e}", "researched", "s")],
            stories=[(f"0{s}-story", f"S{s}", [], f"t-{e}s{s}") for s in range(stories)],
            slug=f"epic-{e}"))
        for s in range(stories):
            write(epics_root() / f"t-{e}/stories/t-{e}s{s}/story.md",
                  story_md(f"0{s}-story", f"S{s}", "Not started", eid=f"t-{e}s{s}"))
    return root


def test_a_warm_snapshot_parses_no_document(tmp_path, index_home, monkeypatch):
    """A cold load reads every document of the book, and a warm snapshot reads none."""
    milestones, epics, stories = 400, 4, 8
    book = big_book(tmp_path / "book", milestones=milestones, epics=epics, stories=stories)
    reads = [0]
    real = model.read_doc

    def counting(path):
        reads[0] += 1
        return real(path)

    monkeypatch.setattr(model, "read_doc", counting)

    cold = Ostler(book)
    cold.graph
    assert cold.snapshot_stats()["misses"] == 1
    assert reads[0] >= milestones + epics + epics * stories
    reads[0] = 0

    warm = Ostler(book)
    warm.graph
    assert warm.snapshot_stats()["hits"] == 1
    assert reads[0] == 0
