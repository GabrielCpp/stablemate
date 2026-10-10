"""Which prompt body a turn renders, and who owns it."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, TypeVar

import yaml
from pydantic import BaseModel
from workhorse.pyflow import WorkflowFailed
from workhorse.templates import BODY_PREFIX
from workhorse_workflows.coder.shared.schemas.render import schema_block
from workhorse_workflows.kit import find_repo_root

T = TypeVar("T", bound=BaseModel)

PACKAGE = "workhorse_workflows.coder"

LIBRARY_SUBDIR = Path("library") / "prompts" / "coder"

ROLES: dict[str, str] = {
    "dev-story": "develop one story: plan, build, review and fix it, through subagents",
    "qa-story": "own the story's QA: plan, run, audit and repair it, through subagents",
    "fix-item": "own one drained backlog item: fix it and QA it, through subagents",
    "document-story": "fold the story into the as-built book: write, review and fix it, through subagents",
    "fix-ci": "repair a red CI run",
    "replan-epic": "replan an epic whose stories no longer fit",
}

@dataclass(frozen=True)
class Turn(Generic[T]):
    """What a role resolves to: the envelope, the args that find its body, and the model."""

    prompt: str
    args: dict[str, Any]
    returns: type[T]


def turn(flow: Any, role: str, *, returns: type[T]) -> Turn[T]:
    """Resolve `role` to the envelope, the body arguments and the contract for one turn."""
    if role not in ROLES:
        raise WorkflowFailed(
            f"unknown prompt role {role!r}; the coder workflow's roles are: "
            + ", ".join(sorted(ROLES))
        )
    body = _body(role, flow.repo_dir, flow.library_dirs)
    prompt = f"{flow_dir(flow)}/prompts/{role}.md"
    args: dict[str, Any] = {"result_schema": schema_block(returns)}
    if body is not None:
        args |= {"_body_dir": str(body.parent), "body_template": f"{BODY_PREFIX}/{body.name}"}
    return Turn(prompt, args, returns)


def flow_dir(flow: Any) -> str:
    """The flow package's own directory name, as a prompt path is prefixed with it."""
    module = type(flow).__module__
    prefix = f"{PACKAGE}."
    if not module.startswith(prefix):
        raise WorkflowFailed(
            f"{type(flow).__name__} is defined in {module!r}, outside {PACKAGE!r}, so it "
            "has no flow directory to resolve its prompts against. A coder flow lives in "
            "its own package under `coder/`, beside the `prompts/` it renders."
        )
    return module[len(prefix) :].split(".", 1)[0]


def _body(role: str, repo_dir: str | Path, library_dirs: tuple[str, ...]) -> Path | None:
    """The first body file that exists, repo before overlay before base."""
    override = _repo_prompts(repo_dir).get(role)
    if override:
        candidate = Path(override)
        if not candidate.is_absolute():
            candidate = find_repo_root(repo_dir) / candidate
        if candidate.is_file():
            return candidate
    for layer in library_dirs:
        candidate = Path(layer) / LIBRARY_SUBDIR / f"{role}.md"
        if candidate.is_file():
            return candidate
    return None


def _repo_prompts(repo_dir: str | Path) -> dict[str, str]:
    """The repo's `prompts:` block, read the way `dev._services_config` reads `services:`."""
    config = find_repo_root(repo_dir) / "agents.yml"
    if not config.is_file():
        return {}
    try:
        loaded = yaml.safe_load(config.read_text()) or {}
    except yaml.YAMLError:
        return {}
    if not isinstance(loaded, dict):
        return {}
    block = loaded.get("prompts")
    if not isinstance(block, dict):
        workflow = loaded.get("workflow")
        block = workflow.get("prompts") if isinstance(workflow, dict) else None
    if not isinstance(block, dict):
        return {}
    return {str(k): str(v) for k, v in block.items() if isinstance(v, str)}


__all__ = ["LIBRARY_SUBDIR", "PACKAGE", "ROLES", "Turn", "flow_dir", "turn"]
