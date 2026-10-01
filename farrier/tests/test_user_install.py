"""`farrier install --user` — the library installed once per machine, not per repo."""

from pathlib import Path

import pytest

from farrier.install import main


def make_library(tmp_path: Path) -> Path:
    library = tmp_path / "agents"
    skills = library / "library" / "skills" / "stablemate"
    skills.mkdir(parents=True)
    (skills / "db.md").write_text(
        "---\nname: db\ndescription: A skill.\n---\n\nBody.\n", encoding="utf-8"
    )
    (skills / "cache.md").write_text(
        "---\nname: cache\ndescription: Another skill.\n---\n\nBody.\n",
        encoding="utf-8",
    )
    prompts = library / "library" / "prompts" / "stablemate"
    prompts.mkdir(parents=True)
    (prompts / "grill.md").write_text(
        "---\ndescription: A prompt.\n---\n\nAsk me things.\n", encoding="utf-8"
    )
    (library / "packs").mkdir()
    return library


def write_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    config = tmp_path / "stablemate.toml"
    config.write_text(f"config_version = 1\n\n{body}", encoding="utf-8")
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))


def install(home: Path, library: Path, *extra: str) -> int:
    return main(["install", "--user", "--home", str(home), "--library", str(library),
                 *extra])


CLAUDE_BOTH = (
    '[user_library.claude]\nskills = ["stablemate/*"]\nprompts = ["stablemate/grill"]\n'
)
CLAUDE_ONE = '[user_library.claude]\nskills = ["stablemate/db"]\n'

HANDWRITTEN = "---\nname: mine\ndescription: Hand written.\n---\n\nMine.\n"


def test_skills_and_prompts_land_in_the_harness_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    write_config(tmp_path, monkeypatch, CLAUDE_BOTH + '\n[user_library.codex]\nskills = ["stablemate/db"]\n')
    home = tmp_path / "home"

    assert install(home, library) == 0

    assert (home / ".claude/skills/db/SKILL.md").is_file()
    assert (home / ".claude/skills/cache/SKILL.md").is_file()
    assert (home / ".claude/commands/grill.md").is_file()
    assert (home / ".agents/skills/db/SKILL.md").is_file()
    assert not (home / ".agents/commands").exists()


