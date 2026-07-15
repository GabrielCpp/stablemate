"""Tests for flush-root-screenshots.py — the pre-commit stray-screenshot sweep.

Subprocess tests (AGENT_REPO_DIR sandbox). The script must never exit non-zero, must move only
UNTRACKED top-level image files into the story's qa/ dir, leave tracked assets and subdirectory
files alone, avoid clobbering on name collision, and no-op cleanly when there is nothing to move or
the story dir cannot be resolved.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "flush-root-screenshots.py"
# The script takes a spec DIRECTORY (the workflow passes `{{ spec_dir }}`) and files
# strays under `<spec_dir>/qa/` — not the story.md path.
SPEC_DIR = "docs/epics/e1/stories/s-1"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    story_dir = tmp_path / "docs" / "epics" / "e1" / "stories" / "s-1"
    story_dir.mkdir(parents=True)
    (story_dir / "story.md").write_text("# story\n", encoding="utf-8")
    return tmp_path


def _png(repo: Path, name: str) -> Path:
    p = repo / name
    p.write_bytes(b"\x89PNG\r\n")
    return p


def _run(repo: Path, spec_dir: str = SPEC_DIR) -> dict:
    env = dict(os.environ, AGENT_REPO_DIR=str(repo))
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), spec_dir],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, f"non-zero exit\nstderr:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_no_images_is_noop(tmp_path):
    repo = _repo(tmp_path)
    out = _run(repo)
    assert out["screenshots_flushed"] == 0


def test_untracked_root_image_moved_to_qa(tmp_path):
    repo = _repo(tmp_path)
    _png(repo, "ac1-foo-1280.png")
    out = _run(repo)
    assert out["screenshots_flushed"] == 1
    assert not (repo / "ac1-foo-1280.png").exists()
    assert (repo / "docs/epics/e1/stories/s-1/qa/ac1-foo-1280.png").is_file()


def test_tracked_root_image_left_in_place(tmp_path):
    repo = _repo(tmp_path)
    _png(repo, "logo.png")
    _git(repo, "add", "logo.png")
    _git(repo, "commit", "-qm", "add logo")
    out = _run(repo)
    assert out["screenshots_flushed"] == 0
    assert out["screenshots_kept_tracked"] == 1
    assert (repo / "logo.png").is_file()  # untouched


def test_subdirectory_images_untouched(tmp_path):
    repo = _repo(tmp_path)
    sub = repo / "web" / "assets"
    sub.mkdir(parents=True)
    (sub / "hero.png").write_bytes(b"\x89PNG\r\n")
    out = _run(repo)
    assert out["screenshots_flushed"] == 0
    assert (sub / "hero.png").is_file()


def test_only_image_extensions_considered(tmp_path):
    repo = _repo(tmp_path)
    _png(repo, "shot.png")
    (repo / "notes.txt").write_text("x", encoding="utf-8")
    out = _run(repo)
    assert out["screenshots_flushed"] == 1
    assert (repo / "notes.txt").is_file()  # left alone


def test_collision_does_not_clobber(tmp_path):
    repo = _repo(tmp_path)
    qa = repo / "docs/epics/e1/stories/s-1/qa"
    qa.mkdir(parents=True)
    (qa / "shot.png").write_bytes(b"EXISTING")
    _png(repo, "shot.png")  # same name at root, different content
    out = _run(repo)
    assert out["screenshots_flushed"] == 1
    assert (qa / "shot.png").read_bytes() == b"EXISTING"  # original preserved
    assert (qa / "shot-1.png").is_file()  # stray relocated under a suffixed name


def test_blank_story_path_leaves_strays_in_place(tmp_path):
    repo = _repo(tmp_path)
    _png(repo, "orphan.png")
    out = _run(repo, spec_dir="")
    assert out["screenshots_flushed"] == 0
    assert (repo / "orphan.png").is_file()  # not mis-filed under a guessed story


def test_multiple_untracked_images_all_moved(tmp_path):
    repo = _repo(tmp_path)
    for n in ("a.png", "b.jpg", "c.webp"):
        _png(repo, n)
    out = _run(repo)
    assert out["screenshots_flushed"] == 3
    qa = repo / "docs/epics/e1/stories/s-1/qa"
    assert {p.name for p in qa.iterdir()} == {"a.png", "b.jpg", "c.webp"}
