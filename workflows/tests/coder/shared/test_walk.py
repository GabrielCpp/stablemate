"""The acceptance walk: how many criteria a story has, and which of them a plan walked."""
from __future__ import annotations

from workhorse_workflows.coder.shared.walk import criteria_count, walked

STORY = """\
# Story

## Acceptance Criteria

- first criterion
  continued on an indented line
- second criterion
    - a nested point
- third criterion

## Technical Notes

- not a criterion
"""


def test_three_top_level_bullets_count_three_whatever_their_continuations() -> None:
    assert criteria_count(STORY) == 3


def test_a_numbered_list_counts_its_items() -> None:
    text = "## Acceptance Criteria\n\n1. one\n2. two\n   more\n3. three\n4. four\n"

    assert criteria_count(text) == 4


def test_a_story_with_no_criteria_section_counts_none() -> None:
    assert criteria_count("# Story\n\n## Context\n\n- a bullet\n") == 0


def test_headings_in_any_spelling_name_the_criteria_walked() -> None:
    plan = "## Acceptance Walk\n\n### AC 1: one\n\n### AC2 - two\n\n### ac 3\n"

    assert walked(plan) == {1, 2, 3}


def test_headings_outside_the_walk_do_not_count() -> None:
    plan = "### AC 1: elsewhere\n\n## Acceptance Walk\n\n### AC 2: here\n\n## Notes\n\n### AC 3: later\n"

    assert walked(plan) == {2}


def test_no_walk_section_walks_nothing() -> None:
    assert walked("# Plan\n\ntext\n") == set()


def test_a_follow_up_s_nested_walk_does_not_shadow_the_plan_s_own() -> None:
    plan = (
        "# Plan\n\n## Follow-up: tidy\n\n### Acceptance Walk\n\n#### AC 3: here\n\n"
        "## Acceptance Walk\n\n### AC 1: one\n\n### AC 2: two\n\n### AC 3: three\n"
    )

    assert walked(plan) == {1, 2, 3}
