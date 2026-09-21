"""Bring a book's stack up and run its compiled plan through ostler — family-neutral."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from ostler import Ostler, graph as graph_mod, model, path as path_mod
from ostler.model import Graph, UINode
from ostler.qa import runbook

from workhorse_workflows.coder.shared.schemas.qa import QaPlanRun, QaStatus, StackStatus
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.kit.credentials import scoped_envs
from workhorse_workflows.qa.support import QA_PLAN_FILE, notes_for

RUN_STATUSES: dict[str, QaStatus] = {
    "passed": "passed",
    "failed": "failed",
    "blocked": "blocked",
    "invalid": "invalid",
}

SECRET_MINT_TIMEOUT_S = 60.0


def _entry_result(
    results: list[dict],
    runbooks: tuple[UINode, ...],
    near: str,
    graph: Graph,
) -> dict:
    """Of a successful bring-up, the result the caller actually needs to drive."""
    if near and len(results) > 1:
        near_path = Path(near)
        features_root = path_mod.features_root(graph)
        near_abs = near_path if near_path.is_absolute() else graph.root / near_path
        target_surface = graph_mod.surface_of(near_abs, features_root)
        if target_surface:
            for result, node in zip(results, runbooks, strict=False):
                if graph_mod.surface_of(node.path, features_root) == target_surface:
                    return result
    return results[-1]


def _merge_secrets(manifests: list[dict]) -> tuple[dict[str, str], str]:
    """Every manifest's mint recipes in one namespace, or the reason there cannot be one."""
    secrets: dict[str, str] = {}
    sources: dict[str, str] = {}
    for manifest in manifests:
        source = manifest.get("source", "?")
        for name, recipe in (manifest.get("secrets") or {}).items():
            if name in secrets and secrets[name] != recipe:
                return {}, (
                    f"The stack declares secret {name!r} twice with different mint "
                    f"recipes: {sources[name]} and {source}. A QA run substitutes "
                    "secrets by name into one environment, so it cannot hold both. "
                    "Give them distinct names, or declare one recipe both services use.")
            secrets[name] = recipe
            sources.setdefault(name, source)
    return secrets, ""


def ensure_stack(
    logger: logging.Logger,
    docs_path: str = "",
    repo_dir: str = "",
    near: str = "",
) -> StackStatus:
    """Bring the durable QA stack up (or adopt one already serving) before the runner."""
    root = find_docs_root(docs_path, repo_dir)
    graph = model.load(root)
    manifests, selection = runbook.load_stacks(
        graph, near=Path(near) if near else None, logger=logger)
    if not manifests:
        if not runbook.has_served_surface(graph):
            return StackStatus(
                ready="unneeded",
                notes=("The book serves nothing — no `screen`, no `server` — so an empty "
                       "stack is its documented topology. QA scenarios invoke the repo's "
                       "commands directly; there is nothing to bring up first."),
            )
        if selection.reason == "ambiguous":
            return StackStatus(
                ready="none",
                notes=(f"The book declares {len(selection.candidates)} stack runbooks "
                       "across several environments and names none, so bring-up would "
                       "have to guess which system to start: "
                       f"{', '.join(selection.candidates)}. Bind the ones that serve one "
                       "system to a shared `environment:` node, or say which one to bring "
                       "up — there is no missing runbook to author here."),
            )
        return StackStatus(
            ready="none",
            notes=("The book describes a served surface but declares no stack — no stack "
                   "`runbook` node and no `server` node — so QA would run "
                   "against nothing. Author the runbook that brings it up; `ostler doctor` "
                   "reports this as `runbook-missing`."),
        )

    results = runbook.bring_up_stacks(manifests, repo_root=str(root), logger=logger)
    last = results[-1]
    if last.get("ready") == "yes":
        chosen = _entry_result(results, selection.runbooks, near, graph)
        common = {
            "app_pid": chosen.get("app_pid", ""),
            "app_pgid": chosen.get("app_pgid", ""),
            "entry_url": chosen.get("entry_url", ""),
            "failed_step": chosen.get("failed_step", ""),
        }
        how = "adopted" if chosen.get("adopted") == "yes" else "brought up"
        where = ", ".join(r.get("entry_url") or "(no entry url)" for r in results)
        plural = "" if len(results) == 1 else f" ({len(results)} services)"
        return StackStatus(
            ready="yes", notes=f"Stack {how} and healthy at {where}{plural}.", **common)

    common = {
        "app_pid": last.get("app_pid", ""),
        "app_pgid": last.get("app_pgid", ""),
        "entry_url": last.get("entry_url", ""),
        "failed_step": last.get("failed_step", ""),
    }
    step = last.get("failed_step", "unknown")
    error = (last.get("error") or "").strip()
    manifest = last.get("manifest") or {}
    return StackStatus(
        ready="no",
        notes=(
            f"Stack bring-up failed at step '{step}'"
            + (f": {error}" if error else "")
            + f". Repair the runbook at `{manifest.get('source', '')}` or its seed recipe "
            "(never background the stack in the agent shell)."
        ),
        **common,
    )


