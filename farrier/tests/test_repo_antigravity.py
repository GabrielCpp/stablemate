"""Antigravity at repo scope: it shares `.agents/skills` with Codex."""

from pathlib import Path


from repo_install import install, make_library, shipped


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


def test_antigravity_takes_a_prompt_as_a_skill_only_its_name_runs(
    tmp_path: Path,
) -> None:
    config = "agents:\n  antigravity: true\nskills:\n  - ship\n  - review\nprompts:\n  - go\n"
    code, repo = install(tmp_path, config)
    assert code == 0
    folder = repo / ".agents/skills/acme-go"
    skill = (folder / "SKILL.md").read_text(encoding="utf-8")
    assert "name: acme-go" in skill
    assert "disable-model-invocation: true" in skill
    assert "Go ahead." in skill
    assert (folder / "agents/openai.yaml").read_text(encoding="utf-8") == (
        "policy:\n  allow_implicit_invocation: false\n"
    )
    assert not (repo / ".gemini").exists()
    assert install(tmp_path, config, "--check")[0] == 0


def test_a_skill_can_reference_a_prompt_that_landed_as_a_skill(
    tmp_path: Path,
) -> None:
    make_library(tmp_path)
    (tmp_path / "agents/library/skills/ship.md").write_text(
        "---\nname: ship\ndescription: Ship.\n---\n\nThen {{ skill_command('go') }}.\n",
        encoding="utf-8",
    )
    config = "agents:\n  antigravity: true\nskills:\n  - ship\nprompts:\n  - go\n"
    code, repo = install(tmp_path, config)
    assert code == 0
    assert "Then /acme-go." in shipped(repo)
