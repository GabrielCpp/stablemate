#!/usr/bin/env python3
"""Resolve the GitHub token for the coder PR / CI steps.

The name of the environment variable that carries the token is configurable
per-repo in ``agents.yml`` — it is NOT hardcoded. Configure it under the
``workflow`` block (and forward it into the agent run via ``envPassthrough``):

    workflow:
      githubTokenEnv: ACME_GITHUB_TOKEN   # env var holding the token
      envPassthrough:
        - ACME_GITHUB_TOKEN               # forward it into the run

Resolution order: the configured ``githubTokenEnv`` (if set and non-empty), then
the conventional ``GH_TOKEN``, then ``GITHUB_TOKEN``. The token *value* is printed
to stdout (empty string if none is set) for in-process command substitution by the
calling shell script — it is never logged.

Stdlib + PyYAML (available in the local-worker runtime, as in select-next-story.py).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Conventional fallbacks, tried after the repo-configured name.
FALLBACK_ENV = ["GH_TOKEN", "GITHUB_TOKEN"]


def find_repo_root() -> Path:
    """Resolve the repo root. Workflows run from the shared library, so prefer the
    AGENT_REPO_DIR the makefile pins to the starting repo; otherwise walk up from
    this script (marked by agents.yml or .git)."""
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return here


def configured_token_env(root: Path) -> str | None:
    """The env-var name configured in agents.yml workflow.githubTokenEnv (or None)."""
    cfg = root / "agents.yml"
    if not cfg.is_file():
        return None
    try:
        import yaml  # available in the local-worker runtime

        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    workflow = data.get("workflow") or {}
    if isinstance(workflow, dict):
        name = workflow.get("githubTokenEnv") or workflow.get("github_token_env")
        if name:
            return str(name).strip()
    return None


def main() -> None:
    root = find_repo_root()
    names: list[str] = []
    configured = configured_token_env(root)
    if configured:
        names.append(configured)
    for fallback in FALLBACK_ENV:
        if fallback not in names:
            names.append(fallback)

    for name in names:
        value = os.environ.get(name)
        if value:
            sys.stdout.write(value)
            return
    # Nothing set — emit nothing; callers treat empty as "no token" (best-effort skip).


if __name__ == "__main__":
    main()
