#!/usr/bin/env python3
"""Validate the planner's plan-context.json against the real workspace.

Checks that every service path declared by the planner:
  1. Points to a directory that actually exists in the resolved workspace.
  2. Contains the expected service marker file (main.go, package.json, etc.).
  3. Has a corresponding plan file written to the spec directory.

If any check fails, outputs {"status": "invalid", "errors": [...]} so the
workflow can route back to the planner with actionable feedback.

Usage: validate-plan-context.py <spec_dir>
Prints one JSON object on stdout (parsed by the local-worker ScriptNode).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from workhorse import scriptutil
from workhorse.scriptutil import find_repo_root, load_json, resolve_workspace

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")

    spec_dir_rel = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else ""
    def _emit(status: str, errors: list[str]) -> None:
        print(json.dumps({"validation_result": {"status": status, "errors": errors}}))

    if not spec_dir_rel:
        _emit("invalid", ["spec_dir argument is empty"])
        return

    root = find_repo_root()
    spec_dir = root / spec_dir_rel

    plan_ctx = load_json(spec_dir / "plan-context.json", "plan-context.json", logger)
    if not plan_ctx:
        # No plan-context.json → single-service (non-multi-repo) story; treat as valid.
        _emit("valid", [])
        return

    services = plan_ctx.get("services")
    if not services:
        # A plan-context.json that EXISTS but declares no services is a planner
        # schema error, not a single-service story (that case has no file at
        # all). Waving it through used to silently skip the whole implement
        # stage and send an unimplemented story into review/QA
        # (06-choice-field-rendering, 2026-07-03: planner wrote `touched_layers`
        # instead of `services`). Route it back to the planner with the schema.
        _emit("invalid", [
            "plan-context.json exists but has no 'services' array "
            f"(found keys: {sorted(plan_ctx.keys())}). Rewrite plan-context.json "
            "so it declares every layer to implement as "
            '{"services": [{"repo": "<workspace repo name>", "path": "<service dir, e.g. api or web>", '
            '"type": "<go|react-router|...>", "plan_file": "<plan file in the spec dir>", "skills": [...]}], '
            '"implementation_order": ["<repo>::<path>", ...]} — '
            "keys like 'touched_layers' are not read by the implementation dispatcher.",
        ])
        return

    repos = resolve_workspace("CODER_WORKSPACE")
    errors: list[str] = []

    # Producer-contract pre-check: `ostler artifact vet plan-context` applies the
    # structural contract (services shape, plan_file existence, order refs) the
    # planner was told to self-check against; workspace-specific repo resolution
    # stays below (ostler has no workspace context). Union its problems in;
    # ostler being absent never blocks validation itself.
    try:
        ostler_out = scriptutil.run_tool(
            ["ostler", "artifact", "vet", "plan-context", "--spec", spec_dir_rel, "--json"],
            cwd=root,
        )
        if ostler_out.stdout.strip():
            parsed = json.loads(ostler_out.stdout)
            errors.extend(f"[ostler] {p}" for p in parsed.get("problems", []))
    except Exception:  # noqa: BLE001
        pass

    # Case-insensitive lookup of the real workspace repo keys. The planner tends to
    # emit the human-facing project name ("Acme") while the workspace key is the
    # folder name ("acme"); resolve that deterministically here rather than routing
    # a symptom-only error back to the LLM, which re-authors the same casing from the
    # title-cased branding all over the plan prompt. Repair, don't just reject.
    canon_by_lower = {name.lower(): name for name in repos}
    rewrites: dict[str, str] = {}  # emitted repo name -> canonical workspace key

    def canonicalize(repo_name: str) -> str:
        """Map an emitted repo name to its canonical workspace key when it differs
        only by case; record the rewrite. Returns the input unchanged when unknown."""
        if repo_name in repos:
            return repo_name
        canon = canon_by_lower.get(repo_name.lower())
        if canon is not None and canon != repo_name:
            rewrites[repo_name] = canon
        return canon if canon is not None else repo_name

    for svc in services:
        emitted_repo = svc.get("repo", "")
        repo_name = canonicalize(emitted_repo)
        svc["repo"] = repo_name  # normalize in place; persisted below if anything changed
        svc_path = svc.get("path", "")
        svc_type = svc.get("type", "")
        plan_file = svc.get("plan_file", "")
        label = f"{repo_name}::{svc_path}"

        if repo_name not in repos:
            valid = ", ".join(sorted(repos)) or "<none>"
            errors.append(f"{label}: repo '{repo_name}' not found in workspace (valid: {valid})")
            continue

        repo_info = repos[repo_name]
        repo_abs = Path(repo_info["path"])
        service_abs = repo_abs / svc_path

        # new_service: true means the directory will be scaffolded during implementation
        if svc.get("new_service"):
            logger.info("%s: new_service=true — skipping path existence check", label)
            continue

        if not service_abs.exists():
            errors.append(f"{label}: path does not exist at {service_abs}")
            continue

        if not service_abs.is_dir():
            errors.append(f"{label}: path is not a directory")
            continue

        markers = repo_info.get("service_markers", [])
        if svc_type == "terraform":
            markers = ["main.tf"]
        if markers and not any((service_abs / m).exists() for m in markers):
            errors.append(f"{label}: no service marker found (expected one of {markers} in {service_abs})")

        if plan_file and not (spec_dir / plan_file).exists():
            errors.append(f"{label}: plan file '{plan_file}' not found in spec dir")

    # Persist any case normalization so downstream deterministic consumers
    # (resolve-impl-context, detect-regression-platform, dispatch) and any
    # re-validation see the canonical repo key. services[].repo was rewritten in
    # place above; also fix the "repo::path" prefixes in implementation_order.
    if rewrites:
        order = plan_ctx.get("implementation_order")
        if isinstance(order, list):
            plan_ctx["implementation_order"] = [
                f"{rewrites.get(entry.split('::', 1)[0], entry.split('::', 1)[0])}::{entry.split('::', 1)[1]}"
                if isinstance(entry, str) and "::" in entry else entry
                for entry in order
            ]
        (spec_dir / "plan-context.json").write_text(
            json.dumps(plan_ctx, indent=2) + "\n", encoding="utf-8"
        )
        for emitted, canon in sorted(rewrites.items()):
            logger.info("normalized repo '%s' -> '%s' in plan-context.json", emitted, canon)

    if errors:
        _emit("invalid", errors)
    else:
        _emit("valid", [])


if __name__ == "__main__":
    main()
