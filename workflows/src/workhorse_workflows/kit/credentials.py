"""The one module in this package that reads the environment — and only for secrets.

Nodes and workflows may not read the environment (see `workflows/README.md`): a run's
inputs belong in its parameters, where a caller can set them, a second run can be
compared against the first, and the checkpoint records what the run was actually given.

A credential is the exception, and it is an exception for exactly the reason the rule
exists. Parameters are **written to disk** in the run directory and echoed in logs and
telemetry, so routing a token through one would publish it. So a token stays in the
process environment, is read here and nowhere else, and is passed to the client that
needs it as an ordinary argument — never stored, never checkpointed, never logged.

`scripts/check_no_env.py` enforces the rule and exempts this file by name, so the
exception is one auditable module rather than a habit.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

#: Where a GitHub token is looked for when `agents.yml` names no variable of its own.
GITHUB_FALLBACKS = ("GH_TOKEN", "GITHUB_TOKEN")

#: The variable a workflow-specific checkout hook leaves a clone/fetch credential in.
GIT_CREDENTIAL_ENV = "WORKHORSE_GIT_TOKEN"


def _configured_token_env(root: Path) -> str | None:
    """The env-var name configured in agents.yml ``workflow.githubTokenEnv`` (or None)."""
    cfg = root / "agents.yml"
    if not cfg.is_file():
        return None
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return None
    workflow = data.get("workflow") or {}
    if isinstance(workflow, dict):
        name = workflow.get("githubTokenEnv") or workflow.get("github_token_env")
        if name:
            return str(name).strip()
    return None


def github_token(root: str | Path) -> str:
    """The GitHub token for the PR/CI steps, or ``""`` when none is set.

    Order: the variable named by agents.yml ``workflow.githubTokenEnv`` (repo-configurable
    rather than hardcoded), then ``GH_TOKEN``, then ``GITHUB_TOKEN``. Callers treat an
    empty string as "no token" and degrade to a best-effort unauthenticated path.
    """
    names: list[str] = []
    configured = _configured_token_env(Path(root).resolve())
    if configured:
        names.append(configured)
    for fallback in GITHUB_FALLBACKS:
        if fallback not in names:
            names.append(fallback)
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def api_token() -> str:
    """The token an unconfigured API client falls back to: ``GH_TOKEN``, then the
    checkout credential. Empty means "call the API anonymously"."""
    return os.environ.get("GH_TOKEN") or os.environ.get(GIT_CREDENTIAL_ENV) or ""


def has_git_credential(name: str = GIT_CREDENTIAL_ENV) -> bool:
    """Whether ``name`` holds a clone/fetch credential for git to pick up.

    Only the *presence* is read. The value stays in the environment and is expanded by
    git itself inside the credential helper, so the secret never enters this process's
    memory, its logs, or a subprocess argument list where `ps` would show it.
    """
    return bool(os.environ.get(name, ""))
