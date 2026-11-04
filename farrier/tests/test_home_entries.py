"""MCP servers merged into files Claude and Codex also write."""

import json
import tomllib
from pathlib import Path

import pytest

from farrier._vendor.stablemate_core.schema.base import stray_keys
from farrier.home_entries import LEDGER
from farrier.install import main
from farrier.manifest import as_manifest

CODEX_CONFIG = """# my settings
model = "gpt"  # keep this comment

[mcp_servers.node_repl]
command = "node"  # desktop app owns this

[projects."/tmp/x"]
trust_level = "trusted"
"""
CLAUDE_STATE = {"numStartups": 7, "projects": {"/tmp/x": {"mcpServers": {}}}}
BOTH = (
    '[user_library.claude]\nmcp = ["playwright"]\n\n'
    '[user_library.codex]\nmcp = ["playwright"]\n'
)


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "agents"
    servers = root / "library" / "mcp"
    servers.mkdir(parents=True)
    (root / "packs").mkdir()
    (servers / "playwright.yml").write_text(
        'command: npx\nargs: ["@playwright/mcp"]\nenv:\n  MODE: headless\n', encoding="utf-8"
    )
    return root


@pytest.fixture
def home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "config.toml").write_text(CODEX_CONFIG, encoding="utf-8")
    (home / ".claude.json").write_text(json.dumps(CLAUDE_STATE, indent=2), encoding="utf-8")
    (home / ".claude.json").chmod(0o600)
    return home


def configure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    config = tmp_path / "stablemate.toml"
    config.write_text(f"config_version = 1\n\n{body}", encoding="utf-8")
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))


def run(home: Path, library: Path, *extra: str) -> int:
    return main(["install", "--user", "--home", str(home), "--library", str(library), *extra])


def codex_servers(home: Path) -> dict:
    return tomllib.loads((home / ".codex" / "config.toml").read_text())["mcp_servers"]


def claude_servers(home: Path) -> dict:
    return json.loads((home / ".claude.json").read_text()).get("mcpServers", {})


def test_both_harnesses_get_the_server_and_everything_else_survives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, BOTH)

    assert run(home, library) == 0

    assert claude_servers(home)["playwright"] == {
        "type": "stdio",
        "command": "npx",
        "args": ["@playwright/mcp"],
        "env": {"MODE": "headless"},
    }
    assert codex_servers(home)["playwright"]["env"] == {"MODE": "headless"}
    text = (home / ".codex" / "config.toml").read_text()
    assert text.startswith(CODEX_CONFIG.split("[projects")[0])
    assert '[projects."/tmp/x"]\ntrust_level = "trusted"' in text
    state = json.loads((home / ".claude.json").read_text())
    assert state["numStartups"] == 7 and state["projects"] == CLAUDE_STATE["projects"]
    assert (home / ".claude.json").stat().st_mode & 0o777 == 0o600
    assert run(home, library, "--check") == 0


def test_a_foreign_value_stops_the_install_before_anything_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, BOTH)
    (home / ".claude.json").write_text(
        json.dumps({"mcpServers": {"playwright": {"command": "mine"}}}), encoding="utf-8"
    )
    before = (home / ".claude.json").read_text()
    codex_before = (home / ".codex" / "config.toml").read_text()

    with pytest.raises(SystemExit, match=r"\.claude\.json mcpServers\.playwright"):
        run(home, library)

    assert (home / ".claude.json").read_text() == before
    assert (home / ".codex" / "config.toml").read_text() == codex_before
    assert not (home / LEDGER).exists()


def test_removing_a_server_deletes_only_ours_and_restores_the_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, BOTH)
    run(home, library)
    (library / "library" / "skills").mkdir(parents=True)
    (library / "library" / "skills" / "a.md").write_text(
        "---\nname: a\ndescription: A.\n---\n\nBody.\n", encoding="utf-8"
    )
    configure(tmp_path, monkeypatch, '[user_library.claude]\nskills = ["a"]\n')

    assert run(home, library, "--check") == 1
    assert run(home, library) == 0

    assert "playwright" not in claude_servers(home)
    assert list(codex_servers(home)) == ["node_repl"]
    assert (home / ".codex" / "config.toml").read_text() == CODEX_CONFIG
    assert run(home, library, "--check") == 0


