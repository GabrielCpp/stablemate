"""Tests for prune-backlog.py — removing authored bullets from the backlog (ostler model).

The script reads the epic's seeds via ostler (each seed's ``sourceBullet``) and drops matching
backlog lines. ``write_epic`` writes ``sourceBullet`` per seed into ``epic.md``, so a test points a
seed's ``sourceBullet`` at a backlog line and asserts that line is removed.
"""
from __future__ import annotations

from conftest import init_repo, requires_ostler, run_script, write_epic

pytestmark = requires_ostler


def _backlog(tmp_path, text):
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "backlog.md").write_text(text, encoding="utf-8")


def _read_backlog(tmp_path):
    return (tmp_path / "docs" / "backlog.md").read_text(encoding="utf-8")


def test_removes_matching_bullets(tmp_path):
    write_epic(tmp_path, "e1",
               seeds=[{"id": "i1", "sourceBullet": "the report button is missing"}],
               stories=[{"slug": "s1", "covers": ["i1"]}])
    _backlog(tmp_path, "# Backlog\n\n- the report button is missing\n- add dark mode\n- fix login\n")

    out = run_script("prune-backlog.py", "docs/backlog.md", "docs/epics/e1", repo=tmp_path)
    assert out["backlog_pruned"]["removed"] == 1
    body = _read_backlog(tmp_path)
    assert "report button" not in body
    assert "add dark mode" in body and "fix login" in body


def test_no_match_leaves_backlog_untouched(tmp_path):
    write_epic(tmp_path, "e1",
               seeds=[{"id": "i1", "sourceBullet": "something unrelated entirely"}],
               stories=[{"slug": "s1", "covers": ["i1"]}])
    _backlog(tmp_path, "- alpha\n- beta\n")

    out = run_script("prune-backlog.py", "docs/backlog.md", "docs/epics/e1", repo=tmp_path)
    assert out["backlog_pruned"]["removed"] == 0
    assert _read_backlog(tmp_path) == "- alpha\n- beta\n"


def test_missing_backlog_is_noop(tmp_path):
    init_repo(tmp_path)
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "s1", "covers": ["i1"]}])
    out = run_script("prune-backlog.py", "docs/backlog.md", "docs/epics/e1", repo=tmp_path)
    assert out["backlog_pruned"] == {"removed": 0, "remaining": 0}


def test_keeps_non_bullet_lines(tmp_path):
    write_epic(tmp_path, "e1",
               seeds=[{"id": "i1", "sourceBullet": "consumed item here"}],
               stories=[{"slug": "s1", "covers": ["i1"]}])
    _backlog(tmp_path, "# Backlog\n\nSome intro prose.\n\n- consumed item here\n")

    run_script("prune-backlog.py", "docs/backlog.md", "docs/epics/e1", repo=tmp_path)
    body = _read_backlog(tmp_path)
    assert "# Backlog" in body and "Some intro prose." in body
    assert "consumed item here" not in body
