"""Antigravity at repo scope: it shares `.agents/skills` with Codex."""

from pathlib import Path

import pytest

from farrier.agents import parse_agents
from farrier.install import main


def make_library(tmp_path: Path) -> Path:
    library = tmp_path / "agents"
    skills = library / "library" / "skills"
    skills.mkdir(parents=True)
    (skills / "review.md").write_text(
        "---\nname: review\ndescription: Review.\n---\n\nReview.\n", encoding="utf-8"
    )
    (skills / "ship.md").write_text(
        "---\nname: ship\ndescription: Ship.\n---\n\nThen {{ skill_command('review') }}.\n",
        encoding="utf-8",
    )
    (library / "library" / "prompts").mkdir(parents=True)
    (library / "packs").mkdir()
    return library


def install(tmp_path: Path, config: str, *extra: str) -> tuple[int, Path]:
    library = (
        make_library(tmp_path)
        if not (tmp_path / "agents").exists()
        else tmp_path / "agents"
    )
    repo = tmp_path / "acme"
    repo.mkdir(exist_ok=True)
    (repo / "agents.yml").write_text(config, encoding="utf-8")
    code = main(["install", "--repo", str(repo), "--library", str(library), *extra])
    return code, repo


def shipped(repo: Path) -> str:
    return (repo / ".agents/skills/acme-ship/SKILL.md").read_text(encoding="utf-8")


def test_antigravity_alone_keeps_slash_references(tmp_path: Path) -> None:
    code, repo = install(
        tmp_path, "agents:\n  antigravity: true\nskills:\n  - ship\n  - review\n"
    )
    assert code == 0
    assert "Then /acme-review." in shipped(repo)
    assert (
        install(
            tmp_path,
            "agents:\n  antigravity: true\nskills:\n  - ship\n  - review\n",
            "--check",
        )[0]
        == 0
    )


def test_codex_alone_keeps_dollar_references(tmp_path: Path) -> None:
    code, repo = install(
        tmp_path, "agents:\n  codex: true\nskills:\n  - ship\n  - review\n"
    )
    assert code == 0
    assert "Then $acme-review." in shipped(repo)


def test_both_on_render_the_folder_once_with_the_path_form(tmp_path: Path) -> None:
    config = (
        "agents:\n  codex: true\n  antigravity: true\nskills:\n  - ship\n  - review\n"
    )
    code, repo = install(tmp_path, config)
    assert code == 0
    text = shipped(repo)
    assert "Then /acme-review." not in text
    assert "Then $acme-review." not in text
    assert "Read `../acme-review/SKILL.md`" in text
    assert install(tmp_path, config, "--check")[0] == 0


def test_antigravity_has_no_prompts_folder(tmp_path: Path) -> None:
    code, repo = install(
        tmp_path, "agents:\n  antigravity: true\nskills:\n  - ship\n  - review\n"
    )
    assert code == 0
    assert not (repo / ".gemini").exists()


def test_sharers_of_a_folder_cannot_link_from_different_sources() -> None:
    config = {
        "agents": {
            "claude": True,
            "copilot": True,
            "codex": {"skills_from": "claude"},
            "antigravity": {"skills_from": "copilot"},
        }
    }
    with pytest.raises(SystemExit):
        parse_agents(config)
