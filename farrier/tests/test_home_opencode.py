"""OpenCode's home: rules, MCP servers, helper agents and guards reached through a generated plugin."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from farrier.install import main

PROFILES = (
    '[profiles.opencode]\ncli = "opencode"\n\n'
    '[profiles.opencode.delegates.lookup]\nmodel = "kimi/k3"\neffort = "low"\n\n'
    '[profiles.opencode.delegates.worker]\nmodel = "kimi/k3-pro"\neffort = "medium"\n\n'
)
AGENTS = '[user_library.opencode]\nagents = ["lookup", "worker"]\n'
USER_CONFIG = '{\n  // my settings\n  "model": "kimi/k3",\n  "mcp": {"playwright": {"type": "local", "command": ["npx"]},},\n}\n'
NODE = shutil.which("node")
CALL_BRIDGE = """
const { FarrierGuards } = await import(process.argv[2])
const hooks = await FarrierGuards({ directory: "/project" })
const [tool, args] = JSON.parse(process.argv[3])
try {
  await hooks["tool.execute.before"]({ tool, sessionID: "s" }, { args })
  console.log("allowed")
} catch (error) {
  console.log("denied: " + error.message)
}
"""


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "agents"
    agents = root / "library" / "agents"
    agents.mkdir(parents=True)
    (root / "packs").mkdir()
    (agents / "lookup.md").write_text(
        '---\ndescription: "Read-only lookup."\nread_only: true\n---\n\nYou answer one question.\n',
        encoding="utf-8",
    )
    (agents / "worker.md").write_text(
        "---\ndescription: Carries out a plan.\n---\n\nYou carry out a plan.\n", encoding="utf-8"
    )
    return root


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    monkeypatch.setenv("STABLEMATE_FETCH_BASE", "0")
    monkeypatch.setenv("STABLEMATE_CONFIG", str(tmp_path / "config.toml"))
    return path


def install(home: Path, library: Path, config: str, *flags: str) -> int:
    (home.parent / "config.toml").write_text(config, encoding="utf-8")
    return main(["--user", "--home", str(home), "--library", str(library), *flags])


def add_server(library: Path) -> str:
    servers = library / "library" / "mcp"
    servers.mkdir()
    (servers / "search.yml").write_text("command: ostler\nargs: [mcp]\n", encoding="utf-8")
    return '[user_library.opencode]\nmcp = ["search"]\n'


def add_guard(library: Path, name: str, script: str, watches: str = "[shell, edit]") -> None:
    folder = library / "library" / "hooks" / name
    folder.mkdir(parents=True)
    (folder / "hook.yml").write_text(
        f"command: sh {{dir}}/check.sh\nwatches: {watches}\ntimeout: 5\n", encoding="utf-8"
    )
    (folder / "check.sh").write_text(script, encoding="utf-8")


def bridge(home: Path) -> Path:
    return home / ".config/opencode/plugins/farrier-guards.ts"


def call_bridge(home: Path, tool: str, args: dict) -> str:
    """What the installed plugin decides on one tool call, run as OpenCode's runtime would load it."""
    assert NODE is not None
    module = home.parent / "bridge.mjs"
    module.write_text(bridge(home).read_text(encoding="utf-8"), encoding="utf-8")
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", CALL_BRIDGE, "bridge", str(module), json.dumps([tool, args])],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return done.stdout.strip()


def test_one_agent_record_lands_with_the_opencode_model_and_no_provider_key(
    home: Path, library: Path
) -> None:
    assert install(home, library, PROFILES + AGENTS) == 0
    lookup = (home / ".config/opencode/agents/lookup.md").read_text(encoding="utf-8")
    head = yaml.safe_load(lookup.split("---\n")[1])
    assert head == {
        "description": "Read-only lookup.",
        "mode": "subagent",
        "model": "kimi/k3",
        "variant": "minimal",
        "permission": {"edit": "deny"},
    }
    assert lookup.endswith("You answer one question.\n")
    worker = yaml.safe_load((home / ".config/opencode/agents/worker.md").read_text(encoding="utf-8").split("---\n")[1])
    assert "variant" not in worker
    assert "permission" not in worker


def test_the_rules_land_where_opencode_reads_them(home: Path, library: Path) -> None:
    roots = library / "library" / "roots"
    roots.mkdir()
    (roots / "rules.md").write_text('---\ndescription: "Rules."\n---\n\nSay hello.\n', encoding="utf-8")
    assert install(home, library, '[user_library.opencode]\nroots = ["rules"]\n') == 0
    assert "Say hello." in (home / ".config/opencode/AGENTS.md").read_text(encoding="utf-8")


def test_servers_land_in_their_own_file_and_the_users_config_keeps_every_byte(
    home: Path, library: Path
) -> None:
    mine = home / ".config/opencode/opencode.jsonc"
    mine.parent.mkdir(parents=True)
    mine.write_text(USER_CONFIG, encoding="utf-8")
    config = add_server(library)
    assert install(home, library, config) == 0
    assert mine.read_text(encoding="utf-8") == USER_CONFIG
    written = json.loads((home / ".config/opencode/opencode.json").read_text(encoding="utf-8"))
    assert written["mcp"] == {"search": {"type": "local", "command": ["ostler", "mcp"]}}
    assert install(home, library, config, "--check") == 0


