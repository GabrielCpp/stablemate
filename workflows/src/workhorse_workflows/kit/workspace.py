"""Workspace resolution: which repos a run spans, where they are, and getting them.

A `.code-workspace` file (VSCode's format, with an optional ``url``/``branch`` key per
folder that VSCode ignores) is the multi-repo manifest. :func:`resolve_workspace` reads
an existing checkout; :func:`checkout_workspace` creates one. They fall back
differently, which is why ``_read_workspace_file`` returns None rather than guessing.

The clone/update path here shells out to ``git`` rather than going through
:mod:`workhorse_workflows.kit.git`: it runs from ``entrypoint.sh`` before the engine
starts, on directories that are not repos yet, with a credential helper built per
command. That is also why :func:`checkout_workspace` has a ``__main__`` entry: the
container shell is the process boundary and passes what it knows as arguments, so
nothing inside the run has to read the environment to learn the same facts.
"""
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
    """A repo's name: its directory name, normalized the same way farrier's kebab()
    derives the install prefix, so the key here and the prefix on that repo's
    installed skills are the same string by construction.

    It is derived, never configured. ``agents.yml`` used to be able to override it
    with ``repo.name``, which let a checkout disagree with itself — the name in the
    run record and the name on the skills came from different places, and a clone
    under a different directory name changed one of them and not the other."""
    name = re.sub(r"[^a-zA-Z0-9/-]+", "-", path.name.replace(".", "-").replace("_", "-"))
    return re.sub(r"-+", "-", name).strip("-").lower()


def _read_workspace_file(workspace_file: str | Path) -> tuple[list[dict], Path] | None:
    """Parse the `.code-workspace` file at ``workspace_file``, if it exists.

    Returns ``(folders, ws_dir)`` when the path names an existing file, else ``None`` —
    callers apply their own single-folder fallback in that case, since
    resolve_workspace() (read an existing checkout) and checkout_workspace() (create
    one) fall back differently.
    """
    if not workspace_file or not Path(workspace_file).exists():
        return None
    ws = jsonio.load_jsonc(Path(workspace_file).read_text(encoding="utf-8"))
    ws_dir = Path(workspace_file).parent
    return ws.get("folders", []), ws_dir


def resolve_workspace(
    workspace_file: str | Path = "", repo_dir: str | Path = ""
) -> dict[str, dict]:
    """Build {repo_name: {path, ...}} from a workspace file, or from ``repo_dir`` alone.

    Resolution order:
    1. ``workspace_file`` — the run's own input (a workflow field, defaulted by the
       CLI/entrypoint from whatever the operator configured). When it names an existing
       file, parse it as a VSCode workspace.
    2. Otherwise treat ``repo_dir`` (a single repo) as a one-folder workspace.

    Neither is read from the environment: both are the run's inputs, so both arrive as
    arguments — see `workflows/README.md` on why a node may not read the environment.

    For each folder, reads agents.yml and merges the workspace: section into the record.
    """
    parsed = _read_workspace_file(workspace_file)
    if parsed is not None:
        folders, ws_dir = parsed
    else:
        # A single-repo run: key the synthesized folder off the *repo* root rather than
        # the process cwd, which for a node is the workflow's own directory and would
        # name the workspace after the workflow (e.g. "coder") instead of the repo.
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
    """True if ``dest`` has uncommitted changes or commits not on ``origin/<branch>``.

    Used by ``checkout_workspace`` to tell "container restarted mid-run, resume
    where we left off" apart from "clean checkout, safe to fast-forward to the
    host's latest commit" — a bare reset can't distinguish the two, and would
    otherwise silently discard uncommitted in-container work (e.g. a blocked
    operator-gate node's edits) on every restart.
    """
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
    """Build a Git command with transient credentials for clone/fetch.

    A workflow-specific checkout hook may leave a token in ``token_env`` after resolving
    credentials according to that workflow's own configuration; the generic checkout code
    knows no token names or provider conventions. Only the variable's *presence* is read
    here — the helper string names it, and the git subprocess expands it from its own
    inherited environment, so the secret never reaches an argument list or a log.
    """
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


#: How a folder's working tree is materialised.
#:
#: ``clone`` is the container-with-its-own-volume model: a disposable copy, reset to
#: the remote on every restart. ``worktree`` is the concurrent-runs model: N runs each
#: get their own working tree of ONE bind-mounted host repo, so they share a ref
#: namespace and an object store and cost no extra clone.
SOURCE_MODES = ("clone", "worktree")


