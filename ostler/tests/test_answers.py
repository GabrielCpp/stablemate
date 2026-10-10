from __future__ import annotations

from ostler.answers import parse_answers


def test_fixed_answer_collects_every_evidence_line():
    result = parse_answers(
        "# Answers\n\nPreamble the parser ignores.\n\n"
        "## F-1: fixed\n\n"
        "- commit: abc1234\n- path: src/api-service/handler.py\n"
        "- test: test_handler_rejects_empty\n- commit: def5678\n")
    assert result.errors == []
    [answer] = result.answers
    assert answer.finding_id == "F-1" and answer.disposition == "fixed"
    assert answer.commits == ["abc1234", "def5678"]
    assert answer.paths == ["src/api-service/handler.py"]
    assert answer.tests == ["test_handler_rejects_empty"]
    assert answer.reason == ""


def test_declined_answer_reason_runs_to_the_next_heading():
    result = parse_answers(
        "# Answers\n\n"
        "## F-2: declined\n\nReason: the endpoint is internal.\n"
        "It never sees acme traffic.\n\n"
        "## F-3: fixed\n\n- test: test_three\n")
    assert result.errors == []
    declined, fixed = result.answers
    assert declined.disposition == "declined"
    assert declined.reason == "the endpoint is internal.\nIt never sees acme traffic."
    assert fixed.finding_id == "F-3" and fixed.tests == ["test_three"]


def test_disposition_is_case_insensitive_and_backticked_values_unwrap():
    result = parse_answers("## F-1: Fixed\n\n- path: `web-app/src/index.ts`\n")
    assert result.errors == []
    assert result.answers[0].disposition == "fixed"
    assert result.answers[0].paths == ["web-app/src/index.ts"]


def test_text_before_the_first_answer_is_ignored():
    result = parse_answers("Some notes.\n\n- commit: notevidence\n\n## F-1: fixed\n\n- commit: abc\n")
    assert result.errors == []
    assert [a.commits for a in result.answers] == [["abc"]]


def test_duplicate_id_is_one_error_and_no_answer():
    result = parse_answers("## F-1: fixed\n\n- commit: a\n\n## F-1: fixed\n\n- commit: b\n")
    assert result.answers == []
    assert len(result.errors) == 1 and "F-1" in result.errors[0]
    assert "2 times" in result.errors[0]


def test_unknown_disposition_names_the_id():
    result = parse_answers("## F-1: deferred\n\n- commit: a\n")
    assert result.answers == []
    assert result.errors == ["F-1: unknown disposition 'deferred' (expected fixed or declined)"]


def test_fixed_without_evidence_is_an_error():
    result = parse_answers("## F-1: fixed\n\nI fixed it, trust me.\n")
    assert result.answers == []
    assert len(result.errors) == 1 and result.errors[0].startswith("F-1:")
    assert "no evidence" in result.errors[0]


def test_declined_without_reason_is_an_error():
    result = parse_answers("## F-1: declined\n\nNot doing this.\n")
    assert result.answers == []
    assert result.errors[0].startswith("F-1:") and "no reason" in result.errors[0]


def test_declined_with_an_empty_reason_label_is_an_error():
    result = parse_answers("## F-1: declined\n\nReason:\n")
    assert result.answers == []
    assert "no reason" in result.errors[0]


def test_malformed_headings_are_errors_and_skip_the_section():
    result = parse_answers(
        "## F-1 fixed\n\n- commit: a\n\n"
        "## two words: fixed\n\n- commit: b\n\n"
        "## F-4:\n\n- commit: c\n\n"
        "## F-5: fixed\n\n- commit: d\n")
    assert [a.finding_id for a in result.answers] == ["F-5"]
    assert len(result.errors) == 3
    assert all("malformed answer heading" in e for e in result.errors)
    assert "## F-1 fixed" in result.errors[0]


def test_a_bad_answer_does_not_drop_its_neighbours():
    result = parse_answers("## F-1: fixed\n\n## F-2: declined\n\nReason: out of scope.\n")
    assert [a.finding_id for a in result.answers] == ["F-2"]
    assert result.answers[0].reason == "out of scope."
    assert len(result.errors) == 1 and result.errors[0].startswith("F-1:")


def test_empty_text_has_no_answers_and_no_errors():
    result = parse_answers("")
    assert result.answers == [] and result.errors == []


def test_by_id_keys_answers_by_finding():
    result = parse_answers("## F-1: fixed\n\n- commit: a\n\n## F-2: declined\n\nReason: no.\n")
    assert sorted(result.by_id()) == ["F-1", "F-2"]
    assert result.by_id()["F-2"].as_dict() == {
        "disposition": "declined", "commits": [], "paths": [], "tests": [], "reason": "no."}
