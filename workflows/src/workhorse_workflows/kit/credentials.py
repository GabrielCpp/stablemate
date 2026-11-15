"""Where a workflow gets its GitHub token: the saddlebag secret agents.yml names, and nothing else."""
from __future__ import annotations

from pathlib import Path

from saddlebag import SecretUnavailable, secret_value
from workhorse.pyflow import WorkflowFailed

from workhorse_workflows.kit.manifest import read_manifest

GIT_TOKEN_VAR = "GH_TOKEN"

CREDENTIAL_HELPER = f'!f() {{ echo username=x-access-token; echo "password=${{{GIT_TOKEN_VAR}}}"; }}; f'


def _configured_secret(root: Path) -> str | None:
    """The saddlebag secret named by agents.yml ``workflow.githubTokenSecret`` (or None)."""
    manifest = read_manifest(root)
    if manifest is None:
        return None
    name = manifest.workflow.githubTokenSecret
    return name.strip() if name else None


def github_token(root: str | Path) -> str:
    """The GitHub token for the PR/CI steps, or ``""`` when no secret is configured."""
    name = _configured_secret(Path(root).resolve())
    if not name:
        return ""
    try:
        return secret_value(name)
    except SecretUnavailable as exc:
        raise WorkflowFailed(f"cannot read the GitHub token from saddlebag secret {name}: {exc}") from exc
