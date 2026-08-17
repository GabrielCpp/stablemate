"""Tests for the run-scoped inbox primitive (workhorse/inbox.py).

Covered: append is a pure append (no read-modify-write), outstanding vs.
all_messages, reply rewrites the one matching line, extra fields survive a
round trip, and a reply to a missing id is an error rather than a silent no-op.

Run: ./.venv/bin/python tests/test_inbox.py   (or via pytest)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from workhorse import inbox


def test_append_returns_and_persists_the_message(tmp_path: Path):
    path = tmp_path / "inbox.jsonl"
    m = inbox.append(path, id="m1", body="hold off on the migration", at="t0")
    assert m.id == "m1" and m.body == "hold off on the migration" and m.reply == ""
    assert inbox.all_messages(path) == [m]


def test_appends_do_not_read_modify_write(tmp_path: Path):
    """Two appends are two independent writes to the file, not one read + one
    rewrite of the whole thing — the property that makes concurrent appends safe
    to interleave rather than clobber."""
    path = tmp_path / "inbox.jsonl"
    inbox.append(path, id="m1", body="first", at="t0")
    inbox.append(path, id="m2", body="second", at="t1")
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["id"] == "m1"
    assert json.loads(lines[1])["id"] == "m2"


def test_outstanding_excludes_replied_messages(tmp_path: Path):
    path = tmp_path / "inbox.jsonl"
    inbox.append(path, id="m1", body="first", at="t0")
    inbox.append(path, id="m2", body="second", at="t1")
    inbox.reply(path, "m1", "done", at="t2")
    got = inbox.outstanding(path)
    assert [m.id for m in got] == ["m2"]
    assert [m.id for m in inbox.all_messages(path)] == ["m1", "m2"]


def test_reply_sets_reply_and_replied_at(tmp_path: Path):
    path = tmp_path / "inbox.jsonl"
    inbox.append(path, id="m1", body="first", at="t0")
    replied = inbox.reply(path, "m1", "acknowledged", at="t1")
    assert replied.reply == "acknowledged"
    assert replied.replied_at == "t1"
    stored = inbox.all_messages(path)[0]
    assert stored.reply == "acknowledged" and stored.replied_at == "t1"


def test_reply_to_missing_id_raises(tmp_path: Path):
    path = tmp_path / "inbox.jsonl"
    inbox.append(path, id="m1", body="first", at="t0")
    with pytest.raises(KeyError):
        inbox.reply(path, "no-such-id", "text", at="t1")


def test_extra_fields_survive_a_round_trip(tmp_path: Path):
    """extra="allow" is what lets a failure-handoff entry carry kind/node/artifact
    without this module learning that vocabulary."""
    path = tmp_path / "inbox.jsonl"
    inbox.append(
        path,
        id="m1",
        body="story 02 gave up",
        at="t0",
        kind="failure",
        node="qa.exhausted",
        artifact="runs/coder-x/checkpoint.json",
    )
    got = inbox.all_messages(path)[0]
    assert getattr(got, "kind") == "failure"
    assert getattr(got, "node") == "qa.exhausted"
    assert getattr(got, "artifact") == "runs/coder-x/checkpoint.json"


def test_all_messages_of_missing_file_is_empty(tmp_path: Path):
    assert inbox.all_messages(tmp_path / "no-such-inbox.jsonl") == []
    assert inbox.outstanding(tmp_path / "no-such-inbox.jsonl") == []


if __name__ == "__main__":
    import subprocess
    import sys

    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))
