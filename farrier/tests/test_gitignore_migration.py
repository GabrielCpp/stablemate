"""Standalone tests for the managed `.agents/` .gitignore block.

`ensure_agents_gitignore` names the generated and ephemeral paths under `.agents/`
and ignores exactly those, leaving everything else in the directory tracked — the
launcher Makefile, prompt flavor overrides, and repo state a tool writes there
(ostler's `ids.json`) alike. It migrates both earlier spellings: the wholesale
`.agents` line, and the `/.agents/*`-plus-negations exclude list.

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
        assert _ignored(repo, ".agents/agents-context.claude.json") is True
        assert _ignored(repo, ".agents/skills/foo/SKILL.md") is True
        assert _ignored(repo, ".agents/local.compose.yaml") is True
        assert _ignored(repo, ".agents/operator/ci-operator.md") is True
        assert _ignored(repo, ".agents/agents.mk") is False
        assert _ignored(repo, ".agents/flavors/author/write-story.md") is False
        # Tracked by default: the block names what to ignore, so a path no one
        # listed — ostler's id registry — is committed rather than silently lost.
        assert _ignored(repo, ".agents/ids.json") is False
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


def test_migrates_exclude_list_block():
    """The `/.agents/*` exclude list is stripped, not left to keep excluding."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        _git_init(repo)
        (repo / ".gitignore").write_text(
            "node_modules\n\n/.agents/*\n!/.agents/agents.mk\n!/.agents/flavors/\n"
        )
        assert install.ensure_agents_gitignore(repo) is True
        lines = (repo / ".gitignore").read_text().splitlines()
        assert "/.agents/*" not in lines
        assert "!/.agents/agents.mk" not in lines
        assert "node_modules" in lines
        # The whole point of the migration: a path nobody listed is tracked again.
        assert _ignored(repo, ".agents/ids.json") is False
        assert _ignored(repo, ".agents/skills/foo/SKILL.md") is True
    print("ok: migrates exclude-list block")


if __name__ == "__main__":
    test_fresh_repo_appends_block()
    test_idempotent()
    test_migrates_legacy_wholesale_agents_line()
    test_migrates_exclude_list_block()
    print("\nall gitignore-migration tests passed")
