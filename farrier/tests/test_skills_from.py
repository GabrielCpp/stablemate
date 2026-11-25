"""`agents.claude.skills_from`: Claude links each skill folder to the one in `.agents/skills`."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from farrier._vendor.stablemate_core.schema.manifest import (
    HARNESSES,
    LINK_SOURCES,
    LINKING_HARNESS,
)
from farrier.agents import parse_agents
from farrier.install import main

LINKED = "agents:\n  codex: true\n  claude:\n    skills_from: codex\n"


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
    with pytest.raises(SystemExit, match="cursor"):
        parse_agents({"agents": {"codex": True, "claude": {"skills_from": "cursor"}}})


@pytest.mark.parametrize("source", [h for h in HARNESSES if h not in LINK_SOURCES])
def test_claude_links_only_from_a_harness_that_reads_agents_skills(source: str) -> None:
    with pytest.raises(SystemExit, match=r"\.agents/skills"):
        parse_agents({"agents": {"claude": {"skills_from": source}}})


@pytest.mark.parametrize("harness", [h for h in HARNESSES if h != LINKING_HARNESS])
def test_only_claude_may_link_its_skills(harness: str) -> None:
    with pytest.raises(SystemExit, match=f"agents.{harness}"):
        parse_agents({"agents": {"claude": True, harness: {"skills_from": "claude"}}})


def test_a_link_from_a_disabled_harness_is_rejected() -> None:
    with pytest.raises(SystemExit, match="not enabled"):
        parse_agents({"agents": {"codex": False, "claude": {"skills_from": "codex"}}})


def test_a_mapping_without_skills_from_is_rejected() -> None:
    with pytest.raises(SystemExit) as excinfo:
        parse_agents({"agents": {"claude": True, "codex": {"skill_from": "claude"}}})
    assert "skills_from" in str(excinfo.value)


def test_a_linked_harness_counts_as_enabled() -> None:
    agents = parse_agents(
        {"agents": {"codex": True, "claude": {"skills_from": "codex"}}}
    )
    assert agents.get("claude")
    assert agents.links == {"claude": "codex"}
    assert agents.real_skill_harnesses() == ["codex"]


def test_install_links_each_skill_folder_relatively(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, LINKED + "skills:\n  - db\n  - cache\n") == 0

    link = repo / ".claude/skills/acme-db"
    assert link.is_symlink()
    assert os.readlink(link) == "../../.agents/skills/acme-db"
    assert (link / "SKILL.md").read_text(encoding="utf-8").startswith("---\n")
    assert not (repo / ".claude/skills/acme-db/SKILL.md").is_symlink()
    assert (repo / ".agents/skills/acme-db/SKILL.md").is_file()


def test_a_hand_written_skill_in_the_source_dir_gets_a_symlink(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    mine = repo / ".agents/skills/mine/SKILL.md"
    mine.parent.mkdir(parents=True)
    mine.write_text(
        "---\nname: mine\ndescription: Mine.\n---\n\nMine.\n", encoding="utf-8"
    )

    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0

    assert os.readlink(repo / ".claude/skills/mine") == "../../.agents/skills/mine"
    assert mine.read_text(encoding="utf-8").endswith("Mine.\n")
    assert check(repo, library) == 0


def test_a_wrong_symlink_is_rewritten(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    config = LINKED + "skills:\n  - db\n"
    assert install(repo, library, config) == 0
    link = repo / ".claude/skills/acme-db"
    link.unlink()
    os.symlink("../../.agents/skills/elsewhere", link)

    assert install(repo, library, config) == 0

    assert os.readlink(link) == "../../.agents/skills/acme-db"


def test_a_stale_symlink_is_swept(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, LINKED + "skills:\n  - db\n  - cache\n") == 0
    assert (repo / ".claude/skills/acme-cache").is_symlink()

    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0

    assert not (repo / ".claude/skills/acme-cache").is_symlink()
    assert not (repo / ".claude/skills/acme-cache").exists()
    assert (repo / ".claude/skills/acme-db").is_symlink()


def test_a_foreign_symlink_is_not_swept(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    foreign = repo / ".claude/skills/theirs"
    os.symlink(outside, foreign)

    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0

    assert foreign.is_symlink()
    assert os.readlink(foreign) == str(outside)


def test_a_foreign_symlink_at_a_link_path_aborts_the_install(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    foreign = repo / ".claude/skills/acme-db"
    foreign.parent.mkdir(parents=True)
    os.symlink(outside, foreign)

    with pytest.raises(SystemExit) as excinfo:
        install(repo, library, LINKED + "skills:\n  - db\n")

    assert ".claude/skills/acme-db" in str(excinfo.value)
    assert os.readlink(foreign) == str(outside)
    assert not (repo / ".agents/skills/acme-db").exists()


def test_a_real_folder_at_a_link_path_aborts_the_install(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    held = repo / ".claude/skills/acme-db/SKILL.md"
    held.parent.mkdir(parents=True)
    held.write_text("---\nname: acme-db\n---\n\nMine.\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        install(repo, library, LINKED + "skills:\n  - db\n")

    assert ".claude/skills/acme-db" in str(excinfo.value)
    assert held.read_text(encoding="utf-8").endswith("Mine.\n")


def test_switching_to_linked_sweeps_the_generated_copy(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    both = "agents:\n  claude: true\n  codex: true\nskills:\n  - db\n"
    assert install(repo, library, both) == 0
    assert (repo / ".claude/skills/acme-db/SKILL.md").is_file()

    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0

    assert (repo / ".claude/skills/acme-db").is_symlink()
    assert (repo / ".agents/skills/acme-db/SKILL.md").is_file()
    assert check(repo, library) == 0


def test_switching_back_to_real_folders_refuses_to_write_through_the_links(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0
    before = (repo / ".agents/skills/acme-db/SKILL.md").read_text(encoding="utf-8")

    both = "agents:\n  claude: true\n  codex: true\nskills:\n  - db\n"
    with pytest.raises(SystemExit):
        install(repo, library, both)

    assert (repo / ".agents/skills/acme-db/SKILL.md").read_text(
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
    (repo / ".claude/skills/acme-db").unlink()

    assert check(repo, library) == 1
    assert "missing: .claude/skills/acme-db" in capsys.readouterr().out


def test_check_reports_a_wrong_symlink(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0
    link = repo / ".claude/skills/acme-db"
    link.unlink()
    os.symlink("../../.agents/skills/acme-cache", link)

    assert check(repo, library) == 1
    out = capsys.readouterr().out
    assert "changed: .claude/skills/acme-db" in out
    assert "symlink to ../../.agents/skills/acme-cache" in out


def test_check_reports_an_extra_symlink(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0
    os.symlink("../../.agents/skills/gone", repo / ".claude/skills/gone")

    assert check(repo, library) == 1
    assert "extra: .claude/skills/gone" in capsys.readouterr().out


def test_check_reports_a_real_folder_where_a_link_belongs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "acme"
    assert install(repo, library, LINKED + "skills:\n  - db\n") == 0
    link = repo / ".claude/skills/acme-db"
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
    source_file = repo / ".agents/skills/acme-db/SKILL.md"

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

    body = (repo / ".claude/skills/acme-db/SKILL.md").read_text(encoding="utf-8")
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

    body = (repo / ".claude/skills/acme-db/SKILL.md").read_text(encoding="utf-8")
    assert "See ~/.agents/skills/review/SKILL.md." in body


def test_a_harness_that_takes_prompts_gets_no_link_to_their_skill_form(
    tmp_path: Path,
) -> None:
    library = make_library(tmp_path)
    (library / "library" / "prompts" / "ship.md").write_text(
        "---\ndescription: Ship it\n---\n\nShip.\n", encoding="utf-8"
    )
    repo = tmp_path / "acme"
    selection = "agents:\n  codex: true\n  claude:\n    skills_from: codex\n"
    assert install(repo, library, selection + "skills:\n  - db\nprompts:\n  - ship\n") == 0

    assert (repo / ".agents/skills/acme-ship/SKILL.md").is_file()
    assert (repo / ".claude/commands/acme-ship.md").is_file()
    assert (repo / ".claude/skills/acme-db").is_symlink()
    assert not (repo / ".claude/skills/acme-ship").exists()
    assert (repo / ".agents/agents-context.claude.json").is_file()


def test_a_codex_prompt_from_an_earlier_install_is_swept(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    (library / "library" / "prompts" / "ship.md").write_text(
        "---\ndescription: Ship it\n---\n\nShip.\n", encoding="utf-8"
    )
    repo = tmp_path / "acme"
    selection = "skills:\n  - db\nprompts:\n  - ship\n"
    assert install(repo, library, "agents:\n  claude: true\n" + selection) == 0
    earlier = repo / ".agents/prompts/acme-ship.prompt.md"
    earlier.parent.mkdir(parents=True)
    earlier.write_text(
        (repo / ".claude/commands/acme-ship.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    hand_written = repo / ".agents/prompts/mine.md"
    hand_written.write_text("Mine.\n", encoding="utf-8")

    assert install(repo, library, "agents:\n  codex: true\n" + selection) == 0

    assert not earlier.exists()
    assert hand_written.is_file()
    assert (repo / ".agents/skills/acme-ship/SKILL.md").is_file()
