"""Settings files merged key by key into a harness's home settings."""

import json
import tomllib
from pathlib import Path

import pytest

from farrier.home_entries import LEDGER
from home_install import configure, run

BASE = {"model": "sonnet", "permissions": {"deny": ["NotebookEdit"]}, "disableBundledSkills": True}
USER_SETTINGS = {"theme": "dark", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "x"}]}]}}


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "agents"
    settings = root / "library" / "settings"
    settings.mkdir(parents=True)
    (root / "packs").mkdir()
    (settings / "base.json").write_text(json.dumps(BASE), encoding="utf-8")
    return root


@pytest.fixture
def home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text(json.dumps(USER_SETTINGS, indent=2) + "\n")
    return home


def claude_settings(home: Path) -> dict:
    return json.loads((home / ".claude" / "settings.json").read_text())


def write_settings(library: Path, name: str, value: object) -> None:
    (library / "library" / "settings" / f"{name}.json").write_text(json.dumps(value))


def test_each_key_lands_and_the_keys_it_does_not_name_survive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, '[user_library.claude]\nsettings = ["base"]\n')

    assert run(home, library) == 0

    assert claude_settings(home) == {**USER_SETTINGS, **BASE}
    ledger = json.loads((home / LEDGER).read_text())
    assert sorted(ledger[".claude/settings.json"]["."]) == sorted(BASE)


def test_a_key_dropped_from_the_file_leaves_the_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, '[user_library.claude]\nsettings = ["base"]\n')
    run(home, library)
    write_settings(library, "base", {"model": "sonnet"})

    assert run(home, library) == 0

    assert claude_settings(home) == {**USER_SETTINGS, "model": "sonnet"}


def test_an_edit_in_the_home_is_reported_then_restored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path, capsys
) -> None:
    configure(tmp_path, monkeypatch, '[user_library.claude]\nsettings = ["base"]\n')
    run(home, library)
    edited = {**claude_settings(home), "model": "opus"}
    (home / ".claude" / "settings.json").write_text(json.dumps(edited))

    assert run(home, library, "--check") == 1
    assert "changed entry: .claude/settings.json ..model" in capsys.readouterr().out

    assert run(home, library) == 0
    assert claude_settings(home)["model"] == "sonnet"


def test_a_value_it_did_not_install_stops_the_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, '[user_library.claude]\nsettings = ["base"]\n')
    mine = {**USER_SETTINGS, "model": "opus"}
    (home / ".claude" / "settings.json").write_text(json.dumps(mine))

    with pytest.raises(SystemExit, match="will not overwrite"):
        run(home, library)

    assert claude_settings(home) == mine


def test_a_file_that_sets_hooks_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    write_settings(library, "hooky", {"hooks": {}})
    configure(tmp_path, monkeypatch, '[user_library.claude]\nsettings = ["hooky"]\n')

    with pytest.raises(SystemExit, match="sets `hooks`, which farrier writes from library/hooks"):
        run(home, library)


def test_two_files_that_set_one_key_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    write_settings(library, "other", {"model": "opus"})
    configure(tmp_path, monkeypatch, '[user_library.claude]\nsettings = ["base", "other"]\n')

    with pytest.raises(SystemExit, match="'base' and 'other' both set `model`"):
        run(home, library)


def test_a_file_that_is_not_an_object_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    write_settings(library, "list", ["model"])
    configure(tmp_path, monkeypatch, '[user_library.claude]\nsettings = ["list"]\n')

    with pytest.raises(SystemExit, match="must hold one JSON object"):
        run(home, library)


def test_an_unknown_file_is_refused_with_what_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, '[user_library.claude]\nsettings = ["nope"]\n')

    with pytest.raises(SystemExit, match="unknown settings file 'nope'. Available: base"):
        run(home, library)


def test_codex_settings_land_in_its_toml_beside_what_the_person_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, library: Path
) -> None:
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    mine = '# mine\napproval_policy = "on-request"\n\n[projects."/p"]\ntrust_level = "trusted"\n'
    (home / ".codex" / "config.toml").write_text(mine)
    write_settings(library, "codex", {"model": "gpt", "features": {"apps": False}})
    configure(tmp_path, monkeypatch, '[user_library.codex]\nsettings = ["codex"]\n')

    assert run(home, library) == 0
    config = tomllib.loads((home / ".codex" / "config.toml").read_text())
    assert config == {
        "approval_policy": "on-request",
        "model": "gpt",
        "projects": {"/p": {"trust_level": "trusted"}},
        "features": {"apps": False},
    }
    assert (home / ".codex" / "config.toml").read_text().startswith("# mine\n")

    write_settings(library, "codex", {"model": "gpt"})
    assert run(home, library) == 0
    assert "features" not in tomllib.loads((home / ".codex" / "config.toml").read_text())


def test_opencode_takes_no_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, '[user_library.opencode]\nsettings = ["base"]\n')

    with pytest.raises(SystemExit, match="merges them only for claude, codex, copilot"):
        run(home, library)
