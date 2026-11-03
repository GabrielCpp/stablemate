"""`farrier hooks run-user` — the user library's hooks, run from a repo's generated runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from farrier import cli
from farrier.install import main

GATE = "from pathlib import Path\nPath('gate-ran').touch()\nraise SystemExit({status})\n"

USER_LIBRARY = '[user_library.claude]\nskills = ["demo/*"]\n'


def _library(root: Path, status: int) -> Path:
    skill = root / "library" / "skills" / "demo" / "gated" / "SKILL.md"
    (skill.parent / "scripts").mkdir(parents=True)
    (skill.parent / "scripts" / "check.py").write_text(GATE.format(status=status), encoding="utf-8")
    skill.write_text(
        "---\nname: gated\ndescription: a skill that declares a hook\n"
        "hooks:\n  - stage: pre-commit\n    run: scripts/check.py\n---\n\nBody.\n",
        encoding="utf-8",
    )
    (root / "packs").mkdir()
    return root


@pytest.fixture
def machine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A home with the user library installed, and a repo that selects nothing."""

    def build(status: int = 0, *, config: str = USER_LIBRARY) -> Path:
        library = _library(tmp_path / "agents", status)
        home = tmp_path / "home"
        settings = tmp_path / "stablemate.toml"
        settings.write_text(f"config_version = 1\n\n{config}", encoding="utf-8")
        monkeypatch.setenv("STABLEMATE_CONFIG", str(settings))
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setattr(cli, "resolve_library_dir", lambda _cli: library)
        if config == USER_LIBRARY:
            assert main(["install", "--user", "--home", str(home), "--library", str(library)]) == 0
        repo = tmp_path / "repo"
        repo.mkdir()
        return repo

    return build


def _run(repo: Path) -> int:
    return cli.main(["hooks", "run-user", "--repo", str(repo)])


def test_a_user_skill_gate_runs_in_a_repo_that_does_not_select_it(machine):
    repo = machine()

    assert _run(repo) == 0
    assert (repo / "gate-ran").is_file()


def test_a_refusing_gate_refuses_the_commit(machine):
    repo = machine(status=3)

    assert _run(repo) == 3


def test_a_skill_the_repo_selects_runs_from_the_repo_runner_only(machine):
    repo = machine()
    (repo / "agents.yml").write_text("agents:\n  claude: true\nskills:\n  - demo/gated\n", encoding="utf-8")

    assert _run(repo) == 0
    assert not (repo / "gate-ran").exists()


def test_a_repo_opts_out_by_excluding_the_skill(machine):
    repo = machine(status=3)
    (repo / "agents.yml").write_text(
        "agents:\n  claude: true\nexclude:\n  skills:\n    - demo/gated\n", encoding="utf-8"
    )

    assert _run(repo) == 0
    assert not (repo / "gate-ran").exists()


def test_a_machine_with_no_user_library_runs_nothing(machine):
    repo = machine(config="")

    assert _run(repo) == 0
    assert not (repo / "gate-ran").exists()


def test_a_hook_whose_script_is_not_installed_is_left_out(machine, tmp_path: Path):
    repo = machine(status=3)
    (tmp_path / "home/.claude/skills/gated/scripts/check.py").unlink()

    assert _run(repo) == 0


def test_a_broken_user_library_skips_with_a_note(machine, tmp_path: Path, capsys):
    repo = machine(config='[user_library.claude]\nskills = ["demo/missing"]\n')

    assert _run(repo) == 0
    assert "Skipped the user library's hooks" in capsys.readouterr().err