def test_the_repo_scaffolding_stays_out_of_the_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No launcher, no context manifest, no .gitignore — a home is not a checkout."""
    library = make_library(tmp_path)
    write_config(tmp_path, monkeypatch, CLAUDE_BOTH)
    home = tmp_path / "home"

    assert install(home, library) == 0

    assert not (home / ".agents").exists()
    assert not (home / ".gitignore").exists()
    assert not (home / "AGENTS.md").exists()


def test_a_second_run_reports_no_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    write_config(tmp_path, monkeypatch, CLAUDE_BOTH)
    home = tmp_path / "home"

    assert install(home, library) == 0
    assert install(home, library, "--check") == 0


def test_check_reports_an_edited_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    write_config(tmp_path, monkeypatch, CLAUDE_ONE)
    home = tmp_path / "home"
    assert install(home, library) == 0

    installed = home / ".claude/skills/db/SKILL.md"
    installed.write_text(installed.read_text(encoding="utf-8") + "\nEdited.\n",
                         encoding="utf-8")

    assert install(home, library, "--check") == 1


def test_a_deselected_skill_is_swept_and_a_hand_written_one_is_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    write_config(tmp_path, monkeypatch, CLAUDE_BOTH)
    home = tmp_path / "home"
    assert install(home, library) == 0

    mine = home / ".claude/skills/mine/SKILL.md"
    mine.parent.mkdir(parents=True)
    mine.write_text(HANDWRITTEN, encoding="utf-8")

    write_config(tmp_path, monkeypatch, CLAUDE_ONE)
    assert install(home, library) == 0

    assert not (home / ".claude/skills/cache").exists()
    assert not (home / ".claude/commands/grill.md").exists()
    assert mine.read_text(encoding="utf-8") == HANDWRITTEN


def test_a_hand_written_file_in_the_way_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    write_config(tmp_path, monkeypatch, CLAUDE_ONE)
    home = tmp_path / "home"
    clash = home / ".claude/skills/db/SKILL.md"
    clash.parent.mkdir(parents=True)
    clash.write_text(HANDWRITTEN, encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        install(home, library)

    assert "skills/db/SKILL.md" in str(exc.value)
    assert clash.read_text(encoding="utf-8") == HANDWRITTEN


def test_prompts_under_a_non_claude_harness_are_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    write_config(
        tmp_path,
        monkeypatch,
        '[user_library.codex]\nskills = ["stablemate/db"]\n'
        'prompts = ["stablemate/grill"]\n',
    )

    with pytest.raises(SystemExit) as exc:
        install(tmp_path / "home", library)

    assert "prompts are Claude-only at user scope" in str(exc.value)


def test_a_pack_under_a_non_claude_harness_installs_its_skills_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    (library / "packs" / "general.yml").write_text(
        "skills:\n  - stablemate/*\nprompts:\n  - stablemate/grill\n", encoding="utf-8"
    )
    write_config(
        tmp_path,
        monkeypatch,
        '[user_library.claude]\npacks = ["general"]\n\n'
        '[user_library.codex]\npacks = ["general"]\n',
    )
    home = tmp_path / "home"

    assert install(home, library) == 0

    assert (home / ".claude/commands/grill.md").is_file()
    assert (home / ".agents/skills/db/SKILL.md").is_file()
    assert not (home / ".agents/commands").exists()


def test_codex_and_copilot_install_the_union_of_their_tables_into_one_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    write_config(
        tmp_path,
        monkeypatch,
        '[user_library.codex]\nskills = ["stablemate/db"]\n\n'
        '[user_library.copilot]\nskills = ["stablemate/cache"]\n',
    )
    home = tmp_path / "home"

    assert install(home, library) == 0

    assert (home / ".agents/skills/db/SKILL.md").is_file()
    assert (home / ".agents/skills/cache/SKILL.md").is_file()
    assert not (home / ".codex").exists()
    assert not (home / ".copilot").exists()


def test_a_skill_left_in_the_old_codex_and_copilot_folders_is_swept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    write_config(tmp_path, monkeypatch, '[user_library.codex]\nskills = ["stablemate/db"]\n')
    home = tmp_path / "home"
    assert install(home, library) == 0
    generated = (home / ".agents/skills/db/SKILL.md").read_text(encoding="utf-8")
    for old in (".codex", ".copilot"):
        stale = home / old / "skills/db/SKILL.md"
        stale.parent.mkdir(parents=True)
        stale.write_text(generated, encoding="utf-8")
        mine = home / old / "skills/mine/SKILL.md"
        mine.parent.mkdir(parents=True)
        mine.write_text(HANDWRITTEN, encoding="utf-8")

    assert install(home, library) == 0

    for old in (".codex", ".copilot"):
        assert not (home / old / "skills/db").exists()
        assert (home / old / "skills/mine/SKILL.md").read_text(encoding="utf-8") == HANDWRITTEN


def test_an_unknown_harness_table_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    write_config(tmp_path, monkeypatch, '[user_library.cursor]\nskills = ["stablemate/db"]\n')

    with pytest.raises(SystemExit) as exc:
        install(tmp_path / "home", library)

    assert "cursor" in str(exc.value)


def test_no_user_library_at_all_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    write_config(tmp_path, monkeypatch, "")

    with pytest.raises(SystemExit) as exc:
        install(tmp_path / "home", library)

    assert "no user library is configured" in str(exc.value)


def test_a_template_value_comes_from_the_shared_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    skill = library / "library" / "skills" / "stablemate" / "db.md"
    skill.write_text(
        "---\nname: db\ndescription: A skill.\n---\n\nBacked by {{ template.backend }}.\n",
        encoding="utf-8",
    )
    write_config(
        tmp_path,
        monkeypatch,
        CLAUDE_ONE + '\n[user_library.template]\nbackend = "Postgres"\n',
    )
    home = tmp_path / "home"

    assert install(home, library) == 0

    body = (home / ".claude/skills/db/SKILL.md").read_text(encoding="utf-8")
    assert "Backed by Postgres." in body


def test_an_undefined_template_value_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    skill = library / "library" / "skills" / "stablemate" / "db.md"
    skill.write_text(
        "---\nname: db\ndescription: A skill.\n---\n\nBacked by {{ template.backend }}.\n",
        encoding="utf-8",
    )
    write_config(tmp_path, monkeypatch, CLAUDE_ONE)

    with pytest.raises(SystemExit) as exc:
        install(tmp_path / "home", library)

    assert "user_library.template" in str(exc.value)


def test_a_repo_reference_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`repo.…` has no value in a home directory, and must not render as empty."""
    library = make_library(tmp_path)
    skill = library / "library" / "skills" / "stablemate" / "db.md"
    skill.write_text(
        "---\nname: db\ndescription: A skill.\n---\n\nIn {{ repo.name }}.\n",
        encoding="utf-8",
    )
    write_config(tmp_path, monkeypatch, CLAUDE_ONE)

    with pytest.raises(SystemExit) as exc:
        install(tmp_path / "home", library)

    assert "user scope" in str(exc.value)


