"""Guards installed from one library record into Claude's settings and Codex's guard file."""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from farrier.home_guards import approval_keys
from farrier.install import main

SETTINGS: dict[str, Any] = {"model": "opus", "hooks": {"Stop": [{"hooks": []}]}}
BOTH = (
    '[user_library.claude]\nhooks = ["comments", "secrets", "timeouts"]\n\n'
    '[user_library.codex]\nhooks = ["comments", "secrets", "timeouts"]\n'
)
CODEX_ONLY = '[user_library.codex]\nhooks = ["comments"]\n'


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "agents"
    guards = root / "library" / "hooks"
    (root / "packs").mkdir(parents=True)
    records = {
        "comments": "command: python3 {dir}/check.py --hook\nwatches: [edit, shell]\ntimeout: 10\nstatus: Checking\n",
        "secrets": "command: /bin/guard --hook\nwatches: [read, search, shell]\n",
        "timeouts": 'command: "{dir}/check.sh"\nwatches: [shell]\nnot_on: [codex]\n',
    }
    for name, record in records.items():
        (guards / name).mkdir(parents=True)
        (guards / name / "hook.yml").write_text(record, encoding="utf-8")
    (guards / "comments" / "check.py").write_text("print('guard')\n", encoding="utf-8")
    (guards / "comments" / "tests").mkdir()
    (guards / "comments" / "tests" / "test_check.py").write_text("x = 1\n", encoding="utf-8")
    script = guards / "timeouts" / "check.sh"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    return root


@pytest.fixture
def home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".codex").mkdir()
    (home / ".claude" / "settings.json").write_text(json.dumps(SETTINGS, indent=2), encoding="utf-8")
    return home


def configure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    config = tmp_path / "stablemate.toml"
    config.write_text(f"config_version = 1\n\n{body}", encoding="utf-8")
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))


def run(home: Path, library: Path, *extra: str) -> int:
    return main(["install", "--user", "--home", str(home), "--library", str(library), *extra])


def groups(path: Path) -> list[dict]:
    return json.loads(path.read_text())["hooks"]["PreToolUse"]


def claude_groups(home: Path) -> list[dict]:
    return groups(home / ".claude" / "settings.json")


def codex_groups(home: Path) -> list[dict]:
    return groups(home / ".codex" / "hooks.json")


def approve(home: Path) -> None:
    keys = approval_keys(home / ".codex" / "hooks.json")
    rows = "".join(f'[hooks.state."{key}"]\ntrusted_hash = "sha256:x"\n' for key in keys.values())
    (home / ".codex" / "config.toml").write_text(rows, encoding="utf-8")


def test_each_harness_gets_its_own_tool_names_from_one_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, BOTH)

    assert run(home, library) == 0

    folder = home / ".agents" / "hooks"
    assert [group["matcher"] for group in claude_groups(home)] == [
        "Write|Edit|MultiEdit|Bash",
        "Read|Grep|Bash",
        "Bash",
    ]
    assert [group["matcher"] for group in codex_groups(home)] == ["apply_patch|Bash", "Bash"]
    assert claude_groups(home)[0]["hooks"] == [
        {
            "type": "command",
            "command": f"python3 {folder}/comments/check.py --hook",
            "timeout": 10,
            "statusMessage": "Checking",
        }
    ]


def test_settings_outside_the_guards_survive_and_a_guard_joins_the_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    settings = home / ".claude" / "settings.json"
    mine = {"matcher": "Bash", "hooks": [{"type": "command", "command": "mine"}]}
    settings.write_text(
        json.dumps({**SETTINGS, "hooks": {**SETTINGS["hooks"], "PreToolUse": [mine]}}),
        encoding="utf-8",
    )
    configure(tmp_path, monkeypatch, BOTH)

    assert run(home, library) == 0

    written = json.loads(settings.read_text())
    assert written["model"] == "opus"
    assert written["hooks"]["Stop"] == SETTINGS["hooks"]["Stop"]
    assert written["hooks"]["PreToolUse"][0] == mine
    assert len(written["hooks"]["PreToolUse"]) == 4


def test_scripts_install_beside_their_record_and_tests_stay_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, BOTH)

    assert run(home, library) == 0

    folder = home / ".agents" / "hooks"
    assert (folder / "comments" / "check.py").read_text() == "print('guard')\n"
    assert os.access(folder / "timeouts" / "check.sh", os.X_OK)
    assert not (folder / "comments" / "tests").exists()


def test_a_guard_the_record_excepts_is_left_out_with_a_note(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    home: Path,
    library: Path,
) -> None:
    configure(tmp_path, monkeypatch, BOTH)

    assert run(home, library) == 0

    commands = [hook["command"] for group in codex_groups(home) for hook in group["hooks"]]
    assert not any("timeouts" in command for command in commands)
    assert "Left out on codex: guard timeouts" in capsys.readouterr().out


def test_a_guard_excepted_everywhere_installs_no_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, '[user_library.codex]\nhooks = ["timeouts"]\n')

    assert run(home, library) == 0

    assert not (home / ".agents" / "hooks" / "timeouts").exists()


