"""A story's plan context: loading `plan-context.json`, projecting it, and the dispatch order."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ostler import Ostler
from workhorse_workflows.kit import find_docs_root, find_repo_root, load_json, resolve_workspace
from workhorse_workflows.coder.shared.contract import service_problems
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.dev import (
    DispatchEntry,
    ImplContext,
    PlanFixture,
    PlanSummary,
    PlanValidation,
    QaRunEntry,
    lift_fixture,
)


def _spec_dir(spec_dir: str, root: Path) -> Path:
    """A spec dir as an absolute path, taken relative to `root` unless already absolute."""
    path = Path(spec_dir)
    return path if path.is_absolute() else root / path


def _spec_relative(plan_file: str, spec_abs: Path | None, root: Path | None) -> str:
    """`plan_file` as the spec-relative path it is declared to be, under either reading."""
    if not plan_file or spec_abs is None or root is None:
        return plan_file
    if (spec_abs / plan_file).is_file():
        return plan_file
    candidate = Path(plan_file)
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if not resolved.is_file():
        return plan_file
    try:
        return resolved.relative_to(spec_abs.resolve()).as_posix()
    except ValueError:
        return plan_file


def plan_document(
    plan: dict[str, Any],
    repos: dict[str, dict],
    spec_abs: Path | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """The plan-context mapping, built from a `PlanResult` and the resolved workspace."""
    canon_by_lower = {name.lower(): name for name in repos}

    def canon(repo_name: str) -> str:
        return repo_name if repo_name in repos else canon_by_lower.get(repo_name.lower(), repo_name)

    def entry(svc: Any) -> dict[str, Any]:
        svc = dict(svc or {})
        svc["repo"] = canon(str(svc.get("repo", "")))
        if "plan_file" in svc:
            svc["plan_file"] = _spec_relative(str(svc.get("plan_file", "")), spec_abs, root)
        return svc

    services = [entry(svc) for svc in plan.get("services") or []]
    order = [
        f"{canon(str(item).split('::', 1)[0])}::{str(item).split('::', 1)[1]}"
        if "::" in str(item)
        else str(item)
        for item in plan.get("implementation_order") or []
    ]
    return {
        "services": services,
        "implementation_order": order,
        "shared_packages": [entry(pkg) for pkg in plan.get("shared_packages") or []],
        "verification_setup": _verification_setup(plan),
        "fixtures": _fixtures(plan),
    }


def _verification_setup(doc: dict[str, Any]) -> dict[str, Any]:
    """The story's `## Verification setup`, under either spelling."""
    return doc.get("verification_setup") or doc.get("qa_stack") or {}


def _fixtures(doc: dict[str, Any]) -> list[dict[str, str]]:
    """The story's declared fixtures, from the typed field or nested in the setup block."""
    raw = doc.get("fixtures")
    if not isinstance(raw, list):
        setup = _verification_setup(doc)
        raw = setup.get("fixtures")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, str):
            out.append({"name": "", "provides": "", **lift_fixture(item)})
        elif isinstance(item, dict):
            out.append(
                {"name": str(item.get("name", "")), "provides": str(item.get("provides", ""))}
            )
    return [item for item in out if item["name"] or item["provides"]]


def build_dispatch_list(plan_ctx: dict, repos: dict[str, dict], *, fallback: bool = False) -> list[dict]:
    """Build ordered dispatch records from plan-context.json + workspace repos."""
    services = plan_ctx.get("services") or []
    impl_order = plan_ctx.get("implementation_order") or []

    service_map: dict[str, dict] = {}
    for svc in services:
        key = f"{svc['repo']}::{svc['path']}"
        service_map[key] = svc

    ordered_keys = impl_order if impl_order else [f"{s['repo']}::{s['path']}" for s in services]

    dispatch_list: list[dict] = []
    for key in ordered_keys:
        svc = service_map.get(key)
        if not svc:
            continue
        repo_name = svc["repo"]
        repo_info = repos.get(repo_name, {})
        repo_path = repo_info.get("path", "")
        template = repo_info.get("template") or {}
        svc_type = svc.get("type", "unknown")
        label = template.get("backend_layer_name") or template.get("mobile_layer_name") or svc_type

        dispatch_list.append({
            "service": key,
            "repo": repo_name,
            "cwd": repo_path,
            "service_path": svc["path"],
            "type": svc_type,
            "plan_file": svc.get("plan_file", "plan.md"),
            "qa_mode": repo_info.get("qa_mode", "cli"),
            "qa_skills": repo_info.get("qa_skills", []),
            "verification": repo_info.get("verification", ""),
            "label": label,
        })

    if fallback and not dispatch_list and repos:
        repo_name = next(iter(repos))
        repo_info = repos[repo_name]
        dispatch_list = [{
            "service": f"{repo_name}::.",
            "repo": repo_name,
            "cwd": repo_info.get("path", "."),
            "service_path": ".",
            "type": "unknown",
            "plan_file": "plan.md",
            "qa_mode": repo_info.get("qa_mode", "cli"),
            "qa_skills": [],
            "verification": repo_info.get("verification", ""),
            "label": repo_name,
        }]

    return dispatch_list


