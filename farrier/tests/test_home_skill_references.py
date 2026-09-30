"""A repo skill that names a skill the repo does not select finds it in the user library."""

from pathlib import Path

import pytest

from farrier.install import main


def make_library(tmp_path: Path, body: str) -> Path:
    library = tmp_path / "agents"
    skills = library / "library" / "skills" / "general"
    skills.mkdir(parents=True)
    (skills / "review.md").write_text(
        "---\nname: review\ndescription: A shared skill.\n---\n\nReview.\n",
        encoding="utf-8",
    )
    stack = library / "library" / "skills" / "stack"
    stack.mkdir(parents=True)
    (stack / "api.md").write_text(
        f"---\nname: api\ndescription: A stack skill.\n---\n\n{body}\n",
        encoding="utf-8",
    )
    (library / "library" / "prompts").mkdir(parents=True)
    (library / "packs").mkdir()
    return library


def write_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    config = tmp_path / "stablemate.toml"
    config.write_text(f"config_version = 1\n\n{body}", encoding="utf-8")
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))


def install(
    tmp_path: Path, library: Path, *extra: str, selects: str = '  - "stack/*"\n'
) -> int:
    repo = tmp_path / "acme"
    repo.mkdir(exist_ok=True)
    (repo / "agents.yml").write_text(
        f"agents:\n  claude: true\nskills:\n{selects}", encoding="utf-8"
    )
    return main(["install", "--repo", str(repo), "--home", str(tmp_path / "home"),
                 "--library", str(library), *extra])


def installed_api(tmp_path: Path) -> str:
    path = tmp_path / "acme/.claude/skills/acme-stack-api/SKILL.md"
    return path.read_text(encoding="utf-8")


HOME_REVIEW = '[user_library.claude]\nskills = ["general/review"]\n'


def test_a_reference_resolves_to_the_user_library_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path, 'See {{ instruction_file("review") }}.')
    write_config(tmp_path, monkeypatch, HOME_REVIEW)

    assert install(tmp_path, library) == 0

    assert "See ~/.claude/skills/general-review/SKILL.md." in installed_api(tmp_path)
    assert (tmp_path / "home/.claude/skills/general-review/SKILL.md").is_file()


def test_a_skill_the_repo_selects_wins_over_the_user_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path, 'See {{ instruction_file("review") }}.')
    write_config(tmp_path, monkeypatch, HOME_REVIEW)

    selects = '  - "stack/*"\n  - "general/review"\n'
    assert install(tmp_path, library, selects=selects) == 0

    assert "See ../acme-general-review/SKILL.md." in installed_api(tmp_path)


def test_a_reference_found_nowhere_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path, 'See {{ instruction_file("review") }}.')
    write_config(tmp_path, monkeypatch, "")

    with pytest.raises(SystemExit) as exc:
        install(tmp_path, library)

    assert "'review'" in str(exc.value)
    assert "[user_library.claude]" in str(exc.value)


def test_a_check_that_cannot_resolve_a_reference_can_be_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CI and a public clone have no user library, like they have no overlay."""
    library = make_library(tmp_path, 'See {{ instruction_file("review") }}.')
    write_config(tmp_path, monkeypatch, "")

    assert install(tmp_path, library, "--check", "--skip-unresolvable") == 0


def test_a_guard_sees_a_user_library_skill_as_in_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(
        tmp_path,
        '{% if isUsingInstruction("review") %}Reviewed.{% else %}Unreviewed.{% endif %}',
    )
    write_config(tmp_path, monkeypatch, HOME_REVIEW)

    assert install(tmp_path, library) == 0

    assert "Reviewed." in installed_api(tmp_path)
    assert "Unreviewed." not in installed_api(tmp_path)


def test_a_user_library_skill_keeps_the_soft_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At user scope the missing skill may live in any repo, so it cannot fail."""
    library = make_library(tmp_path, 'See {{ instruction_file("review") }}.')
    write_config(tmp_path, monkeypatch, '[user_library.claude]\nskills = ["stack/api"]\n')
    home = tmp_path / "home"

    assert main(["install", "--user", "--home", str(home), "--library", str(library)]) == 0

    text = (home / ".claude/skills/stack-api/SKILL.md").read_text(encoding="utf-8")
    assert "See generated review instruction file when installed." in text
