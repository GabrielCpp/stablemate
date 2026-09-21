"""Tests for hardened JSON extraction from agent responses."""
from __future__ import annotations

import importlib

import pytest

from _fakes import present

m = importlib.import_module("workhorse.runner.extract")
failure = importlib.import_module("workhorse.runner.failure")
nodes = importlib.import_module("workhorse.runner.spec")


def _node(*keys: str):
    return nodes.AgentNode(
        type="agent",
        id="n",
        prompt="p.md",
        outputs=[nodes.OutputSpec(key=k) for k in keys],
    )



def test_strict_fenced_block():
    text = 'sure:\n```json\n{"status": "ok"}\n```\n'
    assert m.parse_json_from_text(text, ["status"]) == {"status": "ok"}


def test_strict_bare_object():
    assert m.parse_json_from_text('{"status": "ok"}', ["status"]) == {"status": "ok"}


def test_strict_nested_object():
    text = '```json\n{"a": {"b": 1}}\n```'
    assert m.parse_json_from_text(text, ["a"]) == {"a": {"b": 1}}



def test_prose_with_stray_brace_picks_real_object():
    text = 'I considered options {like this} and decided. {"status": "ok", "notes": "done"}'
    got = m.parse_json_from_text(text, ["status", "notes"])
    assert got == {"status": "ok", "notes": "done"}



def test_multiple_objects_prefers_one_with_wanted_keys():
    text = 'Example shape: {"x": 1}. Real answer: {"status": "ok", "notes": "hi"}'
    got = m.parse_json_from_text(text, ["status", "notes"])
    assert got == {"status": "ok", "notes": "hi"}


def test_multiple_objects_falls_back_to_last_when_none_match():
    text = '{"a": 1} then {"b": 2}'
    got = m.parse_json_from_text(text, ["status"])
    assert got == {"b": 2}



def test_trailing_comma_repaired():
    assert m.parse_json_from_text('{"status": "ok",}', ["status"]) == {"status": "ok"}


def test_single_quotes_repaired():
    assert m.parse_json_from_text("{'status': 'ok'}", ["status"]) == {"status": "ok"}



def test_truncated_object_closed():
    text = '{"status": "ok", "items": [1, 2'
    got = m.parse_json_from_text(text, ["status", "items"])
    assert got == {"status": "ok", "items": [1, 2]}



def test_pure_prose_returns_none():
    assert m.parse_json_from_text("I cannot complete this task.", ["status"]) is None


def test_empty_returns_none():
    assert m.parse_json_from_text("", ["status"]) is None



def test_extract_outputs_happy_path():
    text = 'Result: {"status": "ok", "notes": "all good"}'
    assert m.extract_outputs(text, _node("status", "notes")) == {
        "status": "ok",
        "notes": "all good",
    }


def test_extract_outputs_no_json_raises():
    with pytest.raises(failure.OutputParseError, match="no parseable JSON"):
        m.extract_outputs("nope", _node("status"))


def test_extract_outputs_missing_key_raises():
    with pytest.raises(failure.OutputParseError, match="not found"):
        m.extract_outputs('{"status": "ok"}', _node("status", "notes"))


def test_extract_outputs_no_outputs_returns_empty():
    assert m.extract_outputs("anything at all", _node()) == {}



def test_wrapped_answer_is_read_through_the_envelope():
    text = '```json\n{"code_review_result": {"status": "clean", "findings": []}}\n```'
    assert m.parse_json_from_text(text, ["status", "findings"]) == {
        "status": "clean",
        "findings": [],
    }


def test_extract_outputs_accepts_the_wrapped_answer():
    text = '{"result": {"status": "ok", "notes": "done"}}'
    assert m.extract_outputs(text, _node("status", "notes")) == {
        "status": "ok",
        "notes": "done",
    }


