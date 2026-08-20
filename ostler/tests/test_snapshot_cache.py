"""The whole-graph snapshot cache: it may save a load, and it may never change an answer.

The parse index makes each *document* cheap to re-read. What no caller could avoid until now
is the load itself — the walk, the frontmatter dispatch and the cross-linking that turn some
thousands of parsed documents into a graph — and every fresh `Ostler`, in-process or in a new
`ostler` process, paid it again while nothing in the book had moved.

The bar these tests hold the cache to is the one every cache in this repo is held to: damage
is a miss, a moved dependency is a miss, and the only observable difference between a hit and
a miss is how long it took. So each invalidation below asserts the *graph*, not merely the
counter — a cache that notices a change and still hands back the old answer would satisfy a
hit/miss assertion perfectly.
"""

from __future__ import annotations

import inspect
import time
from pathlib import Path

import pytest

from ostler import api, model, index
from ostler.api import Ostler

from conftest import epic_md, feature_md, story_md, write


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
    """Delete just the snapshot entry, leaving the parse products warm.

    The store sharded on the first two characters of the key; repeating that here is the
    price of measuring the two caches apart, and it is asserted rather than assumed — an
    entry that was not there to delete fails the call.
    """
    assert key is not None
    entry = directory / key[:2] / key
    entry.unlink()