def test_a_server_the_users_config_spells_differently_stops_the_install(
    home: Path, library: Path
) -> None:
    mine = home / ".config/opencode/opencode.jsonc"
    mine.parent.mkdir(parents=True)
    mine.write_text(USER_CONFIG.replace('"playwright"', '"search"'), encoding="utf-8")
    with pytest.raises(SystemExit, match="search"):
        install(home, library, add_server(library))
    assert not (home / ".config/opencode/opencode.json").exists()


def test_opencode_takes_no_skills_because_it_reads_another_harness_folder(
    home: Path, library: Path
) -> None:
    skill = library / "library" / "skills" / "note"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: note\ndescription: d\n---\n\nbody\n", encoding="utf-8")
    assert install(home, library, PROFILES + '[user_library.opencode]\nskills = ["note"]\nagents = ["lookup"]\n') == 0
    assert not (home / ".config/opencode/skills").exists()
    assert (home / ".config/opencode/agents/lookup.md").is_file()


@pytest.mark.skipif(NODE is None, reason="needs node to load the plugin")
@pytest.mark.parametrize(
    ("script", "expected"),
    [
        pytest.param("cat >/dev/null; exit 0\n", "allowed", id="silent-allows"),
        pytest.param("cat >/dev/null; echo refused >&2; exit 2\n", "denied: refused", id="exit-2-denies"),
        pytest.param(
            """cat >/dev/null; printf '{"hookSpecificOutput":{"permissionDecision":"deny","permissionDecisionReason":"no"}}'\n""",
            "denied: no",
            id="json-denies",
        ),
        pytest.param("cat >/dev/null; exit 1\n", "allowed", id="crash-allows"),
    ],
)
def test_the_bridge_reads_each_verdict_as_a_harness_does(
    home: Path, library: Path, script: str, expected: str
) -> None:
    add_guard(library, "stub", script)
    assert install(home, library, '[user_library.opencode]\nhooks = ["stub"]\n') == 0
    assert call_bridge(home, "bash", {"command": "ls"}) == expected


@pytest.mark.skipif(NODE is None, reason="needs node to load the plugin")
@pytest.mark.parametrize(
    ("tool", "args", "claude_name", "field", "value"),
    [
        ("bash", {"command": "ls", "timeout": 5}, "Bash", "command", "ls"),
        ("edit", {"filePath": "/a.py", "oldString": "x", "newString": "y"}, "Edit", "new_string", "y"),
        ("write", {"filePath": "/a.py", "content": "z"}, "Write", "file_path", "/a.py"),
        ("apply_patch", {"patchText": "*** Begin Patch"}, "apply_patch", "command", "*** Begin Patch"),
    ],
)
def test_the_bridge_hands_a_guard_the_call_in_claude_shape(
    home: Path, library: Path, tool: str, args: dict, claude_name: str, field: str, value: str
) -> None:
    seen = home.parent / "seen.json"
    add_guard(library, "stub", f"cat > {seen}\n")
    assert install(home, library, '[user_library.opencode]\nhooks = ["stub"]\n') == 0
    assert call_bridge(home, tool, args) == "allowed"
    call = json.loads(seen.read_text(encoding="utf-8"))
    assert call["tool_name"] == claude_name
    assert call["tool_input"][field] == value
    assert call["hook_event_name"] == "PreToolUse"
    assert call["cwd"] == "/project"


@pytest.mark.skipif(NODE is None, reason="needs node to load the plugin")
def test_a_guard_sees_only_the_tools_it_watches(home: Path, library: Path) -> None:
    add_guard(library, "stub", "cat >/dev/null; echo refused >&2; exit 2\n", watches="[shell]")
    assert install(home, library, '[user_library.opencode]\nhooks = ["stub"]\n') == 0
    assert call_bridge(home, "read", {"filePath": "/a.py"}) == "allowed"
    assert call_bridge(home, "bash", {"command": "ls"}) == "denied: refused"


def test_a_dropped_guard_takes_the_bridge_with_it_and_a_hand_written_plugin_survives(
    home: Path, library: Path
) -> None:
    add_guard(library, "stub", "exit 0\n")
    mine = home / ".config/opencode/plugins/mine.ts"
    mine.parent.mkdir(parents=True)
    mine.write_text("export const Mine = async () => ({})\n", encoding="utf-8")
    assert install(home, library, '[user_library.opencode]\nhooks = ["stub"]\n') == 0
    assert bridge(home).is_file()
    assert install(home, library, AGENTS + "\n" + PROFILES) == 0
    assert not bridge(home).exists()
    assert mine.is_file()


def test_a_hand_written_plugin_of_the_bridge_name_stops_the_install(home: Path, library: Path) -> None:
    add_guard(library, "stub", "exit 0\n")
    bridge(home).parent.mkdir(parents=True)
    bridge(home).write_text("export const Mine = async () => ({})\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="will not overwrite"):
        install(home, library, '[user_library.opencode]\nhooks = ["stub"]\n')
    assert "Mine" in bridge(home).read_text(encoding="utf-8")


def test_check_reports_a_stale_bridge_and_writes_nothing(
    home: Path, library: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_guard(library, "stub", "exit 0\n")
    config = '[user_library.opencode]\nhooks = ["stub"]\n'
    assert install(home, library, config) == 0
    assert install(home, library, config, "--check") == 0
    capsys.readouterr()
    before = bridge(home).read_text(encoding="utf-8")
    bridge(home).write_text(before.replace("spawn(", "spawned("), encoding="utf-8")
    edited = bridge(home).read_text(encoding="utf-8")
    assert install(home, library, config, "--check") == 1
    assert "farrier-guards.ts" in capsys.readouterr().out
    assert bridge(home).read_text(encoding="utf-8") == edited
