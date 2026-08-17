"""The QA flow's deterministic spine: clear evidence, bring the stack up, validate, run.

Ports `clear-qa-evidence.py`, `ensure-stack.py`, `validate-qa-plan.py` and
`run-qa-plan.py`. The ostler-backed nodes call `Ostler` directly and read the `QaOutcome`
it answers with — each turns it into a status by its own rule, which is why there is no
adapter between them and the API — and they resolve their docs root the same way, through
`find_docs_root(docs_path, repo_dir)` rather than a per-node cwd the driver does not have.

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
from typing import Any

import yaml
from ostler import Ostler, registry
from workhorse import stack
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
    QaGiveupRecord,
    QaPlanValidation,
    QaRunResult,
    QaToolCatalog,
    StackStatus,
)

#: The four states `ostler qa run` is allowed to report. Anything else is `invalid` —
#: a runner that answered something unrecognized has not established a verdict.
RUN_STATUSES = frozenset({"passed", "failed", "blocked", "invalid"})

#: Where a plan turn's dry runs land — `ostler qa run --scenario … --out-dir`. Spec-relative
#: and deliberately *not* `qa/`: that directory is the scored ledger the evidence gate reads,
#: and a scenario tuned until it passed would otherwise be able to leave its own proof. It is
#: cleared with the evidence for the same reason, so no dry run outlives the pass that made it.
QA_SCRATCH_DIRNAME = "qa-dry-run"


@blueprint.node
def clear_qa_evidence(logger: logging.Logger, spec_dir: str = "") -> QaCleared:
    """Delete last pass's `qa/` outputs and root verdict, and make sure the spec dir exists.

    Deliberately does not recreate `qa/`: the ostler runner owns that directory, its log,
    its manifest and its evidence, and a node that pre-created it would be authoring an
    empty shell the evidence gate then has to tell apart from a real run.

    `QA_SCRATCH_DIRNAME` goes with it. A dry run is authoring exhaust — it exists to tell the
    planner whether a locator resolves — and leaving it in the spec directory would both ship
    it in the story's commit and offer the audit a second, unscored ledger to read.
    """
    if not spec_dir:
        logger.warning("no spec_dir given — nothing to clear")
        return QaCleared()
    root = Path(spec_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    for name in ("qa", QA_SCRATCH_DIRNAME):
        stale = root / name
        if stale.exists():
            shutil.rmtree(stale)
            logger.info("removed stale qa dir %s", stale)
    evidence = root / "qa-evidence.json"
    if evidence.exists():
        evidence.unlink()
        logger.info("removed stale evidence file %s", evidence)
    return QaCleared(cleared=True)


@blueprint.node
def record_qa_giveup(
    logger: logging.Logger,
    spec_dir: str = "",
    story_slug: str = "",
    spent: str = "",
    plan_validation_notes: str = "",
    assessment_notes: str = "",
    audit_notes: str = "",
    context_notes: str = "",
    evidence_notes: str = "",
) -> QaGiveupRecord:
    """Write `<spec_dir>/qa.md` when the flow gives up before any QA run produced one.

    A give-up ends the run, and `Coder.give_up`'s failure names this file when it is there.
    It is not always there — the QA-plan repair budget can run out with no plan ever
    executed — and on that path the operator is handed a stop with nothing to read. The flow
    is not empty-handed at that moment, though: the gate that refused the
    plan handed its findings to `QaLoop`, and they are still on the loop when `_exhausted`
    builds the result. They are simply dropped there, because `QaFlowResult` carries the
    *code*-rework verdict and the plan gates never touch it.

    A live run made the cost concrete. `group-membership` exhausted its QA-plan repairs; the
    refusal was specific and correct — three scenarios asserted a raw substring against a
    validation error body the API double-JSON-encodes, so they could never match — and the
    only copy of it was a run-dir artifact that the next story's QA flow overwrote within the
    hour. The retry starts from the same blank story and walks into the same wall.

    Deliberately never overwrites: a real QA run's assessment is the better document, and a
    give-up that happens *after* one has run has nothing to add to it.
    """
    if not spec_dir:
        logger.warning("no spec_dir given — the give-up leaves no explanation behind")
        return QaGiveupRecord()
    path = Path(spec_dir) / "qa.md"
    if path.exists():
        logger.info("%s already exists — leaving the QA run's own assessment in place", path)
        return QaGiveupRecord(path=str(path))

    # The schema verdict leads: on the budget-exhausted path, where no plan ever ran, it is
    # usually the only diagnosis there is.
    sections = [
        f"## {heading}\n\n{notes.strip()}\n"
        for heading, notes in (
            ("Plan validation — `ostler qa validate`", plan_validation_notes),
            ("Run assessment", assessment_notes),
            ("Evidence audit", audit_notes),
            ("Obligation packet", context_notes),
            ("Last QA verdict", evidence_notes),
        )
        if notes.strip()
    ]
    body = "\n".join(sections) if sections else (
        "No gate left a diagnostic. The flow ended without reaching one — check the run's\n"
        "`events.jsonl` for where it stopped.\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    # Stamped with the same `type:` a real QA assessment carries. A doc under `docs/specs/`
    # with no non-empty `type` is an `okf-missing-type` *error* in `ostler doctor`, and this
    # file lands in exactly that directory. Leaving it bare made the give-up plant a
    # permanent doctor error, which the next story's documentation gate then read as its own
    # blocker and refused to converge on — one story's QA give-up blocking an unrelated
    # story's docs phase, days later, with nothing connecting the two.
    front = f"---\ntype: {registry.spec_type_for(path.name)}\n---\n\n"
    path.write_text(
        front
        + f"# QA give-up — {story_slug or 'story'}\n\n"
        f"QA never reached a verdict on this story: {spent or 'the retry budget'} was spent "
        "and no\nrun produced an assessment. There is no evidence directory, because nothing "
        "ran. What\nfollows is what the gates said before the budget ended, which is the whole "
        "of what the\nrun knew when it stopped.\n\n" + body,
        encoding="utf-8",
    )
    logger.info("recorded the give-up diagnostics at %s", path)
    return QaGiveupRecord(written=True, path=str(path))


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
    if "sandbox" in manifest:
        return StackStatus(
            failed_step="manifest",
            notes=(
                f"{manifest_rel} has a top-level `sandbox:` key, which no longer does "
                "anything — QA's docker sandbox was removed. Delete the key."
            ),
        )

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
    `ostler qa run … --scenario <id> --out-dir qa-dry-run/<id>`; this reads what that left
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

    Scratch, never scored: this reads `qa-dry-run/`, which `clear_qa_evidence` deletes and
    which the evidence gate never looks at. A scenario tuned until it passed cannot leave
    its own proof in `qa/`.
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
                f"--out-dir {QA_SCRATCH_DIRNAME}/{scenario}` and repair it until it passes."
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
def run_qa_plan(
    logger: logging.Logger,
    spec_dir: str = "",
    docs_path: str = "",
    repo_dir: str = "",
) -> QaRunResult:
    """Execute the QA plan through ostler and normalize its four-state outcome.

    The returncode is deliberately ignored: `failed` and `blocked` are answers the runner
    is *supposed* to give, and both exit non-zero. The status comes off the payload, and
    only an unrecognized one becomes `invalid`.
    """
    plan = str(Path(spec_dir) / QA_PLAN_FILE)
    docs_root = find_docs_root(docs_path, repo_dir)
    outcome = Ostler(docs_root).qa_run(plan, spec=spec_dir)
    status = outcome.status.lower()
    if status not in RUN_STATUSES:
        status = "invalid"
    notes = notes_for(outcome, f"Ostler QA run returned {status}.")
    logger.info("ostler qa run for %s returned status=%s", spec_dir, status)
    return QaRunResult(status=status, notes=notes, ostler=outcome.data)


__all__ = [
    "clear_qa_evidence",
    "ensure_stack",
    "lint_qa_plan",
    "qa_tools_catalog",
    "run_qa_plan",
    "validate_qa_plan",
    "verify_qa_dry_run",
]
