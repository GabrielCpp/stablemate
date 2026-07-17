#!/usr/bin/env python3
"""Decide whether the approved plan touched a UI layer, and which platform(s).

Reads ``<spec_dir>/plan-context.json`` (written by the planner) and maps the
per-service ``type`` of each entry in its ``services`` array to a regression
platform the coder workflow can branch on:

  - a ``react-router``/``svelte`` service -> "web"
  - a ``flutter`` service                 -> "mobile"
  - both                                  -> "both"
  - neither (API/infra/docs-only, etc.)   -> "none"  (regression step is skipped)

The ``services`` array is the per-repo/per-service source of truth (each entry is
a touched layer scoped to a repo + service folder), so the platform is derived
from ``type`` and the touched service ``path``\\s are surfaced for the regression
gate to scope its journeys. Legacy plan-context files that only carry the flat
``touched_layers`` list still resolve via a fallback.

Output (stdout, JSON): ``{"regression": {"platform": "<web|mobile|both|none>",
"layers": [<the UI layers touched>], "paths": [<repo::path for each UI service>]}}``.
Missing/unreadable plan-context -> "none" (fail-open to skip, never block a
non-UI story).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

# Per-service ``type`` -> regression platform (the ``services`` array source).
UI_TYPE_PLATFORM = {"react-router": "web", "svelte": "web", "flutter": "mobile"}
# Legacy flat ``touched_layers`` -> platform (fallback for pre-services specs).
UI_LAYER_PLATFORM = {"react-router": "web", "flutter": "mobile"}


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return here


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        print(f"[detect-regression-platform] plan-context unreadable at {path}: {e}", file=sys.stderr)
        return {}


def main(logger: logging.Logger) -> None:
    spec_dir = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else ""
    root = find_repo_root()
    plan_ctx = _load_json(root / spec_dir / "plan-context.json") if spec_dir else {}

    services = plan_ctx.get("services") or []
    if services:
        logger.info("deriving regression platform from %d service(s) in plan-context", len(services))
        # Per-service source of truth: derive platform from each service's type,
        # and surface the repo::path of every UI service so the gate can scope.
        ui_layers = [svc.get("type") for svc in services if svc.get("type") in UI_TYPE_PLATFORM]
        ui_paths = [
            f"{svc.get('repo', '')}::{svc.get('path', '.')}"
            for svc in services
            if svc.get("type") in UI_TYPE_PLATFORM
        ]
        platforms = sorted({UI_TYPE_PLATFORM[layer] for layer in ui_layers})
    else:
        logger.info("no services in plan-context — falling back to legacy touched_layers")
        # Legacy fallback: flat touched_layers, no per-service scoping available.
        touched = plan_ctx.get("touched_layers") or []
        ui_layers = [layer for layer in touched if layer in UI_LAYER_PLATFORM]
        ui_paths = []
        platforms = sorted({UI_LAYER_PLATFORM[layer] for layer in ui_layers})

    if not platforms:
        platform = "none"
    elif len(platforms) == 1:
        platform = platforms[0]
    else:
        platform = "both"

    logger.info("resolved regression platform=%s", platform)
    print(json.dumps({"regression": {"platform": platform, "layers": ui_layers, "paths": ui_paths}}))


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("detect-regression-platform"))
