"""Shared utilities for workhorse workflow scripts.

Workflow scripts that need workspace resolution, JSON/JSONC parsing, or git/gh
operations import from here rather than maintaining a local ``lib/`` directory:

    from workhorse.scriptutil import resolve_workspace, load_json, build_dispatch_list

Because workhorse is installed editable (``pip install -e``), this module is
available to any script invoked via ``sys.executable``.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from git import Repo


def load_jsonc(text: str) -> dict:
    """Parse JSON with Comments (trailing commas, // comments) as used by VSCode."""
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return json.loads(text)


def load_json(path: Path, label: str, logger: logging.Logger) -> dict:
    """Load a JSON file; logs warnings via caller's logger. Returns {} on failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("%s not found at %s", label, path)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("%s unreadable at %s: %s", label, path, exc)
    return {}


def _read_workspace_file(workspace_env_key: str) -> tuple[list[dict], Path] | None:
    """Parse the `.code-workspace` file named by ``workspace_env_key``, if set.

    Returns ``(folders, ws_dir)`` when the env var points at an existing file,
    else ``None`` — callers apply their own single-folder fallback in that case,
    since resolve_workspace() (read an existing checkout) and checkout_workspace()
    (create one) fall back differently.
    """
    workspace_path = os.environ.get(workspace_env_key)
    if not workspace_path or not Path(workspace_path).exists():
        return None
    ws = load_jsonc(Path(workspace_path).read_text(encoding="utf-8"))
    ws_dir = Path(workspace_path).parent
    return ws.get("folders", []), ws_dir


def resolve_workspace(workspace_env_key: str = "WORKSPACE_FILE") -> dict[str, dict]:
    """Build {repo_name: {path, ...}} from workspace file or CWD fallback.

    Resolution order:
    1. Read the env var named by ``workspace_env_key`` (caller-supplied; default
       ``WORKSPACE_FILE`` for generic use). Workflow scripts should pass their
       own convention (e.g. ``"CODER_WORKSPACE"``).
    2. If that env var points to an existing file, parse it as a VSCode workspace.
    3. Otherwise treat the repo root as a single-folder workspace.

    For each folder, reads agents.yml and merges the workspace: section into the record.
    """
    parsed = _read_workspace_file(workspace_env_key)
    if parsed is not None:
        folders, ws_dir = parsed
    else:
        # Script nodes run with cwd = the workflow definition's own directory, not the
        # consuming repo (see main.py's AGENT_REPO_DIR comment), so a bare Path.cwd()
        # here would synthesize a single-folder workspace keyed off the workflow dir's
        # name (e.g. "coder") instead of the real repo. Mirror find_repo_root()'s
        # AGENT_REPO_DIR-first resolution so mono-repo setups (no CODER_WORKSPACE) key
        # correctly off the actual repo.
        cwd = Path(os.environ.get("AGENT_REPO_DIR") or Path.cwd()).resolve()
        agents_yml = cwd / "agents.yml"
        if agents_yml.exists():
            try:
                meta = yaml.safe_load(agents_yml.read_text(encoding="utf-8")) or {}
                cwd_name = (meta.get("repo") or {}).get("name") or cwd.name
            except (yaml.YAMLError, OSError):
                cwd_name = cwd.name
        else:
            cwd_name = cwd.name
        folders = [{"name": cwd_name, "path": str(cwd)}]
        ws_dir = cwd.parent

    repos: dict[str, dict] = {}
    for folder in folders:
        name = folder.get("name", Path(folder["path"]).name)
        abs_path = (ws_dir / folder["path"]).resolve()
        agents_yml = abs_path / "agents.yml"
        if agents_yml.exists():
            try:
                meta = yaml.safe_load(agents_yml.read_text(encoding="utf-8"))
            except (yaml.YAMLError, OSError):
                repos[name] = {"path": str(abs_path)}
                continue
            ws_section = meta.get("workspace") or {}
            template = meta.get("template") or {}
            repos[name] = {"path": str(abs_path), "template": template, **ws_section}
        else:
            repos[name] = {"path": str(abs_path)}
    return repos


def _has_unsynced_work(dest: Path, branch: str) -> bool:
    """True if ``dest`` has uncommitted changes or commits not on ``origin/<branch>``.

    Used by ``checkout_workspace`` to tell "container restarted mid-run, resume
    where we left off" apart from "clean checkout, safe to fast-forward to the
    host's latest commit" — a bare reset can't distinguish the two, and would
    otherwise silently discard uncommitted in-container work (e.g. a blocked
    operator-gate node's edits) on every restart.
    """
    status = subprocess.run(
        ["git", "-C", str(dest), "status", "--porcelain"], capture_output=True, text=True, check=True,
    )
    if status.stdout.strip():
        return True
    ahead = subprocess.run(
        ["git", "-C", str(dest), "rev-list", "--count", f"origin/{branch}..HEAD"],
        capture_output=True, text=True, check=True,
    )
    return ahead.stdout.strip() != "0"


def checkout_workspace(
    workspace_env_key: str = "CODER_WORKSPACE",
    workspace_root: str | Path = "/workspace",
) -> None:
    """Clone/update every `url`-bearing folder in the `.code-workspace` file into
    ``workspace_root``, transparent to whichever workflow graph runs next.

    Meant to be invoked once from entrypoint.sh, before the workflow engine starts —
    neither coder nor author has a "setup" node; by the time the graph starts, every
    folder's working tree already exists under ``workspace_root/<folder name>``.

    Resolution order:
    1. If the workspace file (named by ``workspace_env_key``) is set, clone/update
       every folder in its `folders` list that carries a `url` key (its own optional
       schema extension — VSCode ignores unknown keys, so plain `.code-workspace`
       files stay valid whether or not they use it). A missing `branch` defaults to
       "main". Folders WITHOUT a `url` are left untouched — they may not be git repos
       at all (e.g. a plain documentation directory); their content can only reach the
       container via the workspace-directory bind mount (see compose.yaml), not a clone.
    2. Otherwise (no workspace file set), synthesize a single folder from the existing
       REPO_URL/REPO_NAME/REPO_BRANCH env vars (today's single-primary-repo mechanism)
       and feed it through the exact same clone path — this keeps 1-repo and N-repo
       runs on one code path with zero repo-name defaulting. Cloning from a local
       bind-mounted path (Predykt's read-only host-working-tree trick) works exactly
       like cloning from a remote, so nothing about that mechanism needs to change.
    """
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[checkout] %(message)s")
    logger = logging.getLogger("workhorse.checkout")
    workspace_root = Path(workspace_root)

    parsed = _read_workspace_file(workspace_env_key)
    if parsed is not None:
        folders, _ws_dir = parsed
    else:
        repo_url = os.environ.get("REPO_URL", "")
        if not repo_url:
            logger.info("no workspace file and no REPO_URL set — nothing to check out")
            return
        folders = [{
            "name": os.environ.get("REPO_NAME") or "repo",
            "url": repo_url,
            "branch": os.environ.get("REPO_BRANCH", "main"),
        }]

    workspace_root.mkdir(parents=True, exist_ok=True)

    for folder in folders:
        url = folder.get("url")
        if not url:
            continue
        name = folder.get("name") or Path(folder["path"]).name
        branch = folder.get("branch", "main")
        dest = workspace_root / name

        if (dest / ".git").exists():
            subprocess.run(["git", "-C", str(dest), "fetch", "--quiet", "origin"], check=True)
            if _has_unsynced_work(dest, branch):
                logger.info(
                    "%s has uncommitted changes or commits not on origin/%s — "
                    "preserving existing checkout, skipping reset",
                    name, branch,
                )
                continue
            logger.info("updating %s from %s (%s)", name, url, branch)
            subprocess.run(["git", "-C", str(dest), "checkout", "--quiet", branch], check=True)
            subprocess.run(["git", "-C", str(dest), "reset", "--quiet", "--hard", f"origin/{branch}"], check=True)
        else:
            logger.info("cloning %s from %s (%s)", name, url, branch)
            subprocess.run(
                ["git", "clone", "--quiet", "--branch", branch, "--single-branch", url, str(dest)],
                check=True,
            )


def find_repo_root() -> Path:
    """Find repo root via AGENT_REPO_DIR env or walking up from CWD."""
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return here


def find_docs_root(docs_path: str = "") -> Path:
    """Resolve the docs repo root.

    Priority:
    1. Explicit ``docs_path`` argument (from workflow var)
    2. ``CODER_DOCS_PATH`` environment variable
    3. Falls back to ``find_repo_root()`` (AGENT_REPO_DIR / CWD walk)
    """
    path = docs_path or os.environ.get("CODER_DOCS_PATH", "")
    if path:
        p = Path(path)
        if p.is_absolute():
            return p.resolve()
        return (find_repo_root() / p).resolve()
    return find_repo_root()


def get_repo_config(repo_name: str, key: str, default=None, *, repos: dict | None = None):
    """Get a config value from a repo's agents.yml workspace section.

    Examples:
        get_repo_config("olympus", "qa_mode")            # → "cli"
        get_repo_config("olympus", "base_branch", "main") # → "develop"
    """
    if repos is None:
        repos = resolve_workspace()
    repo = repos.get(repo_name, {})
    return repo.get(key, default)


def build_dispatch_list(plan_ctx: dict, repos: dict[str, dict], *, fallback: bool = False) -> list[dict]:
    """Build ordered dispatch records from plan-context.json + workspace repos.

    When ``fallback=True`` and the plan has no services (i.e., plan-context.json is
    absent or empty), returns a single fallback record using the first workspace repo.
    Pass ``fallback=True`` only from callers that know the plan-context was not found.
    """
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
            "skills": svc.get("skills", []),
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
            "skills": [],
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


def open_repo(path: str | Path) -> Repo:
    # Import GitPython lazily: importing it runs a `git --version` probe at import
    # time, which crashes (IndexError parsing the version) whenever `git` is shadowed
    # by a stub — e.g. the workflow test harness mocks `git`, returning empty output.
    # Only the handful of scripts that actually open a repo should pay that cost; the
    # many git-free scripts (select-next-*, resolve-*, detect-*) must import this
    # module without needing a real git on PATH.
    from git import Repo

    return Repo(str(path))


def run_gh(args: list[str], cwd: str | Path, logger: logging.Logger) -> subprocess.CompletedProcess:
    """Run gh CLI command. Logs and raises RuntimeError on failure."""
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd),
    )
    if result.returncode != 0:
        logger.error("gh %s failed (exit %d): %s", " ".join(args), result.returncode, result.stderr.strip())
        raise RuntimeError(f"gh {args[0]} failed: {result.stderr.strip()}")
    return result
