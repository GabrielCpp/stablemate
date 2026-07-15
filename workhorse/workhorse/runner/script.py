from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Protocol

from ..graph.nodes import ScriptNode
from ..graph.context import WorkflowContext
from ..templates import render_string


class ScriptExitError(Exception):
    """Raised when a workflow script exits with a non-zero code.

    Carries the original exit code so callers (e.g. ``workhorse run``) can
    propagate it faithfully — e.g. ``await_operator.py`` exits with 2 to signal
    "operator input required", which is distinct from an unexpected crash (1).
    """

    def __init__(self, script: str, exit_code: int, stderr: str) -> None:
        super().__init__(
            f"Script '{script}' exited with code {exit_code}.\nstderr: {stderr.strip()}"
        )
        self.exit_code = exit_code


class ScriptRunner(Protocol):
    """Executes one script node's file and returns ``(returncode, stdout, stderr)``.

    The seam that lets the engine run a script node as a child subprocess in
    production (``SubprocessScriptRunner``) but IN-PROCESS under test (the
    ``InProcessScriptRunner`` in ``workhorse.testing``), so a test can monkeypatch
    the ``scriptutil`` helpers the script calls — no PATH shims, no CLI subprocess.
    """

    def run(
        self, script_path: Path, argv: list[str], cwd: str, env: dict[str, str]
    ) -> tuple[int, str, str]:
        ...


class SubprocessScriptRunner:
    """Default runner: spawn the script as a child process (the production path)."""

    def run(
        self, script_path: Path, argv: list[str], cwd: str, env: dict[str, str]
    ) -> tuple[int, str, str]:
        cmd = _interpreter_cmd(script_path) + argv
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
        )
        return proc.returncode, proc.stdout, proc.stderr


def _interpreter_cmd(script_path: Path) -> list[str]:
    """Prefix the interpreter so scripts don't need the executable bit. Only Python
    is supported; shell scripts are rejected at load (graph/nodes.py) and here as
    defense-in-depth against a dynamically-constructed ``.sh`` path."""
    suffix = script_path.suffix.lower()
    if suffix == ".py":
        return [sys.executable, str(script_path)]
    if suffix in (".sh", ".bash"):
        raise ScriptExitError(
            str(script_path),
            1,
            "shell scripts are not supported; port to a Python script using "
            "workhorse.scriptutil",
        )
    return [str(script_path)]


def run_script(
    node: ScriptNode,
    context: WorkflowContext,
    workflow_dir: Path,
    graph_env: dict[str, str] | None = None,
    *,
    runner: ScriptRunner | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Render script args via Jinja2, run the script, parse stdout as JSON.

    Returns (command_str, extracted_outputs_dict).
    """
    ctx = context.as_dict()

    script_path = workflow_dir / node.script
    rendered_args = [render_string(arg, ctx) for arg in node.args]

    # Render per-node working directory; fall back to WORKHORSE_DEFAULT_SCRIPT_CWD
    # (injected by the test harness) or workflow_dir when unset.
    resolved_cwd = render_string(node.cwd, ctx).strip() if node.cwd else ""
    effective_cwd = resolved_cwd or os.environ.get("WORKHORSE_DEFAULT_SCRIPT_CWD") or str(workflow_dir)

    cmd_str = " ".join(_interpreter_cmd(script_path) + rendered_args)

    env = {**os.environ}
    if graph_env:
        env.update({k: render_string(v, ctx) for k, v in graph_env.items()})
    if node.env:
        env.update({k: render_string(v, ctx) for k, v in node.env.items()})

    runner = runner or SubprocessScriptRunner()
    returncode, stdout, stderr = runner.run(
        script_path, rendered_args, effective_cwd, env
    )

    if returncode != 0:
        raise ScriptExitError(node.script, returncode, stderr)

    outputs = _extract_outputs(stdout, node)
    return cmd_str, outputs


def _extract_outputs(stdout: str, node: ScriptNode) -> dict[str, Any]:
    if not node.outputs:
        return {}

    try:
        parsed = json.loads(stdout.strip())
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Script '{node.script}' stdout is not valid JSON: {e}\n"
            f"stdout: {stdout[:500]}"
        ) from e

    result: dict[str, Any] = {}
    for spec in node.outputs:
        if spec.key not in parsed:
            raise RuntimeError(
                f"Node '{node.id}': expected output key '{spec.key}' not found in script JSON"
            )
        result[spec.key] = parsed[spec.key]
    return result
