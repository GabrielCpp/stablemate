"""The installed name carries the source's group, and never repeats a segment."""

from pathlib import Path

import pytest

from farrier.install import main


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
        ("architecture/hexagonal.md", "architecture/hexagonal", "acme-architecture-hexagonal"),
        ("stacks/flutter/api.md", "stacks/flutter/api", "acme-flutter-api"),
        ("stacks/flutter/flutter-api.md", "stacks/flutter/flutter-api", "acme-flutter-api"),
        ("db.md", "db", "acme-db"),
    ],
)
def test_the_group_prefixes_the_installed_name(
    tmp_path: Path, rel: str, select: str, installed: str
) -> None:
    repo = _install(tmp_path, rel, select)

    assert (repo / ".claude/skills" / installed / "SKILL.md").is_file()


def test_the_repo_name_collapses_when_it_is_also_the_group(tmp_path: Path) -> None:
    """One prefix, not two."""
    repo = _install(tmp_path, "acme/deploy.md", "acme/deploy")

    assert (repo / ".claude/skills/acme-deploy/SKILL.md").is_file()
    assert not (repo / ".claude/skills/acme-acme-deploy").exists()


def test_a_skill_stays_selectable_by_every_spelling(tmp_path: Path) -> None:
    """Selection accepts the library path, the bare basename and the grouped name."""
    for select in ("stacks/flutter/api", "api", "flutter-api"):
        repo = _install(
            tmp_path / select.replace("/", "_"), "stacks/flutter/api.md", select
        )
        assert (repo / ".claude/skills/acme-flutter-api/SKILL.md").is_file()
