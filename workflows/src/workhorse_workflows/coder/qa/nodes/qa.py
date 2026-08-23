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
import subprocess
from pathlib import Path

from ostler import Ostler
from ostler.qa import runbook, stack
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.kit.credentials import scoped_envs
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
    QaRunResult,
    QaToolCatalog,
    StackStatus,
    StackTornDown,
)

#: The four states `ostler qa run` is allowed to report. Anything else is `invalid` —
#: a runner that answered something unrecognized has not established a verdict.
RUN_STATUSES = frozenset({"passed", "failed", "blocked", "invalid"})

#: How long one `secrets:` mint recipe may take. Generous because a recipe may lease a
#: password or sign in against an emulator, and short enough that a recipe waiting on a
#: prompt nobody will answer fails the pass instead of hanging the run.
SECRET_MINT_TIMEOUT_S = 60.0

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

    A long-running stack has to start *outside* any agent turn, or the turn's teardown kills
    it mid-build. The lifecycle is `ostler.qa.stack.ensure_stack` and the recipe is
    `ostler.qa.runbook.load_stack`, which reads it off the book's `runbook` node — this node
    is only the outcome's translator.

    `none` means the book declares no stack, and unlike the `skip` it replaces it is not a
    pass: a repo that never authored a runbook used to run QA against nothing and say so
    only in a log line, which is how one story spent an entire run's budget discovering it.
    """
    root = find_docs_root(docs_path, repo_dir)
    manifest = runbook.load_stack(root, logger=logger)
    if not manifest:
        return StackStatus(
            ready="none",
            notes=("The book declares no `runbook` node and no `walkthrough: true` server, "
                   "so there is no stack to bring up. Author the runbook before QA runs "
                   "against nothing — `ostler doctor` reports this as `runbook-missing`."),
        )

    result = stack.ensure_stack(manifest, repo_root=str(root), logger=logger)
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
            + f". Repair the runbook at `{manifest.get('source', '')}` or its seed recipe "
            "(never background the stack in the agent shell)."
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
    torn = str(outcome.data.get("torn_down") or outcome.status or "no")
    logger.info("QA stack teardown: %s", torn)
    return StackTornDown(torn_down=torn, notes=outcome.message)


def _mint_qa_secrets(
    secrets: dict[str, str], root: Path, logger: logging.Logger
) -> tuple[dict[str, str], str]:
    """Run the runbook's `secrets:` recipes; return ``({NAME: token}, error)``.

    A short-lived credential (a token signed against a local auth emulator, say) goes
    stale between QA-plan authoring and the run that spends it — minutes to hours apart
    in this flow. The runbook's `prepare`/`seed`/`health` steps run once per stack
    bring-up, not once per plan execution, so they cannot be the freshening point; this
    runs immediately before the one call that spends the token.

    Each recipe is a repo-owned shell command (never interpreted here) that resolves
    whatever the repo needs and prints the fresh secret to stdout and nothing else. This
    module knows none of that shape; it runs the recipe and reads its output back.

    A non-empty `error` means the plan must not run this pass: a stale or absent secret
    would only fail with a confusing 401 deep inside the runner, not at the boundary
    that actually knows what broke. The first failure stops the loop, because a partial
    set is a run that fails later for a reason the caller has already been told.

    The tokens are returned to the caller's local scope only, never logged, and never
    part of a node's return value — see `workhorse_workflows.kit.credentials.scoped_envs`,
    which is the only place they are allowed to touch `os.environ`.
    """
    minted: dict[str, str] = {}
    cwd = str(root.resolve())
    for name, recipe in secrets.items():
        if not name or not recipe:
            return {}, f"secret `{name or '(unnamed)'}` declares no mint recipe"
        try:
            result = subprocess.run(  # noqa: S602 (documented repo-owned recipe)
                recipe, shell=True, cwd=cwd, capture_output=True, text=True,
                timeout=SECRET_MINT_TIMEOUT_S, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {}, f"mint command for {name} could not be run: {exc}"
        if result.returncode != 0:
            return {}, (
                f"mint command for {name} exited {result.returncode}: "
                f"{result.stderr.strip()[:500]}"
            )
        token = result.stdout.strip()
        if not token:
            return {}, f"mint command for {name} produced no output"
        minted[name] = token
    if minted:
        logger.info("minted fresh QA secrets for %s", ", ".join(minted))
    return minted, ""


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

    Before the run, the book's runbook `secrets:` (if any) are minted and set in the
    process environment for the duration of `Ostler(...).qa_run` only — see
    `_mint_qa_secrets`. `qa_run` executes the plan **in this process**, so a `secret(...,
    from_env=...)` in the plan reads whatever this scope just set; nothing shells out for
    the plan itself, so there is no other boundary to cross the value at.
    """
    docs_root = find_docs_root(docs_path, repo_dir)
    plan = str(Path(spec_dir) / QA_PLAN_FILE)
    manifest = runbook.load_stack(docs_root, logger=logger)
    minted, error = _mint_qa_secrets(manifest.get("secrets") or {}, docs_root, logger)
    if error:
        logger.warning("QA secret refresh failed: %s", error)
        return QaRunResult(status="blocked", notes=f"QA secret refresh failed: {error}")
    with scoped_envs(minted):
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
    "teardown_stack",
    "validate_qa_plan",
    "verify_qa_dry_run",
]
