"""Workspace resolution: which repos a run spans, where they are, and getting them."""
from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from pathlib import Path

import yaml

from workhorse_workflows.kit import credentials, jsonio
from workhorse_workflows.kit import paths as paths_kit


def _repo_name_from_dir(path: Path) -> str:
    """A repo's name: its directory name, normalized the same way farrier's kebab() derives the install prefix, so the key here and the prefix on that repo's installed skills are the same string by construction."""
    name = re.sub(r"[^a-zA-Z0-9/-]+", "-", path.name.replace(".", "-").replace("_", "-"))
    return re.sub(r"-+", "-", name).strip("-").lower()


def _read_workspace_file(workspace_file: str | Path) -> tuple[list[dict], Path] | None:
    """Parse the `.code-workspace` file at ``workspace_file``, if it exists."""
    if not workspace_file or not Path(workspace_file).exists():
        return None
    ws = jsonio.load_jsonc(Path(workspace_file).read_text(encoding="utf-8"))
    ws_dir = Path(workspace_file).parent
    return ws.get("folders", []), ws_dir


def resolve_workspace(
    workspace_file: str | Path = "", repo_dir: str | Path = ""
) -> dict[str, dict]:
    """Build {repo_name: {path, ...}} from a workspace file, or from ``repo_dir`` alone."""
    parsed = _read_workspace_file(workspace_file)
    if parsed is not None:
        folders, ws_dir = parsed
    else:
        cwd = paths_kit.find_repo_root(repo_dir)
        folders = [{"name": _repo_name_from_dir(cwd), "path": str(cwd)}]
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
    """True if ``dest`` has uncommitted changes or commits not on ``origin/<branch>``."""
    status = subprocess.run(
        ["git", "-C", str(dest), "status", "--porcelain"], capture_output=True, text=True, check=True,
        timeout=10,
    )
    if status.stdout.strip():
        return True
    ahead = subprocess.run(
        ["git", "-C", str(dest), "rev-list", "--count", f"origin/{branch}..HEAD"],
        capture_output=True, text=True, check=True, timeout=10,
    )
    return ahead.stdout.strip() != "0"


def _git_network_command(
    *args: str, token_env: str = credentials.GIT_CREDENTIAL_ENV
) -> list[str]:
    """Build a Git command with transient credentials for clone/fetch."""
    if not credentials.has_git_credential(token_env):
        return ["git", *args]
    credential_helper = (
        f'!f() {{ echo username=x-access-token; echo "password=${token_env}"; }}; f'
    )
    return ["git", "-c", f"credential.helper={credential_helper}", *args]


def _set_origin_url(dest: Path, url: str) -> None:
    """Make an existing persistent checkout follow the configured source."""
    current = subprocess.run(
        ["git", "-C", str(dest), "remote", "get-url", "origin"],
        capture_output=True, text=True, check=False, timeout=10,
    )
    if current.returncode == 0 and current.stdout.strip() == url:
        return
    action = "set-url" if current.returncode == 0 else "add"
    subprocess.run(
        ["git", "-C", str(dest), "remote", action, "origin", url],
        check=True, timeout=10,
    )


SOURCE_MODES = ("clone", "worktree")


def _add_worktree(source: Path, dest: Path, ref: str, name: str, logger: logging.Logger) -> None:
    """Give this run its own working tree of ``source``, at ``dest``."""
    if (dest / ".git").exists():
        logger.info("%s already has a working tree at %s — leaving it as it is", name, dest)
        return
    if not (source / ".git").exists():
        raise ValueError(
            f"worktree mode needs {name} to name a git repository on disk, "
            f"but {source} is not one. A remote URL cannot be a worktree source — "
            f"bind the repo into the container at its own host path."
        )

    subprocess.run(
        ["git", "-C", str(source), "worktree", "prune"], check=True, timeout=30
    )
    logger.info("adding worktree for %s at %s (detached at %s)", name, dest, ref)
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-C", str(source), "worktree", "add", "--detach", str(dest), ref],
        check=True, timeout=120,
    )