def get_affected_repos(plan_ctx: dict, repos: dict[str, dict]) -> list[str]:
    """Deduplicated sorted list of repo names from plan-context services."""
    names: set[str] = set()
    for svc in plan_ctx.get("services") or []:
        name = svc.get("repo", "")
        if name and name in repos:
            names.add(name)
    return sorted(names)


def load_plan_context(root: Path, spec_dir: str, logger: logging.Logger) -> dict[str, Any]:
    """The `plan-context.json` under a story's spec dir, or `{}` when there is none."""
    if not spec_dir:
        return {}
    return load_json(_spec_dir(spec_dir, root) / "plan-context.json", "plan-context.json", logger)


def plan_context(
    plan: dict[str, Any] | None, spec_dir: str, root: Path, repos: dict[str, dict],
    logger: logging.Logger,
) -> tuple[dict[str, Any], bool]:
    """The plan document and whether it had to be read off disk."""
    if plan:
        spec_abs = _spec_dir(spec_dir, root) if spec_dir else None
        return plan_document(plan, repos, spec_abs, root), False
    absent = not spec_dir or not (_spec_dir(spec_dir, root) / "plan-context.json").exists()
    return load_plan_context(root, spec_dir, logger), absent


def _dispatched_plan_problems(
    doc: dict[str, Any], repos: dict[str, dict], spec_abs: Path
) -> list[str]:
    """Every plan file the dispatcher will hand an implementer, opened to prove it is there."""
    problems: list[str] = []
    for entry in build_dispatch_list(doc, repos, fallback=not (doc.get("services") or [])):
        plan_file = entry.get("plan_file") or "plan.md"
        try:
            (spec_abs / plan_file).read_text(encoding="utf-8")
        except OSError as exc:
            problems.append(
                f"{entry['service']}: plan file '{plan_file}' is not readable in the spec "
                f"dir ({exc.strerror or exc})"
            )
    return problems


@blueprint.node
def record_plan(
    logger: logging.Logger,
    plan: dict[str, Any] | None = None,
    spec_dir: str = "",
    repo_dir: str = "",
    workspace_file: str = "",
) -> PlanValidation:
    """Write the plan-context projection, and answer whether the plan is implementable."""
    if not spec_dir:
        return PlanValidation(status="invalid", errors=["spec_dir argument is empty"])

    root = find_repo_root(repo_dir)
    spec_abs = _spec_dir(spec_dir, root)
    repos = resolve_workspace(workspace_file, repo_dir)
    doc = plan_document(plan or {}, repos, spec_abs, root)

    spec_abs.mkdir(parents=True, exist_ok=True)
    (spec_abs / "plan-context.json").write_text(
        json.dumps(doc, indent=2) + "\n", encoding="utf-8"
    )
    logger.info("wrote plan-context.json projection (%d service(s))", len(doc["services"]))

    services = doc["services"]
    errors: list[str] = _dispatched_plan_problems(doc, repos, spec_abs)
    if not services:
        return PlanValidation(
            status="invalid" if errors else "valid", errors=errors, document=doc
        )

    vetted = Ostler(root).artifact_vet("plan-context", spec_dir)
    if vetted.data.get("error"):
        errors.append(f"[ostler] plan-context could not be vetted ({vetted.data['error']}).")
    errors.extend(f"[ostler] {p}" for p in vetted.data.get("problems", []))

    declared = {f"{svc.get('repo', '')}::{svc.get('path', '')}" for svc in services}
    for item in doc["implementation_order"]:
        if item not in declared:
            known = ", ".join(sorted(declared))
            errors.append(
                f"implementation_order names '{item}', which is not a declared service "
                f"(declared: {known})"
            )

    for svc in services:
        repo_name = svc.get("repo", "")
        svc_path = svc.get("path", "")
        label = f"{repo_name}::{svc_path}"

        if repo_name not in repos:
            valid = ", ".join(sorted(repos)) or "<none>"
            errors.append(f"{label}: repo '{repo_name}' not found in workspace (valid: {valid})")
            continue

        repo_info = repos[repo_name]
        if svc.get("new_service"):
            logger.info("%s: new_service=true — skipping path existence check", label)
            continue

        markers = repo_info.get("service_markers", [])
        problems = service_problems(Path(repo_info["path"]) / svc_path, markers, label)
        if problems:
            errors.extend(problems)
            continue

    return PlanValidation(
        status="invalid" if errors else "valid", errors=errors, document=doc
    )


