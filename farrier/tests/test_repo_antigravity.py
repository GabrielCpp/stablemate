"""Antigravity at repo scope: it shares `.agents/skills` with Codex."""

from pathlib import Path

import pytest

from farrier.agents import parse_agents
from repo_install import install, shipped


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