def checkout_workspace(
    workspace_file: str | Path = "",
    workspace_root: str | Path = "/workspace",
    *,
    repo_url: str = "",
    repo_name: str = "repo",
    repo_branch: str = "main",
    token_env: str = credentials.GIT_CREDENTIAL_ENV,
    source_mode: str = "clone",
    worktree_root: str | Path = "",
) -> None:
    """Clone/update every `url`-bearing folder in the `.code-workspace` file into ``workspace_root``, transparent to whichever workflow graph runs next."""
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[checkout] %(message)s")
    logger = logging.getLogger("workhorse.checkout")
    workspace_root = Path(workspace_root)
    if source_mode not in SOURCE_MODES:
        raise ValueError(
            f"unknown source mode {source_mode!r}; expected one of {', '.join(SOURCE_MODES)}"
        )
    tree_root = Path(worktree_root) if worktree_root else workspace_root

    parsed = _read_workspace_file(workspace_file)
    if parsed is not None:
        folders, _ws_dir = parsed
    else:
        if not repo_url:
            logger.info("no workspace file and no repo url given — nothing to check out")
            return
        folders = [{
            "name": repo_name or "repo",
            "url": repo_url,
            "branch": repo_branch or "main",
        }]

    workspace_root.mkdir(parents=True, exist_ok=True)

    for folder in folders:
        url = folder.get("url")
        if not url:
            continue
        name = folder.get("name") or Path(folder["path"]).name
        branch = folder.get("branch", "main")

        if source_mode == "worktree":
            _add_worktree(Path(url), tree_root / name, branch, name, logger)
            continue

        dest = workspace_root / name

        if (dest / ".git").exists():
            _set_origin_url(dest, url)
            subprocess.run(
                _git_network_command(
                    "-C", str(dest), "fetch", "--quiet", "origin", token_env=token_env
                ),
                check=True, timeout=300,
            )
            if _has_unsynced_work(dest, branch):
                logger.info(
                    "%s has uncommitted changes or commits not on origin/%s — "
                    "preserving existing checkout, skipping reset",
                    name, branch,
                )
                continue
            logger.info("updating %s from %s (%s)", name, url, branch)
            subprocess.run(
                ["git", "-C", str(dest), "checkout", "--quiet", branch],
                check=True, timeout=10,
            )
            subprocess.run(
                ["git", "-C", str(dest), "reset", "--quiet", "--hard", f"origin/{branch}"],
                check=True, timeout=10,
            )
        else:
            logger.info("cloning %s from %s (%s)", name, url, branch)
            subprocess.run(
                _git_network_command(
                    "clone", "--quiet", "--branch", branch, "--single-branch", url, str(dest),
                    token_env=token_env,
                ),
                check=True, timeout=600,
            )


def get_repo_config(
    repo_name: str,
    key: str,
    default=None,
    *,
    repos: dict | None = None,
    workspace_file: str | Path = "",
    repo_dir: str | Path = "",
):
    """Get a config value from a repo's agents.yml workspace section."""
    if repos is None:
        repos = resolve_workspace(workspace_file, repo_dir)
    repo = repos.get(repo_name, {})
    return repo.get(key, default)


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


def _main(argv: list[str] | None = None) -> int:
    """`python -m workhorse_workflows.kit.workspace` — the entrypoint.sh checkout step."""
    parser = argparse.ArgumentParser(prog="workhorse-checkout", description=__doc__)
    parser.add_argument("--workspace-file", default="", metavar="PATH",
                        help="A .code-workspace manifest listing the repos to check out.")
    parser.add_argument("--workspace-root", default="/workspace", metavar="DIR",
                        help="Directory the folders are checked out under.")
    parser.add_argument("--repo-url", default="", metavar="URL",
                        help="Single-repo fallback when no workspace file is given.")
    parser.add_argument("--repo-name", default="repo", metavar="NAME")
    parser.add_argument("--repo-branch", default="main", metavar="BRANCH")
    parser.add_argument("--token-env", default=credentials.GIT_CREDENTIAL_ENV, metavar="VAR",
                        help="Name of the variable holding a clone/fetch credential. "
                             "Only the name crosses the boundary; git expands the value.")
    parser.add_argument("--source-mode", default="clone", choices=SOURCE_MODES,
                        help="How each folder's working tree is materialised. "
                             "'clone' is a disposable copy; 'worktree' is one working "
                             "tree of a bind-mounted host repo, so N concurrent runs "
                             "share its refs and objects.")
    parser.add_argument("--worktree-root", default="", metavar="DIR",
                        help="Where worktrees are created (default: --workspace-root). "
                             "Must be the same path on the host, since git records a "
                             "worktree's registration on both sides by absolute path.")
    args = parser.parse_args(argv)
    checkout_workspace(
        args.workspace_file,
        args.workspace_root,
        repo_url=args.repo_url,
        repo_name=args.repo_name,
        repo_branch=args.repo_branch,
        token_env=args.token_env,
        source_mode=args.source_mode,
        worktree_root=args.worktree_root,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry
    raise SystemExit(_main())
