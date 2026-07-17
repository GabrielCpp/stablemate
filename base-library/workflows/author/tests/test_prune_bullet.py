"""Tests for prune-bullet.py — story-mode tail prune of one consumed backlog bullet."""
from __future__ import annotations

from conftest import run_script, write_backlog


def test_prunes_single_id_when_from_backlog(tmp_path):
    write_backlog(tmp_path, ["keep-1", "drop-me", "keep-2"])
    out = run_script("prune-bullet.py", "docs/backlog.md", "drop-me", "yes", repo=tmp_path)
    assert out["backlog_pruned"]["removed"] == 1
    assert out["backlog_pruned"]["remaining"] == 2
    text = (tmp_path / "docs" / "backlog.md").read_text()
    assert "drop-me" not in text
    assert "keep-1" in text and "keep-2" in text


def test_noop_when_not_from_backlog(tmp_path):
    write_backlog(tmp_path, ["drop-me"])
    out = run_script("prune-bullet.py", "docs/backlog.md", "drop-me", "no", repo=tmp_path)
    assert out["backlog_pruned"]["removed"] == 0
    assert "drop-me" in (tmp_path / "docs" / "backlog.md").read_text()


def test_noop_when_id_absent(tmp_path):
    write_backlog(tmp_path, ["keep-1"])
    out = run_script("prune-bullet.py", "docs/backlog.md", "ghost", "yes", repo=tmp_path)
    assert out["backlog_pruned"]["removed"] == 0
    assert out["backlog_pruned"]["remaining"] == 1


def test_noop_when_no_backlog_file(tmp_path):
    out = run_script("prune-bullet.py", "docs/backlog.md", "x", "yes", repo=tmp_path)
    assert out["backlog_pruned"]["removed"] == 0
