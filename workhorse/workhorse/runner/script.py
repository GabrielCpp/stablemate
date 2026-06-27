from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

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


def run_script(
    node: ScriptNode,
    context: WorkflowContext,
    workflow_dir: Path,
    graph_env: dict[str, str] | None = None,
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

    # Prefix interpreter so scripts don't need to be executable
    suffix = script_path.suffix.lower()
    if suffix == ".py":
        cmd = [sys.executable, str(script_path)] + rendered_args
    elif suffix in (".sh", ".bash"):
        cmd = ["bash", str(script_path)] + rendered_args
    else:
        cmd = [str(script_path)] + rendered_args
    cmd_str = " ".join(cmd)

    env = {**os.environ}
    if graph_env:
        env.update({k: render_string(v, ctx) for k, v in graph_env.items()})
    if node.env:
        env.update({k: render_string(v, ctx) for k, v in node.env.items()})

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=effective_cwd,
        env=env,
    )

    if proc.returncode != 0:
        raise ScriptExitError(node.script, proc.returncode, proc.stderr)

    outputs = _extract_outputs(proc.stdout, node)
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
