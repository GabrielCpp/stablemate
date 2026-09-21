"""Standalone tests for the managed `.agents/` .gitignore block."""

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
        assert _ignored(repo, ".agents/local.compose.yaml") is True
        assert _ignored(repo, ".agents/operator/ci-operator.md") is True
        assert _ignored(repo, ".agents/agents.mk") is False
        assert _ignored(repo, ".agents/flavors/author/write-story.md") is False
        assert _ignored(repo, ".agents/skills/foo/SKILL.md") is False
        assert _ignored(repo, ".agents/prompts/foo.prompt.md") is False
        assert _ignored(repo, ".agents/ids.json") is False
    print("ok: fresh repo appends block")


def test_block_entries_carry_no_leading_slash():
    """A mid-pattern slash already anchors to the .gitignore's directory."""
    for entry in install.AGENTS_GITIGNORE_BLOCK:
        assert not entry.startswith("/"), entry
        assert "/" in entry.rstrip("/"), entry
    print("ok: no leading slashes")


def test_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        _git_init(repo)
        assert install.ensure_agents_gitignore(repo) is True
        first = (repo / ".gitignore").read_text()
        assert install.ensure_agents_gitignore(repo) is False
        assert (repo / ".gitignore").read_text() == first
    print("ok: idempotent")


def test_migrates_legacy_wholesale_agents_line():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        _git_init(repo)
        (repo / ".gitignore").write_text(
            "node_modules\n.env\n.agents/runs\n.agents\n!.agents/agents.mk\n"
        )
        assert install.ensure_agents_gitignore(repo) is True
        lines = (repo / ".gitignore").read_text().splitlines()
        assert ".agents" not in lines
        assert "node_modules" in lines and ".env" in lines
        for entry in install.AGENTS_GITIGNORE_BLOCK:
            assert entry in lines
        assert _ignored(repo, ".agents/runs/run.json") is True
        assert _ignored(repo, ".agents/skills/foo/SKILL.md") is False
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
        assert _ignored(repo, ".agents/ids.json") is False
        assert _ignored(repo, ".agents/runs/run.json") is True
    print("ok: migrates exclude-list block")


def test_migrates_slash_prefixed_block():
    """The previous block's own spelling is stripped, not appended to."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        _git_init(repo)
        (repo / ".gitignore").write_text(
            "node_modules\n\n"
            "/.agents/runs/\n/.agents/worktrees/\n/.agents/skills/\n/.agents/prompts/\n"
            "/.agents/workflows/\n/.agents/operator/\n/.agents/local.compose.yaml\n"
            "/.agents/agents-context.json\n/.agents/agents-context.*.json\n"
        )
        assert install.ensure_agents_gitignore(repo) is True
        lines = (repo / ".gitignore").read_text().splitlines()
        assert not [ln for ln in lines if ln.startswith("/.agents/")]
        assert "node_modules" in lines
        assert _ignored(repo, ".agents/skills/foo/SKILL.md") is False
        assert _ignored(repo, ".agents/prompts/foo.prompt.md") is False
        assert _ignored(repo, ".agents/runs/run.json") is True
        assert _ignored(repo, ".agents/worktrees/w1/main.go") is True
    print("ok: migrates slash-prefixed block")


if __name__ == "__main__":
    test_fresh_repo_appends_block()
    test_block_entries_carry_no_leading_slash()
    test_idempotent()
    test_migrates_legacy_wholesale_agents_line()
    test_migrates_exclude_list_block()
    test_migrates_slash_prefixed_block()
    print("\nall gitignore-migration tests passed")
