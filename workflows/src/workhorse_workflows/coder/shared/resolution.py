"""The half of an operator gate that tries to answer the block before parking on it."""
from __future__ import annotations

from pathlib import Path

from workhorse.pyflow import Workflow

from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared.schemas.dev import OperatorResolution
from workhorse_workflows.coder.shared.schemas.render import schema_block
from workhorse_workflows.kit import find_docs_root

RESOLVER_POWER = "max"


def resolver_args(
    flow: Workflow, *, block_kind: str, notes: str, docs_path: str
) -> dict[str, str]:
    """The template arguments a `shared/prompts/resolve-operator.md` turn takes."""
    return {
        "story_path": flow.ctx.story_path,
        "spec_dir": flow.ctx.spec_dir,
        "decisions_dir": str(decisions_dir(docs_path, flow.repo_dir)),
        "block_kind": block_kind,
        "block_notes": notes,
        "result_schema": schema_block(OperatorResolution),
    }


def decisions_dir(docs_path: str, repo_dir: str) -> Path:
    """Where this run's standing decisions live, absolute — see `paths.decisions_dir`."""
    return paths.decisions_dir(find_docs_root(docs_path, repo_dir))


def answered(flow: Workflow, result: OperatorResolution, block_kind: str) -> bool:
    """Did the resolver settle the block itself, and say what settled it?"""
    if result.decision != "answered":
        return False
    flow.logger.info(
        "the %s block was resolved from what is already written down — %s%s",
        block_kind,
        result.summary or "no summary given",
        (
            f" (grounded in: {'; '.join(result.grounded)}"
            + (f", recorded as {result.record}" if result.record else "")
            + ")"
            if result.grounded
            else " — WITH NO GROUNDING CITED, which the prompt requires; check this one"
        ),
        extra={"activity": True},
    )
    return True


__all__ = ["RESOLVER_POWER", "answered", "decisions_dir", "resolver_args"]
