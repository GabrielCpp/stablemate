"""`agents.<harness>.skills_from`: one rendered copy of the skills, symlinked for the others."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from farrier.agents import parse_agents
from farrier.install import main

LINKED = "agents:\n  claude: true\n  codex:\n    skills_from: claude\n"


def make_library(tmp_path: Path) -> Path:
    library = tmp_path / "agents"
    skills = library / "library" / "skills"
    skills.mkdir(parents=True)
    for name in ("db", "cache"):
        (skills / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: A skill.\n---\n\nBody of {name}.\n",
            encoding="utf-8",
        )
    (library / "library" / "prompts").mkdir(parents=True)
    (library / "packs").mkdir()
    return library


def install(repo: Path, library: Path, config: str, *extra: str) -> int:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "agents.yml").write_text(config, encoding="utf-8")
    return main(["install", "--repo", str(repo), "--library", str(library), *extra])


def check(repo: Path, library: Path) -> int:
    return main(["install", "--repo", str(repo), "--library", str(library), "--check"])


def test_a_link_to_an_unknown_harness_is_rejected() -> None:
    with pytest.raises(SystemExit) as excinfo:
        parse_agents({"agents": {"claude": True, "codex": {"skills_from": "cursor"}}})
    assert "not a harness" in str(excinfo.value)


def test_a_harness_cannot_link_from_itself() -> None:
    with pytest.raises(SystemExit) as excinfo:
        parse_agents({"agents": {"claude": {"skills_from": "claude"}}})
    assert "cannot link its own skills" in str(excinfo.value)


def test_a_link_from_a_disabled_harness_is_rejected() -> None:
    with pytest.raises(SystemExit) as excinfo:
        parse_agents({"agents": {"claude": False, "codex": {"skills_from": "claude"}}})
    assert "not enabled" in str(excinfo.value)


def test_a_link_from_a_linked_harness_is_rejected() -> None:
    config = {
        "agents": {
            "claude": True,
            "codex": {"skills_from": "claude"},
            "copilot": {"skills_from": "codex"},
        }
    }
    with pytest.raises(SystemExit) as excinfo:
        parse_agents(config)
    assert "itself links its skills" in str(excinfo.value)


def test_a_mapping_without_skills_from_is_rejected() -> None:
    with pytest.raises(SystemExit) as excinfo:
        parse_agents({"agents": {"claude": True, "codex": {"skill_from": "claude"}}})
    assert "skills_from" in str(excinfo.value)


def test_a_linked_harness_counts_as_enabled() -> None:
    agents = parse_agents(
        {"agents": {"claude": True, "codex": {"skills_from": "claude"}}}
    )
    assert agents.get("codex")
    assert agents.links == {"codex": "claude"}
    assert agents.real_skill_harnesses() == ["claude"]


def test_install_links_each_skill_folder_relatively(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, LINKED + "skills:\n  - db\n  - cache\n") == 0

    link = repo / ".agents/skills/acme-db"
    assert link.is_symlink()
    assert os.readlink(link) == "../../.claude/skills/acme-db"
    assert (link / "SKILL.md").read_text(encoding="utf-8").startswith("---\n")
    assert not (repo / ".agents/skills/acme-db/SKILL.md").is_symlink()
    assert (repo / ".claude/skills/acme-db/SKILL.md").is_file()


def test_a_linked_harness_still_gets_its_own_prompts_and_manifest(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    (library / "library" / "prompts" / "ship.md").write_text(
        "---\ndescription: Ship it\n---\n\nShip.\n", encoding="utf-8"
    )
    repo = tmp_path / "acme"
    assert install(repo, library, LINKED + "skills:\n  - db\nprompts:\n  - ship\n") == 0

    assert (repo / ".agents/prompts/acme-ship.prompt.md").is_file()
    assert (repo / ".agents/agents-context.codex.json").is_file()


def test_a_hand_written_skill_in_the_source_dir_gets_a_symlink(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    mine = repo / ".claude/skills/mine/SKILL.md"
    mine.parent.mkdir(parents=True)
    mine.write_text(
        "---\nname: mine\ndescription: Mine.\n---\n\nMine.\n", encoding="utf-8"
    )

    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0

    assert os.readlink(repo / ".agents/skills/mine") == "../../.claude/skills/mine"
    assert mine.read_text(encoding="utf-8").endswith("Mine.\n")
    assert check(repo, library) == 0


def test_a_wrong_symlink_is_rewritten(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    config = LINKED + "skills:\n  - db\n"
    assert install(repo, library, config) == 0
    link = repo / ".agents/skills/acme-db"
    link.unlink()
    os.symlink("../../.claude/skills/elsewhere", link)

    assert install(repo, library, config) == 0

    assert os.readlink(link) == "../../.claude/skills/acme-db"


def test_a_stale_symlink_is_swept(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, LINKED + "skills:\n  - db\n  - cache\n") == 0
    assert (repo / ".agents/skills/acme-cache").is_symlink()

    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0

    assert not (repo / ".agents/skills/acme-cache").is_symlink()
    assert not (repo / ".agents/skills/acme-cache").exists()
    assert (repo / ".agents/skills/acme-db").is_symlink()


def test_a_foreign_symlink_is_not_swept(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    foreign = repo / ".agents/skills/theirs"
    os.symlink(outside, foreign)

    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0

    assert foreign.is_symlink()
    assert os.readlink(foreign) == str(outside)


def test_a_foreign_symlink_at_a_link_path_aborts_the_install(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    foreign = repo / ".agents/skills/acme-db"
    foreign.parent.mkdir(parents=True)
    os.symlink(outside, foreign)

    with pytest.raises(SystemExit) as excinfo:
        install(repo, library, LINKED + "skills:\n  - db\n")

    assert ".agents/skills/acme-db" in str(excinfo.value)
    assert os.readlink(foreign) == str(outside)
    assert not (repo / ".claude/skills/acme-db").exists()


def test_a_real_folder_at_a_link_path_aborts_the_install(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    held = repo / ".agents/skills/acme-db/SKILL.md"
    held.parent.mkdir(parents=True)
    held.write_text("---\nname: acme-db\n---\n\nMine.\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        install(repo, library, LINKED + "skills:\n  - db\n")

    assert ".agents/skills/acme-db" in str(excinfo.value)
    assert held.read_text(encoding="utf-8").endswith("Mine.\n")


def test_switching_to_linked_sweeps_the_generated_copy(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    both = "agents:\n  claude: true\n  codex: true\nskills:\n  - db\n"
    assert install(repo, library, both) == 0
    assert (repo / ".agents/skills/acme-db/SKILL.md").is_file()

    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0

    assert (repo / ".agents/skills/acme-db").is_symlink()
    assert (repo / ".claude/skills/acme-db/SKILL.md").is_file()
    assert check(repo, library) == 0


def test_switching_back_to_real_folders_refuses_to_write_through_the_links(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0
    before = (repo / ".claude/skills/acme-db/SKILL.md").read_text(encoding="utf-8")

    both = "agents:\n  claude: true\n  codex: true\nskills:\n  - db\n"
    with pytest.raises(SystemExit):
        install(repo, library, both)

    assert (repo / ".claude/skills/acme-db/SKILL.md").read_text(
        encoding="utf-8"
    ) == before


def test_check_passes_when_every_link_is_in_place(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, LINKED + "skills:\n  - db\n  - cache\n") == 0

    assert check(repo, library) == 0


def test_check_reports_a_missing_symlink(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0
    (repo / ".agents/skills/acme-db").unlink()

    assert check(repo, library) == 1
    assert "missing: .agents/skills/acme-db" in capsys.readouterr().out


def test_check_reports_a_wrong_symlink(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0
    link = repo / ".agents/skills/acme-db"
    link.unlink()
    os.symlink("../../.claude/skills/acme-cache", link)

    assert check(repo, library) == 1
    out = capsys.readouterr().out
    assert "changed: .agents/skills/acme-db" in out
    assert "symlink to ../../.claude/skills/acme-cache" in out


def test_check_reports_an_extra_symlink(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0
    os.symlink("../../.claude/skills/gone", repo / ".agents/skills/gone")

    assert check(repo, library) == 1
    assert "extra: .agents/skills/gone" in capsys.readouterr().out


def test_check_reports_a_real_folder_where_a_link_belongs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0
    link = repo / ".agents/skills/acme-db"
    link.unlink()
    link.mkdir()

    assert check(repo, library) == 1
    assert "a real folder" in capsys.readouterr().out


def test_a_sweep_of_the_linked_dir_never_deletes_the_source_files(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    config = LINKED + "skills:\n  - db\n"
    assert install(repo, library, config) == 0
    source_file = repo / ".claude/skills/acme-db/SKILL.md"

    assert install(repo, library, config) == 0
    assert install(repo, library, config) == 0

    assert source_file.is_file()


def test_cross_skill_links_in_the_shared_copy_point_at_the_source_homes(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    (library / "library" / "skills" / "db.md").write_text(
        "---\nname: db\ndescription: A skill.\n---\n\n{{ skill_link('cache') }}\n",
        encoding="utf-8",
    )
    repo = tmp_path / "acme"
    assert install(repo, library, LINKED + "skills:\n  - db\n  - cache\n") == 0

    body = (repo / ".agents/skills/acme-db/SKILL.md").read_text(encoding="utf-8")
    assert "../acme-cache/SKILL.md" in body


def test_a_home_skill_link_in_the_shared_copy_points_at_the_source_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    (library / "library" / "skills" / "db.md").write_text(
        "---\nname: db\ndescription: A skill.\n---\n\nSee {{ skill_path('review') }}.\n",
        encoding="utf-8",
    )
    (library / "library" / "skills" / "review.md").write_text(
        "---\nname: review\ndescription: Shared.\n---\n\nReview.\n", encoding="utf-8"
    )
    config = tmp_path / "stablemate.toml"
    config.write_text(
        "config_version = 1\n\n"
        '[user_library.claude]\nskills = ["review"]\n\n'
        '[user_library.codex]\nskills = ["review"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))
    repo = tmp_path / "acme"

    assert (
        install(
            repo,
            library,
            LINKED + "skills:\n  - db\n",
            "--home",
            str(tmp_path / "home"),
        )
        == 0
    )

    body = (repo / ".agents/skills/acme-db/SKILL.md").read_text(encoding="utf-8")
    assert "See ~/.claude/skills/review/SKILL.md." in body
