"""Bring a book's stack up and run its compiled plan through ostler — family-neutral."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from ostler import Ostler, graph as graph_mod, model, path as path_mod
from ostler.model import Graph, UINode
from ostler.qa import runbook, stack

from workhorse_workflows.kit.qa.schemas import QaPlanRun, QaStatus, StackStatus
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.kit.credentials import scoped_envs
from workhorse_workflows.kit.qa.support import QA_PLAN_FILE, notes_for

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
    near_path = Path(near) if near else None
    if not runbook.has_served_surface(graph, near_path):
        return StackStatus(
            ready="unneeded",
            notes=("The book serves nothing — no `screen`, no `server` — so it has no stack "
                   "to bring up, whatever runbooks it documents. QA scenarios invoke the "
                   "repo's commands directly."),
        )
    manifests, selection = runbook.load_stacks(graph, near=near_path, logger=logger)
    if not manifests:
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
    owned = tuple(
        r["app_pgid"] for r in results
        if r.get("app_pgid") and r.get("adopted") != "yes" and r["app_pgid"].isdigit() and _group_running(int(r["app_pgid"])))
    app_logs = tuple(r["app_log"] for r in results if r.get("app_log"))
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
            ready="yes", notes=f"Stack {how} and healthy at {where}{plural}.",
            owned_pgids=owned, app_logs=app_logs, **common)

    common = {
        "app_pid": last.get("app_pid", ""),
        "app_pgid": last.get("app_pgid", ""),
        "entry_url": last.get("entry_url", ""),
        "failed_step": last.get("failed_step", ""),
    }
    manifest = last.get("manifest") or {}
    return StackStatus(
        ready="no",
        notes=bring_up_failure(
            last.get("failed_step", "unknown"), (last.get("error") or "").strip(),
            manifest.get("source", "")),
        owned_pgids=owned,
        app_logs=app_logs,
        **common,
    )


def release_stack(logger: logging.Logger, owned_pgids: tuple[str, ...]) -> None:
    """Stop the process groups a bring-up started, newest first, and leave an adopted one up.

    It never raises, because ostler's teardown fails soft on a process group, so a caller releases
    in a `finally` and a failure of the work it wraps is never masked.
    """
    for pgid in reversed(owned_pgids):
        _ = stack.teardown_app(pgid, "", "", logger=logger)


def _group_running(pgid: int) -> bool:
    """Whether a process other than a zombie is left in the process group *pgid*."""
    for stat in Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = stat.read_text(encoding="ascii", errors="replace").rpartition(")")[2].split()
        except OSError:
            continue
        if len(fields) > 2 and fields[2] == str(pgid) and fields[0] != "Z":
            return True
    return False


def stack_stopped(owned_pgids: tuple[str, ...]) -> str:
    """Why the app stopped serving: a process group bring-up launched and left serving has no process left, or nothing when each still runs.

    Bring-up owns a group only when its launch command was still running once the app answered,
    and only when the group still runs once every stack is up, since a later stack's bring-up
    reaps a server an earlier one left on the same port. A group that empties afterwards is a
    server that exited, never a bring-up that handed off.
    """
    for pgid in owned_pgids:
        if pgid.isdigit() and not _group_running(int(pgid)):
            return (f"the server the stack's bring-up launched (process group {pgid}) exited during the run, "
                    "so the app stopped serving and no later scenario could reach it; the runbook step that "
                    "launches it must start a server that keeps serving until the run stops it, with no "
                    "time limit of its own")
    return ""


def bring_up_failure(step: str, error: str, source: str) -> str:
    """Why bring-up failed, and which side repairs it: the runbook, or the app when it serves no health route."""
    failed = f"Stack bring-up failed at step '{step}'" + (f": {error}" if error else "")
    if stack.ROUTE_MISSING in error:
        return (
            f"{failed} Point `health-path` in the runbook at `{source}` at the health route "
            "the app serves. If the app serves none, the app is what is missing a feature: "
            "it must implement a health route before its book can run."
        )
    return (
        f"{failed}. Repair the runbook at `{source}` or its seed recipe "
        "(never background the stack in the agent shell)."
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


__all__ = ["ensure_stack", "run_qa_plan", "stack_stopped"]
