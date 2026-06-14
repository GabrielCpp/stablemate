"""Standalone tests for the managed `.agents/` .gitignore block.

`ensure_agents_gitignore` ignores generated adapter outputs under `.agents/` while
tracking hand-authored files (the launcher Makefile and `.agents/flavors/`), and
migrates a legacy wholesale `.agents` ignore line so git can descend.

Verified against real `git check-ignore` (the ground truth, which honors
ancestor-directory exclusion).

Run directly (no pytest required):
    uv run python tests/test_gitignore_migration.py
"""

import subprocess
import tempfile
from pathlib import Path

from farrier import install


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)


def _ignored(repo: Path, rel: str) -> bool:
    """True iff git would ignore `rel` (honors ancestor-dir exclusion)."""
    r = subprocess.run(["git", "check-ignore", "-q", "--", rel], cwd=repo)
    return r.returncode == 0


def test_fresh_repo_appends_block():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        _git_init(repo)
        assert install.ensure_agents_gitignore(repo) is True
        lines = (repo / ".gitignore").read_text().splitlines()
        for entry in install.AGENTS_GITIGNORE_BLOCK:
            assert entry in lines
        assert _ignored(repo, ".agents/runs/run.json") is True
        assert _ignored(repo, ".agents/agents-context.json") is True
        assert _ignored(repo, ".agents/skills/foo/SKILL.md") is True
        assert _ignored(repo, ".agents/agents.mk") is False
        assert _ignored(repo, ".agents/flavors/author/write-story.md") is False
    print("ok: fresh repo appends block")


def test_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        _git_init(repo)
        assert install.ensure_agents_gitignore(repo) is True
        first = (repo / ".gitignore").read_text()
        assert install.ensure_agents_gitignore(repo) is False  # no change second time
        assert (repo / ".gitignore").read_text() == first
    print("ok: idempotent")


def test_migrates_legacy_wholesale_agents_line():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        _git_init(repo)
        # Pre-existing repo state from the old installer + the user's own rules.
        (repo / ".gitignore").write_text(
            "node_modules\n.env\n.agents/runs\n.agents\n!.agents/agents.mk\n"
        )
        assert install.ensure_agents_gitignore(repo) is True
        lines = (repo / ".gitignore").read_text().splitlines()
        # The legacy wholesale-ignore line is gone; user rules are preserved.
        assert ".agents" not in lines
        assert "node_modules" in lines and ".env" in lines
        for entry in install.AGENTS_GITIGNORE_BLOCK:
            assert entry in lines
        # Net effect: generated outputs ignored, hand-authored files tracked.
        assert _ignored(repo, ".agents/skills/foo/SKILL.md") is True
        assert _ignored(repo, ".agents/flavors/author/write-story.md") is False
        assert _ignored(repo, ".agents/agents.mk") is False
    print("ok: migrates legacy .agents line")


if __name__ == "__main__":
    test_fresh_repo_appends_block()
    test_idempotent()
    test_migrates_legacy_wholesale_agents_line()
    print("\nall gitignore-migration tests passed")
