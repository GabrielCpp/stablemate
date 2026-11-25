"""The Activity timeline sent a page at a time: the newest work items with their turns, and a count of the older ones left out."""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from test_activity_groups import _interleaved
from test_run_clock import RUN, _DB

from groom import activity


def _turns(page: dict) -> set[str]:
    return {entry["slug"] for item in page["items"] for one in item["passes"] for entry in one["entries"] if entry["kind"] == "turn"}


@pytest.fixture
def run() -> Iterator[dict]:
    with _DB():
        _interleaved(shared=False)
        yield {"whole": activity.page(RUN), "newest": activity.page(RUN, items=1), "skipped": activity.page(RUN, skip=1), "past": activity.page(RUN, skip=5)}


def test_the_whole_timeline_leaves_nothing_out(run: dict) -> None:
    whole = run["whole"]
    assert [item["work_id"] for item in whole["items"]] == ["alpha", "beta"]
    assert whole["older"] == 0
    assert {row["slug"] for row in whole["rows"]} == _turns(whole)


def test_a_page_keeps_the_newest_work_items_and_only_their_turns(run: dict) -> None:
    newest = run["newest"]
    assert [item["work_id"] for item in newest["items"]] == ["beta"]
    assert newest["older"] == 1
    assert {row["slug"] for row in newest["rows"]} == _turns(newest)
    assert len(newest["rows"]) == 2


def test_skipping_the_older_items_answers_as_the_page_that_left_them_out(run: dict) -> None:
    assert run["skipped"]["items"] == run["newest"]["items"]
    assert run["skipped"]["rows"] == run["newest"]["rows"]
    assert run["skipped"]["older"] == 1


def test_the_step_and_problem_counts_cover_the_whole_run_on_every_page(run: dict) -> None:
    whole = run["whole"]
    assert whole["step_count"] == 5
    for name in ("newest", "skipped", "past"):
        assert run[name]["step_count"] == whole["step_count"]
        assert run[name]["problems"] == whole["problems"]


def test_skipping_past_the_last_item_sends_no_item_and_counts_them_all_older(run: dict) -> None:
    assert run["past"]["items"] == []
    assert run["past"]["rows"] == []
    assert run["past"]["older"] == 2