def _package_label(item: Any) -> str:
    """One shared package as the `repo::path` string the QA prompts render."""
    if isinstance(item, dict):
        repo, path = str(item.get("repo", "")), str(item.get("path", ""))
        return f"{repo}::{path}" if repo and path else repo or path
    return str(item)


@blueprint.node
def resolve_impl_context(
    logger: logging.Logger,
    spec_dir: str = "",
    target_env: str = "local",
    docs_path: str = "",
    repo_dir: str = "",
    workspace_file: str = "",
    plan: dict[str, Any] | None = None,
) -> ImplContext:
    """Decode the approved plan against the workspace into everything downstream needs."""
    root = find_repo_root(repo_dir)
    docs_root = find_docs_root(docs_path, repo_dir)

    repos = resolve_workspace(workspace_file, repo_dir)
    plan_ctx, plan_ctx_absent = plan_context(plan, spec_dir, root, repos, logger)

    services = plan_ctx.get("services") or []

    dispatch = [
        DispatchEntry(**entry)
        for entry in build_dispatch_list(
            plan_ctx, repos, fallback=plan_ctx_absent or not services
        )
    ]

    qa_run_plan = [
        QaRunEntry(
            service=entry.service,
            label=entry.label,
            qa_mode=entry.qa_mode,
            qa_skill=skills[0] if skills else "",
            qa_skills=skills,
        )
        for entry in dispatch
        if entry.type not in ("terraform", "docs")
        for skills in [
            [s for s in entry.qa_skills if target_env == "local" or not s.endswith("-local")]
        ]
    ]

    affected_repos = get_affected_repos(plan_ctx, repos)
    affected_repo_paths = [repos[name]["path"] for name in affected_repos if name in repos]
    if str(docs_root) not in affected_repo_paths:
        affected_repo_paths = [str(docs_root), *affected_repo_paths]

    qa_source_roots: list[str] = []
    for entry in dispatch:
        surface = (entry.repo or entry.service).strip()
        source_path = entry.cwd.strip()
        if not surface or not source_path:
            continue
        source_root = f"{surface}={source_path}"
        if source_root not in qa_source_roots:
            qa_source_roots.append(source_root)

    return ImplContext(
        qa_run_plan=qa_run_plan,
        verification_setup=_verification_setup(plan_ctx),
        fixtures=[PlanFixture(**item) for item in _fixtures(plan_ctx)],
        shared_packages=[_package_label(item) for item in plan_ctx.get("shared_packages") or []],
        dispatch_list=dispatch,
        affected_repos=affected_repos,
        affected_repo_paths=affected_repo_paths,
        qa_source_roots=qa_source_roots,
    )


@blueprint.node
def plan_summary(
    logger: logging.Logger,
    spec_dir: str = "",
    repo_dir: str = "",
    workspace_file: str = "",
) -> PlanSummary:
    """The plan's structure, rendered for a turn in a lane that did not plan it."""
    root = find_repo_root(repo_dir)
    repos = resolve_workspace(workspace_file, repo_dir)
    plan_ctx, _ = plan_context(None, spec_dir, root, repos, logger)

    services = plan_ctx.get("services") or []
    if not services:
        return PlanSummary()

    lines = ["Services this story changes (from the plan):"]
    for svc in services:
        label = f"{svc.get('repo', '')}::{svc.get('path', '')}"
        plan_file = svc.get("plan_file", "") or "plan.md"
        lines.append(f"- {label} (type: {svc.get('type', '')}) — plan: {plan_file}")
    order = plan_ctx.get("implementation_order") or []
    if order:
        lines.append("Build order: " + " → ".join(str(item) for item in order))
    shared = [_package_label(item) for item in plan_ctx.get("shared_packages") or []]
    if shared:
        lines.append("Shared packages: " + ", ".join(shared))
    verification_setup = _verification_setup(plan_ctx)
    if verification_setup:
        lines.append("Verification setup: " + json.dumps(verification_setup))
    fixtures = _fixtures(plan_ctx)
    declared = [item for item in fixtures if item["name"]]
    if declared:
        lines.append(
            "Declared fixtures: "
            + ", ".join(
                f"{item['name']} ({item['provides']})" if item["provides"] else item["name"]
                for item in declared
            )
        )
    described = [item["provides"] for item in fixtures if not item["name"]]
    if described:
        lines.append("Arrangements this story described without declaring: " + "; ".join(described))
    return PlanSummary(text="\n".join(lines))


__all__ = [
    "build_dispatch_list",
    "get_affected_repos",
    "load_plan_context",
    "plan_context",
    "plan_document",
    "plan_summary",
    "record_plan",
    "resolve_impl_context",
]
