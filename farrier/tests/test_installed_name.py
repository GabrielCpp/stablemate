"""The installed name is the repo folder and the skill's folder name, never its category."""

from pathlib import Path

import pytest

from farrier.install import main
from farrier.layers import BASE_DIR_ENV


def _library(tmp_path: Path, rel: str) -> Path:
    library = tmp_path / "agents"
    skill = library / "library" / "skills" / rel
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(
        "---\nname: x\ndescription: A skill.\n---\n\nBody.\n", encoding="utf-8"
    )
    (library / "library" / "prompts").mkdir(parents=True, exist_ok=True)
    (library / "packs").mkdir(exist_ok=True)
    return library


def _install(tmp_path: Path, rel: str, select: str, repo_name: str = "acme") -> Path:
    library = _library(tmp_path, rel)
    repo = tmp_path / repo_name
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "agents.yml").write_text(
        f"agents:\n  claude: true\nskills:\n  - {select}\n", encoding="utf-8"
    )
    assert main(["install", "--repo", str(repo), "--library", str(library)]) == 0
    return repo


@pytest.mark.parametrize(
    ("rel", "select", "installed"),
    [
        ("architecture/hexagonal.md", "architecture/hexagonal", "acme-hexagonal"),
        ("stacks/flutter/flutter-api.md", "stacks/flutter/flutter-api", "acme-flutter-api"),
        ("db.md", "db", "acme-db"),
    ],
)
def test_the_category_never_joins_the_installed_name(
    tmp_path: Path, rel: str, select: str, installed: str
) -> None:
    repo = _install(tmp_path, rel, select)

    assert (repo / ".claude/skills" / installed / "SKILL.md").is_file()


def test_the_repo_name_collapses_when_the_skill_already_carries_it(tmp_path: Path) -> None:
    """One prefix, not two."""
    repo = _install(tmp_path, "acme/acme-deploy.md", "acme/acme-deploy")

    assert (repo / ".claude/skills/acme-deploy/SKILL.md").is_file()
    assert not (repo / ".claude/skills/acme-acme-deploy").exists()


def test_a_skill_is_selectable_by_its_path_or_its_name(tmp_path: Path) -> None:
    for select in ("stacks/flutter/flutter-api", "flutter-api"):
        repo = _install(
            tmp_path / select.replace("/", "_"), "stacks/flutter/flutter-api.md", select
        )
        assert (repo / ".claude/skills/acme-flutter-api/SKILL.md").is_file()


def test_the_category_alone_no_longer_selects(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        _install(tmp_path, "stacks/flutter/api.md", "flutter-api")


def test_an_overlay_skill_overrides_the_base_skill_of_the_same_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = tmp_path / "base"
    skill = base / "library" / "skills" / "web" / "api" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: api\ndescription: Base.\n---\n\nBase copy.\n", encoding="utf-8")
    monkeypatch.setenv(BASE_DIR_ENV, str(base))

    repo = _install(tmp_path, "stacks/api/SKILL.md", "api")

    installed = (repo / ".claude/skills/acme-api/SKILL.md").read_text(encoding="utf-8")
    assert "Body." in installed
    assert "Base copy." not in installed
    notice = "skill 'api' (stacks/api/SKILL.md) overrides base-library (base) (web/api/SKILL.md)"
    assert notice in capsys.readouterr().out
