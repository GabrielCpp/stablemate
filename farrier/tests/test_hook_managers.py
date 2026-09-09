"""Wiring farrier's one hook command into the repo's hook manager.

Every case here is about the *fence*. Farrier used to own a whole `pre-commit` file or
refuse — which is why this repo's own staged-files gate was never installed: something
else was already there, so farrier declined, and every report still said the install
succeeded. Owning a marked region instead is what makes both halves of that file
possible at once, and what these pin is that the user's half comes through untouched
in each of the five managers. The runner-regeneration cases below pin the same
contract for the per-repo runner that lives on farrier's side of the fence.

    ./.venv/bin/python -m pytest tests/test_hook_managers.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from farrier import cli
from farrier.hook_managers import (
    FENCE_END,
    FENCE_START,
    HOOK_COMMAND,
    HOOK_RUNNER,
    LEFTHOOK_INCLUDE,
    LEGACY_HOOK_MARKER,
    configured_manager,
    detect_manager,
    fence_drift,
    install_manager,
    install_runner,
    runner_text,
    splice,
    unsplice,
)
from farrier.skill_hooks import SkillHook


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def _read(repo: Path, rel: str) -> str:
    return (repo / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# which manager
# ---------------------------------------------------------------------------


def test_the_config_names_the_manager(repo: Path):
    assert configured_manager({"hooks": {"manager": "lefthook"}}, repo) == "lefthook"


def test_an_unconfigured_repo_falls_back_to_what_it_looks_like(repo: Path):
    """Detection stays the default rather than requiring the key: a config key that must
    be set before hooks work at all turns them off for every repo already installed."""
    (repo / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")

    assert configured_manager({}, repo) == "pre-commit"


def test_a_bare_repo_detects_as_githooks(repo: Path):
    assert detect_manager(repo) == "githooks"


def test_husky_is_detected_before_npm_install_has_run(repo: Path):
    """Marker file, not `core.hooksPath`: husky sets that config during `npm install`,
    and a config-only probe would call a husky repo bare and wire the wrong manager."""
    (repo / "package.json").write_text('{"devDependencies": {"husky": "^9"}}', encoding="utf-8")

    assert detect_manager(repo) == "husky"


def test_a_manager_outside_the_vocabulary_is_refused(repo: Path):
    with pytest.raises(SystemExit) as excinfo:
        configured_manager({"hooks": {"manager": "lint-staged"}}, repo)

    assert "lint-staged" in str(excinfo.value)


# ---------------------------------------------------------------------------
# the fence itself
# ---------------------------------------------------------------------------


def test_the_fence_is_replaced_in_place_not_appended():
    existing = f"before\n{FENCE_START}\nold\n{FENCE_END}\nafter\n"

    result = splice(existing, f"{FENCE_START}\nnew\n{FENCE_END}\n")

    assert result == f"before\n{FENCE_START}\nnew\n{FENCE_END}\nafter\n"


def test_unsplicing_leaves_the_rest_of_the_file(repo: Path):
    existing = f"before\n{FENCE_START}\nold\n{FENCE_END}\nafter\n"

    assert unsplice(existing) == "before\nafter\n"


@pytest.mark.parametrize(
    ("manager", "rel"),
    [
        ("pre-commit", ".pre-commit-config.yaml"),
        ("lefthook", "lefthook.yml"),
        ("husky", ".husky/pre-commit"),
        ("githooks", ".githooks/pre-commit"),
    ],
)
def test_every_manager_gets_the_command_and_keeps_the_users_lines(
    repo: Path, manager: str, rel: str
):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("repos: []\n# mine\n", encoding="utf-8")

    install_manager(repo, manager)

    text = _read(repo, rel)
    assert "# mine" in text
    assert FENCE_START in text and FENCE_END in text
    assert HOOK_COMMAND in text or LEFTHOOK_INCLUDE in text


def test_installing_twice_changes_nothing(repo: Path):
    install_manager(repo, "githooks")
    before = _read(repo, ".githooks/pre-commit")

    assert install_manager(repo, "githooks") == []
    assert _read(repo, ".githooks/pre-commit") == before


def test_a_shell_hook_farrier_creates_is_executable(repo: Path):
    install_manager(repo, "githooks")

    hook = repo / ".githooks" / "pre-commit"
    assert hook.stat().st_mode & 0o111
    assert hook.read_text(encoding="utf-8").startswith("#!/bin/sh")


def test_githooks_points_git_at_the_tracked_directory(repo: Path):
    install_manager(repo, "githooks")

    configured = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=repo, capture_output=True, text=True, check=False,
    ).stdout.strip()
    assert configured == ".githooks"


def test_lefthook_references_a_file_farrier_owns_whole(repo: Path):
    """The body lives on farrier's side so the region spliced into `lefthook.yml` is one
    unchanging line — it must not churn when a skill selection changes."""
    (repo / "lefthook.yml").write_text("pre-push:\n  commands: {}\n", encoding="utf-8")

    install_manager(repo, "lefthook")

    text = _read(repo, "lefthook.yml")
    assert LEFTHOOK_INCLUDE in text
    assert HOOK_COMMAND not in text


def test_a_legacy_whole_file_hook_is_migrated_not_appended_to(repo: Path):
    """A repo on the old whole-file marker would otherwise end up running the gate twice
    and reporting each failure twice."""
    hook = repo / ".githooks" / "pre-commit"
    hook.parent.mkdir()
    hook.write_text(
        f"#!/bin/sh\n{LEGACY_HOOK_MARKER}\nexec python3 old-gate.py\n", encoding="utf-8"
    )

    install_manager(repo, "githooks")

    text = _read(repo, ".githooks/pre-commit")
    assert LEGACY_HOOK_MARKER not in text
    assert "old-gate.py" not in text
    assert text.count(HOOK_COMMAND) == 1


def test_a_pre_commit_config_farrier_creates_opens_with_repos(repo: Path):
    install_manager(repo, "pre-commit")

    assert _read(repo, ".pre-commit-config.yaml").startswith("repos:\n")


def test_none_removes_the_entry_and_leaves_the_file(repo: Path):
    (repo / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    install_manager(repo, "pre-commit")

    install_manager(repo, "none")

    text = _read(repo, ".pre-commit-config.yaml")
    assert FENCE_START not in text
    assert "repos: []" in text


# ---------------------------------------------------------------------------
# what --check says about it
# ---------------------------------------------------------------------------


def test_a_missing_fence_is_drift_not_an_opt_out(repo: Path):
    """agents.yml is the authority on what is installed, so deleting the block is an
    edit about to be reverted. `manager: none` is the opt-out."""
    assert fence_drift(repo, "githooks") == [".githooks/pre-commit"]

    install_manager(repo, "githooks")
    assert fence_drift(repo, "githooks") == []


def test_an_edit_inside_the_fence_is_drift(repo: Path):
    install_manager(repo, "githooks")
    hook = repo / ".githooks" / "pre-commit"
    hook.write_text(
        hook.read_text(encoding="utf-8").replace(HOOK_COMMAND, "make something-else"),
        encoding="utf-8",
    )

    assert fence_drift(repo, "githooks") == [".githooks/pre-commit"]


def test_an_edit_outside_the_fence_is_not(repo: Path):
    install_manager(repo, "githooks")
    hook = repo / ".githooks" / "pre-commit"
    hook.write_text(hook.read_text(encoding="utf-8") + "\necho mine\n", encoding="utf-8")

    assert fence_drift(repo, "githooks") == []


def test_a_leftover_fence_is_drift_under_none(repo: Path):
    install_manager(repo, "githooks")

    assert fence_drift(repo, "none") == [".githooks/pre-commit"]


# ---------------------------------------------------------------------------
# the generated runner
# ---------------------------------------------------------------------------


def test_the_runner_tries_every_adapter_path_for_a_declared_hook():
    text = runner_text([SkillHook(skill="acme-ostler", stage="pre-commit", run="scripts/g.py")])

    for root in (".claude/skills", ".agents/skills", ".github/skills"):
        assert f"{root}/acme-ostler/scripts/g.py" in text


def test_a_repo_whose_skills_declare_nothing_still_gets_a_runner():
    """The drift check lives in the make target, not here, so an empty runner is not an
    empty hook — and a repo that later selects a hook-declaring skill needs no rewiring."""
    text = runner_text([])

    assert text.startswith("#!/bin/sh")
    assert "exit 0" in text


# ---------------------------------------------------------------------------
# install_runner + dry_run on install_manager
# ---------------------------------------------------------------------------


def test_install_runner_writes_when_text_differs(repo: Path):
    """`install_runner` regenerates `.agents/hooks/pre-commit` from the declared
    hooks, marking the runner executable so git will pick it up via `core.hooksPath`."""
    hooks = [SkillHook(skill="acme-ostler", stage="pre-commit", run="scripts/g.py")]

    messages = install_runner(repo, hooks)

    assert messages == [f"Wrote {HOOK_RUNNER}"]
    runner = repo / HOOK_RUNNER
    assert runner.is_file()
    assert runner.stat().st_mode & 0o111


def test_install_runner_is_silent_when_runner_is_current(repo: Path):
    """Re-running the verb on a repo whose runner is already up to date is a
    no-op — no message, no rewrite, no `mtime` change to chase in CI logs."""
    hooks = [SkillHook(skill="acme-ostler", stage="pre-commit", run="scripts/g.py")]
    install_runner(repo, hooks)

    assert install_runner(repo, hooks) == []


def test_install_runner_dry_run_prints_without_writing(repo: Path):
    """`--dry-run` reports what the verb would write and never touches disk."""
    hooks = [SkillHook(skill="acme-ostler", stage="pre-commit", run="scripts/g.py")]

    messages = install_runner(repo, hooks, dry_run=True)

    assert messages == [f"[dry-run] would regenerate {HOOK_RUNNER}"]
    assert not (repo / HOOK_RUNNER).exists()


def test_install_runner_with_none_signals_no_library(repo: Path):
    """`hooks=None` is the no-library signal: silent without `--dry-run`, the
    cause-named note under `--dry-run`. The next `farrier install` regenerates."""
    assert install_runner(repo, None) == []
    assert install_runner(repo, None, dry_run=True) == [
        f"[dry-run] would regenerate {HOOK_RUNNER} "
        "(no library — run 'farrier install' to refresh)"
    ]
    assert not (repo / HOOK_RUNNER).exists()


def test_install_manager_dry_run_prints_with_prefix_and_writes_nothing(repo: Path):
    """`--dry-run` on the manager writes nothing and prefixes every action
    message so a dry-run and a real run can be diffed line by line."""
    (repo / "agents.yml").write_text("hooks:\n  manager: githooks\n", encoding="utf-8")

    messages = install_manager(repo, "githooks", dry_run=True)

    assert any(line.startswith("[dry-run]") for line in messages)
    assert not (repo / ".githooks" / "pre-commit").exists()


# ---------------------------------------------------------------------------
# `farrier hooks` — the wiring without the render
# ---------------------------------------------------------------------------


def test_hooks_install_wires_when_packs_dont_resolve(repo: Path):
    """The clone most likely to trip a guard is the one that cannot render.

    A public contributor has no overlay, so `farrier install` raises on the first pack
    it cannot resolve and never reaches the wiring at the end of it. `farrier hooks
    install` reads `agents.yml` for the manager name and nothing else, so the hook
    still gets installed on the machine that has no library to install from.
    """
    (repo / "agents.yml").write_text(
        "packs:\n  - a-pack-that-is-not-anywhere\nhooks:\n  manager: githooks\n",
        encoding="utf-8",
    )

    assert cli.main(["hooks", "install", "--repo", str(repo)]) == 0

    hook = repo / ".githooks" / "pre-commit"
    assert HOOK_COMMAND in hook.read_text(encoding="utf-8")
    assert hook.stat().st_mode & 0o111
    assert fence_drift(repo, "githooks") == []
    configured = subprocess.run(
        ["git", "config", "core.hooksPath"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert configured == ".githooks"


def test_hooks_install_falls_back_to_detection_with_no_agents_yml(repo: Path):
    assert cli.main(["hooks", "install", "--repo", str(repo)]) == 0

    assert HOOK_COMMAND in (repo / ".githooks" / "pre-commit").read_text(encoding="utf-8")


def test_hooks_install_dry_run_writes_nothing(repo: Path):
    """Every action that would have written, set, or changed a file is reported
    with a `[dry-run]` prefix and nothing is touched on disk."""
    (repo / "agents.yml").write_text("hooks:\n  manager: githooks\n", encoding="utf-8")

    assert cli.main(["hooks", "install", "--dry-run", "--repo", str(repo)]) == 0

    assert not (repo / ".githooks" / "pre-commit").exists()
    configured = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    assert configured == ""


def test_hooks_install_dry_run_with_no_library_prints_runner_note(
    capsys, repo: Path, monkeypatch
):
    """When no library resolves, `--dry-run` reports the cause-named line so the
    operator can see why the runner regeneration step was skipped."""
    from farrier import cli as cli_module

    monkeypatch.setattr(cli_module, "LAYERS", [])

    (repo / "agents.yml").write_text("hooks:\n  manager: githooks\n", encoding="utf-8")

    assert cli.main(["hooks", "install", "--dry-run", "--repo", str(repo)]) == 0

    out = capsys.readouterr().out
    assert "[dry-run] would regenerate .agents/hooks/pre-commit (no library" in out


def test_bare_hooks_is_a_subcommand_error(capsys, repo: Path):
    """Breaking change: the bare `farrier hooks` form no longer maps to the
    install verb — argparse rejects it because the subparser is required."""
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["hooks", "--repo", str(repo)])

    assert excinfo.value.code != 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
