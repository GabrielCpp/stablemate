"""`commit_checks:` declarations and the `farrier checks` listing."""

from __future__ import annotations

from pathlib import Path

import pytest

from farrier import cli
from farrier.install import set_layers
from farrier._vendor.stablemate_core.schema import HomeConfig
from farrier.skill_hooks import CommitCheck, check_findings, checks_for, findings


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "agents"
    skill = root / "library" / "skills" / "demo" / "checked" / "SKILL.md"
    (skill.parent / "scripts").mkdir(parents=True)
    (skill.parent / "scripts" / "check.py").write_text("print('ok')\n", encoding="utf-8")
    skill.write_text(
        "---\n"
        "name: checked\n"
        "description: a skill that declares a commit check\n"
        "commit_checks:\n"
        "  - run: scripts/check.py\n"
        "    budget: 1.5\n"
        "---\n\n# Checked\n",
        encoding="utf-8",
    )
    (root / "packs").mkdir()
    return root


@pytest.fixture(autouse=True)
def _wire_library(monkeypatch, library: Path, tmp_path: Path):
    monkeypatch.setattr(cli, "resolve_library_dir", lambda _cli: library)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(cli, "load_home_config", lambda: HomeConfig())


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "agents.yml").write_text(
        "agents:\n  claude: true\nskills:\n  - demo/checked\n", encoding="utf-8"
    )
    return repo


def test_checks_for_keeps_entries_with_a_run_and_a_positive_budget():
    data = {"commit_checks": [
        {"run": "scripts/a.py", "budget": 2},
        {"run": "scripts/b.py"},
        {"run": "", "budget": 1},
        {"run": "scripts/c.py", "budget": 0},
        "scripts/d.py",
    ]}

    assert checks_for("owner", data) == [CommitCheck("owner", "scripts/a.py", 2.0)]


def test_check_findings_name_every_broken_entry(tmp_path: Path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "ok.py").write_text("", encoding="utf-8")
    data = {"commit_checks": [
        {"run": "scripts/ok.py", "budget": 1},
        {"run": "scripts/gone.py", "budget": 1},
        {"run": "scripts/ok.py"},
        {"budget": 1},
        {"run": "../out.py", "budget": 1},
        "loose",
    ]}

    codes = [code for _, code, _ in check_findings(data, tmp_path)]

    assert codes == [
        "hook-run-missing",
        "commit-check-bad-budget",
        "commit-check-no-run",
        "hook-run-escapes",
        "commit-check-not-a-mapping",
    ]


def test_findings_cover_commit_checks_beside_hooks(tmp_path: Path):
    data = {"hooks": "nope", "commit_checks": "nope"}

    codes = [code for _, code, _ in findings(data, tmp_path)]

    assert codes == ["hooks-not-a-list", "commit-checks-not-a-list"]


def test_checks_list_the_library_script_before_install(library: Path, tmp_path: Path, capsys):
    set_layers(library)
    repo = _repo(tmp_path)

    assert cli.main(["checks", "--repo", str(repo)]) == 0

    script = library / "library" / "skills" / "demo" / "checked" / "scripts" / "check.py"
    assert capsys.readouterr().out == f"python3 {script}\t1.5\n"


def test_checks_prefer_the_installed_script(library: Path, tmp_path: Path, capsys):
    set_layers(library)
    repo = _repo(tmp_path)
    installed = repo / ".claude" / "skills" / "demo-checked" / "scripts" / "check.py"
    installed.parent.mkdir(parents=True)
    installed.write_text("print('ok')\n", encoding="utf-8")

    assert cli.main(["checks", "--repo", str(repo)]) == 0

    assert capsys.readouterr().out == f"python3 {installed}\t1.5\n"


def test_checks_in_a_repo_without_agents_yml_list_nothing(library: Path, tmp_path: Path, capsys):
    set_layers(library)
    repo = tmp_path / "bare"
    repo.mkdir()

    assert cli.main(["checks", "--repo", str(repo)]) == 0

    assert capsys.readouterr().out == ""


def test_checks_in_a_repo_farrier_cannot_resolve_list_nothing(library: Path, tmp_path: Path, capsys):
    set_layers(library)
    repo = tmp_path / "broken"
    repo.mkdir()
    (repo / "agents.yml").write_text("agents:\n  claude: true\npacks:\n  - missing\n", encoding="utf-8")

    assert cli.main(["checks", "--repo", str(repo)]) == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Listed no commit checks" in captured.err
