"""Workflow metadata for the launcher scaffolding.

Resolving the launcher's repo/branch/agents-dir meta, plus the template values and
skip rules the installer shares with it. Farrier does not read a workflow's own
prompts: what a workflow depends on is the workflow's business, declared by the
package that ships it (see docs/plans/workflow-as-python-state-machine.md).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from farrier.git import get_default_branch, get_git_remote
from farrier.launcher import DEFAULT_AGENTS_DIR


WORKFLOW_SKIP_PARTS = {
    "__pycache__",
    ".runs",
    ".state",
    ".codex-home",
}


def collect_template_values(config: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key in ["vars", "template"]:
        configured = config.get(key) or {}
        if not isinstance(configured, dict):
            raise SystemExit(f"{key} must be a YAML mapping when present")
        values.update(configured)
    return values


def resolve_workflow_meta(
    config: dict[str, Any], repo: Path, repo_name: str
) -> dict[str, Any]:
    """Resolve repo_url / branch / agents-dir for the launcher scaffolding.

    Precedence: explicit `agents.yml` `workflow:` block, then the repo's own
    git origin + DEFAULT branch (master/main — NOT the branch currently checked
    out), then a clearly-marked placeholder. REPO_BRANCH is the trunk the worker
    clones and the coder workflow targets/merges PRs into, so it must be the
    long-lived integration branch, not the install-time HEAD. An explicit repo URL
    selects authenticated remote checkout; otherwise local runs clone a read-only
    bind mount of the host repository.
    """
    workflow_cfg = config.get("workflow") or {}
    if not isinstance(workflow_cfg, dict):
        raise SystemExit("workflow must be a YAML mapping when present")

    repo_url = workflow_cfg.get("repoUrl") or workflow_cfg.get("repo_url")
    remote_checkout = bool(repo_url)
    branch = workflow_cfg.get("branch")
    agents_dir = workflow_cfg.get("agentsDir") or workflow_cfg.get("agents_dir")
    # Host env vars to forward into the Docker run (interpolated from the local
    # env at `docker compose up` time). E.g. a GitHub token for opening PRs.
    env_passthrough = (
        workflow_cfg.get("envPassthrough") or workflow_cfg.get("env_passthrough") or []
    )
    if not isinstance(env_passthrough, list):
        raise SystemExit("workflow.envPassthrough must be a list of env var names")
    env_passthrough = [str(name) for name in env_passthrough]
    if not repo_url:
        repo_url = get_git_remote(repo)
    if not branch:
        branch = get_default_branch(repo)

    return {
        "repo_url": str(repo_url) if repo_url else "REPLACE_ME-git-remote-url",
        "branch": str(branch) if branch else "main",
        "agents_dir": str(agents_dir) if agents_dir else DEFAULT_AGENTS_DIR,
        "repo_name": repo_name,
        "env_passthrough": env_passthrough,
        "remote_checkout": remote_checkout,
    }


def should_skip_workflow_file(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    return (
        any(part in WORKFLOW_SKIP_PARTS for part in rel.parts) or path.suffix == ".pyc"
    )
