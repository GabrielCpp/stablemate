#!/usr/bin/env python3
"""Decode the planner's per-story resolution into the implementer/QA run context.

The planner writes ``<spec_dir>/plan-context.json`` with a ``services`` array —
each entry is a concrete service path (repo::path) with its type, skills, and
plan file. This script reads it together with the workspace configuration
(VSCode workspace file + per-repo agents.yml) and resolves it into:

  - ``impl_instruction_paths``: the coding-standard instruction files this story
    needs, resolved (logical name → repo-root-relative path) and filtered to what
    the repo actually has.
  - ``qa_run_plan``: one entry per service — its label, QA mode, and skills.
  - ``qa_stack``: the data/fixture/stack the surface needs to render with realistic
    data, copied verbatim from the plan.
  - ``dispatch_list``: per-service dispatch records for the layer iteration loop —
    each with repo, cwd, service_path, type, plan_file, skills, qa_mode, verification.
  - ``dispatch_count``: number of services to implement.
  - ``affected_repos``: deduplicated list of repos touched by this story.
  - ``affected_repo_paths``: absolute paths for those repos, plus the docs root
    itself (for ``add_dirs``, so implement/QA agents get filesystem access to
    every affected repo AND the docs root holding story/plan files — mirroring how
    resolve-review-context.py grants it to the review agents; see
    docs/repo-modes.md for why the docs root cannot be inferred from the affected
     repos alone).
  - ``qa_source_roots_json``: JSON-encoded ``SURFACE=PATH`` arguments for
    ``ostler qa context``. One repository root is emitted per affected surface.

Resolution is deterministic and side-effect-free. A missing/garbled plan-context
degrades to empty lists (logged to stderr) so the implementer falls back to reading
the plan text — never a hard failure that aborts the run.

Usage: resolve-impl-context.py <spec_dir> [target_env] [docs_path]
Prints one JSON object on stdout (parsed by the local-worker ScriptNode).
"""

from __future__ import annotations

import json
import logging
import sys

from workhorse.scriptutil import (
    build_dispatch_list,
    find_docs_root,
    find_repo_root,
    get_affected_repos,
    load_json,
    resolve_workspace,
)

MANIFEST_REL = ".agents/agents-context.json"


def main(logger: logging.Logger) -> None:
    spec_dir_rel = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else ""
    target_env = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else "local"
    docs_path_arg = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else ""
    # `root` is the orchestrating repo (AGENT_REPO_DIR) — where the context manifest
    # (.agents/agents-context.json) and library live. `docs_root` is the docs repo
    # (story/spec/plan-context.json) — a separate concept that may or may not be
    # the same directory, may not be a git repo, and may not have an agents.yml (see
    # docs/repo-modes.md). Never conflate the two: use `docs_path_arg` explicitly
    # rather than inferring the docs root by walking up from CWD.
    root = find_repo_root()
    docs_root = find_docs_root(docs_path_arg)

    plan_ctx_path = root / spec_dir_rel / "plan-context.json" if spec_dir_rel else None
    plan_ctx = (
        load_json(plan_ctx_path, "plan-context.json", logger) if plan_ctx_path else {}
    )
    plan_ctx_absent = not plan_ctx_path or not plan_ctx_path.exists()
    manifest = load_json(root / MANIFEST_REL, "context manifest", logger)

    instructions: dict[str, str] = manifest.get("instructions") or {}
    services = plan_ctx.get("services") or []
    qa_stack = plan_ctx.get("qa_stack") or {}

    repos = resolve_workspace("CODER_WORKSPACE")

    # Resolve instruction paths from all services' skills, deduplicated in order.
    impl_instruction_paths: list[str] = []
    seen_instructions: set[str] = set()
    for svc in services:
        for skill_name in svc.get("skills") or []:
            path = instructions.get(str(skill_name).replace(".", "-"))
            if not path:
                logger.warning("skill '%s' not in repo manifest — skipping", skill_name)
                continue
            if path not in seen_instructions:
                seen_instructions.add(path)
                impl_instruction_paths.append(path)

    # Fall back to a single repo-root dispatch whenever the plan has no services —
    # whether plan-context.json is absent OR present in the legacy flat form
    # (touched_layers only). Without this, a legacy/serviceless plan-context yields an
    # EMPTY dispatch_list and the implement/QA per-service loop degenerates to nothing.
    dispatch_list = build_dispatch_list(
        plan_ctx, repos, fallback=plan_ctx_absent or not services
    )

    # QA run plan: one entry per non-infra/docs service.
    qa_run_plan: list[dict] = []
    for entry in dispatch_list:
        if entry["type"] in ("terraform", "docs"):
            continue
        all_skills = entry["qa_skills"]
        # local-only skills (those ending in -local) are irrelevant when running against DEV
        skills = [
            s for s in all_skills if target_env == "local" or not s.endswith("-local")
        ]
        qa_run_plan.append(
            {
                "service": entry["service"],
                "label": entry["label"],
                "qa_mode": entry["qa_mode"],
                "qa_skill": skills[0] if skills else "",
                "qa_skills": skills,
            }
        )

    affected_repos = get_affected_repos(plan_ctx, repos)
    affected_repo_paths = [
        repos[name]["path"] for name in affected_repos if name in repos
    ]
    # Every dispatch's cwd is one specific service repo (current_layer.cwd); the
    # story/spec/plan files always live in the docs root, which is not necessarily
    # one of the plan's affected services (and may not even be a workspace folder —
    # see docs/repo-modes.md). Grant it explicitly so implement_layer/implement_fix's
    # add_dirs covers it — otherwise a backend with a per-repo path sandbox (e.g.
    # Copilot) can read/write its own service repo but gets "permission denied" on
    # the story/plan files it was told to implement.
    docs_root_str = str(docs_root)
    if docs_root_str not in affected_repo_paths:
        affected_repo_paths = [docs_root_str, *affected_repo_paths]

    qa_source_roots: list[str] = []
    seen_source_roots: set[str] = set()
    for entry in dispatch_list:
        surface = str(entry.get("repo") or entry.get("service") or "").strip()
        source_path = str(entry.get("cwd") or "").strip()
        source_root = f"{surface}={source_path}" if surface and source_path else ""
        if source_root and source_root not in seen_source_roots:
            seen_source_roots.add(source_root)
            qa_source_roots.append(source_root)

    print(
        json.dumps(
            {
                "impl_instruction_paths": impl_instruction_paths,
                "qa_run_plan": qa_run_plan,
                "qa_stack": qa_stack,
                "dispatch_list": dispatch_list,
                "dispatch_count": str(len(dispatch_list)),
                "affected_repos": affected_repos,
                "affected_repo_paths": affected_repo_paths,
                "qa_source_roots_json": json.dumps(qa_source_roots),
            }
        )
    )


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(name)s %(levelname)s: %(message)s",
    )
    main(logging.getLogger("resolve-impl-context"))
