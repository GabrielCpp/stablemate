"""Harnesses that read one skill folder render it once, with one reference form."""

from pathlib import Path

import pytest

from farrier.install import main
from farrier.render_groups import render_groups, skill_forms
from farrier.sources import Source


def source(tmp_path: Path, name: str) -> Source:
    path = tmp_path / f"{name}.md"
    path.write_text(f"---\nname: {name}\n---\n\nBody.\n", encoding="utf-8")
    return Source(kind="skill", path=path, rel=f"{name}.md", id=name)


def test_two_harnesses_with_mixed_syntax_get_the_path_form(tmp_path: Path) -> None:
    a = source(tmp_path, "a")
    groups = render_groups("home", {"codex": ([a], []), "copilot": ([a], [])})

    assert [group.harnesses for group in groups] == [("codex", "copilot")]
    assert groups[0].skill_ref == "path"
    assert skill_forms(groups) == {"codex": "path", "copilot": "path"}


def test_a_group_with_one_syntax_keeps_it(tmp_path: Path) -> None:
    a = source(tmp_path, "a")
    groups = render_groups("home", {"claude": ([a], []), "codex": ([a], [])})

    assert {group.harnesses: group.skill_ref for group in groups} == {
        ("claude",): "slash",
        ("codex",): "dollar",
    }


def test_a_union_of_two_selections_lists_each_skill_once(tmp_path: Path) -> None:
    a, b = source(tmp_path, "a"), source(tmp_path, "b")
    groups = render_groups("home", {"codex": ([a], []), "copilot": ([a, b], [])})

    assert len(groups) == 1
    assert groups[0].skills == [a, b]


def test_a_folder_never_renders_twice(tmp_path: Path) -> None:
    a = source(tmp_path, "a")
    groups = render_groups("home", {"codex": ([a], []), "copilot": ([a], [])})

    assert len({group.folder for group in groups}) == len(groups)


def test_repo_harnesses_with_their_own_folders_stay_apart(tmp_path: Path) -> None:
    a = source(tmp_path, "a")
    groups = render_groups(
        "repo", {"codex": ([a], []), "copilot": ([a], []), "claude": ([a], [])}
    )

    assert {group.harnesses: group.skill_ref for group in groups} == {
        ("claude",): "slash",
        ("codex",): "dollar",
        ("copilot",): "slash",
    }


def test_the_shared_home_folder_installs_once_with_the_path_form(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "agents"
    skills = library / "library" / "skills" / "general"
    skills.mkdir(parents=True)
    (library / "library" / "prompts").mkdir(parents=True)
    (library / "packs").mkdir()
    (skills / "review.md").write_text(
        "---\nname: review\ndescription: Review.\n---\n\nReview.\n", encoding="utf-8"
    )
    (skills / "ship.md").write_text(
        "---\nname: ship\ndescription: Ship.\n---\n\nThen {{ skill_command('review') }}.\n",
        encoding="utf-8",
    )
    config = tmp_path / "stablemate.toml"
    config.write_text(
        'config_version = 1\n\n[user_library.codex]\nskills = ["general/ship"]\n\n'
        '[user_library.copilot]\nskills = ["general/review"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))
    home = tmp_path / "home"

    assert (
        main(["install", "--user", "--home", str(home), "--library", str(library)]) == 0
    )

    shipped = (home / ".agents/skills/ship/SKILL.md").read_text(encoding="utf-8")
    assert "Read `../review/SKILL.md` and follow its instructions" in shipped
    assert (home / ".agents/skills/review/SKILL.md").is_file()