def _mint_qa_secrets(
    secrets: dict[str, str], root: Path, logger: logging.Logger
) -> tuple[dict[str, str], str]:
    """Run the runbook's `secrets:` recipes; return ``({NAME: token}, error)``."""
    minted: dict[str, str] = {}
    cwd = str(root.resolve())
    for name, recipe in secrets.items():
        if not name or not recipe:
            return {}, f"secret `{name or '(unnamed)'}` declares no mint recipe"
        try:
            result = subprocess.run(  # noqa: S602 (documented repo-owned recipe)
                recipe, shell=True, cwd=cwd, capture_output=True, text=True,
                timeout=SECRET_MINT_TIMEOUT_S, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {}, f"mint command for {name} could not be run: {exc}"
        if result.returncode != 0:
            return {}, (
                f"mint command for {name} exited {result.returncode}: "
                f"{result.stderr.strip()[:500]}"
            )
        token = result.stdout.strip()
        if not token:
            return {}, f"mint command for {name} produced no output"
        minted[name] = token
    if minted:
        logger.info("minted fresh QA secrets for %s", ", ".join(minted))
    return minted, ""


def run_qa_plan(
    logger: logging.Logger,
    spec_dir: str = "",
    docs_path: str = "",
    repo_dir: str = "",
    only: list[str] | None = None,
    plan_file: str | None = None,
) -> QaPlanRun:
    """Execute the QA plan through ostler and normalize its four-state outcome."""
    docs_root = find_docs_root(docs_path, repo_dir)
    plan = plan_file if plan_file is not None else str(Path(spec_dir) / QA_PLAN_FILE)
    docs_graph = model.load(docs_root)
    near = str(docs_root / spec_dir) if spec_dir else ""
    manifests, _selection = runbook.load_stacks(
        docs_graph, near=Path(near) if near else None, logger=logger)
    secrets, collision = _merge_secrets(manifests)
    if collision:
        return QaPlanRun(status="blocked", notes=collision)
    minted, error = _mint_qa_secrets(secrets, docs_root, logger)
    if error:
        logger.warning("QA secret refresh failed: %s", error)
        return QaPlanRun(status="blocked", notes=f"QA secret refresh failed: {error}")
    with scoped_envs(minted):
        outcome = Ostler(docs_root).qa_run(plan, spec=spec_dir, only=only)
    status = RUN_STATUSES.get(outcome.status.lower(), "invalid")
    notes = notes_for(outcome, f"Ostler QA run returned {status}.")
    logger.info("ostler qa run for %s returned status=%s", spec_dir, status)
    return QaPlanRun(status=status, notes=notes, ostler=outcome.data)


__all__ = ["ensure_stack", "run_qa_plan"]
