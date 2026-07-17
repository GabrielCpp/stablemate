"""Unit tests for the fix-loop's standalone scripts:

    select-next-fix-item.py, seed-fix-story.py, prune-fix-item.py, mark-fix-blocked.py

Each test drives the script as a subprocess against a hermetic tmp_path sandbox (a
fake docs/backlog.md and/or docs/epics tree), mirroring test_multi_repo_scripts.py's
pattern. seed-fix-story.py shells out to the real `ostler` CLI (available on PATH)
rather than being mocked, since it's itself a thin ostler wrapper — asserting
against ostler's real output is the only way to catch drift in ostler's CLI
contract.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _run(script: str, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True, cwd=str(cwd),
    )


def _backlog(root: Path, text: str) -> Path:
    p = root / "docs" / "backlog.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# select-next-fix-item.py
# ---------------------------------------------------------------------------


def test_select_next_fix_item_empty_backlog(tmp_path):
    _backlog(tmp_path, "# Backlog\n")
    result = _run("select-next-fix-item.py", [str(tmp_path)], tmp_path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["has_fix"] == "no"


def test_select_next_fix_item_no_backlog_file(tmp_path):
    result = _run("select-next-fix-item.py", [str(tmp_path)], tmp_path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["has_fix"] == "no"


def test_select_next_fix_item_draws_first_bullet(tmp_path):
    _backlog(tmp_path, (
        "# Backlog\n\n## Filed by coder\n\n"
        "- [bug-a] fix the flake\n- [bug-b] fix the other flake\n"
    ))
    result = _run("select-next-fix-item.py", [str(tmp_path)], tmp_path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["has_fix"] == "yes"
    assert out["fix_bullet_id"] == "bug-a"
    assert out["fix_bullet_text"] == "fix the flake"


def test_select_next_fix_item_skips_blocked(tmp_path):
    _backlog(tmp_path, (
        "# Backlog\n\n## Filed by coder\n\n"
        "- [bug-a] fix the flake (blocked: qa failed after retry)\n"
        "- [bug-b] fix the other flake\n"
    ))
    result = _run("select-next-fix-item.py", [str(tmp_path)], tmp_path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["has_fix"] == "yes"
    assert out["fix_bullet_id"] == "bug-b"


def test_select_next_fix_item_all_blocked(tmp_path):
    _backlog(tmp_path, (
        "# Backlog\n\n## Filed by coder\n\n"
        "- [bug-a] fix the flake (blocked: qa failed after retry)\n"
    ))
    result = _run("select-next-fix-item.py", [str(tmp_path)], tmp_path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["has_fix"] == "no"


def test_select_next_fix_item_ignores_other_sections(tmp_path):
    """A roadmap bullet under ## Projects must never be drawn by the fix loop —
    only the ## Filed by coder pool is fix-eligible."""
    _backlog(tmp_path, (
        "# Backlog\n\n## Projects\n\n- [roadmap-x] a real feature\n\n"
        "## Filed by coder\n\n- [bug-a] fix the flake\n"
    ))
    result = _run("select-next-fix-item.py", [str(tmp_path)], tmp_path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["has_fix"] == "yes"
    assert out["fix_bullet_id"] == "bug-a"


def test_select_next_fix_item_no_filed_section(tmp_path):
    _backlog(tmp_path, "# Backlog\n\n## Projects\n\n- [roadmap-x] a real feature\n")
    result = _run("select-next-fix-item.py", [str(tmp_path)], tmp_path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["has_fix"] == "no"


# ---------------------------------------------------------------------------
# seed-fix-story.py (real ostler CLI, not mocked)
# ---------------------------------------------------------------------------


def test_seed_fix_story_creates_fixes_epic_and_story(tmp_path):
    (tmp_path / "docs" / "epics").mkdir(parents=True)
    result = _run(
        "seed-fix-story.py",
        ["bug-a", "Fix the sentinel gate flake", "", "", str(tmp_path)],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["epic"] == "fixes"
    assert out["bullet_id"] == "bug-a"
    assert out["story_slug"]

    story_path = tmp_path / out["story_path"]
    assert story_path.is_file()
    body = story_path.read_text(encoding="utf-8")
    assert "## Acceptance Criteria" in body
    assert "- Fix the sentinel gate flake" in body
    assert (tmp_path / "docs" / "epics" / "fixes" / "epic.md").is_file()

    # The fixes bucket is never registered in the epics queue that select_epic /
    # prune_epic manage — it must not collide with epic-mode story selection.
    assert not (tmp_path / "docs" / "epics" / "epics-todo.json").is_file()


def test_seed_fix_story_is_idempotent(tmp_path):
    (tmp_path / "docs" / "epics").mkdir(parents=True)
    first = _run(
        "seed-fix-story.py",
        ["bug-a", "Fix the sentinel gate flake", "", "", str(tmp_path)],
        tmp_path,
    )
    second = _run(
        "seed-fix-story.py",
        ["bug-a", "Fix the sentinel gate flake", "", "", str(tmp_path)],
        tmp_path,
    )
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    out1, out2 = json.loads(first.stdout), json.loads(second.stdout)
    assert out1["story_slug"] == out2["story_slug"]
    assert "already covers" in out2["reason"]

    # Only one story directory exists for this bullet — no duplicate created.
    stories_dir = tmp_path / "docs" / "epics" / "fixes" / "stories"
    assert len(list(stories_dir.iterdir())) == 1


def test_seed_fix_story_reuses_existing_fixes_epic(tmp_path):
    """A second distinct bullet lands in the SAME self-created 'fixes' bucket."""
    (tmp_path / "docs" / "epics").mkdir(parents=True)
    _run("seed-fix-story.py", ["bug-a", "First fix", "", "", str(tmp_path)], tmp_path)
    result = _run("seed-fix-story.py", ["bug-b", "Second fix", "", "", str(tmp_path)], tmp_path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["epic"] == "fixes"

    stories_dir = tmp_path / "docs" / "epics" / "fixes" / "stories"
    assert len(list(stories_dir.iterdir())) == 2


def test_seed_fix_story_requires_bullet_id_and_text(tmp_path):
    (tmp_path / "docs" / "epics").mkdir(parents=True)
    result = _run("seed-fix-story.py", ["", "some text", "", "", str(tmp_path)], tmp_path)
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# prune-fix-item.py
# ---------------------------------------------------------------------------


def test_prune_fix_item_removes_bullet(tmp_path):
    _backlog(tmp_path, "# Backlog\n\n## Filed by coder\n\n- [bug-a] fix the flake\n- [bug-b] other\n")
    result = _run("prune-fix-item.py", ["bug-a", str(tmp_path)], tmp_path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["pruned"] == "yes"
    body = (tmp_path / "docs" / "backlog.md").read_text(encoding="utf-8")
    assert "[bug-a]" not in body
    assert "[bug-b]" in body


def test_prune_fix_item_missing_bullet_is_noop(tmp_path):
    _backlog(tmp_path, "# Backlog\n\n## Filed by coder\n\n- [bug-b] other\n")
    result = _run("prune-fix-item.py", ["bug-a", str(tmp_path)], tmp_path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["pruned"] == "no"
    assert "[bug-b]" in (tmp_path / "docs" / "backlog.md").read_text(encoding="utf-8")


def test_prune_fix_item_no_backlog_file(tmp_path):
    result = _run("prune-fix-item.py", ["bug-a", str(tmp_path)], tmp_path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["pruned"] == "no"


# ---------------------------------------------------------------------------
# mark-fix-blocked.py
# ---------------------------------------------------------------------------


def test_mark_fix_blocked_annotates_bullet(tmp_path):
    _backlog(tmp_path, "# Backlog\n\n## Filed by coder\n\n- [bug-a] fix the flake\n")
    result = _run("mark-fix-blocked.py", ["bug-a", "qa failed after retry", str(tmp_path)], tmp_path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["marked"] == "yes"
    body = (tmp_path / "docs" / "backlog.md").read_text(encoding="utf-8")
    assert "- [bug-a] fix the flake (blocked: qa failed after retry)" in body


def test_mark_fix_blocked_is_idempotent(tmp_path):
    """Re-marking an already-blocked bullet must not double-annotate it — this is
    what keeps select-next-fix-item.py's `(blocked` skip stable across reruns."""
    _backlog(
        tmp_path,
        "# Backlog\n\n## Filed by coder\n\n- [bug-a] fix the flake (blocked: qa failed after retry)\n",
    )
    result = _run("mark-fix-blocked.py", ["bug-a", "qa failed after retry", str(tmp_path)], tmp_path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["marked"] == "yes"
    body = (tmp_path / "docs" / "backlog.md").read_text(encoding="utf-8")
    assert body.count("(blocked") == 1


def test_mark_fix_blocked_missing_bullet(tmp_path):
    _backlog(tmp_path, "# Backlog\n\n## Filed by coder\n\n- [bug-b] other\n")
    result = _run("mark-fix-blocked.py", ["bug-a", "note", str(tmp_path)], tmp_path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["marked"] == "no"
