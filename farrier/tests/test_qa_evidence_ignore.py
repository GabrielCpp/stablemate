"""The QA-evidence ignore block that ships with the staged-files gate.

The hook *wiring* moved out of this module and into `hook_managers` (see
`test_hook_managers.py`); what stays here is the other half of shipping the gate — the
ignore rules that keep a run's artifacts out of the index before any hook has to refuse
them. Both are guarded on the gate script being among the outputs, so a repo that did
not select the ostler skill gets neither and no explaining.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from farrier.hooks import QA_GITIGNORE_BLOCK, ensure_qa_gitignore
from farrier.outputs import install_outputs
from farrier.naming import compose_name, repo_prefix


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


# ---------------------------------------------------------------------------
# the ignore block
# ---------------------------------------------------------------------------


def test_the_ignore_block_names_artifacts_not_the_qa_directory(repo: Path):
    """`**/qa/` would swallow a source package called `qa`, and a new file born ignored
    is the silent failure this repo has already paid for once."""
    assert "**/qa/" not in QA_GITIGNORE_BLOCK
    assert "**/qa/**/traces/" in QA_GITIGNORE_BLOCK

    assert ensure_qa_gitignore(repo)

    text = (repo / ".gitignore").read_text(encoding="utf-8")
    assert "**/qa/**/videos/" in text and "**/qa/qa-run.ndjson" in text


def test_the_ignore_block_is_idempotent_and_keeps_the_repo_rules(repo: Path):
    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")

    assert ensure_qa_gitignore(repo)
    assert not ensure_qa_gitignore(repo)
    assert (repo / ".gitignore").read_text(encoding="utf-8").startswith("node_modules/\n")


def test_the_block_is_refreshed_in_place_when_it_changes(repo: Path):
    (repo / ".gitignore").write_text(
        f"{QA_GITIGNORE_BLOCK[0]}\n**/qa/**/older/\n{QA_GITIGNORE_BLOCK[-1]}\ndist/\n",
        encoding="utf-8",
    )

    assert ensure_qa_gitignore(repo)

    text = (repo / ".gitignore").read_text(encoding="utf-8")
    assert "**/qa/**/older/" not in text
    assert "dist/" in text


# ---------------------------------------------------------------------------
# what triggers it
# ---------------------------------------------------------------------------


def test_the_install_follows_the_skill_that_ships_the_gate(repo: Path):
    """A repo that selected the skill has already chosen the rules; one that did not
    gets nothing, and no explaining."""
    skill = compose_name(repo_prefix(repo), "ostler")
    gate = repo / ".claude/skills" / skill / "scripts/check_staged_files.py"

    install_outputs(repo, {gate: "print('gate')\n"})

    assert "**/qa/**/traces/" in (repo / ".gitignore").read_text(encoding="utf-8")


def test_a_repo_without_the_skill_gets_nothing(repo: Path):
    install_outputs(repo, {repo / ".claude/skills/other/SKILL.md": "# other\n"})

    assert not (repo / ".gitignore").exists()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
