"""The QA stack a run brings up, runs a plan against and tears down: the nodes dev and QA both call."""
from __future__ import annotations

import logging
from typing import Literal

from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.qa import (
    QaPlanRun,
    StackStatus,
    StackTarget,
    StackTornDown,
)
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.kit.qa import runner as _qa_runner
from ostler import model

TEARDOWN_STATES: dict[str, Literal["yes", "no", "skipped"]] = {
    "yes": "yes",
    "no": "no",
    "skipped": "skipped",
}


@blueprint.node
def stack_target(
    logger: logging.Logger,
    story: str = "",
    lease: str = "",
    docs_path: str = "",
    repo_dir: str = "",
) -> StackTarget:
    """The book whose stack this story's QA runs against, and the copy *lease* names there."""
    graph = model.load(find_docs_root(docs_path, repo_dir))
    near = _qa_runner.story_near(graph, story) if story else ""
    env = _qa_runner.stack_env(logger, graph, near=near, lease=lease)
    logger.info("QA stack for %s: near=%s lease=%s", story, near or "(none)", lease or "(none)")
    return StackTarget(near=near, lease=lease, env=env)


@blueprint.node
def ensure_stack(
    logger: logging.Logger,
    docs_path: str = "",
    repo_dir: str = "",
    near: str = "",
    lease: str = "",
) -> StackStatus:
    """Bring the durable QA stack up (or adopt one already serving) before the runner."""
    return _qa_runner.ensure_stack(
        logger, docs_path=docs_path, repo_dir=repo_dir, near=near, lease=lease
    )


@blueprint.node
def release_copy(
    logger: logging.Logger,
    docs_path: str = "",
    repo_dir: str = "",
    near: str = "",
    lease: str = "",
) -> StackTornDown:
    """Tear down this run's copy of a per-run stack, so the next pass builds the code it QAs."""
    outcome = _qa_runner.release_copy(
        logger, docs_path=docs_path, repo_dir=repo_dir, near=near, lease=lease
    )
    if outcome is None:
        return StackTornDown(torn_down="skipped", notes="The stack is shared, so it stays serving.")
    torn = TEARDOWN_STATES.get(
        str(outcome.data.get("torn_down") or outcome.status or "no"), "no"
    )
    logger.info("QA stack copy %s teardown: %s", lease, torn)
    return StackTornDown(torn_down=torn, notes=outcome.message)


@blueprint.node
def run_qa_plan(
    logger: logging.Logger,
    spec_dir: str = "",
    docs_path: str = "",
    repo_dir: str = "",
    near: str = "",
    lease: str = "",
    only: list[str] | None = None,
) -> QaPlanRun:
    """Execute the QA plan through ostler and normalize its four-state outcome."""
    return _qa_runner.run_qa_plan(
        logger,
        spec_dir=spec_dir,
        docs_path=docs_path,
        repo_dir=repo_dir,
        only=only,
        near=near,
        lease=lease,
    )


__all__ = [
    "TEARDOWN_STATES",
    "ensure_stack",
    "release_copy",
    "run_qa_plan",
    "stack_target",
]
