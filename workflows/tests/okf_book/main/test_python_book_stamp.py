"""A green first book is stamped verified before it is committed, so a later catch-up finds where it was judged."""
from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from okf_book.main.flows import book_exits, build_flow, written_book
from okf_book.support import dry_run_said, git
from workhorse.pyflow import Await, Continue

from workhorse_workflows.okf_book.main import python_book_flow


def test_a_green_first_book_is_stamped_before_it_is_committed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = book_exits(monkeypatch)
    flow, _runner = build_flow(tmp_path, kind="http,web")

    accounted = flow.account(lap=1)
    stamped = flow.stamp(lap=1)

    assert isinstance(accounted, Continue) and accounted.state == "stamp"
    assert isinstance(stamped, Continue) and stamped.state == "render"
    assert [argv[3:] for argv in seen if argv[3] == "verified"] == [
        ["verified", "services.ledger.http", "--app", str(flow.code_root)],
        ["verified", "services.ledger.web", "--app", str(flow.code_root)],
    ]
    assert [argv[3] for argv in seen][-2:] == ["verified", "verified"]


def test_a_stamp_that_refuses_sends_the_owner_another_lap_with_its_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, verified=1)
    flow, _runner = build_flow(tmp_path)

    step = flow.stamp(lap=1)

    assert isinstance(step, Continue) and step.state == "write"
    assert step.params["lap"] == 2
    assert "`python -m ostler.book verified services.ledger` exited 1" in cast("str", step.params["gate"])
    assert "verified said cell 7 differs" in cast("str", step.params["gate"])


def test_a_stamp_that_still_refuses_after_the_last_lap_waits_for_the_operator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, verified=1)
    flow, _runner = build_flow(tmp_path)

    step = flow.stamp(lap=python_book_flow.MAX_LAPS)

    assert isinstance(step, Await) and step.path == flow.run_dir / python_book_flow.RED_GATE
    assert "verified said cell 7 differs" in step.questions


def test_the_stamp_the_book_wrote_rides_in_the_commit_of_its_package(tmp_path: Path) -> None:
    flow, _runner = build_flow(tmp_path)
    repo = written_book(flow)
    (repo / "services/ledger/VERIFIED").write_text("9f8e7d6\n", encoding="utf-8")

    flow.commit(lap=1)

    assert sorted(git(repo, "show", "--name-only", "--format=", "HEAD").split()) == ["services/ledger/VERIFIED", "services/ledger/service.py"]


def test_a_dry_run_walks_the_python_book_to_a_green_end(tmp_path: Path) -> None:
    done = dry_run_said(tmp_path, "python_book")

    said = done.stdout + done.stderr
    assert done.returncode == 0, said
    assert "dry-run ok" in said
    assert "call   → python_book_verified (dry-run)" in said
    assert "done   ← commit" in said
