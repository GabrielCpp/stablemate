"""`farrier install --user` — the library installed once per machine, not per repo.

A skill that needs nothing from the repo it is invoked in was still being installed
into every checkout, once per checkout, and every one of those copies drifted
separately. User scope renders the same sources into the harness home directories
instead, selected by a `[user_library.<harness>]` table in the stablemate config.

What these tests hold down is where the two scopes deliberately *differ*: no repo
prefix, no launcher, no repo context — and the errors that must stay loud, because a
silent skip at user scope is a skill the agent never sees and nobody misses.
"""

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

    # Named by their library group, not by a repo — there is no repo to prefix with.
    assert (home / ".claude/skills/stablemate-db/SKILL.md").is_file()
    assert (home / ".claude/skills/stablemate-cache/SKILL.md").is_file()
    assert (home / ".claude/commands/stablemate-grill.md").is_file()
    assert (home / ".codex/skills/stablemate-db/SKILL.md").is_file()
    assert not (home / ".codex/commands").exists()


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

    installed = home / ".claude/skills/stablemate-db/SKILL.md"
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

    assert not (home / ".claude/skills/stablemate-cache").exists()
    assert not (home / ".claude/commands/stablemate-grill.md").exists()
    assert mine.read_text(encoding="utf-8") == HANDWRITTEN


def test_a_hand_written_file_in_the_way_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = make_library(tmp_path)
    write_config(tmp_path, monkeypatch, CLAUDE_ONE)
    home = tmp_path / "home"
    clash = home / ".claude/skills/stablemate-db/SKILL.md"
    clash.parent.mkdir(parents=True)
    clash.write_text(HANDWRITTEN, encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        install(home, library)

    assert "stablemate-db" in str(exc.value)
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

    body = (home / ".claude/skills/stablemate-db/SKILL.md").read_text(encoding="utf-8")
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

    text = (home / ".claude/skills/stablemate-db/SKILL.md").read_text(encoding="utf-8")
    assert "farrier install --user" in text
    assert "make agent-install" not in text
    assert 'resolve: "farrier source ~/.claude/skills/stablemate-db/SKILL.md"' in text
