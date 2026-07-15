#!/usr/bin/env python3
"""Advance the layer iteration index and return the next dispatch record.

Called in a loop by workflow.yaml to iterate over the dispatch_list built by
resolve-impl-context.py. Each call advances the index by one and returns the
current layer's record. When the list is exhausted, returns has_next_layer="no".

Usage: select-next-layer.py <spec_dir> <current_index>
  current_index: the index of the LAST completed layer (-1 on first call)

Prints one JSON object on stdout:
  {
    "has_next_layer": "yes" | "no",
    "current_layer_index": "<new_index>",
    "current_layer": { ... dispatch record ... } | {},
    "dispatch_count": "<total>"
  }
"""
from __future__ import annotations

import json
import logging
import sys

from workhorse.scriptutil import build_dispatch_list, find_repo_root, load_json, resolve_workspace

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")

    spec_dir_rel = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else ""
    current_index = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].lstrip("-").isdigit() else -1

    root = find_repo_root()

    plan_ctx_path = root / spec_dir_rel / "plan-context.json" if spec_dir_rel else None
    plan_ctx = load_json(plan_ctx_path, "plan-context.json", logger) if plan_ctx_path else {}
    plan_ctx_absent = not plan_ctx_path or not plan_ctx_path.exists()
    repos = resolve_workspace("CODER_WORKSPACE")
    dispatch_list = build_dispatch_list(plan_ctx, repos, fallback=plan_ctx_absent)

    # A plan-context that EXISTS, has no `services` key at all, and yields zero
    # dispatch records means the planner wrote a nonconforming schema (e.g.
    # `touched_layers` instead of `services`). validate-plan-context.py rejects
    # that shape and routes it back to the planner (rework_plan_paths), so
    # reaching this point means the validation gate was bypassed or regressed.
    # Do NOT guess a fallback repo — silently dispatching the wrong layer (or
    # skipping implementation, as happened to 06-choice-field-rendering on
    # 2026-07-03) is worse than halting. Fail the node loudly so the run stops
    # visibly and resumably. An explicit `"services": []` is a legitimate,
    # already-exhausted plan (a story that touches no code repos) — not an error.
    if not dispatch_list and plan_ctx and not plan_ctx_absent and "services" not in plan_ctx:
        logger.error(
            "plan-context.json at %s has no usable 'services' entries "
            "(keys: %s). This should have been rejected by "
            "validate-plan-context.py and sent back to the planner; refusing "
            "to guess a dispatch. Fix plan-context.json's schema and resume.",
            plan_ctx_path, sorted(plan_ctx.keys()),
        )
        sys.exit(1)

    next_index = current_index + 1
    total = len(dispatch_list)

    if next_index < total:
        print(json.dumps({
            "has_next_layer": "yes",
            "current_layer_index": str(next_index),
            "current_layer": dispatch_list[next_index],
            "dispatch_count": str(total),
        }))
    else:
        print(json.dumps({
            "has_next_layer": "no",
            "current_layer_index": str(current_index),
            "current_layer": {},
            "dispatch_count": str(total),
        }))


if __name__ == "__main__":
    main()
