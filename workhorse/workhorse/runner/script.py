from __future__ import annotations
import json
import subprocess
from pathlib import Path
from typing import Any

from ..graph.nodes import ScriptNode
from ..graph.context import WorkflowContext
from ..templates import render_string


def run_script(
    node: ScriptNode,
    context: WorkflowContext,
    workflow_dir: Path,
) -> tuple[str, dict[str, Any]]:
    """
    Render script args via Jinja2, run the script, parse stdout as JSON.

    Returns (command_str, extracted_outputs_dict).
    """
    ctx = context.as_dict()

    script_path = workflow_dir / node.script
    rendered_args = [render_string(arg, ctx) for arg in node.args]

    # Prefix interpreter so scripts don't need to be executable
    suffix = script_path.suffix.lower()
    if suffix == ".py":
        cmd = ["python3", str(script_path)] + rendered_args
    elif suffix in (".sh", ".bash"):
        cmd = ["bash", str(script_path)] + rendered_args
    else:
        cmd = [str(script_path)] + rendered_args
    cmd_str = " ".join(cmd)

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(workflow_dir),
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"Script '{node.script}' exited with code {proc.returncode}.\n"
            f"stderr: {proc.stderr.strip()}"
        )

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
