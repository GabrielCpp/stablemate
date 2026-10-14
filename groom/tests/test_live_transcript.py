"""Native transcript tailing: byte-offset reads, partial lines and the live-to-captured rename."""
from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

from groom import live_transcript, localfs, state
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


def test_the_picker_prefers_the_captured_name_and_ignores_other_files():
    picked = localfs.pick_transcripts(
        [
            f"transcripts/live/{SLUG}.jsonl",
            f"transcripts/{SLUG}__sess-1.acp.jsonl",
            "transcripts/live/002-00002-review.jsonl",
            "transcripts/003-00003-qa__s.jsonl",
            "transcripts/003-00003-qa__s.meta.json",
            "sessions.jsonl",
            "turns/001-00001-implement/prompt.md",
        ]
    )
    assert picked == {
        SLUG: f"transcripts/{SLUG}__sess-1.acp.jsonl",
        "002-00002-review": "transcripts/live/002-00002-review.jsonl",
    }


class _Remote:
    """A sidecar connection over an in-memory run dir, answering the two turn RPCs in small chunks."""

    def __init__(self, chunk: int = 64) -> None:
        self.container_id = "c0ffee"
        self.files: dict[str, bytes] = {}
        self.chunk = chunk
        self.calls: list[tuple[str, dict]] = []

    async def rpc(self, method: str, params: dict, *, timeout: float = 0.0):
        self.calls.append((method, params))
        if method == "listTurns":
            return {"run": "run-1", "files": [{"path": p, "size": len(b)} for p, b in self.files.items()]}
        body = self.files[params["path"]]
        offset = params.get("offset", 0)
        data = body[offset : offset + self.chunk]
        return {
            "data": base64.b64encode(data).decode(),
            "offset": offset,
            "size": len(body),
            "eof": offset + len(data) >= len(body),
        }

    def reads(self) -> list[tuple[str, int]]:
        return [(p["path"], p.get("offset", 0)) for m, p in self.calls if m == "readTurnFile"]


def _tail(conn: _Remote, history: LiveHistory) -> None:
    state.HISTORY_LOCK = asyncio.Lock()
    asyncio.run(live_transcript.tail(conn, history, "run-1"))


def test_the_container_tail_reads_from_the_offset_and_holds_a_partial_line():
    conn = _Remote()
    live = f"transcripts/live/{SLUG}.jsonl"
    first, second = _line("one"), _line("two", 2.0)
    conn.files[live] = (first + second[:15]).encode()
    history = LiveHistory(log_limit=5)
    _tail(conn, history)
    assert _texts(history) == ["one"]
    assert history.offsets[SLUG] == len(first) + 15
    conn.calls.clear()
    _tail(conn, history)
    assert conn.reads() == []
    conn.files[live] += second[15:].encode()
    _tail(conn, history)
    assert conn.reads()[0] == (live, len(first) + 15)
    assert _texts(history) == ["two", "one"]


def test_the_container_tail_continues_across_the_rename_without_duplicates():
    conn = _Remote()
    live = f"transcripts/live/{SLUG}.jsonl"
    conn.files[live] = (_line("one") + _line("two", 2.0)).encode()
    history = LiveHistory(log_limit=5)
    _tail(conn, history)
    captured = f"transcripts/{SLUG}__sess-1.acp.jsonl"
    conn.files[captured] = conn.files.pop(live) + _line("three", 3.0).encode()
    conn.calls.clear()
    _tail(conn, history)
    _tail(conn, history)
    assert _texts(history) == ["three", "two", "one"]
    assert {path for path, _ in conn.reads()} == {captured}


def test_the_container_tail_reads_only_the_newest_two_turns():
    conn = _Remote()
    for n in (1, 2, 3):
        conn.files[f"transcripts/live/001-0000{n}-implement.jsonl"] = _line(f"turn{n}", float(n)).encode()
    history = LiveHistory(log_limit=5)
    _tail(conn, history)
    assert _texts(history) == ["turn3", "turn2"]
    assert sorted({path for path, _ in conn.reads()}) == [
        "transcripts/live/001-00002-implement.jsonl",
        "transcripts/live/001-00003-implement.jsonl",
    ]


def test_a_failing_container_tail_is_swallowed():
    class _Broken(_Remote):
        async def rpc(self, method: str, params: dict, *, timeout: float = 0.0):
            raise RuntimeError("socket went away")

    history = LiveHistory(log_limit=5)
    _tail(_Broken(), history)
    assert history.recent() == []
