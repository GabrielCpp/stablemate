"""A repair turn pays for every tool schema on every step, so the adapter narrows the agent."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from workhorse._vendor.stablemate_core import config
from workhorse.config_run import AgentResilience
from workhorse.runner.backends import AgentProfile
from workhorse.runner.backends import turn
from workhorse.runner.backends.opencode import OpenCodeBackend

RESILIENCE = AgentResilience()

PROFILE = AgentProfile(
    name="okf-repair",
    tools={"webfetch": False, "websearch": False, "task": False},
    steps=20,
    disable_mcp=("playwright",),
    tool_output_max_lines=400,
    tool_output_max_bytes=20000,
)


@contextmanager
def _config(text: str):
    """Point the shared config at a temp file holding ``text``."""
    prior_cli = os.environ.pop("AGENT_CLI", None)
    prior_path = os.environ.get(config.CONFIG_PATH_ENV)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.toml"
        path.write_text(text)
        os.environ[config.CONFIG_PATH_ENV] = str(path)
        try:
            yield path
        finally:
            if prior_path is None:
                os.environ.pop(config.CONFIG_PATH_ENV, None)
            else:
                os.environ[config.CONFIG_PATH_ENV] = prior_path
            if prior_cli is not None:
                os.environ["AGENT_CLI"] = prior_cli


def _fake_stream(canned):
    """A ``stream_jsonl`` stand-in that records the argv and environment of one turn."""
    captured = {}

    def fake(cmd, node_id, timeout, stdin_data, on_event, **kwargs):
        captured["cmd"] = cmd
        captured["env_extra"] = kwargs.get("env_extra")
        return canned

    return fake, captured


def _turn(
    profile,
    *,
    operator_config: str = "",
    model: str | None = "minimax/MiniMax-M3",
    cwd: str | None = None,
    add_dirs: list[str] | None = None,
):
    """Run one canned turn under ``profile`` and return its argv and injected config."""
    cfg = (
        "[harness.opencode]\n"
        f"env = {{ OPENCODE_CONFIG_CONTENT = '{operator_config}' }}\n"
        if operator_config
        else ""
    )
    with _config(cfg):
        fake, captured = _fake_stream(turn.TurnState(result_text="X", session_id="s"))
        OpenCodeBackend(fake).run_turn(
            "P", "n", None, model, timeout=RESILIENCE.result_timeout_s,
            resilience=RESILIENCE, agent=profile, cwd=cwd, add_dirs=add_dirs,
        )
    raw = captured["env_extra"].get("OPENCODE_CONFIG_CONTENT")
    return captured["cmd"], json.loads(raw) if raw else {}


def test_the_turn_names_the_profile_and_the_config_defines_it():
    """``--agent`` alone is inert: opencode falls back to its default agent when nothing defines the name."""
    cmd, cfg = _turn(PROFILE)
    assert cmd[cmd.index("--agent") + 1] == "okf-repair"
    assert "okf-repair" in cfg["agent"]


def test_the_tools_the_turn_never_calls_are_denied():
    """A denied tool leaves the request entirely, which is the point: its schema is resent on every step."""
    _, cfg = _turn(PROFILE)
    assert cfg["agent"]["okf-repair"]["tools"] == {
        "webfetch": False,
        "websearch": False,
        "task": False,
    }


def test_denying_an_edit_alias_is_refused():
    """opencode folds ``write``, ``edit`` and ``patch`` onto one permission, so denying any of them disarms the turn."""
    for alias in ("write", "edit", "patch"):
        try:
            _turn(AgentProfile(name="x", tools={alias: False}))
        except ValueError as exc:
            assert alias in str(exc)
        else:
            raise AssertionError(f"denying {alias} should have been refused")


def test_the_browser_server_and_the_output_clip_ride_along():
    """A Playwright MCP server the repair turn has never called still ships its schemas on every step."""
    _, cfg = _turn(PROFILE)
    assert cfg["mcp"] == {"playwright": {"enabled": False}}
    assert cfg["tool_output"] == {"max_lines": 400, "max_bytes": 20000}


def test_the_step_budget_is_absent_until_a_profile_asks_for_one():
    """An unset budget must not become a default one: opencode's own limit stands."""
    _, cfg = _turn(AgentProfile(name="okf-repair"))
    assert "steps" not in cfg["agent"]["okf-repair"]
    _, budgeted = _turn(PROFILE)
    assert budgeted["agent"]["okf-repair"]["steps"] == 20


def test_an_operator_config_is_merged_rather_than_replaced():
    """The previous adapter skipped itself whenever an operator set the variable, losing the ``small_model`` pin on every machine with a harness env entry."""
    _, cfg = _turn(PROFILE, operator_config='{"theme":"ansi","small_model":"openai/gpt-5.5"}')
    assert cfg["theme"] == "ansi"
    assert cfg["small_model"] == "openai/gpt-5.5"
    assert cfg["agent"]["okf-repair"]["steps"] == 20


def test_a_turn_with_no_profile_is_unchanged():
    """Every other node still invokes opencode exactly as it did before."""
    cmd, cfg = _turn(None)
    assert "--agent" not in cmd
    assert cfg == {"small_model": "minimax/MiniMax-M3"}


CONFINED = AgentProfile(name="docs-writer", tools={"*": False}, confined=True, commands=("ostler", "python -m check /runs/job.json"))