def test_a_top_level_answer_still_wins_over_a_nested_one():
    """Shallowest match, so an envelope's payload beats a same-shaped list element."""
    text = (
        '{"status": "findings", "findings": [{"status": "bad", "findings": []}], '
        '"detail": {"status": "nested", "findings": []}}'
    )
    assert present(m.parse_json_from_text(text, ["status", "findings"]))["status"] == "findings"


def test_an_envelope_missing_a_key_still_fails():
    """Unwrapping widens where the keys may be, not which answers count as complete."""
    text = '{"code_review_result": {"status": "clean"}}'
    with pytest.raises(failure.OutputParseError, match="not found"):
        m.extract_outputs(text, _node("status", "notes"))


def test_nothing_wanted_keeps_the_top_object():
    """No declared keys means every dict qualifies, so descending would be arbitrary."""
    assert m.parse_json_from_text('{"outer": {"inner": 1}}') == {"outer": {"inner": 1}}


def test_a_wrapped_answer_survives_repair_too():
    """The envelope is still an envelope after json-repair fixes the syntax around it."""
    text = "here you go:\n{'code_review_result': {'status': 'clean', 'findings': [],}}"
    assert m.parse_json_from_text(text, ["status", "findings"]) == {
        "status": "clean",
        "findings": [],
    }



def test_prose_after_the_object_containing_a_brace():
    """The old first-brace-to-last-brace span swallowed the trailing prose and parsed as nothing, dropping a perfectly good answer onto the retry ladder."""
    text = '{"status": "ok"}\n\nNote: the `}` above closes the object.'
    assert m.parse_json_from_text(text, ["status"]) == {"status": "ok"}


def test_an_example_object_then_the_real_one():
    """Two complete objects: the one carrying the declared keys wins, whichever came first."""
    text = 'For reference the shape is {"status": "…"}. My answer:\n{"status": "clean", "n": 1}'
    assert m.parse_json_from_text(text, ["status", "n"]) == {"status": "clean", "n": 1}


def test_a_brace_inside_a_string_does_not_end_the_object():
    text = '```json\n{"status": "ok", "note": "use } to close"}\n```'
    assert m.parse_json_from_text(text, ["status", "note"]) == {
        "status": "ok",
        "note": "use } to close",
    }



def _mixed(*specs: tuple[str, bool]):
    return nodes.AgentNode(
        type="agent",
        id="n",
        prompt="p.md",
        outputs=[nodes.OutputSpec(key=k, required=r) for k, r in specs],
    )


def test_an_omitted_optional_key_is_simply_absent():
    """A field that means something only in one branch of the answer."""
    text = '{"status": "done", "wrote_tests": true}'
    got = m.extract_outputs(text, _mixed(("status", True), ("no_test_reason", False)))
    assert got == {"status": "done"}


def test_an_optional_key_that_is_present_is_still_taken():
    text = '{"status": "done", "no_test_reason": "generated code"}'
    got = m.extract_outputs(text, _mixed(("status", True), ("no_test_reason", False)))
    assert got == {"status": "done", "no_test_reason": "generated code"}


def test_a_required_key_is_still_demanded():
    """Relaxing the optional ones does not relax the rest — an answer that skipped a key the node genuinely needs stays on the retry ladder."""
    text = '{"no_test_reason": "generated code"}'
    with pytest.raises(failure.OutputParseError, match="not found"):
        m.extract_outputs(text, _mixed(("status", True), ("no_test_reason", False)))


def test_the_answer_is_found_by_the_required_keys_alone():
    """The wrapped-answer descent discriminates on what is demanded, so an envelope whose payload omitted an optional key is still recognised as the payload."""
    text = '{"impl_result": {"status": "done", "files": []}}'
    got = m.extract_outputs(
        text, _mixed(("status", True), ("files", True), ("no_test_reason", False))
    )
    assert got == {"status": "done", "files": []}



def test_select_object_from_list_prefers_wanted():
    objs = [{"x": 1}, {"status": "ok"}]
    assert m._select_object(objs, {"status"}) == {"status": "ok"}


def test_select_object_empty_string_is_none():
    assert m._select_object("", {"status"}) is None


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
