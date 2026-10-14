"""The live transcript: ACP updates appended to the run dir while a turn streams."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from _fakes import FakeBackend, FakeClock
from workhorse import turnkey
from workhorse.config_run import AgentResilience
from workhorse.runner import acp, ladder, transcript
from workhorse.runner.acp import MappedUpdate, TranscriptMapper


class FakeMapper(TranscriptMapper):
    """Maps ``{"say": text}`` to a message chunk and ``{"sub": text}`` to one from a subagent."""

    def updates(self, event: dict[str, Any]) -> list[MappedUpdate]:
        if "boom" in event:
            raise RuntimeError("mapper bug")
        if "session" in event:
            self.session_id = event["session"]
        if "say" in event:
            return [MappedUpdate(acp.agent_message_chunk(event["say"]))]
        if "sub" in event:
            return [MappedUpdate(acp.agent_message_chunk(event["sub"]), parent="toolu_1")]
        return []


@pytest.fixture(autouse=True)
def _clean():
    turnkey.clear()
    transcript.unbind()
    yield
    turnkey.clear()
    transcript.unbind()
    transcript._STORES.pop("acme-cli", None)


def _visit(run_dir: Path, node: str = "implement") -> str:
    turnkey.begin(run_dir, node)
    key = turnkey.current()
    assert key is not None
    return key.slug


def _live_lines(run_dir: Path, slug: str) -> list[dict[str, Any]]:
    path = run_dir / "transcripts" / "live" / f"{slug}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_the_prompt_is_the_first_line(tmp_path):
    transcript.bind(tmp_path)
    slug = _visit(tmp_path)
    with transcript.live_turn("implement", "do the thing", FakeMapper()):
        pass
    first = _live_lines(tmp_path, slug)[0]
    assert first["update"] == acp.user_message_chunk("do the thing")
    assert first["_meta"]["node"] == "implement"
    assert isinstance(first["_meta"]["ts"], float)
    assert "parent" not in first["_meta"]


def test_mapped_updates_follow_with_meta_and_session(tmp_path):
    transcript.bind(tmp_path)
    slug = _visit(tmp_path)
    with transcript.live_turn("implement", "p", FakeMapper()):
        transcript.live_feed(json.dumps({"session": "s-1"}) + "\n")
        transcript.live_feed(json.dumps({"say": "hello"}) + "\n")
        transcript.live_feed("not json\n")
        transcript.live_feed(json.dumps({"sub": "inner"}) + "\n")
    lines = _live_lines(tmp_path, slug)
    assert [line["update"]["sessionUpdate"] for line in lines] == [
        "user_message_chunk",
        "agent_message_chunk",
        "agent_message_chunk",
    ]
    assert lines[1]["sessionId"] == "s-1"
    assert lines[1]["update"]["content"]["text"] == "hello"
    assert "parent" not in lines[1]["_meta"]
    assert lines[2]["_meta"]["parent"] == "toolu_1"


def test_a_line_is_readable_before_the_turn_ends(tmp_path):
    transcript.bind(tmp_path)
    slug = _visit(tmp_path)
    with transcript.live_turn("implement", "p", FakeMapper()):
        transcript.live_feed(json.dumps({"say": "now"}) + "\n")
        assert _live_lines(tmp_path, slug)[-1]["update"]["content"]["text"] == "now"


def test_two_attempts_append_to_one_file(tmp_path):
    transcript.bind(tmp_path)
    slug = _visit(tmp_path)
    with transcript.live_turn("implement", "first", FakeMapper()):
        transcript.live_feed(json.dumps({"say": "a"}) + "\n")
    with transcript.live_turn("implement", "second", FakeMapper()):
        transcript.live_feed(json.dumps({"say": "b"}) + "\n")
    texts = [line["update"]["content"]["text"] for line in _live_lines(tmp_path, slug)]
    assert texts == ["first", "a", "second", "b"]


def test_it_writes_even_when_the_cli_keeps_its_own_store(tmp_path):
    transcript.bind(tmp_path)
    transcript._settings.store_proven = True
    slug = _visit(tmp_path)
    with transcript.live_turn("implement", "p", FakeMapper()):
        pass
    assert len(_live_lines(tmp_path, slug)) == 1


def test_nothing_is_written_when_unbound(tmp_path):
    _visit(tmp_path)
    with transcript.live_turn("implement", "p", FakeMapper()):
        transcript.live_feed(json.dumps({"say": "x"}) + "\n")
    assert not (tmp_path / "transcripts").exists()


def test_nothing_is_written_for_another_node(tmp_path):
    transcript.bind(tmp_path)
    _visit(tmp_path, "other")
    with transcript.live_turn("implement", "p", FakeMapper()):
        pass
    assert not (tmp_path / "transcripts").exists()


def test_a_raising_mapper_does_not_raise_and_later_lines_still_write(tmp_path):
    transcript.bind(tmp_path)
    slug = _visit(tmp_path)
    with transcript.live_turn("implement", "p", FakeMapper()):
        transcript.live_feed(json.dumps({"boom": 1}) + "\n")
        transcript.live_feed(json.dumps({"say": "after"}) + "\n")
    texts = [line["update"]["content"]["text"] for line in _live_lines(tmp_path, slug)]
    assert texts == ["p", "after"]


def test_feeding_without_an_open_turn_is_a_no_op(tmp_path):
    transcript.live_feed(json.dumps({"say": "x"}) + "\n")


def test_the_byte_cap_ends_the_file_with_the_truncation_marker(tmp_path):
    transcript.bind(tmp_path, max_bytes=400)
    slug = _visit(tmp_path)
    with transcript.live_turn("implement", "p", FakeMapper()):
        for _ in range(20):
            transcript.live_feed(json.dumps({"say": "x" * 50}) + "\n")
    last = (tmp_path / "transcripts" / "live" / f"{slug}.jsonl").read_text().splitlines()[-1]
    assert json.loads(last)["truncated"] is True


def test_a_captured_turn_moves_its_live_file_beside_the_capture(tmp_path):
    transcript.bind(tmp_path)
    slug = _visit(tmp_path)
    store = tmp_path / "store.jsonl"
    store.write_text('{"from":"store"}\n')
    transcript._STORES["acme-cli"] = lambda _sid: [store]
    with transcript.live_turn("implement", "p", FakeMapper()):
        transcript.live_feed(json.dumps({"say": "x"}) + "\n")
        transcript.capture("acme-cli", "implement", "sess-1")
    root = tmp_path / "transcripts"
    moved = root / f"{slug}__sess-1.acp.jsonl"
    assert moved.is_file()
    assert [json.loads(line)["update"]["sessionUpdate"] for line in moved.read_text().splitlines()] == [
        "user_message_chunk",
        "agent_message_chunk",
    ]
    assert not (root / "live" / f"{slug}.jsonl").exists()


def test_an_uncaptured_turn_leaves_its_file_in_live(tmp_path):
    transcript.bind(tmp_path)
    slug = _visit(tmp_path)
    with transcript.live_turn("implement", "p", FakeMapper()):
        pass
    assert (tmp_path / "transcripts" / "live" / f"{slug}.jsonl").is_file()


def test_the_ladder_wraps_each_attempt(tmp_path):
    transcript.bind(tmp_path)
    slug = _visit(tmp_path)

    def turn(prompt, node_id, session_id_path, model=None, **kwargs):
        return "ok"

    runner = ladder.AgentRunner(
        backend=FakeBackend(turn=turn), resilience=AgentResilience(), clock=FakeClock()
    )
    assert runner.turn("the node prompt", "implement", None, timeout=60.0) == "ok"
    first = _live_lines(tmp_path, slug)[0]
    assert first["update"] == acp.user_message_chunk("the node prompt")
