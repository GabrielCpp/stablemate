#!/usr/bin/env python3
"""Bring the QA stack up durably before ``run_qa_plan``, owned by the workflow.

A long-running stack (``docker compose``, emulators, a DB + baseline seed) must be
started *outside* any agent turn or node teardown kills it mid-build — the exact
failure that burned three QA attempts on a real run. This node hands that lifecycle
to :func:`workhorse.stack.ensure_stack`, which brings the stack up (or adopts one
already serving), health-gates it, and leaves an expensive shared stack running for
the next story to adopt. Foreground in-QA services (a dev server) stay in the QA
plan's ``background:`` block, owned by ostler for the run — they are not this node's
job.

Usage: ensure-stack.py [manifest_path] [docs_path]
  manifest_path: repo-relative path to the stack manifest (default ``qa-stack.yml``).
  docs_path:     repo root; empty → AGENT_REPO_DIR / CWD (see find_docs_root). Script
    nodes run with cwd = the workflow dir, so without this a relative manifest path or
    a step's ``working-directory`` would resolve against the wrong repo.

Outputs JSON: {stack_ready: yes|no|skip, stack_app_pid, stack_app_pgid,
               stack_entry_url, stack_failed_step, stack_notes}. ``skip`` (no manifest
authored yet) is not a failure — the flow proceeds to QA exactly as before.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import yaml

from workhorse import stack
from workhorse.scriptutil import find_docs_root


def _emit(ready: str, result: dict[str, str], notes: str) -> None:
    print(json.dumps({
        "stack_ready": ready,
        "stack_app_pid": result.get("app_pid", ""),
        "stack_app_pgid": result.get("app_pgid", ""),
        "stack_entry_url": result.get("entry_url", ""),
        "stack_failed_step": result.get("failed_step", ""),
        "stack_notes": notes,
    }))


def _absolutize(manifest: dict, root: Path) -> dict:
    """Resolve the manifest's cwds against the repo root (script cwd is the workflow dir)."""
    manifest["app_cwd"] = str((root / (manifest.get("app_cwd") or ".")).resolve())
    for key in ("prepare", "seed", "health"):
        for step in manifest.get(key) or []:
            if isinstance(step, dict) and step.get("working-directory"):
                step["working-directory"] = str((root / step["working-directory"]).resolve())
    return manifest


def main(logger: logging.Logger) -> None:
    manifest_rel = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else "qa-stack.yml"
    docs_path_arg = sys.argv[2] if len(sys.argv) > 2 else ""
    root = find_docs_root(docs_path_arg)
    manifest_path = root / manifest_rel

    if not manifest_path.is_file():
        logger.info("no stack manifest at %s — skipping durable bring-up (QA-plan "
                    "`background:` services still apply)", manifest_path)
        _emit("skip", {}, f"No stack manifest at {manifest_rel}; nothing to bring up.")
        return

    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("stack manifest %s could not be read: %s", manifest_path, exc)
        _emit("no", {"failed_step": "manifest"}, f"Unreadable stack manifest: {exc}")
        return
    if not isinstance(manifest, dict):
        _emit("no", {"failed_step": "manifest"}, "Stack manifest is not a mapping.")
        return

    result = stack.ensure_stack(_absolutize(manifest, root), repo_root=str(root), logger=logger)
    if result["ready"] == "yes":
        how = "adopted" if result.get("adopted") == "yes" else "brought up"
        _emit("yes", result, f"Stack {how} and healthy at {result.get('entry_url') or '(no url)'}.")
    else:
        step = result.get("failed_step", "unknown")
        _emit("no", result, f"Stack bring-up failed at step '{step}'. Repair the manifest "
              f"or its seed recipe (never background the stack in the agent shell).")


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("ensure-stack"))
