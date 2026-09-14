"""The QA flow's deterministic spine: clear evidence, bring the stack up, validate, run.

Ports `clear-qa-evidence.py`, `ensure-stack.py`, `validate-qa-plan.py` and
`run-qa-plan.py`. The ostler-backed nodes call `Ostler` directly and read the `QaOutcome`
it answers with — each turns it into a status by its own rule, which is why there is no
adapter between them and the API — and they resolve their docs root the same way, through
`find_docs_root(docs_path, repo_dir)` rather than a per-node cwd the driver does not have.

`ensure_stack` and `run_qa_plan` are thin `@blueprint.node` wrappers around the
family-neutral functions in `workhorse_workflows.qa.runner` — the bodies moved there so a
live-audit lane can call the same stack/plan machinery without going through a `Workflow`.
The wrappers keep this module's node names, so a coder run's checkpoints, `INFRA_NODES`
identity check and `Workflow.output` resolution — all keyed on the function object
imported from here — are unaffected by where the logic underneath actually lives.

`clear-qa-gate-state.py` has no node here, deliberately. It blanked five run-context keys
(`qa_plan_validation`, `qa_plan_review`, `qa_assessment`, `qa_audit`, `qa_result`) back
when a semantic plan reviewer still existed, so a
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

#: The three answers a teardown can end on, keyed the same way, and `no` for anything else.
#: Nothing branches on any of them: the field is the run record's account of whether the
#: stack it started is still up.
TEARDOWN_STATES: dict[str, Literal["yes", "no", "skipped"]] = {
    "yes": "yes",
    "no": "no",
    "skipped": "skipped",
}

#: Where a plan turn's dry runs land — `ostler qa run --scenario ID --out-dir ID`, which
#: ostler resolves to `<spec_dir>/qa/<ID>/`. Spec-relative, and *inside* `qa/` on purpose:
#: that is the one directory a repo ignores, and the sibling layout it replaces shipped
#: hundreds of megabytes of traces and video into client repos. Nesting costs nothing here
#: because the evidence gate reads `qa/qa-run.ndjson` and `qa/run-manifest.json` by exact
#: path, so a scenario tuned until it passed still cannot leave its own scored proof — and
#: starting the scored run wipes `qa/` whole, scratch included, which is the intent: no dry
#: run outlives the pass that made it.
QA_SCRATCH_DIRNAME = "qa"


@blueprint.node
def clear_qa_evidence(logger: logging.Logger, spec_dir: str = "") -> QaCleared:
    """Delete last pass's `qa/` outputs, verdict and report, and make sure the spec dir exists.

    Deliberately does not recreate `qa/`: the ostler runner owns that directory, its log,
    its manifest and its evidence, and a node that pre-created it would be authoring an
    empty shell the evidence gate then has to tell apart from a real run.

    Scratch goes with it, and needs no second target: dry runs nest inside `qa/`, so one
    rmtree takes both. A dry run is authoring exhaust — it exists to tell the planner
    whether a locator resolves — and leaving it would both ship it in the story's commit
    and offer the audit a second, unscored ledger to read.
    """
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
    """Bring the durable QA stack up (or adopt one already serving) before the runner.

    Thin wrapper: the lifecycle lives in `workhorse_workflows.qa.runner.ensure_stack`,
    shared with any other family that needs the same stack before its own runner.
    """
    return _qa_runner.ensure_stack(logger, docs_path=docs_path, repo_dir=repo_dir)


@blueprint.node
def lint_qa_plan(
    logger: logging.Logger, spec_dir: str = "", docs_path: str = "", repo_dir: str = ""
) -> QaPlanValidation:
    """`ostler qa lint` on `<spec_dir>/qa_plan.py` — is this plan's AST safe to import?

    Runs ahead of `validate_qa_plan`, which imports the plan to check it: a plan that
    reaches for `subprocess`/`eval`/a dunder escape should never get as far as import,
    since import is where it would run.
    """
    plan = str(Path(spec_dir) / QA_PLAN_FILE)
    docs_root = find_docs_root(docs_path, repo_dir)
    outcome = Ostler(docs_root).qa_lint(plan, spec=spec_dir)
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
    """`ostler qa tools list` — the tools this repo opted into, resolved for this host.

    A node rather than a plain call from `_plan_args`: which tools resolve, and whether
    their binaries are on `PATH`, is a fact about *this* machine, and a resumed run must
    see the catalog it was checkpointed with, not one re-derived against whatever the
    host looks like when the resume happens to run.
    """
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
    """`ostler qa validate` on `<spec_dir>/qa_plan.py` — is this plan executable?

    The whole pre-run plan gate, now that the semantic reviewer is gone: it has to pass
    before the stack comes up, so a plan that cannot run is caught before anything expensive
    starts. Validating a Python plan imports it, so a plan that does not import fails here
    rather than an hour later as a driver failure. It is also the gate that binds each claimed
    obligation to the `verify:` check the node declared, which is the semantic work the
    reviewer used to do by reading.
    """
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
    """Did the repair turn run each scenario it had to repair, and did each one pass?

    The deterministic half of the dry-run contract. `repair-qa-plan.md` is told to execute
    every failing scenario, and every scenario it changed, with
    `ostler qa run … --scenario <id> --out-dir <id>`; this reads what that left
    behind. A scenario has to have a log, that log has to contain at least one `assert`
    record naming it, and none of those records may be a FAIL:

    - **no directory or no log** — the scenario was not run. An unexecuted repair is a
      hypothesis, and the flow already knows what a hypothesis costs: a full suite run to
      test it, and the whole loop again when it was wrong.
    - **a log with no `assert` record for the scenario** — the run reached no assertion, so
      it establishes nothing. This is the shape a locator typo or an unreachable fixture
      makes, and it is exactly what the dry run is for.
    - **any FAIL** — the scenario still fails, and the plan is not repaired.

    One out-dir per scenario is load-bearing rather than tidy: ostler's runner `rmtree`s its
    out-dir at the start of every run, so a shared scratch directory would hold only the last
    scenario's evidence and every earlier one would read as "not run".

    Scratch, never scored: this reads `qa/<id>/`, which `clear_qa_evidence` deletes and
    which the evidence gate never looks at — that gate names `qa/qa-run.ndjson` and
    `qa/run-manifest.json` exactly, so a scenario tuned until it passed still cannot leave
    its own proof where the score is read.
    """
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
        # A single-scenario run is allowed to leave the field off its own records: the
        # out-dir names the scenario, so an unlabelled assert in it is that scenario's.
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
    """Run the runbook's `stop:` recipe now that the run is finished.

    Called on the run's terminal paths, not between stories: the whole point of the reuse
    policy is that a stack survives the laps that follow, and a teardown per story would
    pay the bring-up cost again for every one of them. Before this existed nothing called
    `teardown_stack` at all, so a completed run left its compose project, its emulators and
    its dev server serving until somebody noticed the ports.

    Never fatal. A run that produced its verdict has produced it; failing it here would
    throw that away over a cleanup, and the stack it could not reap is a leak an operator
    can see, not a result they can lose.
    """
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
    """Execute the QA plan through ostler and normalize its four-state outcome.

    Thin wrapper: the run (secret minting, `Ostler(...).qa_run`, status normalization)
    lives in `workhorse_workflows.qa.runner.run_qa_plan`, shared with any other family
    that runs a compiled QA plan the same way.
    """
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