def test_the_generated_file_names_the_user_scope_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A home has no Makefile: `make agent-install` there re-renders the wrong tree."""
    library = make_library(tmp_path)
    write_config(tmp_path, monkeypatch, CLAUDE_ONE)
    home = tmp_path / "home"
    assert install(home, library) == 0

    text = (home / ".claude/skills/db/SKILL.md").read_text(encoding="utf-8")
    assert "farrier install --user" in text
    assert "make agent-install" not in text
    assert 'resolve: "farrier source ~/.claude/skills/db/SKILL.md"' in text


def install_repo(repo: Path, home: Path, library: Path, *extra: str) -> int:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "agents.yml").write_text(
        'agents:\n  claude: true\nskills:\n  - "stablemate/cache"\n', encoding="utf-8"
    )
    return main(["install", "--repo", str(repo), "--home", str(home),
                 "--library", str(library), *extra])


def test_a_repo_install_also_refreshes_the_user_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    write_config(tmp_path, monkeypatch, CLAUDE_ONE)
    repo = tmp_path / "acme"
    home = tmp_path / "home"

    assert install_repo(repo, home, library) == 0

    assert (repo / ".claude/skills/acme-cache/SKILL.md").is_file()
    assert (home / ".claude/skills/db/SKILL.md").is_file()


def test_a_repo_install_leaves_the_home_alone_without_a_user_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    write_config(tmp_path, monkeypatch, "")
    repo = tmp_path / "acme"
    home = tmp_path / "home"

    assert install_repo(repo, home, library) == 0

    assert not home.exists()


def test_a_repo_check_never_writes_the_user_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    write_config(tmp_path, monkeypatch, CLAUDE_ONE)
    repo = tmp_path / "acme"
    home = tmp_path / "home"
    assert install_repo(repo, tmp_path / "other-home", library) == 0

    assert install_repo(repo, home, library, "--check") == 0

    assert not home.exists()


def test_a_repo_install_names_each_skill_the_home_also_installs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    library = make_library(tmp_path)
    write_config(tmp_path, monkeypatch, '[user_library.claude]\nskills = ["stablemate/*"]\n')

    assert install_repo(tmp_path / "acme", tmp_path / "home", library) == 0

    notices = [line for line in capsys.readouterr().out.splitlines() if "user library" in line]
    assert len(notices) == 1
    assert "'cache'" in notices[0]


def test_a_home_copy_for_a_harness_the_repo_does_not_enable_is_no_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    library = make_library(tmp_path)
    write_config(tmp_path, monkeypatch, '[user_library.codex]\nskills = ["stablemate/*"]\n')

    assert install_repo(tmp_path / "acme", tmp_path / "home", library) == 0

    assert "user library" not in capsys.readouterr().out


def test_a_repo_check_prints_no_duplicate_notice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    library = make_library(tmp_path)
    write_config(tmp_path, monkeypatch, '[user_library.claude]\nskills = ["stablemate/*"]\n')
    assert install_repo(tmp_path / "acme", tmp_path / "home", library) == 0
    _ = capsys.readouterr()

    assert install_repo(tmp_path / "acme", tmp_path / "home", library, "--check") == 0

    assert "user library" not in capsys.readouterr().out
