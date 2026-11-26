import json
import os
import subprocess
from pathlib import Path

import pytest

from _guard_bridge_support import add_guard
from home_install import add_search_server, add_skill_pair
from farrier.install import main
from farrier.plugin_build import TOOLS

PROFILES = (
    '[profiles.antigravity]\ncli = "antigravity"\n\n'
    '[profiles.antigravity.delegates.lookup]\nmodel = "flash"\n\n'
)


@pytest.fixture(autouse=True)
def _overlay(library: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FARRIER_LIBRARY_DIR", str(library))


def build(home: Path, library: Path, config: str, out: Path, version: str = "1.2.3") -> int:
    (home.parent / "config.toml").write_text(config, encoding="utf-8")
    return main(
        ["plugin", "build", "--harness", "antigravity", "--out", str(out), "--version", version]
    )


def files(out: Path) -> dict[str, str]:
    return {
        path.relative_to(out).as_posix(): path.read_text(encoding="utf-8")
        for path in out.rglob("*")
        if path.is_file()
    }


def test_a_plugin_carries_the_skills_and_agents_under_its_manifest(
    home: Path, library: Path, tmp_path: Path
) -> None:
    add_skill_pair(library)
    config = PROFILES + (
        '[user_library.antigravity]\nskills = ["general/ship", "general/review"]\n'
        'agents = ["lookup"]\n'
    )
    out = tmp_path / "plugin"
    assert build(home, library, config, out) == 0
    built = files(out)
    assert json.loads(built["plugin.json"])["version"] == "1.2.3"
    assert built["skills/ship/SKILL.md"].startswith("---\nname: ship\n")
    assert "agents/lookup.md" in built
    assert not any(str(tmp_path) in text for text in built.values())


def test_a_guard_runs_from_the_plugin_folder_and_denies(
    home: Path, library: Path, tmp_path: Path
) -> None:
    add_guard(library, "stub", "echo no sleeping >&2\nexit 2\n")
    out = tmp_path / "plugin"
    assert build(home, library, '[user_library.antigravity]\nhooks = ["stub"]\n', out) == 0
    document = json.loads((out / "hooks.json").read_text(encoding="utf-8"))
    (group,) = document["farrier-guards"]["PreToolUse"]
    command = group["hooks"][0]["command"]
    assert str(tmp_path) not in command
    payload = {
        "conversationId": "s",
        "toolCall": {"id": "t", "name": "run_command", "args": {"CommandLine": "sleep 5"}},
    }
    done = subprocess.run(
        ["sh", "-c", command],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=out,
        check=True,
        timeout=30,
    )
    assert json.loads(done.stdout) == {"decision": "deny", "reason": "no sleeping"}


def test_a_guard_that_runs_a_stablemate_tool_runs_its_launcher(
    home: Path, library: Path, tmp_path: Path
) -> None:
    folder = library / "library" / "hooks" / "vault"
    folder.mkdir(parents=True)
    (folder / "hook.yml").write_text(
        "command: saddlebag guard --hook\nwatches: [shell]\n", encoding="utf-8"
    )
    out = tmp_path / "plugin"
    assert build(home, library, '[user_library.antigravity]\nhooks = ["vault"]\n', out) == 0
    document = json.loads((out / "hooks.json").read_text(encoding="utf-8"))
    (group,) = document["farrier-guards"]["PreToolUse"]
    assert group["hooks"][0]["command"].endswith("'bin/saddlebag guard --hook'")


def test_a_tool_server_starts_through_the_plugin_launcher(
    home: Path, library: Path, tmp_path: Path
) -> None:
    add_search_server(library)
    out = tmp_path / "plugin"
    assert build(home, library, '[user_library.antigravity]\nmcp = ["search"]\n', out) == 0
    servers = json.loads((out / "mcp_config.json").read_text(encoding="utf-8"))
    assert servers == {
        "mcpServers": {"search": {"command": "sh", "args": ["${PLUGIN_ROOT}/bin/ostler", "mcp"]}}
    }


def test_every_tool_has_a_launcher_pinned_to_the_plugin_version(
    home: Path, library: Path, tmp_path: Path
) -> None:
    add_search_server(library)
    out = tmp_path / "plugin"
    assert build(home, library, '[user_library.antigravity]\nmcp = ["search"]\n', out) == 0
    launchers = sorted((out / "bin").iterdir())
    assert [path.name for path in launchers] == sorted(TOOLS)
    for path in launchers:
        assert os.access(path, os.X_OK)
        assert f'uvx --from "stablemate==1.2.3" {path.name} "$@"' in path.read_text()


def test_a_skill_longer_than_antigravity_loads_is_refused(
    home: Path, library: Path, tmp_path: Path
) -> None:
    skills = library / "library" / "skills" / "general"
    skills.mkdir(parents=True)
    (skills / "long.md").write_text(
        "---\nname: long\ndescription: Long.\n---\n\n" + "word " * 5200, encoding="utf-8"
    )
    with pytest.raises(SystemExit, match=r"first 24 KB.*skills/long/SKILL.md"):
        build(home, library, '[user_library.antigravity]\nskills = ["general/long"]\n', tmp_path / "p")
    assert not (tmp_path / "p").exists()


def test_a_config_without_an_antigravity_table_is_refused(
    home: Path, library: Path, tmp_path: Path
) -> None:
    add_skill_pair(library)
    with pytest.raises(SystemExit, match=r"no \[user_library.antigravity\] table"):
        build(home, library, '[user_library.claude]\nskills = ["general/review"]\n', tmp_path / "p")


def test_a_folder_holding_other_files_is_left_alone(
    home: Path, library: Path, tmp_path: Path
) -> None:
    add_search_server(library)
    out = tmp_path / "plugin"
    out.mkdir()
    (out / "notes.md").write_text("mine", encoding="utf-8")
    with pytest.raises(SystemExit, match="no plugin.json"):
        build(home, library, '[user_library.antigravity]\nmcp = ["search"]\n', out)
    assert (out / "notes.md").read_text(encoding="utf-8") == "mine"


def test_a_rebuild_drops_what_the_previous_plugin_carried(
    home: Path, library: Path, tmp_path: Path
) -> None:
    add_skill_pair(library)
    out = tmp_path / "plugin"
    both = '[user_library.antigravity]\nskills = ["general/ship", "general/review"]\n'
    assert build(home, library, both, out) == 0
    one = '[user_library.antigravity]\nskills = ["general/review"]\n'
    assert build(home, library, one, out, version="1.2.4") == 0
    assert not (out / "skills/ship").exists()
    assert json.loads((out / "plugin.json").read_text())["version"] == "1.2.4"
