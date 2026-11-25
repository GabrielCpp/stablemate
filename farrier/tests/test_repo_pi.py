"""Pi at repo scope: skills share `.agents/skills` with Codex and prompts go to `.pi/prompts`."""

from pathlib import Path

from farrier.agents import parse_agents
from farrier.outputs import local_instruction_target
from repo_install import install, shipped


def test_pi_alone_renders_the_shared_folder_with_the_path_form(tmp_path: Path) -> None:
    config = "agents:\n  pi: true\nskills:\n  - ship\n  - review\n"
    code, repo = install(tmp_path, config)
    assert code == 0
    assert "Read `../acme-review/SKILL.md`" in shipped(repo)
    assert install(tmp_path, config, "--check")[0] == 0


def test_pi_and_codex_render_the_folder_once(tmp_path: Path) -> None:
    config = "agents:\n  codex: true\n  pi: true\nskills:\n  - ship\n  - review\n"
    code, repo = install(tmp_path, config)
    assert code == 0
    assert "Read `../acme-review/SKILL.md`" in shipped(repo)
    assert install(tmp_path, config, "--check")[0] == 0


def test_pi_prompts_land_in_pi_prompts_with_the_md_suffix(tmp_path: Path) -> None:
    config = "agents:\n  pi: true\nskills:\n  - ship\n  - review\nprompts:\n  - go\n"
    code, repo = install(tmp_path, config)
    assert code == 0
    assert "Go ahead." in (repo / ".pi/prompts/acme-go.md").read_text(encoding="utf-8")
    assert install(tmp_path, config, "--check")[0] == 0


def test_pi_alone_points_local_instructions_at_the_codex_template() -> None:
    assert local_instruction_target(parse_agents({"agents": {"pi": True}})) == "codex"
