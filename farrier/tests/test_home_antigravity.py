"""Antigravity's home: skills, rules, MCP servers, settings, helper agents and guards reached through a bridge."""

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from _guard_bridge_support import add_guard, run_hook
from home_install import (
    add_prompt,
    add_search_server,
    add_settings,
    add_skill_pair,
    install,
    seed,
)
from farrier.antigravity_bridge import ANTIGRAVITY_BRIDGE, ANTIGRAVITY_TOOLS
from farrier._vendor.stablemate_core.harness import workhorse_harnesses

PROFILES = (
    '[profiles.antigravity]\ncli = "antigravity"\n\n'
    '[profiles.antigravity.delegates.lookup]\nmodel = "flash"\n\n'
    '[profiles.antigravity.delegates.worker]\nmodel = "claude-sonnet-5.5"\n\n'
)
AGENTS = '[user_library.antigravity]\nagents = ["lookup", "worker"]\n'
GUARD = '[user_library.antigravity]\nhooks = ["stub"]\n'


def hooks(home: Path) -> dict:
    document = json.loads(
        (home / ".gemini/config/hooks.json").read_text(encoding="utf-8")
    )
    return document["farrier-guards"]


def handler(home: Path, event: str) -> dict:
    (entry,) = hooks(home)[event]
    return entry if event == "Stop" else entry["hooks"][0]