def test_a_matching_entry_it_did_not_install_is_never_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, BOTH)
    server = {
        "type": "stdio",
        "command": "npx",
        "args": ["@playwright/mcp"],
        "env": {"MODE": "headless"},
    }
    (home / ".claude.json").write_text(
        json.dumps({"mcpServers": {"playwright": server}}), encoding="utf-8"
    )

    assert run(home, library) == 0
    assert (home / LEDGER).exists()
    assert "playwright" not in json.loads((home / LEDGER).read_text()).get(".claude.json", {}).get(
        "mcpServers", []
    )

    (library / "library" / "skills").mkdir(parents=True)
    (library / "library" / "skills" / "a.md").write_text(
        "---\nname: a\ndescription: A.\n---\n\nBody.\n", encoding="utf-8"
    )
    configure(tmp_path, monkeypatch, '[user_library.claude]\nskills = ["a"]\n')
    assert run(home, library) == 0

    assert claude_servers(home) == {"playwright": server}


def test_check_reports_an_edit_by_name_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    home: Path,
    library: Path,
) -> None:
    configure(tmp_path, monkeypatch, BOTH)
    run(home, library)
    state = json.loads((home / ".claude.json").read_text())
    state["mcpServers"]["playwright"]["env"]["MODE"] = "secret-value"
    (home / ".claude.json").write_text(json.dumps(state), encoding="utf-8")
    before = (home / ".claude.json").read_text()

    capsys.readouterr()
    assert run(home, library, "--check") == 1

    out = capsys.readouterr().out
    assert "changed entry: .claude.json mcpServers.playwright" in out
    assert "secret-value" not in out
    assert (home / ".claude.json").read_text() == before


def test_install_restores_an_edited_entry_it_owns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, BOTH)
    run(home, library)
    state = json.loads((home / ".claude.json").read_text())
    state["mcpServers"]["playwright"]["command"] = "edited"
    (home / ".claude.json").write_text(json.dumps(state), encoding="utf-8")

    assert run(home, library) == 0

    assert claude_servers(home)["playwright"]["command"] == "npx"


def test_a_pack_carries_the_server_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    (library / "packs" / "mine.yml").write_text("mcp: [playwright]\n", encoding="utf-8")
    configure(tmp_path, monkeypatch, '[user_library.codex]\npacks = ["mine"]\n')

    assert run(home, library) == 0

    assert "playwright" in codex_servers(home)


def test_copilot_takes_no_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, '[user_library.copilot]\nmcp = ["playwright"]\n')
    with pytest.raises(SystemExit, match="only for claude, codex"):
        run(home, library)


def test_an_unknown_server_is_refused_with_what_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, '[user_library.codex]\nmcp = ["nope"]\n')
    with pytest.raises(SystemExit, match="unknown MCP server 'nope'. Available: playwright"):
        run(home, library)


def test_a_record_with_an_unknown_key_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    (library / "library" / "mcp" / "bad.yml").write_text("command: x\nurl: y\n", encoding="utf-8")
    configure(tmp_path, monkeypatch, '[user_library.codex]\nmcp = ["bad"]\n')
    with pytest.raises(SystemExit, match="unknown keys: url"):
        run(home, library)


def test_an_unparseable_config_stops_the_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    configure(tmp_path, monkeypatch, BOTH)
    (home / ".codex" / "config.toml").write_text("not [ toml", encoding="utf-8")
    with pytest.raises(SystemExit, match="cannot parse"):
        run(home, library)
    assert (home / ".codex" / "config.toml").read_text() == "not [ toml"


def test_a_repo_manifest_does_not_declare_servers() -> None:
    manifest = as_manifest({"agents": {"claude": True}, "mcp": ["playwright"]})

    assert [stray.path for stray in stray_keys(manifest)] == ["mcp"]


def test_a_home_with_no_servers_gets_no_ledger_and_no_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, library: Path
) -> None:
    (library / "library" / "skills").mkdir(parents=True)
    (library / "library" / "skills" / "a.md").write_text(
        "---\nname: a\ndescription: A.\n---\n\nBody.\n", encoding="utf-8"
    )
    configure(tmp_path, monkeypatch, '[user_library.claude]\nskills = ["a"]\n')
    home = tmp_path / "bare"

    assert run(home, library) == 0

    assert not (home / LEDGER).exists()
    assert not (home / ".claude.json").exists()


def test_a_config_without_the_table_returns_to_its_bytes_after_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, library: Path
) -> None:
    plain = '# only a comment\nmodel = "gpt"\n'
    (home / ".codex" / "config.toml").write_text(plain, encoding="utf-8")
    configure(tmp_path, monkeypatch, '[user_library.codex]\nmcp = ["playwright"]\n')
    run(home, library)
    assert "playwright" in codex_servers(home)
    (library / "library" / "skills").mkdir(parents=True)
    (library / "library" / "skills" / "a.md").write_text(
        "---\nname: a\ndescription: A.\n---\n\nBody.\n", encoding="utf-8"
    )
    configure(tmp_path, monkeypatch, '[user_library.claude]\nskills = ["a"]\n')

    assert run(home, library) == 0

    assert (home / ".codex" / "config.toml").read_text() == plain