def _confined_turn(**kwargs):
    """Run one confined turn from ``docs/`` of a throwaway worktree that also holds ``skills/``."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".git").mkdir()
        (root / "docs").mkdir()
        (root / "skills").mkdir()
        _, cfg = _turn(CONFINED, cwd=str(root / "docs"), add_dirs=[str(root / "skills")], **kwargs)
    return cfg["agent"]["docs-writer"]


def test_a_confined_turn_reads_and_writes_its_cwd_and_added_dirs():
    """opencode matches these rules relative to the worktree, and an absolute pattern matches nothing."""
    permission = _confined_turn()["permission"]
    assert permission["read"] == {
        "*": "deny",
        "docs/**": "allow",
        "skills/**": "allow",
        ".opencode/skills/**": "allow",
        ".claude/skills/**": "allow",
        ".agents/skills/**": "allow",
    }
    assert permission["edit"] == {"*": "deny", "docs/**": "allow", "skills/**": "allow"}
    assert permission["external_directory"] == {"*": "deny"}


def test_a_confined_turn_reads_the_operators_opencode_and_skill_dirs_but_never_writes_them():
    """opencode loads the operator's config and skills from home, and a path outside the worktree must also pass external_directory."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp).resolve()
        home = base / "home"
        for directory in (".config/opencode", ".claude/skills", ".agents/skills"):
            (home / directory).mkdir(parents=True)
        root = base / "repo"
        (root / ".git").mkdir(parents=True)
        (root / "docs").mkdir()
        env = {key: value for key, value in os.environ.items() if key not in ("XDG_CONFIG_HOME",)}
        with patch.dict(os.environ, {**env, "HOME": str(home)}, clear=True):
            _, cfg = _turn(CONFINED, cwd=str(root / "docs"))
    permission = cfg["agent"]["docs-writer"]["permission"]
    for directory in (home / ".config" / "opencode", home / ".claude" / "skills", home / ".agents" / "skills"):
        assert permission["external_directory"][f"{directory}/**"] == "allow"
        assert permission["read"][f"{directory.relative_to(root, walk_up=True).as_posix()}/**"] == "allow"
    assert permission["edit"] == {"*": "deny", "docs/**": "allow"}


def test_a_confined_turn_reaches_an_added_repo_beside_its_worktree():
    """A frontend turn that also edits its backend repo needs both checks opened: the absolute ``external_directory`` one and the worktree-relative path rules."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        (root / "web-app" / ".git").mkdir(parents=True)
        (root / "api-service").mkdir()
        _, cfg = _turn(CONFINED, cwd=str(root / "web-app"), add_dirs=[str(root / "api-service")])
    permission = cfg["agent"]["docs-writer"]["permission"]
    assert permission["read"]["../api-service/**"] == "allow"
    assert permission["edit"] == {"*": "deny", "**": "allow", "../api-service/**": "allow"}
    assert permission["external_directory"] == {"*": "deny", f"{root / 'api-service'}/**": "allow"}


def test_an_added_directory_holding_the_worktree_opens_all_of_it():
    """Its worktree-relative rule would be ``../**``, which misses the worktree it holds, so the rule is the whole worktree and ``external_directory`` bounds the rest."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        (root / "web-app" / "docs").mkdir(parents=True)
        (root / "web-app" / ".git").mkdir()
        _, cfg = _turn(CONFINED, cwd=str(root / "web-app" / "docs"), add_dirs=[str(root)])
    permission = cfg["agent"]["docs-writer"]["permission"]
    assert permission["edit"] == {"*": "deny", "docs/**": "allow", "**": "allow"}
    assert permission["external_directory"] == {"*": "deny", f"{root}/**": "allow"}


def test_a_confined_turn_outside_any_worktree_is_refused():
    """opencode resolves its path rules against the git worktree, so without one no rule would match."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            _turn(CONFINED, cwd=tmp)
        except ValueError as exc:
            assert "worktree" in str(exc)
        else:
            raise AssertionError("a cwd in no worktree should have been refused")


def test_a_confined_turn_runs_only_its_named_commands():
    assert _confined_turn()["permission"]["bash"] == {
        "*": "deny",
        "ostler": "allow",
        "ostler *": "allow",
        "python -m check /runs/job.json": "allow",
        "python -m check /runs/job.json *": "allow",
    }


def test_a_confined_turn_drops_the_search_tools_that_answer_outside_its_rules():
    """opencode's grep returned a file outside the allowed paths, so a confined turn cannot keep it."""
    tools = _confined_turn()["tools"]
    assert tools["*"] is False
    assert tools["read"] and tools["edit"] and tools["write"] and tools["bash"]
    assert not (tools["grep"] or tools["glob"] or tools["list"])


def test_a_confined_turn_with_no_commands_has_no_shell():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".git").mkdir()
        _, cfg = _turn(AgentProfile(name="quiet", confined=True), cwd=tmp)
    entry = cfg["agent"]["quiet"]
    assert entry["tools"]["bash"] is False
    assert entry["permission"]["bash"] == {"*": "deny"}
    assert entry["permission"]["edit"] == {"*": "deny", "**": "allow"}


def test_naming_commands_without_confinement_is_refused():
    """Commands on an unconfined profile would read as a limit that nothing enforces."""
    try:
        AgentProfile(name="loose", commands=("ostler",))
    except ValueError as exc:
        assert "not confined" in str(exc)
    else:
        raise AssertionError("commands without confinement should have been refused")


if __name__ == "__main__":
    fns = [
        v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)
    ]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
