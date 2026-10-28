"""Closure: ``close`` rewrites a record's status and reason, ``close_record`` applies it without committing, ``backlog prune`` drives both."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from ostler import ids, register
from ostler.api import Ostler
from ostler.cli import main
from ostler.model import load


def run(root: Path, *argv: str) -> int:
    return main(["-C", str(root), *argv])


def artifacts() -> Path:
    return Path(os.environ["STABLEMATE_ARTIFACTS_DIR"]).resolve()


def subjects() -> list[str]:
    if not (artifacts() / ".git").exists():
        return []
    done = subprocess.run(
        ["git", "-C", str(artifacts()), "log", "--format=%s"],
        capture_output=True, text=True, check=False, timeout=30,
    )
    return done.stdout.splitlines()


def shelve(tmp_path: Path, record_id: str = "acme-1") -> Path:
    filing = Ostler(tmp_path).file_record(
        repo="api-service", area="billing", pattern="extract-module",
        summary="Extract the invoice rounding rules", filed_by="qa",
        symbols=["billing/rounding.py"], source_story="acme-9",
        body="The slice worked without it.\n\n- one\n- two", record_id=record_id,
    )
    assert filing.ok and filing.path
    return filing.path


def test_close_marks_a_record_done_and_keeps_every_other_field_and_the_body(tmp_path: Path) -> None:
    target = shelve(tmp_path)
    before = target.read_text(encoding="utf-8")

    closed = register.close(load(tmp_path), "acme-1", "done", "fixed in api-service@abc1234")

    assert closed.ok and closed.paths == [target]
    after = target.read_text(encoding="utf-8")
    assert after == before.replace("status: open", "status: done").replace(
        "reason: ''", "reason: fixed in api-service@abc1234")
    record = register.Record.read(target)
    assert (record.status, record.reason) == ("done", "fixed in api-service@abc1234")


def test_close_takes_dropped_and_promoted_with_their_reasons(tmp_path: Path) -> None:
    dropped = shelve(tmp_path)
    promoted = shelve(tmp_path, "acme-2")

    assert register.close(load(tmp_path), "acme-1", "dropped", "stale since the rewrite").ok
    assert register.close(load(tmp_path), "acme-2", "promoted", "became story rounding-rules").ok

    assert register.Record.read(dropped).reason == "stale since the rewrite"
    assert register.Record.read(promoted).status == "promoted"


def test_closing_at_the_status_a_record_already_has_writes_nothing(tmp_path: Path) -> None:
    target = shelve(tmp_path)
    register.close(load(tmp_path), "acme-1", "done", "first")
    before = target.read_text(encoding="utf-8")

    again = register.close(load(tmp_path), "acme-1", "done", "second")

    assert again.ok and again.paths == []
    assert target.read_text(encoding="utf-8") == before


def test_closing_a_closed_record_at_another_status_is_refused(tmp_path: Path) -> None:
    target = shelve(tmp_path)
    register.close(load(tmp_path), "acme-1", "dropped", "stale")
    before = target.read_text(encoding="utf-8")

    refused = register.close(load(tmp_path), "acme-1", "done", "fixed")

    assert not refused.ok and "dropped" in refused.message
    assert target.read_text(encoding="utf-8") == before


def test_close_refuses_an_unknown_id_and_open_as_a_target(tmp_path: Path) -> None:
    target = shelve(tmp_path)
    before = target.read_text(encoding="utf-8")

    unknown = register.close(load(tmp_path), "acme-404", "done", "x")
    reopened = register.close(load(tmp_path), "acme-1", "open", "x")

    assert not unknown.ok and "acme-404" in unknown.message
    assert not reopened.ok
    assert target.read_text(encoding="utf-8") == before


def test_close_record_commits_nothing_and_a_repeat_succeeds(tmp_path: Path) -> None:
    target = shelve(tmp_path)

    first = Ostler(tmp_path).close_record("acme-1", "done", "fixed in api-service@abc1234")
    again = Ostler(tmp_path).close_record("acme-1", "done", "fixed in api-service@abc1234")

    assert first.ok and again.ok
    assert register.Record.read(target).status == "done"
    assert subjects() == []


def test_prune_closes_as_done_by_default(tmp_path: Path, capsys) -> None:
    target = shelve(tmp_path)

    assert run(tmp_path, "backlog", "prune", "acme-1", "--json") == 0

    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert register.Record.read(target).status == "done"
    assert subjects() == []


def test_prune_dropped_and_promoted_need_a_reason(tmp_path: Path, capsys) -> None:
    target = shelve(tmp_path)

    assert run(tmp_path, "backlog", "prune", "acme-1", "--as", "dropped") == 1
    assert "--reason" in capsys.readouterr().out
    assert run(tmp_path, "backlog", "prune", "acme-1", "--as", "promoted") == 1
    assert register.Record.read(target).status == "open"

    assert run(tmp_path, "backlog", "prune", "acme-1", "--as", "dropped", "--reason", "stale") == 0
    assert register.Record.read(target).reason == "stale"


def test_prune_exits_non_zero_for_an_unknown_id_and_a_conflicting_status(tmp_path: Path) -> None:
    shelve(tmp_path)

    assert run(tmp_path, "backlog", "prune", "acme-404") == 1
    assert run(tmp_path, "backlog", "prune", "acme-1", "--as", "dropped", "--reason", "stale") == 0
    assert run(tmp_path, "backlog", "prune", "acme-1") == 1


def test_prune_takes_a_short_handle(tmp_path: Path) -> None:
    minted = Ostler(tmp_path).file_record(
        repo="api-service", area="billing", pattern="p", summary="s", filed_by="qa", prefix="acme")
    assert minted.record and minted.path
    handle = ids.table(ids.known(load(tmp_path)))[minted.record.id]

    assert run(tmp_path, "backlog", "prune", handle) == 0
    assert register.Record.read(minted.path).status == "done"
