"""``Ostler.open_stories`` and ``Ostler.story``: an epic's unfinished work in dependency order."""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler import Ostler

from conftest import epic_md, present, story_md, write


def _epic(root: Path, name: str, eid: str, stories: list[tuple[str, str, list[str]]]) -> None:
    write(root / f"docs/epics/{name}/epic.md", epic_md(
        eid, name, seeds=[], stories=[(slug, slug, []) for slug, _, _ in stories]))
    for slug, status, deps in stories:
        write(root / f"docs/epics/{name}/stories/{slug}/story.md",
              story_md(slug, slug, status, depends=deps))


@pytest.fixture
def book(tmp_path: Path) -> Path:
    _epic(tmp_path, "epic-a", "t-1", [
        ("03-top", "Not started", ["02-mid"]),
        ("02-mid", "In progress", ["01-base", "01-bar"]),
        ("01-base", "Done", []),
        ("04-side", "Not started", []),
    ])
    _epic(tmp_path, "epic-b", "t-2", [("01-bar", "Not started", [])])
    return tmp_path


def test_open_stories_skip_done_and_follow_dependency_order(book: Path):
    entries = Ostler(book).open_stories("epic-a")
    slugs = [e["slug"] for e in entries]
    assert set(slugs) == {"02-mid", "03-top", "04-side"}
    assert slugs.index("02-mid") < slugs.index("03-top")


def test_open_story_entry_carries_paths_and_every_dep(book: Path):
    okf = Ostler(book)
    mid = next(e for e in okf.open_stories("epic-a") if e["slug"] == "02-mid")
    assert mid["epic"] == "epic-a"
    assert mid["path"] == "docs/epics/epic-a/stories/02-mid/story.md"
    assert mid["spec_dir"] == okf.spec_path("02-mid")
    assert mid["deps"] == ["01-base", "01-bar"]
    assert mid["open_deps"] == ["01-bar"]
    assert set(mid) == {"slug", "id", "path", "spec_dir", "epic", "deps", "open_deps"}


def test_open_stories_of_an_unknown_epic_is_empty(book: Path):
    assert Ostler(book).open_stories("epic-zzz") == []


def test_open_stories_of_a_finished_epic_is_empty(book: Path):
    _epic(book, "epic-c", "t-3", [("01-done", "Merged", [])])
    assert Ostler(book).open_stories("epic-c") == []


def test_an_unknown_dependency_counts_as_open(book: Path):
    _epic(book, "epic-c", "t-3", [("01-lone", "Not started", ["99-missing"])])
    [entry] = Ostler(book).open_stories("epic-c")
    assert entry["open_deps"] == ["99-missing"]


def test_a_cycle_inside_the_epic_raises_naming_its_stories(book: Path):
    _epic(book, "epic-c", "t-3", [
        ("01-one", "Not started", ["02-two"]),
        ("02-two", "Not started", ["01-one"]),
        ("03-three", "Not started", []),
    ])
    with pytest.raises(ValueError, match="cycle") as caught:
        Ostler(book).open_stories("epic-c")
    assert "01-one" in str(caught.value) and "02-two" in str(caught.value)
    assert "03-three" not in str(caught.value)


def test_story_returns_one_entry_in_the_same_shape(book: Path):
    okf = Ostler(book)
    entry = present(okf.story("02-mid"))
    listed = next(e for e in okf.open_stories("epic-a") if e["slug"] == "02-mid")
    assert entry == listed


def test_story_reports_a_done_story_too(book: Path):
    entry = present(Ostler(book).story("01-base"))
    assert entry["epic"] == "epic-a" and entry["open_deps"] == []


def test_story_of_an_unknown_slug_is_none(book: Path):
    assert Ostler(book).story("99-missing") is None
