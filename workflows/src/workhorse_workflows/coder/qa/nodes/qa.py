"""The QA flow's deterministic spine: clear evidence, bring the stack up, validate, run."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from ostler import Ostler
from ostler.qa.compile import Plan
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.kit.qa import runner as _qa_runner
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.compilation import compile_packet
from workhorse_workflows.coder.shared.stack import (
    TEARDOWN_STATES,
    ensure_stack,
    release_copy,
    run_qa_plan,
    stack_target,
)
from workhorse_workflows.coder.shared.qa_support import QA_PLAN_FILE, notes_for
from workhorse_workflows.coder.shared.schemas.qa import (
    CompiledPlan,
    QaCleared,
    QaPlanValidation,
    QaToolCatalog,
    StackTornDown,
)

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
def compile_story_plan(
    logger: logging.Logger, spec_dir: str = "", story: str = ""
) -> CompiledPlan:
    """Write `<spec_dir>/qa_plan.py` from the plan the book compiles, unless one already stands or the book refuses."""
    root = Path(spec_dir)
    target = root / QA_PLAN_FILE
    if target.exists():
        logger.info("%s already stands, so nothing is compiled", target)
        return CompiledPlan()
    compiled = compile_packet(root, story, logger)
    if not isinstance(compiled, Plan):
        gaps = len(compiled.gaps) if compiled else 0
        logger.info("the book refused to compile a QA plan with %d gap(s)", gaps)
        return CompiledPlan(gaps=gaps)
    target.write_text(compiled.source, encoding="utf-8")
    for name, text in compiled.files.items():
        aux = root / name
        aux.parent.mkdir(parents=True, exist_ok=True)
        aux.write_text(text, encoding="utf-8")
    scenarios = compiled.source.count("\n@scenario(")
    logger.info("compiled %d scenario(s) from the book into %s", scenarios, target)
    return CompiledPlan(compiled=True, scenarios=scenarios, gaps=len(compiled.gaps))


@blueprint.node
def lint_qa_plan(
    logger: logging.Logger, spec_dir: str = "", repo_dir: str = ""
) -> QaPlanValidation:
    """`ostler qa lint` on `<spec_dir>/qa_plan.py` — is this plan's AST safe to import?"""
    plan = str(Path(spec_dir) / QA_PLAN_FILE)
    docs_root = find_docs_root(repo_dir)
    outcome = Ostler(docs_root).qa_lint(plan)
    status = "passed" if outcome.ok else "invalid"
    notes = notes_for(
        outcome, "QA plan lint passed." if status == "passed" else "QA plan lint failed."
    )
    logger.info("qa lint for %s returned status=%s", spec_dir, status)
    if status != "passed":
        logger.warning("qa lint findings for %s:\n%s", spec_dir, notes)
    return QaPlanValidation(status=status, notes=notes, ostler=outcome.data)


@blueprint.node
def qa_tools_catalog(
    logger: logging.Logger, repo_dir: str = ""
) -> QaToolCatalog:
    """`ostler qa tools list` — the tools this repo opted into, resolved for this host."""
    docs_root = find_docs_root(repo_dir)
    outcome = Ostler(docs_root).qa_tools_catalog()
    tools = outcome.data.get("tools", [])
    errors = outcome.data.get("errors", [])
    logger.info("qa tools catalog resolved %d tool(s), %d error(s)", len(tools), len(errors))
    return QaToolCatalog(tools=tools, errors=errors)


@blueprint.node
def validate_qa_plan(
    logger: logging.Logger, spec_dir: str = "", repo_dir: str = ""
) -> QaPlanValidation:
    """`ostler qa validate` on `<spec_dir>/qa_plan.py` — is this plan executable?"""
    plan = str(Path(spec_dir) / QA_PLAN_FILE)
    docs_root = find_docs_root(repo_dir)
    outcome = Ostler(docs_root).qa_validate(plan, spec=spec_dir)
    status = "passed" if outcome.ok else "invalid"
    notes = notes_for(
        outcome, "QA plan is valid." if status == "passed" else "QA plan is invalid."
    )
    logger.info("qa validate for %s returned status=%s", spec_dir, status)
    if status != "passed":
        logger.warning("qa validate findings for %s:\n%s", spec_dir, notes)
    return QaPlanValidation(status=status, notes=notes, ostler=outcome.data)


@blueprint.node
def teardown_stack(
    logger: logging.Logger,
    repo_dir: str = "",
) -> StackTornDown:
    """Tear down the shared stack now that the run is finished: the `stack.yml` copy bring-up started, or else the runbook's `stop:` recipe."""
    outcome = _qa_runner.teardown_stack(logger, repo_dir=repo_dir)
    torn = TEARDOWN_STATES.get(
        str(outcome.data.get("torn_down") or outcome.status or "no"), "no"
    )
    logger.info("QA stack teardown: %s", torn)
    return StackTornDown(torn_down=torn, notes=outcome.message)


__all__ = [
    "compile_story_plan",
    "clear_qa_evidence",
    "ensure_stack",
    "lint_qa_plan",
    "qa_tools_catalog",
    "release_copy",
    "run_qa_plan",
    "stack_target",
    "teardown_stack",
    "validate_qa_plan",
]
