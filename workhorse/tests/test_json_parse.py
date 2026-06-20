"""Tests for hardened JSON extraction from agent responses.

`_parse_json_from_text` is strict-first (stdlib `json.loads` on a fenced or bare
brace span) and falls back to a tolerant `json-repair` pass only when strict
parsing can't yield an object carrying the declared output keys. The tolerant
pass fixes the four break modes that produced empty-default `failed` outputs in
practice: prose around the object, multiple embedded objects, lenient syntax
(trailing commas / single quotes / comments), and truncated/unclosed braces.
"""
from __future__ import annotations

import importlib

import pytest

m = importlib.import_module("workhorse.runner.agent")
nodes = importlib.import_module("workhorse.graph.nodes")


def _node(*keys: str):
    return nodes.AgentNode(
        type="agent",
        id="n",
        prompt="p.md",
        outputs=[nodes.OutputSpec(key=k) for k in keys],
    )


# ── strict path is unchanged (no coercion when stdlib already parses) ─────────

def test_strict_fenced_block():
    text = 'sure:\n```json\n{"status": "ok"}\n```\n'
    assert m._parse_json_from_text(text, ["status"]) == {"status": "ok"}


def test_strict_bare_object():
    assert m._parse_json_from_text('{"status": "ok"}', ["status"]) == {"status": "ok"}


def test_strict_nested_object():
    text = '```json\n{"a": {"b": 1}}\n```'
    assert m._parse_json_from_text(text, ["a"]) == {"a": {"b": 1}}


# ── break mode 1: prose containing a brace before the real object ─────────────

def test_prose_with_stray_brace_picks_real_object():
    text = 'I considered options {like this} and decided. {"status": "ok", "notes": "done"}'
    got = m._parse_json_from_text(text, ["status", "notes"])
    assert got == {"status": "ok", "notes": "done"}


# ── break mode 2: multiple objects — prefer the one with the declared keys ────

def test_multiple_objects_prefers_one_with_wanted_keys():
    text = 'Example shape: {"x": 1}. Real answer: {"status": "ok", "notes": "hi"}'
    got = m._parse_json_from_text(text, ["status", "notes"])
    assert got == {"status": "ok", "notes": "hi"}


def test_multiple_objects_falls_back_to_last_when_none_match():
    text = '{"a": 1} then {"b": 2}'
    got = m._parse_json_from_text(text, ["status"])
    assert got == {"b": 2}  # last dict, best effort → caller raises precise key error


# ── break mode 3: lenient syntax ──────────────────────────────────────────────

def test_trailing_comma_repaired():
    assert m._parse_json_from_text('{"status": "ok",}', ["status"]) == {"status": "ok"}


def test_single_quotes_repaired():
    assert m._parse_json_from_text("{'status': 'ok'}", ["status"]) == {"status": "ok"}


# ── break mode 4: truncated / unclosed JSON ───────────────────────────────────

def test_truncated_object_closed():
    text = '{"status": "ok", "items": [1, 2'
    got = m._parse_json_from_text(text, ["status", "items"])
    assert got == {"status": "ok", "items": [1, 2]}


# ── no usable object ──────────────────────────────────────────────────────────

def test_pure_prose_returns_none():
    assert m._parse_json_from_text("I cannot complete this task.", ["status"]) is None


def test_empty_returns_none():
    assert m._parse_json_from_text("", ["status"]) is None


# ── _extract_outputs integration ──────────────────────────────────────────────

def test_extract_outputs_happy_path():
    text = 'Result: {"status": "ok", "notes": "all good"}'
    assert m._extract_outputs(text, _node("status", "notes")) == {
        "status": "ok",
        "notes": "all good",
    }


def test_extract_outputs_no_json_raises():
    with pytest.raises(m.OutputParseError, match="no parseable JSON"):
        m._extract_outputs("nope", _node("status"))


def test_extract_outputs_missing_key_raises():
    # Object recovered but lacks a declared key → precise key error (trips retry).
    with pytest.raises(m.OutputParseError, match="not found"):
        m._extract_outputs('{"status": "ok"}', _node("status", "notes"))


def test_extract_outputs_no_outputs_returns_empty():
    assert m._extract_outputs("anything at all", _node()) == {}


# ── selection helper ──────────────────────────────────────────────────────────

def test_select_object_from_list_prefers_wanted():
    objs = [{"x": 1}, {"status": "ok"}]
    assert m._select_object(objs, {"status"}) == {"status": "ok"}


def test_select_object_empty_string_is_none():
    assert m._select_object("", {"status"}) is None


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
