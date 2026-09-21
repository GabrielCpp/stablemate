"""The QA flow's deterministic spine: clear evidence, bring the stack up, validate, run."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Literal

from ostler import Ostler
from ostler.qa import runbook
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.qa_support import (
    QA_PLAN_FILE,
    QA_RUN_LOG,
    assert_records,
    notes_for,
)
from workhorse_workflows.coder.shared.schemas.qa import (
    DryRunGate,
    QaCleared,
    QaPlanValidation,
    QaPlanRun,
    QaToolCatalog,
    StackStatus,
    StackTornDown,
)
from workhorse_workflows.qa import runner as _qa_runner

TEARDOWN_STATES: dict[str, Literal["yes", "no", "skipped"]] = {
    "yes": "yes",
    "no": "no",
    "skipped": "skipped",
}

QA_SCRATCH_DIRNAME = "qa"


@blueprint.node
def clear_qa_evidence(logger: logging.Logger, spec_dir: str = "") -> QaCleared:
    """Delete last pass's `qa/` outputs, verdict and report, and make sure the spec dir exists."""
    if not spec_dir:
        logger.warning("no spec_dir given — nothing to clear")
        return QaCleared()
    root = Path(spec_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stale = root / QA_SCRATCH_DIRNAME
    if stale.exists():
        shutil.rmtree(stale)
        logger.info("removed stale qa dir %s", stale)
    for name in ("qa-evidence.json", "qa-report.md"):
        stale_file = root / name
        if stale_file.exists():
            stale_file.unlink()
            logger.info("removed stale %s", stale_file)
    return QaCleared(cleared=True)


@blueprint.node
def ensure_stack(
    logger: logging.Logger,
    docs_path: str = "",
    repo_dir: str = "",
) -> StackStatus:
    """Bring the durable QA stack up (or adopt one already serving) before the runner."""
    return _qa_runner.ensure_stack(logger, docs_path=docs_path, repo_dir=repo_dir)


@blueprint.node
def lint_qa_plan(
    logger: logging.Logger, spec_dir: str = "", docs_path: str = "", repo_dir: str = ""
) -> QaPlanValidation:
    """`ostler qa lint` on `<spec_dir>/qa_plan.py` — is this plan's AST safe to import?"""
    plan = str(Path(spec_dir) / QA_PLAN_FILE)
    docs_root = find_docs_root(docs_path, repo_dir)
    outcome = Ostler(docs_root).qa_lint(plan)
    status = "passed" if outcome.ok else "invalid"
    notes = notes_for(
        outcome, "QA plan lint passed." if status == "passed" else "QA plan lint failed."
    )
    logger.info("qa lint for %s returned status=%s", spec_dir, status)
    return QaPlanValidation(status=status, notes=notes, ostler=outcome.data)


@blueprint.node
def qa_tools_catalog(
    logger: logging.Logger, docs_path: str = "", repo_dir: str = ""
) -> QaToolCatalog:
    """`ostler qa tools list` — the tools this repo opted into, resolved for this host."""
    docs_root = find_docs_root(docs_path, repo_dir)
    outcome = Ostler(docs_root).qa_tools_catalog()
    tools = outcome.data.get("tools", [])
    errors = outcome.data.get("errors", [])
    logger.info("qa tools catalog resolved %d tool(s), %d error(s)", len(tools), len(errors))
    return QaToolCatalog(tools=tools, errors=errors)


@blueprint.node
def validate_qa_plan(
    logger: logging.Logger, spec_dir: str = "", docs_path: str = "", repo_dir: str = ""
) -> QaPlanValidation:
    """`ostler qa validate` on `<spec_dir>/qa_plan.py` — is this plan executable?"""
    plan = str(Path(spec_dir) / QA_PLAN_FILE)
    docs_root = find_docs_root(docs_path, repo_dir)
    outcome = Ostler(docs_root).qa_validate(plan, spec=spec_dir)
    status = "passed" if outcome.ok else "invalid"
    notes = notes_for(
        outcome, "QA plan is valid." if status == "passed" else "QA plan is invalid."
    )
    logger.info("qa validate for %s returned status=%s", spec_dir, status)
    return QaPlanValidation(status=status, notes=notes, ostler=outcome.data)


@blueprint.node
def verify_qa_dry_run(
    logger: logging.Logger, spec_dir: str = "", scenarios: tuple[str, ...] = ()
) -> DryRunGate:
    """Did the repair turn run each scenario it had to repair, and did each one pass?"""
    wanted = [s for s in dict.fromkeys(scenarios) if s]
    if not wanted:
        return DryRunGate(
            status="passed", notes="No scenarios required a dry run.", scenarios=[]
        )
    if not spec_dir:
        return DryRunGate(notes="QA dry-run gate: no spec_dir provided to locate the logs.")

    root = Path(spec_dir) / QA_SCRATCH_DIRNAME
    problems: list[str] = []
    verified: list[str] = []
    for scenario in wanted:
        log_path = root / scenario / QA_RUN_LOG
        if not log_path.is_file():
            problems.append(
                f"`{scenario}`: no dry run at {log_path}. Run it with "
                f"`ostler qa run {QA_PLAN_FILE} --spec {spec_dir} --scenario {scenario} "
                f"--out-dir {scenario}` and repair it until it passes."
            )
            continue
        mine = [
            r
            for r in assert_records(log_path)
            if str(r.get("scenario", "")).strip() in ("", scenario)
        ]
        if not mine:
            problems.append(
                f"`{scenario}`: the dry run at {log_path} recorded no assertion for it, so "
                "it proves nothing — the scenario never reached an assert. Find out why "
                "(locator, fixture, navigation) and re-run it."
            )
            continue
        failed = [
            str(r.get("id") or "?")
            for r in mine
            if str(r.get("result", "")).strip().upper() == "FAIL"
        ]
        if failed:
            problems.append(
                f"`{scenario}`: the dry run still fails {len(failed)} assertion(s) "
                f"({', '.join(failed)}). The repair is not finished."
            )
            continue
        verified.append(scenario)

    if problems:
        logger.info("qa dry-run gate refused %d of %d scenario(s)", len(problems), len(wanted))
        return DryRunGate(
            notes=(
                "The QA-plan repair must prove itself before the suite runs again. "
                + " ".join(problems)
            ),
            scenarios=wanted,
            verified=verified,
        )
    logger.info("qa dry-run gate passed %d scenario(s)", len(verified))
    return DryRunGate(
        status="passed",
        notes=f"Dry run passed for {', '.join(verified)}.",
        scenarios=wanted,
        verified=verified,
    )


@blueprint.node
def teardown_stack(
    logger: logging.Logger,
    docs_path: str = "",
    repo_dir: str = "",
) -> StackTornDown:
    """Run the runbook's `stop:` recipe now that the run is finished."""
    root = find_docs_root(docs_path, repo_dir)
    outcome = runbook.cmd_stack_down(root, logger=logger)
    torn = TEARDOWN_STATES.get(
        str(outcome.data.get("torn_down") or outcome.status or "no"), "no"
    )
    logger.info("QA stack teardown: %s", torn)
    return StackTornDown(torn_down=torn, notes=outcome.message)


@blueprint.node
def run_qa_plan(
    logger: logging.Logger,
    spec_dir: str = "",
    docs_path: str = "",
    repo_dir: str = "",
) -> QaPlanRun:
    """Execute the QA plan through ostler and normalize its four-state outcome."""
    return _qa_runner.run_qa_plan(
        logger, spec_dir=spec_dir, docs_path=docs_path, repo_dir=repo_dir
    )


__all__ = [
    "clear_qa_evidence",
    "ensure_stack",
    "lint_qa_plan",
    "qa_tools_catalog",
    "run_qa_plan",
    "teardown_stack",
    "validate_qa_plan",
    "verify_qa_dry_run",
]