def entries(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*") if p.is_file() and p.name != index.PRUNE_STAMP_NAME)


# ---------------------------------------------------------------------------
# the hit
# ---------------------------------------------------------------------------
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
    """The case a key over the whole tree would get wrong.

    A coder run writes a QA plan into `docs/specs/<story>/` between two loads that want the
    same graph. No document `load` reads has moved, so the snapshot still holds — and if it
    did not, the cache would miss on every lap of the exact workflow it exists for.
    """
    Ostler(repo).graph
    counter = loads(monkeypatch)
    write(repo / "docs/specs/01-foo/qa.md", "# QA plan\n")

    okf = Ostler(repo)
    okf.graph

    assert okf.snapshot_stats()["hits"] == 1
    assert counter == [0]


# ---------------------------------------------------------------------------
# the invalidations
# ---------------------------------------------------------------------------
def test_editing_a_story_invalidates(repo, index_home):
    Ostler(repo).graph
    write(repo / "docs/epics/epic-a/stories/01-foo/story.md",
          story_md("01-foo", "Foo", "QA passed"))

    okf = Ostler(repo)
    story = next(s for e in okf.graph.epics for s in e.stories if s.slug == "01-foo")

    assert okf.snapshot_stats() == {"hits": 0, "misses": 1}
    assert story.status == "QA passed"


def test_a_new_document_invalidates(repo, index_home):
    """The listing half: a per-file digest can only speak for files that already existed."""
    Ostler(repo).graph
    write(repo / "docs/features/area/rec3.md", feature_md("rec3", "Rec 3", area="area"))

    okf = Ostler(repo)
    features = {f.slug for f in okf.graph.features}

    assert okf.snapshot_stats()["misses"] == 1
    assert "rec3" in features


def test_a_deleted_document_invalidates(repo, index_home):
    Ostler(repo).graph
    (repo / "docs/features/area/rec2.md").unlink()

    okf = Ostler(repo)
    features = {f.slug for f in okf.graph.features}

    assert okf.snapshot_stats()["misses"] == 1
    assert "rec2" not in features


def test_a_story_file_appearing_where_none_was_invalidates(repo, index_home):
    """The negative half: a graph is a function of what was *not* found, too."""
    write(repo / "docs/epics/epic-c/epic.md", epic_md(
        "t-3", "epic-c", seeds=[("seed-c1", "researched", "see")],
        stories=[("01-baz", "Baz", ["seed-c1"])]))
    first = Ostler(repo)
    story = next(s for e in first.graph.epics if e.name == "epic-c" for s in e.stories)
    assert story.story_md is None

    write(repo / "docs/epics/epic-c/stories/01-baz/story.md", story_md("01-baz", "Baz", "Not started"))
    okf = Ostler(repo)
    grown = next(s for e in okf.graph.epics if e.name == "epic-c" for s in e.stories)

    assert okf.snapshot_stats()["misses"] == 1

    assert grown.story_md is not None


def test_a_different_book_gets_a_different_snapshot(repo, tmp_path, index_home):
    other = tmp_path / "other"
    write(other / "docs/features/area/only.md", feature_md("only", "Only", area="area"))
    Ostler(repo).graph

    okf = Ostler(other)
    features = {f.slug for f in okf.graph.features}

    assert okf.snapshot_stats()["misses"] == 1
    assert features == {"only"}


def test_ids_json_is_part_of_the_snapshot(repo, index_home):
    """`epoch` covers only the `frozen` table; the graph carries the whole registry."""
    write(repo / ".agents/ids.json", '{"counter": 1, "frozen": {}}\n')
    Ostler(repo).graph
    write(repo / ".agents/ids.json", '{"counter": 2, "frozen": {}}\n')

    okf = Ostler(repo)
    ids = okf.graph.ids or {}

    assert okf.snapshot_stats()["misses"] == 1
    assert ids.get("counter") == 2


# ---------------------------------------------------------------------------
# damage, and the off switch
# ---------------------------------------------------------------------------
def test_a_corrupt_entry_is_a_miss_not_a_failure(repo, index_home):
    Ostler(repo).graph
    written = entries(index_home)
    assert written, "the first construction must have stored something"
    for entry in written:
        entry.write_bytes(b"\x80\x04not-a-pickle")

    okf = Ostler(repo)
    names = {e.name for e in okf.graph.epics}

    assert okf.snapshot_stats()["misses"] == 1
    assert names == {"epic-a", "epic-b"}


def test_a_truncated_entry_is_a_miss_not_a_failure(repo, index_home):
    Ostler(repo).graph
    for entry in entries(index_home):
        entry.write_bytes(entry.read_bytes()[: max(1, len(entry.read_bytes()) // 3)])

    okf = Ostler(repo)
    names = {e.name for e in okf.graph.epics}

    assert okf.snapshot_stats()["misses"] == 1
    assert names == {"epic-a", "epic-b"}


def test_a_payload_that_is_not_a_snapshot_is_a_miss(repo, index_home, monkeypatch):
    """A stored value of the wrong shape — an older layout, another product — recomputes."""
    okf = Ostler(repo)
    okf.graph
    key = okf._snapshot_key()
    okf.index.put_key(key, {"graph": "not a Snapshot"})

    fresh = Ostler(repo)
    names = {e.name for e in fresh.graph.epics}

    assert fresh.snapshot_stats()["misses"] == 1
    assert names == {"epic-a", "epic-b"}


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
    """`_story_candidates` repeats `model._attach_story_md`'s list; a drift is a stale hit.

    Asserted against the loader's own source rather than against a book, because today the
    two candidates coincide — `_parse_stories` derives `story.path` as the conventional
    location, so no fixture can make them differ. The day one does, this fails here instead
    of as a snapshot that holds while the graph has moved.
    """
    okf = Ostler(repo)
    epic = next(e for e in okf.graph.epics if e.name == "epic-a")
    story = next(s for s in epic.stories if s.slug == "01-foo")
    candidates = api._story_candidates(okf.graph, epic, story)

    loader = inspect.getsource(model._attach_story_md)
    assert candidates == [okf.graph.root / story.path,
                          epic.directory / "stories" / story.slug / "story.md"]
    assert "candidates.append(graph.root / story.path)" in loader
    assert 'candidates.append(epic.directory / "stories" / story.slug / "story.md")' in loader

    snapshot = api._snapshot_of(okf.graph, okf._loaded_doc_roots())
    assert str(story.story_md) in snapshot.files


def big_book(root: Path, features: int = 400, epics: int = 4, stories: int = 8) -> Path:
    """A book of a few hundred documents — the scale the saving is actually about.

    The `repo` fixture loads in about two milliseconds, which is the same order as digesting
    its six files, so no ratio measured against it would mean anything. A real book is
    thousands of documents; this is the smallest tree that behaves like one.
    """
    for i in range(features):
        write(root / f"docs/features/area{i % 8}/rec{i}.md",
              feature_md(f"rec{i}", f"Rec {i}", area=f"area{i % 8}"))
    for e in range(epics):
        write(root / f"docs/epics/epic-{e}/epic.md", epic_md(
            f"t-{e}", f"epic-{e}", seeds=[(f"seed-{e}", "researched", "s")],
            stories=[(f"0{s}-story", f"S{s}", []) for s in range(stories)]))
        for s in range(stories):
            write(root / f"docs/epics/epic-{e}/stories/0{s}-story/story.md",
                  story_md(f"0{s}-story", f"S{s}", "Not started"))
    return root


def test_a_warm_snapshot_is_much_faster_than_the_load_it_replaces(tmp_path, index_home):
    """The ledger's bar: >5x on a warm cache.

    Both halves run against a warm *parse* index, so this measures the saving the snapshot
    adds on top of the one that already existed — the walk, the dispatch and the linking,
    which no per-document cache can give back. Against a cold index the margin is larger, and
    quoting that number would be crediting this cache with the index's work.
    """
    book = big_book(tmp_path / "book")
    Ostler(book).graph  # warms both the parse index and the snapshot

    without = Ostler(book)
    drop_snapshot(index_home, without._snapshot_key())
    started = time.perf_counter()
    without.graph
    loaded = time.perf_counter() - started
    assert without.snapshot_stats()["misses"] == 1

    warm = []
    for _ in range(5):
        okf = Ostler(book)
        started = time.perf_counter()
        okf.graph
        warm.append(time.perf_counter() - started)
        assert okf.snapshot_stats()["hits"] == 1
    served = min(warm)

    assert loaded > served * 5, f"load {loaded:.4f}s vs snapshot {served:.4f}s"
