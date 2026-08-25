"""What `check_no_shell.py` refuses, and the two shapes it must not refuse.

The guard has two enforcement points over one rule, and they fail differently: the hook that
denies a tool call is the half that gets in the way, so its false positives are what these
cases are mostly about — a Python file, a shell script the repo legitimately owns, a Bash
call that *runs* a script rather than writing one. The sweep is tested against a real tree
(`the repo itself`), because a fabricated one cannot show that the ALLOWED set still names
files that exist.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check_no_shell.py"


@pytest.fixture(scope="module")
def guard() -> Any:
    spec = importlib.util.spec_from_file_location("check_no_shell", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(file_path: str) -> dict[str, Any]:
    return {"tool_name": "Write", "tool_input": {"file_path": file_path}}


def _bash(command: str) -> dict[str, Any]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


@pytest.mark.parametrize(
    "payload",
    [
        _write("/tmp/deploy.sh"),
        _write("scripts/run.bash"),
        _write("~/tools/thing.zsh"),
        _bash("cat > tools/deploy.sh <<'EOF'\nls\nEOF"),
        _bash("echo ls >> helper.sh"),
        _bash("printf 'ls' | tee -a build/x.zsh"),
    ],
)
def test_denies_authoring_a_shell_script(guard: Any, payload: dict[str, Any]) -> None:
    reason = guard.hook_decision(payload)
    assert reason is not None
    assert "unified Python CLI" in reason


@pytest.mark.parametrize(
    "payload",
    [
        _write("scripts/check_no_shell.py"),
        _write("README.md"),
        # The allowlisted files stay editable, or the rule bans maintaining the exceptions.
        _write(str(REPO / "ostler" / "docker" / "sandbox" / "entrypoint.sh")),
        _write(str(REPO / ".githooks" / "pre-commit")),
        # Running a script is not writing one.
        _bash("bash ostler/docker/sandbox/entrypoint.sh"),
        _bash("uv run python scripts/check_no_shell.py"),
        # A `.sh` that is only ever read.
        _bash("grep -n exec ostler/docker/sandbox/entrypoint.sh"),
    ],
)
def test_allows_everything_else(guard: Any, payload: dict[str, Any]) -> None:
    assert guard.hook_decision(payload) is None


def test_malformed_stdin_is_not_a_denial(guard: Any) -> None:
    """A hook that errors on an unexpected payload blocks the tool call it cannot parse."""
    assert guard.hook_decision({}) is None
    assert guard.hook_decision({"tool_name": "Write", "tool_input": "not a dict"}) is None
    assert guard.hook_decision({"tool_name": "Write", "tool_input": {"file_path": 7}}) is None


def test_hook_mode_emits_a_pretooluse_denial() -> None:
    """End to end, over the wire the hook actually speaks: stdin JSON in, decision JSON out."""
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--hook"],
        input=json.dumps(_write("/tmp/x.sh")),
        capture_output=True,
        text=True,
        check=True,
    )
    decision = json.loads(done.stdout)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "deny"


def test_hook_mode_survives_garbage_stdin() -> None:
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--hook"],
        input="}{ not json",
        capture_output=True,
        text=True,
        check=True,
    )
    assert done.stdout == ""


def test_shebang_closes_the_suffix_loophole(guard: Any, tmp_path: Path) -> None:
    script = tmp_path / "deploy"
    script.write_text("#!/usr/bin/env bash\nls\n", encoding="utf-8")
    assert guard._is_shell("bin/deploy", script) is not None
    plain = tmp_path / "notes"
    plain.write_text("just text\n", encoding="utf-8")
    assert guard._is_shell("notes", plain) is None


def test_the_repo_itself_is_clean(guard: Any) -> None:
    assert guard.check_no_shell() == []


def test_allowlist_names_files_that_exist(guard: Any) -> None:
    """An entry for a deleted file is a hole nobody would notice until something fills it."""
    assert [rel for rel in guard.ALLOWED if not (REPO / rel).is_file()] == []
