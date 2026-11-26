from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import agy_plugin as build
import pytest


def _home(tmp_path: Path, hooks: dict, servers: dict) -> Path:
    home = tmp_path / "home"
    config = home / ".gemini/config"
    (config / "skills/review").mkdir(parents=True)
    (config / "skills/review/SKILL.md").write_text("---\nname: review\n---\n", encoding="utf-8")
    (config / "agents").mkdir()
    (config / "agents/worker.md").write_text("---\nname: worker\n---\n", encoding="utf-8")
    (config / "hooks").mkdir()
    (config / "hooks/farrier-guards.py").write_text(
        "import sys\nprint(sys.argv[2])\n", encoding="utf-8"
    )
    (config / "hooks.json").write_text(json.dumps(hooks), encoding="utf-8")
    (config / "mcp_config.json").write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    (config / "AGENTS.md").write_text("Rules.\n", encoding="utf-8")
    guard = home / ".agents/hooks/stub"
    guard.mkdir(parents=True)
    (guard / "stub.py").write_text("print('denied')\n", encoding="utf-8")
    (home / ".agents/.farrier-home.json").write_text("{}", encoding="utf-8")
    return home


def _guard_hooks(home: Path, *inner: str) -> dict:
    bridge = f"{home}/.gemini/config/hooks/farrier-guards.py"
    entries = [{"hooks": [{"type": "command", "command": f"python3 {bridge} tool '{each}'"}]} for each in inner]
    return {"farrier-guards": {"PreToolUse": entries}}


def _built(tmp_path: Path, inner: tuple[str, ...] = (), servers: dict | None = None) -> Path:
    home = tmp_path / "home"
    hooks = _guard_hooks(home, *inner)
    _home(tmp_path, hooks, servers or {})
    out = tmp_path / "plugin"
    build.assemble(home, out, "1.2.3", _wheels(out))
    return out


def _wheels(out: Path) -> tuple[str, ...]:
    names = ("farrier-8.0.0-py3-none-any.whl", "stablemate-1.2.3-py3-none-any.whl", "stablemate_groom-2.3.0-py3-none-any.whl")
    (out / "wheels").mkdir(parents=True)
    for name in names:
        (out / "wheels" / name).write_bytes(b"")
    return names


def test_the_home_render_lands_where_a_plugin_keeps_each_part(tmp_path: Path) -> None:
    out = _built(tmp_path)
    assert (out / "skills/review/SKILL.md").is_file()
    assert (out / "agents/worker.md").is_file()
    assert (out / "rules/AGENTS.md").read_text() == "Rules.\n"
    assert (out / "hooks/stub/stub.py").is_file()
    assert not (out / ".farrier-home.json").exists()
    assert json.loads((out / "plugin.json").read_text())["version"] == "1.2.3"


def test_a_guard_runs_from_the_plugin_folder(tmp_path: Path) -> None:
    home = tmp_path / "home"
    out = _built(tmp_path, (f"python3 {home}/.agents/hooks/stub/stub.py",))
    (entry,) = json.loads((out / "hooks.json").read_text())["farrier-guards"]["PreToolUse"]
    command = entry["hooks"][0]["command"]
    assert str(tmp_path) not in command
    done = subprocess.run(["sh", "-c", command], capture_output=True, text=True, cwd=out, check=True, timeout=30)
    assert done.stdout.strip() == "python3 hooks/stub/stub.py"


def test_a_guard_or_server_that_starts_a_tool_starts_its_launcher(tmp_path: Path) -> None:
    out = _built(tmp_path, ("saddlebag guard --hook",), {"groom": {"command": "groom", "args": ["channel"]}})
    (entry,) = json.loads((out / "hooks.json").read_text())["farrier-guards"]["PreToolUse"]
    assert entry["hooks"][0]["command"].endswith("'bin/saddlebag guard --hook'")
    servers = json.loads((out / "mcp_config.json").read_text())["mcpServers"]
    assert servers == {"groom": {"command": "sh", "args": ["${PLUGIN_ROOT}/bin/groom", "channel"]}}


def _launch(script: Path, cwd: Path, env: dict[str, str]) -> list[str]:
    body = script.read_text().replace("exec uvx", 'printf "%s\\n" "$AGENT_CLI"')
    moved = script.parent / f".{script.name}"
    moved.write_text(body, encoding="utf-8")
    moved.chmod(0o755)
    done = subprocess.run([str(moved)], capture_output=True, text=True, cwd=cwd, env=env, check=True, timeout=30)
    return done.stdout.splitlines()


def test_every_tool_launcher_runs_the_wheels_the_plugin_embeds(tmp_path: Path) -> None:
    out = _built(tmp_path)
    assert sorted(path.name for path in (out / "bin").iterdir()) == sorted(build.TOOLS)
    for path in (out / "bin").iterdir():
        assert os.access(path, os.X_OK)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    words = _launch(out / "bin/farrier", elsewhere, {"PATH": os.environ["PATH"]})
    assert words[1:3] == ["--overrides", str(out / "wheels/overrides.txt")]
    assert words[3:] == ["--from", str(out / "wheels/stablemate-1.2.3-py3-none-any.whl"), "farrier"]
    pinned = dict(line.split(" @ ") for line in (out / "wheels/overrides.txt").read_text().splitlines())
    wheels = {name: Path(path.replace("${STABLEMATE_WHEELS}", str(out / "wheels"))) for name, path in pinned.items()}
    assert sorted(wheels) == ["farrier", "stablemate", "stablemate-groom"]
    assert all(path.is_file() for path in wheels.values())


def test_workhorse_launchers_drive_antigravity_unless_told_otherwise(tmp_path: Path) -> None:
    out = _built(tmp_path)
    for preset, expected in (({}, "antigravity"), ({"AGENT_CLI": "claude"}, "claude")):
        env = {"PATH": os.environ["PATH"], **preset}
        assert _launch(out / "bin/workhorse-coder", tmp_path, env)[0] == expected
    assert "AGENT_CLI" not in (out / "bin/groom").read_text()


def test_a_skill_longer_than_antigravity_reads_is_refused(tmp_path: Path) -> None:
    home = _home(tmp_path, {}, {})
    (home / ".gemini/config/skills/review/SKILL.md").write_text("word " * 5200, encoding="utf-8")
    with pytest.raises(SystemExit, match=r"first 24 KB.*skills/review/SKILL.md"):
        build.assemble(home, tmp_path / "plugin", "1.2.3", _wheels(tmp_path / "plugin"))


def test_a_file_the_render_leaves_unplaced_is_refused(tmp_path: Path) -> None:
    home = _home(tmp_path, {}, {})
    (home / ".codex").mkdir()
    (home / ".codex/config.toml").write_text("", encoding="utf-8")
    with pytest.raises(SystemExit, match=r"\.codex/config\.toml, which has no place"):
        build.assemble(home, tmp_path / "plugin", "1.2.3", _wheels(tmp_path / "plugin"))


def test_a_folder_that_holds_other_work_is_never_cleared(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("keep\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="left alone"):
        build.clear(tmp_path)
    assert (tmp_path / "notes.md").read_text() == "keep\n"