def call(home: Path, event: str, payload: dict | str) -> dict | None:
    command = handler(home, event)["command"]
    if isinstance(payload, dict):
        return run_hook(command, payload)
    done = subprocess.run(
        ["sh", "-c", command],
        input=payload,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(done.stdout) if done.stdout.strip() else None


def tool_call(tool: str, args: dict) -> dict:
    return {
        "conversationId": "s",
        "cwd": "/project",
        "transcriptPath": "/brain/s/transcript_full.jsonl",
        "hookEventName": "PreToolUse",
        "toolCall": {"id": "t1", "name": tool, "args": args},
    }


def test_the_workhorse_offers_antigravity() -> None:
    assert "antigravity" in {spec.name for spec in workhorse_harnesses()}


def test_a_skill_lands_in_the_gemini_config_with_slash_references(
    home: Path, library: Path
) -> None:
    add_skill_pair(library)
    config = '[user_library.antigravity]\nskills = ["general/ship", "general/review"]\n'
    assert install(home, library, config) == 0
    shipped = (home / ".gemini/config/skills/ship/SKILL.md").read_text(encoding="utf-8")
    assert shipped.startswith("---\nname: ship\n")
    assert "Then /review." in shipped
    assert install(home, library, config, "--check") == 0


def test_the_rules_land_in_agents_md_and_never_in_gemini_md(
    home: Path, library: Path
) -> None:
    roots = library / "library" / "roots"
    roots.mkdir()
    (roots / "rules.md").write_text(
        '---\ndescription: "Rules."\n---\n\nSay hello.\n', encoding="utf-8"
    )
    assert (
        install(home, library, '[user_library.antigravity]\nroots = ["rules"]\n') == 0
    )
    assert "Say hello." in (home / ".gemini/config/AGENTS.md").read_text(
        encoding="utf-8"
    )
    assert not (home / ".gemini/GEMINI.md").exists()


def test_a_server_lands_in_the_mcp_file_and_the_operators_servers_stay(
    home: Path, library: Path
) -> None:
    add_search_server(library)
    mine = seed(
        home / ".gemini/config/mcp_config.json",
        '{"mcpServers": {"mine": {"command": "tool"}}}\n',
    )
    config = '[user_library.antigravity]\nmcp = ["search"]\n'
    assert install(home, library, config) == 0
    assert json.loads(mine.read_text(encoding="utf-8"))["mcpServers"] == {
        "mine": {"command": "tool"},
        "search": {"command": "ostler", "args": ["mcp"]},
    }
    assert install(home, library, config, "--check") == 0


def test_settings_merge_and_the_operators_keys_stay(home: Path, library: Path) -> None:
    add_settings(library, '{"banner": "never"}\n')
    mine = seed(home / ".gemini/antigravity-cli/settings.json", '{"theme": "dim"}\n')
    config = '[user_library.antigravity]\nsettings = ["prefs"]\n'
    assert install(home, library, config) == 0
    assert json.loads(mine.read_text(encoding="utf-8")) == {
        "theme": "dim",
        "banner": "never",
    }
    assert install(home, library, config, "--check") == 0


def test_a_settings_entry_with_hooks_is_refused_and_points_at_guards(
    home: Path, library: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    add_settings(library, '{"hooks": {}}\n')
    with pytest.raises(SystemExit) as refused:
        install(home, library, '[user_library.antigravity]\nsettings = ["prefs"]\n')
    assert "library/hooks guards" in str(refused.value)
    assert not (home / ".gemini/antigravity-cli/settings.json").exists()


def test_a_prompt_lands_as_a_skill_with_no_codex_policy_file(
    home: Path, library: Path
) -> None:
    add_prompt(library)
    config = '[user_library.antigravity]\nprompts = ["general/go"]\n'
    assert install(home, library, config) == 0
    folder = home / ".gemini/config/skills/go"
    skill = (folder / "SKILL.md").read_text(encoding="utf-8")
    assert "disable-model-invocation: true" in skill
    assert "Run `ship <arguments>`." in skill
    assert not (folder / "agents").exists()
    assert install(home, library, config, "--check") == 0


def test_each_agent_lands_inheriting_the_model_unless_it_names_flash_or_pro(
    home: Path, library: Path
) -> None:
    assert install(home, library, PROFILES + AGENTS) == 0
    lookup = (home / ".gemini/config/agents/lookup.md").read_text(encoding="utf-8")
    assert yaml.safe_load(lookup.split("---\n")[1]) == {
        "name": "lookup",
        "description": "Read-only lookup.",
        "tools": ["read_file", "run_command", "manage_task"],
        "model": "flash",
        "mainAgent": False,
        "subagent": True,
    }
    assert lookup.endswith("You answer one question.\n")
    worker = yaml.safe_load(
        (home / ".gemini/config/agents/worker.md")
        .read_text(encoding="utf-8")
        .split("---\n")[1]
    )
    assert worker["model"] == "inherit"
    assert worker["tools"] == ["read_file", "run_command", "manage_task", "edit_file", "write_file"]


def agent_head(home: Path, name: str) -> dict:
    text = (home / f".gemini/config/agents/{name}.md").read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---\n")[1])


def test_a_delegating_agent_is_a_main_agent_that_can_invoke_subagents(
    home: Path, library: Path
) -> None:
    (library / "library/agents/orchestrator.md").write_text(
        "---\ndescription: Coordinates.\nread_only: true\ndelegates: [lookup, worker]\n---\n\nYou coordinate.\n",
        encoding="utf-8",
    )
    config = (
        PROFILES
        + '[profiles.antigravity.delegates.orchestrator]\nmodel = "pro"\n\n'
        + '[user_library.antigravity]\nagents = ["orchestrator", "lookup"]\n'
    )
    assert install(home, library, config) == 0
    head = agent_head(home, "orchestrator")
    assert head["tools"][-1] == "invoke_subagent"
    assert (head["mainAgent"], head["subagent"]) == (True, False)
    assert "invoke_subagent" not in agent_head(home, "lookup")["tools"]


def test_an_agent_server_is_listed_inside_that_agent_only(
    home: Path, library: Path
) -> None:
    add_search_server(library)
    (library / "library/agents/browser.md").write_text(
        "---\ndescription: Browses.\nread_only: true\nmcp: [search]\nsession_mcp: [groom]\n---\n\nYou browse.\n",
        encoding="utf-8",
    )
    config = (
        PROFILES
        + '[profiles.antigravity.delegates.browser]\nmodel = "flash"\n\n'
        + '[user_library.antigravity]\nagents = ["browser", "worker"]\n'
    )
    assert install(home, library, config) == 0
    head = agent_head(home, "browser")
    assert head["mcpServers"] == [{"name": "search", "command": "ostler", "args": ["mcp"]}]
    assert head["inheritMcp"] is True
    assert "mcpServers" not in agent_head(home, "worker")
    assert "inheritMcp" not in agent_head(home, "worker")
    assert not (home / ".gemini/config/mcp_config.json").exists()


def test_a_guard_lands_as_hooks_json_and_a_bridge(home: Path, library: Path) -> None:
    add_guard(library, "stub", "exit 0\n")
    assert install(home, library, GUARD) == 0
    (group,) = hooks(home)["PreToolUse"]
    assert group["matcher"] == "|".join(
        [ANTIGRAVITY_TOOLS["shell"], ANTIGRAVITY_TOOLS["edit"]]
    )
    assert group["hooks"][0]["timeout"] == 5
    assert str(home / ".agents/hooks/stub") in group["hooks"][0]["command"]
    assert (home / ANTIGRAVITY_BRIDGE).is_file()
    assert install(home, library, GUARD, "--check") == 0


@pytest.mark.parametrize(
    ("script", "expected"),
    [
        pytest.param("cat >/dev/null; exit 0\n", None, id="silent-allows"),
        pytest.param(
            "cat >/dev/null; echo refused >&2; exit 2\n",
            {"decision": "deny", "reason": "refused"},
            id="exit-2-denies",
        ),
        pytest.param(
            """cat >/dev/null; printf '{"hookSpecificOutput":{"permissionDecision":"deny","permissionDecisionReason":"no"}}'\n""",
            {"decision": "deny", "reason": "no"},
            id="json-denies",
        ),
        pytest.param("cat >/dev/null; exit 1\n", None, id="crash-allows"),
    ],
)
def test_the_bridge_denies_a_call_a_guard_refuses(
    home: Path, library: Path, script: str, expected: dict | None
) -> None:
    add_guard(library, "stub", script)
    assert install(home, library, GUARD) == 0
    assert (
        call(home, "PreToolUse", tool_call("run_command", {"CommandLine": "ls"}))
        == expected
    )


def test_the_bridge_hands_a_guard_the_call_in_claude_shape(
    home: Path, library: Path
) -> None:
    seen = home.parent / "seen.json"
    add_guard(library, "stub", f"cat > {seen}\n")
    assert install(home, library, GUARD) == 0
    assert (
        call(home, "PreToolUse", tool_call("run_command", {"CommandLine": "ls"}))
        is None
    )
    assert json.loads(seen.read_text(encoding="utf-8")) == {
        "hook_event_name": "PreToolUse",
        "session_id": "s",
        "cwd": "/project",
        "transcript_path": "/brain/s/transcript_full.jsonl",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
    }


def test_a_done_guard_registers_on_stop_and_can_send_the_agent_back(
    home: Path, library: Path
) -> None:
    script = (
        'cat >/dev/null; printf \'{"decision":"block","reason":"finish the epic"}\'\n'
    )
    add_guard(library, "stub", script, "when: done\n")
    assert install(home, library, GUARD) == 0
    assert "matcher" not in hooks(home)["Stop"][0]
    stop = {
        "conversationId": "s",
        "cwd": "/project",
        "transcriptPath": "/t.jsonl",
        "continuationActive": False,
    }
    assert call(home, "Stop", stop) == {
        "decision": "continue",
        "reason": "finish the epic",
    }


def test_a_second_stop_in_the_same_turn_reaches_the_guard_as_already_continued(
    home: Path, library: Path
) -> None:
    seen = home.parent / "seen.jsonl"
    script = f'cat >> {seen}; echo >> {seen}; printf \'{{"decision":"block","reason":"again"}}\'\n'
    add_guard(library, "stub", script, "when: done\n")
    assert install(home, library, GUARD) == 0
    stop = {
        "conversationId": f"conv-{home.parent.name}",
        "lastUserInput": "build it",
        "continuationActive": False,
    }
    call(home, "Stop", stop)
    call(home, "Stop", stop)
    active = [
        json.loads(line)["stop_hook_active"]
        for line in seen.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert active == [False, True]


@pytest.mark.parametrize(
    ("tool", "args", "expected"),
    [
        pytest.param(
            "edit_file",
            {"Path": "/p/a.py", "Target": "beta", "Replacement": "gamma"},
            {"file_path": "/p/a.py", "old_string": "beta", "new_string": "gamma"},
            id="edit_file",
        ),
        pytest.param(
            "write_file",
            {"Path": "/p/b.py", "Content": "hi"},
            {"file_path": "/p/b.py", "content": "hi"},
            id="write_file",
        ),
        pytest.param(
            "replace_file_content",
            {
                "TargetFile": "/p/a.py",
                "ReplacementChunks": [
                    {"TargetContent": "beta", "ReplacementContent": "gamma"}
                ],
            },
            {"file_path": "/p/a.py", "old_string": "beta", "new_string": "gamma"},
            id="replace_file_content",
        ),
        pytest.param(
            "write_to_file",
            {"TargetFile": "/p/b.py", "CodeContent": "hi"},
            {"file_path": "/p/b.py", "content": "hi"},
            id="write_to_file",
        ),
    ],
)
def test_the_bridge_hands_a_guard_each_edit_tool_in_claude_shape(
    home: Path, library: Path, tool: str, args: dict, expected: dict
) -> None:
    seen = home.parent / "seen.json"
    add_guard(library, "stub", f"cat > {seen}\n")
    assert install(home, library, GUARD) == 0
    assert call(home, "PreToolUse", tool_call(tool, args)) is None
    assert json.loads(seen.read_text(encoding="utf-8"))["tool_input"] == expected


def test_an_unreadable_payload_is_denied(home: Path, library: Path) -> None:
    add_guard(library, "stub", "cat >/dev/null; exit 0\n")
    assert install(home, library, GUARD) == 0
    verdict = call(home, "PreToolUse", "not json")
    assert verdict is not None
    assert verdict["decision"] == "deny"


def test_a_dropped_guard_takes_the_hooks_file_and_the_bridge_with_it(
    home: Path, library: Path
) -> None:
    add_guard(library, "stub", "exit 0\n")
    assert install(home, library, GUARD) == 0
    mine = home / ".gemini/config/hooks/mine.py"
    mine.write_text("print()\n", encoding="utf-8")
    assert install(home, library, PROFILES + AGENTS) == 0
    assert not (home / ".gemini/config/hooks.json").exists()
    assert not (home / ANTIGRAVITY_BRIDGE).exists()
    assert mine.is_file()
