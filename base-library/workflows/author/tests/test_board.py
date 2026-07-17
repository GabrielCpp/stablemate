"""Tests for board.py — the read-only status projection over the OKF / ostler file model.

board.py reads the epics queue from ``docs/epics/index.md`` (``ostler todo list``) and each epic's
story statuses from its ``epic.md`` ``## Stories`` (``ostler list --type story``), so these tests
build the markdown graph via the conftest builders and exercise board.py's real contract.
"""
from __future__ import annotations

from conftest import init_repo, requires_ostler, run_script, write_backlog, write_epic, write_queue


def board(repo):
    return run_script("board.py", "--json", repo=repo)


@requires_ostler
def test_counts_by_status_and_not_authored_epic(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "s1"}], stories=[
        {"slug": "a", "covers": ["s1"], "status": "QA passed"},
        {"slug": "b", "status": "In progress"},
        {"slug": "c", "status": "Not started"},
    ])
    write_queue(tmp_path, ["e2"], append=True)  # e2 queued but not authored (no epic.md/stories)
    write_backlog(tmp_path, ["x", "y"])

    out = board(tmp_path)
    assert out["totals"] == {
        "stories": 3, "done": 1, "in_progress": 1, "not_started": 1, "backlog_open": 2,
    }
    e2 = next(e for e in out["epics"] if e["epic"] == "e2")
    assert e2["authored"] is False


@requires_ostler
def test_qa_give_up_marker_counts_as_done(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "s1"}], stories=[
        {"slug": "a", "covers": ["s1"],
         "status": "QA passed [QA give-up after 3 attempts — needs manual review]"},
    ])
    out = board(tmp_path)
    assert out["totals"]["done"] == 1


@requires_ostler
def test_empty_repo_is_clean(tmp_path):
    init_repo(tmp_path)
    out = board(tmp_path)
    assert out["epics"] == []
    assert out["totals"]["stories"] == 0
