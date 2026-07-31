"""The QA flow's deterministic spine: clear evidence, bring the stack up, validate, run.

Ports `clear-qa-evidence.py`, `ensure-stack.py`, `validate-qa-plan.py` and
`run-qa-plan.py`. The two ostler-backed nodes are the same adapter shape `shared/okf.py`
already uses — `ostler_qa` returns `(returncode, payload, stderr)` and the node turns it
into a status by its own rule — and they resolve their docs root the same way, through
`find_docs_root(docs_path, repo_dir)` rather than a per-node cwd the driver does not have.

`clear-qa-gate-state.py` has no node here, deliberately. It blanked five run-context keys
(`qa_plan_validation`, `qa_plan_review`, `qa_assessment`, `qa_audit`, `qa_result`) so a
stale diagnostic from an earlier pass could not be fed to the next `plan_qa`. Those five
are not global state under the driver — they are the QA flow's own parameters — so
"forget them" is expressed by the transition out of the planning turn not carrying them
forward, which is where the flow does it. A node that blanked five keys nobody else could
see would have nothing to blank.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import yaml
from workhorse import stack
from workhorse.scriptutil import find_docs_root
from workhorse_workflows.coder.shared import ostler_qa
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.qa import (
    QaCleared,
    QaPlanValidation,
    QaRunResult,
    StackStatus,
)

#: The four states `ostler qa run` is allowed to report. Anything else is `invalid` —
#: a runner that answered something unrecognized has not established a verdict.
RUN_STATUSES = frozenset({"passed", "failed", "blocked", "invalid"})


@blueprint.node
def clear_qa_evidence(logger: logging.Logger, spec_dir: str = "") -> QaCleared:
    """Delete last pass's `qa/` outputs and root verdict, and make sure the spec dir exists.

    Deliberately does not recreate `qa/`: the ostler runner owns that directory, its log,
    its manifest and its evidence, and a node that pre-created it would be authoring an
    empty shell the evidence gate then has to tell apart from a real run.
    """
    if not spec_dir:
        logger.warning("no spec_dir given — nothing to clear")
        return QaCleared()
    root = Path(spec_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    qa_dir = root / "qa"
    if qa_dir.exists():
        shutil.rmtree(qa_dir)
        logger.info("removed stale qa dir %s", qa_dir)
    evidence = root / "qa-evidence.json"
    if evidence.exists():
        evidence.unlink()
        logger.info("removed stale evidence file %s", evidence)
    return QaCleared(cleared=True)


def _absolutize(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    """Resolve the manifest's working directories against the repo root.

    The manifest is written repo-relative because that is what a human authoring it means.
    Nothing in the engine resolves it for us: `ensure_stack` runs the steps with whatever
    `working-directory` they carry, so an unresolved `.` would launch the stack from the
    engine's cwd instead of the repo.
    """
    manifest["app_cwd"] = str((root / (manifest.get("app_cwd") or ".")).resolve())
    for key in ("prepare", "seed", "health"):
        for step in manifest.get(key) or []:
            if isinstance(step, dict) and step.get("working-directory"):
                step["working-directory"] = str((root / step["working-directory"]).resolve())
    return manifest


@blueprint.node
def ensure_stack(
    logger: logging.Logger,
    manifest_path: str = "qa-stack.yml",
    docs_path: str = "",
    repo_dir: str = "",
) -> StackStatus:
    """Bring the durable QA stack up (or adopt one already serving) before the runner.

    A long-running stack has to start *outside* any agent turn, or the turn's teardown
    kills it mid-build. The lifecycle itself is `workhorse.stack.ensure_stack`, shared with
    the okf-builder; this node is the manifest's reader and the outcome's translator.

    A missing manifest is `skip`, not a failure — a repo that has not authored one runs QA
    exactly as it did before the manifest existed.
    """
    root = find_docs_root(docs_path, repo_dir)
    manifest_rel = manifest_path or "qa-stack.yml"
    path = root / manifest_rel

    if not path.is_file():
        logger.info(
            "no stack manifest at %s — skipping durable bring-up (QA-plan `background:` "
            "services still apply)",
            path,
        )
        return StackStatus(
            ready="skip", notes=f"No stack manifest at {manifest_rel}; nothing to bring up."
        )

    try:
        manifest = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("stack manifest %s could not be read: %s", path, exc)
        return StackStatus(failed_step="manifest", notes=f"Unreadable stack manifest: {exc}")
    if not isinstance(manifest, dict):
        return StackStatus(failed_step="manifest", notes="Stack manifest is not a mapping.")

    result = stack.ensure_stack(_absolutize(manifest, root), repo_root=str(root), logger=logger)
    common = {
        "app_pid": result.get("app_pid", ""),
        "app_pgid": result.get("app_pgid", ""),
        "entry_url": result.get("entry_url", ""),
        "failed_step": result.get("failed_step", ""),
    }
    if result["ready"] == "yes":
        how = "adopted" if result.get("adopted") == "yes" else "brought up"
        where = result.get("entry_url") or "(no url)"
        return StackStatus(ready="yes", notes=f"Stack {how} and healthy at {where}.", **common)
    step = result.get("failed_step", "unknown")
    # The step's own message goes in the notes, because the notes are what the setup
    # fixer is briefed with: told only *which* step failed, it re-derives the failure
    # from scratch — an expensive turn spent rediscovering a line the stack already had.
    error = (result.get("error") or "").strip()
    return StackStatus(
        ready="no",
        notes=(
            f"Stack bring-up failed at step '{step}'"
            + (f": {error}" if error else "")
            + ". Repair the manifest or its seed recipe (never background the stack in "
            "the agent shell)."
        ),
        **common,
    )


@blueprint.node
def validate_qa_plan(
    logger: logging.Logger, spec_dir: str = "", docs_path: str = "", repo_dir: str = ""
) -> QaPlanValidation:
    """`ostler qa validate` on `<spec_dir>/qa-plan.yml` — is this plan executable?

    The deterministic half of the plan gate; `review-qa-plan.md` is the semantic half. Both
    have to pass before the stack comes up, so a plan that cannot run is caught before
    anything expensive starts.
    """
    plan = str(Path(spec_dir) / "qa-plan.yml")
    docs_root = find_docs_root(docs_path, repo_dir)
    returncode, payload, stderr = ostler_qa.qa_validate(plan, spec_dir, docs_root=docs_root)
    cli_status = str(payload.get("status", "invalid")).lower()
    status = "passed" if returncode == 0 and cli_status == "passed" else "invalid"
    notes = ostler_qa.notes_for(
        payload, stderr, "QA plan is valid." if status == "passed" else "QA plan is invalid."
    )
    logger.info("qa validate for %s returned status=%s", spec_dir, status)
    return QaPlanValidation(status=status, notes=notes, ostler=payload)


@blueprint.node
def run_qa_plan(
    logger: logging.Logger, spec_dir: str = "", docs_path: str = "", repo_dir: str = ""
) -> QaRunResult:
    """Execute the QA plan through ostler and normalize its four-state outcome.

    The returncode is deliberately ignored: `failed` and `blocked` are answers the runner
    is *supposed* to give, and both exit non-zero. The status comes off the payload, and
    only an unrecognized one becomes `invalid`.
    """
    plan = str(Path(spec_dir) / "qa-plan.yml")
    docs_root = find_docs_root(docs_path, repo_dir)
    _returncode, payload, stderr = ostler_qa.qa_run(plan, spec_dir, docs_root=docs_root)
    status = str(payload.get("status", "invalid")).lower()
    if status not in RUN_STATUSES:
        status = "invalid"
    notes = ostler_qa.notes_for(payload, stderr, f"Ostler QA run returned {status}.")
    logger.info("ostler qa run for %s returned status=%s", spec_dir, status)
    return QaRunResult(status=status, notes=notes, ostler=payload)


__all__ = ["clear_qa_evidence", "ensure_stack", "run_qa_plan", "validate_qa_plan"]
