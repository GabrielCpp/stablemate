"""Installing the staged-files gate as a `pre-commit` hook.

Every case here is about *ownership*. Farrier writes whole files it owns and refuses
anything else, so what these pin is where the line falls: a repo with no hook manager
gets a tracked `.githooks/pre-commit` and `core.hooksPath`, a repo that already runs
something at pre-commit gets a printed snippet and its own file untouched. The failure
this guards against is silent in both directions — a stomped hook stops firing and says
nothing, and a hook farrier declined to write leaves the gate installed but never run.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from farrier.hooks import (
    HOOK_MARKER,
    OSTLER_BASE,
    QA_GITIGNORE_BLOCK,
    ensure_qa_gitignore,
    hook_text,
    install_hook,
    plan_hook,
)
from farrier.naming import compose_name, repo_prefix
from farrier.outputs import install_outputs


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def _hooks_path(repo: Path) -> str:
    return subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


# ---------------------------------------------------------------------------
# the file-drop case
# ---------------------------------------------------------------------------


def test_a_plain_repo_gets_a_tracked_hook(repo: Path):
    """`.git/hooks/` is per-clone and invisible to review; `.githooks/` is committed, so
    the gate arrives with the checkout rather than with a setup step nobody runs."""
    message = install_hook(repo)

    hook = repo / ".githooks" / "pre-commit"
    assert hook.is_file()
    assert hook.stat().st_mode & 0o111
    assert _hooks_path(repo) == ".githooks"
    assert "Installed" in message


def test_the_hook_finds_the_gate_wherever_the_adapter_put_it(repo: Path):
    skill = compose_name(repo_prefix(repo), OSTLER_BASE)
    text = hook_text(skill)
    assert f".claude/skills/{skill}/scripts/check_staged_files.py" in text
    assert f".agents/skills/{skill}/scripts/check_staged_files.py" in text
    assert "exec python3" in text


def test_installing_twice_rewrites_nothing(repo: Path):
    install_hook(repo)
    before = (repo / ".githooks" / "pre-commit").read_text(encoding="utf-8")

    message = install_hook(repo)

    assert (repo / ".githooks" / "pre-commit").read_text(encoding="utf-8") == before
    assert "Verified" in message


def test_farrier_rewrites_the_hook_it_owns(repo: Path):
    hook = repo / ".githooks" / "pre-commit"
    hook.parent.mkdir()
    hook.write_text(f"#!/bin/sh\n{HOOK_MARKER}\necho an older generation\n", encoding="utf-8")

    install_hook(repo)

    skill = compose_name(repo_prefix(repo), OSTLER_BASE)
    assert hook.read_text(encoding="utf-8") == hook_text(skill)


def test_a_repo_with_its_own_githooks_hook_is_refused(repo: Path):
    """stablemate itself is this case: `.githooks/pre-commit` already runs its
    private-names guard, and overwriting it would drop that check on the floor."""
    hook = repo / ".githooks" / "pre-commit"
    hook.parent.mkdir()
    hook.write_text("#!/bin/sh\nexec python3 scripts/check_public.py\n", encoding="utf-8")

    message = install_hook(repo)

    assert hook.read_text(encoding="utf-8").endswith("check_public.py\n")
    assert "Skipped" in message and "check_staged_files.py" in message


def test_a_legacy_git_hooks_pre_commit_is_not_silenced(repo: Path):
    """Setting `core.hooksPath` stops git reading `.git/hooks/` at all. The old hook
    would keep sitting there looking installed and never fire again."""
    legacy = repo / ".git" / "hooks" / "pre-commit"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    message = install_hook(repo)

    assert not (repo / ".githooks").exists()
    assert _hooks_path(repo) == ""
    assert "Skipped" in message


def test_an_existing_hooks_path_is_where_the_hook_lands(repo: Path):
    subprocess.run(["git", "config", "core.hooksPath", "tools/hooks"], cwd=repo, check=True)

    install_hook(repo)

    assert (repo / "tools" / "hooks" / "pre-commit").is_file()
    assert _hooks_path(repo) == "tools/hooks"


# ---------------------------------------------------------------------------
# hook managers
# ---------------------------------------------------------------------------


def test_husky_without_a_pre_commit_gets_one(repo: Path):
    (repo / ".husky").mkdir()

    install_hook(repo)

    assert (repo / ".husky" / "pre-commit").is_file()
    assert not (repo / ".githooks").exists()


def test_husky_is_detected_before_npm_install_has_run(repo: Path):
    """Marker file, not `core.hooksPath`: husky sets that config during `npm install`,
    and a config-only probe would call a husky repo bare and stomp it."""
    (repo / "package.json").write_text('{"devDependencies": {"husky": "^9"}}', encoding="utf-8")

    plan = plan_hook(repo)

    assert plan.action == "write"
    assert plan.path == repo / ".husky" / "pre-commit"


def test_husky_with_a_pre_commit_is_refused(repo: Path):
    (repo / ".husky").mkdir()
    (repo / ".husky" / "pre-commit").write_text("npm test\n", encoding="utf-8")

    message = install_hook(repo)

    assert (repo / ".husky" / "pre-commit").read_text(encoding="utf-8") == "npm test\n"
    assert "Skipped" in message


@pytest.mark.parametrize(
    ("marker", "snippet"),
    [
        (".pre-commit-config.yaml", "repo: local"),
        ("lefthook.yml", "pre-commit:"),
    ],
)
def test_a_yaml_hook_manager_gets_a_snippet_not_an_edit(repo: Path, marker: str, snippet: str):
    """Farrier's pipeline is `path -> full text` end to end and `--check` diffs whole
    files, so a fragment inside a config we do not own has no honest place in it."""
    (repo / marker).write_text("repos: []\n", encoding="utf-8")

    message = install_hook(repo)

    assert not (repo / ".githooks").exists()
    assert "Skipped" in message and snippet in message


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


def test_the_install_follows_the_ostler_skill(repo: Path):
    """A repo that selected the skill has already chosen the gate; one that did not gets
    neither the hook nor the ignore block, and no explaining."""
    skill = compose_name(repo_prefix(repo), OSTLER_BASE)
    gate = repo / ".claude/skills" / skill / "scripts/check_staged_files.py"

    install_outputs(repo, {gate: "print('gate')\n"})

    assert (repo / ".githooks" / "pre-commit").is_file()
    assert "**/qa/**/traces/" in (repo / ".gitignore").read_text(encoding="utf-8")


def test_a_repo_without_the_skill_gets_neither(repo: Path):
    install_outputs(repo, {repo / ".claude/skills/other/SKILL.md": "# other\n"})

    assert not (repo / ".githooks").exists()
    assert not (repo / ".gitignore").exists()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