def test_the_check_names_each_unapproved_codex_guard_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    home: Path,
    library: Path,
) -> None:
    configure(tmp_path, monkeypatch, BOTH)
    assert run(home, library) == 0
    capsys.readouterr()
    before = (home / ".codex" / "hooks.json").read_bytes()

    assert run(home, library, "--check") == 1

    out = capsys.readouterr().out
    assert "pending approval: Codex skips guard comments" in out
    assert "pending approval: Codex skips guard secrets" in out
    assert "timeouts" not in out
    assert "Farrier never approves" in out
    assert (home / ".codex" / "hooks.json").read_bytes() == before
    assert not (home / ".codex" / "config.toml").exists()


def test_the_check_passes_once_codex_records_the_approvals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, BOTH)
    assert run(home, library) == 0

    approve(home)

    assert run(home, library, "--check") == 0


def test_install_reminds_only_when_a_codex_guard_moved_and_never_grants_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    home: Path,
    library: Path,
) -> None:
    configure(tmp_path, monkeypatch, CODEX_ONLY)

    assert run(home, library) == 0
    assert "Codex skips a new or changed guard" in capsys.readouterr().out
    assert not (home / ".codex" / "config.toml").exists()

    assert run(home, library) == 0
    assert "Codex skips a new or changed guard" not in capsys.readouterr().out


def test_a_foreign_group_running_the_same_command_stops_the_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    home: Path,
    library: Path,
) -> None:
    foreign = {"matcher": "Read", "hooks": [{"type": "command", "command": "/bin/guard --hook"}]}
    (home / ".codex" / "hooks.json").write_text(
        json.dumps({"hooks": {"PreToolUse": [foreign]}}), encoding="utf-8"
    )
    configure(tmp_path, monkeypatch, '[user_library.codex]\nhooks = ["secrets"]\n')

    with pytest.raises(SystemExit, match="will not overwrite"):
        run(home, library)

    assert codex_groups(home) == [foreign]


def test_a_dropped_guard_leaves_and_takes_only_its_own_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, '[user_library.claude]\nhooks = ["secrets"]\n')
    assert run(home, library) == 0
    assert len(claude_groups(home)) == 1

    configure(tmp_path, monkeypatch, '[user_library.claude]\nskills = []\nmcp = []\nhooks = ["comments"]\n')
    assert run(home, library) == 0

    assert [group["matcher"] for group in claude_groups(home)] == ["Write|Edit|MultiEdit|Bash"]
    assert json.loads((home / ".claude" / "settings.json").read_text())["model"] == "opus"


def test_a_dropped_guard_takes_its_installed_folder_with_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, CODEX_ONLY)
    assert run(home, library) == 0
    assert (home / ".agents" / "hooks" / "comments" / "check.py").exists()

    configure(tmp_path, monkeypatch, '[user_library.codex]\nhooks = ["secrets"]\n')
    assert run(home, library) == 0

    assert not (home / ".agents" / "hooks" / "comments").exists()
    assert [group["matcher"] for group in codex_groups(home)] == ["Bash"]


def test_a_library_change_shows_as_drift_and_a_second_install_settles_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    home: Path,
    library: Path,
) -> None:
    configure(tmp_path, monkeypatch, '[user_library.claude]\nhooks = ["comments"]\n')
    assert run(home, library) == 0
    assert run(home, library, "--check") == 0
    record = library / "library" / "hooks" / "comments" / "hook.yml"
    record.write_text(record.read_text().replace("timeout: 10", "timeout: 20"), encoding="utf-8")

    assert run(home, library, "--check") == 1
    assert "changed entry" in capsys.readouterr().out

    assert run(home, library) == 0
    assert claude_groups(home)[0]["hooks"][0]["timeout"] == 20
    assert run(home, library, "--check") == 0


def test_a_pack_brings_its_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    (library / "packs" / "safe.yml").write_text("hooks: [secrets]\n", encoding="utf-8")
    configure(tmp_path, monkeypatch, '[user_library.codex]\npacks = ["safe"]\n')

    assert run(home, library) == 0

    assert [group["matcher"] for group in codex_groups(home)] == ["Bash"]


def test_a_harness_with_no_guard_file_refuses_guards_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, '[user_library.copilot]\nhooks = ["secrets"]\n')

    with pytest.raises(SystemExit, match="only for claude, codex"):
        run(home, library)


def test_an_unknown_guard_lists_the_ones_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, '[user_library.codex]\nhooks = ["nope"]\n')

    with pytest.raises(SystemExit, match="comments, secrets, timeouts"):
        run(home, library)


def test_a_record_with_an_unknown_key_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    record = library / "library" / "hooks" / "secrets" / "hook.yml"
    record.write_text(record.read_text() + "tools: [Bash]\n", encoding="utf-8")
    configure(tmp_path, monkeypatch, '[user_library.codex]\nhooks = ["secrets"]\n')

    with pytest.raises(SystemExit, match="unknown keys: tools"):
        run(home, library)


def test_a_guard_watching_nothing_a_harness_has_is_refused_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    (library / "library" / "hooks" / "reads").mkdir()
    (library / "library" / "hooks" / "reads" / "hook.yml").write_text(
        "command: /bin/reads\nwatches: [read]\n", encoding="utf-8"
    )
    configure(tmp_path, monkeypatch, '[user_library.codex]\nhooks = ["reads"]\n')

    with pytest.raises(SystemExit, match="'reads' watches read, which codex"):
        run(home, library)
