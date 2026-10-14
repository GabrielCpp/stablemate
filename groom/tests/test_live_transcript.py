"""Native transcript tailing: byte-offset reads, partial lines and the live-to-captured rename."""
from __future__ import annotations

import json
from pathlib import Path

from groom import live_transcript, localfs
from groom.live_history import LiveHistory

SLUG = "001-00001-implement"


def _line(text: str, ts: float = 1.0) -> str:
    record = {
        "sessionId": "s",
        "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}},
        "_meta": {"ts": ts, "node": "implement"},
    }
    return json.dumps(record) + "\n"


def _texts(history: LiveHistory) -> list[str]:
    return [
        row["update"]["content"]["text"]
        for row in history.recent()
        if row["kind"] == "transcript"
    ]


def test_read_range_returns_the_bytes_from_an_offset(tmp_path):
    path = tmp_path / "f.jsonl"
    path.write_bytes(b"abcdef")
    assert localfs.read_range(str(path), 2) == b"cdef"
    assert localfs.read_range(str(path), 6) == b""
    assert localfs.read_range(str(tmp_path / "missing"), 0) == b""


def test_transcript_files_prefer_the_captured_name_over_the_live_one(tmp_path):
    (tmp_path / "transcripts" / "live").mkdir(parents=True)
    (tmp_path / "transcripts" / "live" / f"{SLUG}.jsonl").write_text("")
    (tmp_path / "transcripts" / f"{SLUG}__sess-1.acp.jsonl").write_text("")
    (tmp_path / "transcripts" / "002-00002-review.jsonl").write_text("")
    found = localfs.transcript_files(str(tmp_path))
    assert found == {SLUG: str(tmp_path / "transcripts" / f"{SLUG}__sess-1.acp.jsonl")}


def test_poll_reads_only_what_is_new_and_holds_a_partial_line(tmp_path):
    live = tmp_path / "transcripts" / "live"
    live.mkdir(parents=True)
    path = live / f"{SLUG}.jsonl"
    first = _line("one")
    second = _line("two", 2.0)
    path.write_text(first + second[:15])
    history = LiveHistory(log_limit=5)
    live_transcript.poll(history, str(tmp_path))
    assert _texts(history) == ["one"]
    with path.open("a") as handle:
        handle.write(second[15:])
    live_transcript.poll(history, str(tmp_path))
    live_transcript.poll(history, str(tmp_path))
    assert _texts(history) == ["two", "one"]


def test_a_file_moved_out_of_live_is_not_shown_twice(tmp_path):
    live = tmp_path / "transcripts" / "live"
    live.mkdir(parents=True)
    path = live / f"{SLUG}.jsonl"
    path.write_text(_line("one") + _line("two", 2.0))
    history = LiveHistory(log_limit=5)
    live_transcript.poll(history, str(tmp_path))
    with path.open("a") as handle:
        handle.write(_line("three", 3.0))
    path.rename(tmp_path / "transcripts" / f"{SLUG}__sess-1.acp.jsonl")
    live_transcript.poll(history, str(tmp_path))
    live_transcript.poll(history, str(tmp_path))
    assert _texts(history) == ["three", "two", "one"]


def test_only_the_newest_two_turns_are_read(tmp_path):
    live = tmp_path / "transcripts" / "live"
    live.mkdir(parents=True)
    for n in (1, 2, 3):
        (live / f"001-0000{n}-implement.jsonl").write_text(_line(f"turn{n}", float(n)))
    history = LiveHistory(log_limit=5)
    live_transcript.poll(history, str(tmp_path))
    assert _texts(history) == ["turn3", "turn2"]


def test_poll_on_a_run_without_transcripts_is_a_no_op(tmp_path: Path):
    history = LiveHistory(log_limit=5)
    live_transcript.poll(history, str(tmp_path))
    assert history.recent() == []
