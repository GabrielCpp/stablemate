"""The end review's criteria, verdict helpers, review file and record."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from workhorse_workflows.coder.book_qa import nodes as book_nodes
from workhorse_workflows.coder.book_qa.review import missing_criteria, unmet_findings
from workhorse_workflows.coder.shared.schemas.book_qa import ReviewVerdict, ServiceCalls
from workhorse_workflows.coder.shared.walk import criteria_count, criteria_texts, story_criteria

STORY = """# Story

## Acceptance Criteria

- the first thing
- the second thing

## Non-Functional Acceptance Criteria

- the third thing is fast

## Technical Notes

- not a criterion
"""


def _verdict(criterion: int, verdict: str = "played", **fields: str) -> ReviewVerdict:
    return ReviewVerdict.model_validate({"criterion": criterion, "verdict": verdict} | fields)


def test_the_criteria_are_the_functional_items_then_the_non_functional_ones_in_order() -> None:
    assert criteria_texts(STORY) == ["the first thing", "the second thing", "the third thing is fast"]


def test_a_bullet_that_wraps_reads_as_one_line() -> None:
    text = "## Acceptance Criteria\n\n- the first\n  part of one thing\n- second\n"
    assert criteria_texts(text) == ["the first part of one thing", "second"]


def test_criteria_count_still_counts_only_the_functional_criteria() -> None:
    assert criteria_count(STORY) == 2


def test_story_criteria_reads_the_story_file(tmp_path: Path) -> None:
    story = tmp_path / "story.md"
    story.write_text(STORY, encoding="utf-8")
    result = story_criteria(logging.getLogger("test"), str(story), str(tmp_path))
    assert result.criteria == ["the first thing", "the second thing", "the third thing is fast"]


def test_missing_criteria_names_each_number_with_no_verdict_and_drops_numbers_out_of_range() -> None:
    verdicts = [_verdict(1), _verdict(9), _verdict(1, "unmet")]
    assert missing_criteria(verdicts, 3) == [2, 3]


def test_an_unmet_verdict_becomes_a_finding_with_its_target_and_repair() -> None:
    verdicts = [_verdict(1), _verdict(2, "unmet", evidence="no such option", target="acme/cli.py:10", repair="add it")]
    [found] = unmet_findings(verdicts, ["a", "b"], "docs/story.md")
    assert found.id == "review-criterion-2"
    assert found.target == "acme/cli.py:10"
    assert found.issue == "Acceptance criterion 2 is unmet: b. no such option"
    assert found.repair == "add it"


def test_an_unmet_verdict_with_no_target_points_at_the_story() -> None:
    [found] = unmet_findings([_verdict(1, "unmet")], ["a"], "docs/story.md")
    assert found.target == "docs/story.md"
    assert found.repair == "Meet the criterion as the story states it."


def test_the_review_file_is_a_table_of_criterion_verdict_and_evidence(tmp_path: Path) -> None:
    verdicts = [_verdict(1, evidence="a | b\nsecond line")]
    book_nodes.write_qa_review(logging.getLogger("test"), str(tmp_path), ["one", "two"], verdicts)
    lines = (tmp_path / "qa-review.md").read_text(encoding="utf-8").splitlines()
    assert lines[:4] == ["# QA review", "", "| criterion | verdict | evidence |", "| --- | --- | --- |"]
    assert lines[4] == "| 1. one | played | a \\| b second line |"
    assert lines[5] == "| 2. two | none |  |"


def test_the_record_keeps_only_the_unobserved_verdicts(tmp_path: Path) -> None:
    seen = _verdict(2, "unobserved", evidence="nothing")
    book_nodes.write_book_record(
        logging.getLogger("test"), str(tmp_path), [ServiceCalls(service="api")], None, None, [seen]
    )
    record = json.loads((tmp_path / "book-qa.json").read_text(encoding="utf-8"))
    assert record["unobserved"] == [{"criterion": 2, "verdict": "unobserved", "evidence": "nothing"}]
    book_nodes.write_book_record(logging.getLogger("test"), str(tmp_path), [ServiceCalls(service="api")])
    assert "unobserved" not in json.loads((tmp_path / "book-qa.json").read_text(encoding="utf-8"))
