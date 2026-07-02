from __future__ import annotations

from pathlib import Path
from typing import Any

from ..builtins import REGISTRY
from ..graph.context import WorkflowContext
from ..graph.nodes import CallNode
from ..templates import render_string


def run_call(
    node: CallNode,
    ctx: WorkflowContext,
    workflow_dir: Path,
) -> tuple[str, dict[str, Any]]:
    fn = REGISTRY.get(node.fn)
    if fn is None:
        raise RuntimeError(
            f"CallNode '{node.id}': unknown built-in '{node.fn}'. "
            f"Available: {sorted(REGISTRY)}"
        )

    ctx_dict = ctx.as_dict()
    rendered_args = {k: render_string(v, ctx_dict) for k, v in node.args.items()}
    raw_result = fn(**rendered_args)

    label = f"call:{node.fn}({', '.join(f'{k}={v!r}' for k, v in rendered_args.items())})"

    outputs: dict[str, Any] = {}
    for spec in node.outputs:
        outputs[spec.key] = {spec.wrap: raw_result} if spec.wrap else raw_result

    return label, outputs