def _add_worktree(source: Path, dest: Path, ref: str, name: str, logger: logging.Logger) -> None:
    """Give this run its own working tree of ``source``, at ``dest``.

    Three rules here are not defensive, they are the model:

    **Detached.** No workflow knows its branch at checkout time — the branch is cut
    later, at a workflow node. Checking one out here would claim it in this
    worktree's name, and git then refuses to check it out anywhere else, so a second
    concurrent run of the same workflow would fail at its own checkout instead of at
    a place that could explain why.

    **Never reset an existing worktree.** Unlike a clone in a disposable volume, this
    is a directory next to the operator's own checkout, on their disk. A restart
    mid-run finds work in progress; a reset would discard it. So an existing tree is
    left exactly as it is, which is also what makes ``docker restart`` a resume.

    **Prune first.** Worktree registration is recorded on *both* sides, by absolute
    path. A run whose directory was deleted without ``git worktree remove`` leaves a
    registration behind in the source repo, and `worktree add` then refuses the path
    as already registered. Pruning drops exactly those entries whose directory is
    gone, and touches no live worktree.
    """
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
    """Clone/update every `url`-bearing folder in the `.code-workspace` file into
    ``workspace_root``, transparent to whichever workflow graph runs next.

    Meant to be invoked once from entrypoint.sh, before the workflow engine starts —
    neither coder nor author has a "setup" node; by the time the graph starts, every
    folder's working tree already exists under ``workspace_root/<folder name>``. The
    shell is the process boundary, so it reads its own environment and passes the
    values here as arguments (see ``__main__`` at the bottom of this module).

    Resolution order:
    1. If ``workspace_file`` names an existing file, clone/update every folder in its
       `folders` list that carries a `url` key (its own optional schema extension —
       VSCode ignores unknown keys, so plain `.code-workspace` files stay valid whether
       or not they use it). A missing `branch` defaults to "main". Folders WITHOUT a
       `url` are left untouched — they may not be git repos at all (e.g. a plain
       documentation directory); their content can only reach the container via the
       workspace-directory bind mount (see compose.yaml), not a clone.
    2. Otherwise, synthesize a single folder from ``repo_url``/``repo_name``/
       ``repo_branch`` (the single-primary-repo mechanism) and feed it through the exact
       same clone path — this keeps 1-repo and N-repo runs on one code path with zero
       repo-name defaulting. The URL may be a local bind-mounted source or a remote
       authenticated through the token in ``token_env``.

    ``source_mode`` picks how each folder is materialised (see :data:`SOURCE_MODES`).
    ``worktree`` needs every `url` to be a **local path** — the host repo, bound into
    the container at its own path — because git records a worktree's registration on
    both sides by absolute path, so a container that saw the repo somewhere else
    would write host-invalid paths into the operator's own `.git`. Worktrees are
    created under ``worktree_root`` (defaulting to ``workspace_root``) for the same
    reason: that path is bind-mounted from the host and has to agree with it.

    Both are **arguments, not environment**: everything a run is given must be in its
    checkpoint, so a resume days later takes the same value, and reachable from
    ``--params``. The process boundary (the container's supervisor) is what reads the
    environment and expands it into these flags.
    """
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[checkout] %(message)s")
    logger = logging.getLogger("workhorse.checkout")
    workspace_root = Path(workspace_root)
    if source_mode not in SOURCE_MODES:
        raise ValueError(
            f"unknown source mode {source_mode!r}; expected one of {', '.join(SOURCE_MODES)}"
        )
    # Defaulting rather than requiring it: a single-run container has no reason to
    # separate the two, and the concurrent launcher passes the host path explicitly.
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
    """Get a config value from a repo's agents.yml workspace section.

    Pass ``repos`` when the caller already resolved the workspace (the usual case, and
    the cheap one); otherwise the workspace is resolved from the same two run inputs
    :func:`resolve_workspace` takes.

    Examples:
        get_repo_config("api-service", "qa_mode", repos=repos)             # → "cli"
        get_repo_config("api-service", "base_branch", "main", repos=repos) # → "develop"
    """
    if repos is None:
        repos = resolve_workspace(workspace_file, repo_dir)
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
    """`python -m workhorse_workflows.kit.workspace` — the entrypoint.sh checkout step.

    The container shell owns its environment and expands it into these flags, which is
    what keeps the environment on the *outside* of the run: this module never reads a
    variable of its own, and the one thing it cannot take as a flag — the credential —
    is named, not passed, so the secret stays out of the argument list.
    """
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
