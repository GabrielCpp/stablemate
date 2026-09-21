"""The one module in this package that reads the environment — and only for secrets."""
from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator, Mapping
from pathlib import Path

import yaml

GITHUB_FALLBACKS = ("GH_TOKEN", "GITHUB_TOKEN")

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
    """The GitHub token for the PR/CI steps, or ``""`` when none is set."""
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
    """The token an unconfigured API client falls back to: ``GH_TOKEN``, then the checkout credential."""
    return os.environ.get("GH_TOKEN") or os.environ.get(GIT_CREDENTIAL_ENV) or ""


@contextlib.contextmanager
def scoped_env(name: str, value: str) -> Iterator[None]:
    """Set ``name=value`` in the process environment for the block, then restore it."""
    previous = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


@contextlib.contextmanager
def scoped_envs(values: Mapping[str, str]) -> Iterator[None]:
    """`scoped_env` over several names at once, restored in reverse on exit."""
    with contextlib.ExitStack() as stack:
        for name, value in values.items():
            stack.enter_context(scoped_env(name, value))
        yield


def has_git_credential(name: str = GIT_CREDENTIAL_ENV) -> bool:
    """Whether ``name`` holds a clone/fetch credential for git to pick up."""
    return bool(os.environ.get(name, ""))
