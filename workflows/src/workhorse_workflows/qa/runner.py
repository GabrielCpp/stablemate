"""Bring a book's stack up and run its compiled plan through ostler — family-neutral.

Plain, undecorated functions: no `Workflow` state, no `@blueprint.node`. `coder`'s
`ensure_stack`/`run_qa_plan` nodes (`coder/qa/nodes/qa.py`) are thin wrappers around the
two public functions here, so a coder run's node names, checkpoints and telemetry are
unchanged — only the body moved. A live-audit lane (or any other family) calls these two
functions directly, the same way `coder` does, since `Workflow.call` takes any function
object and never checked blueprint membership in the first place.

Coder-specific return types (`StackStatus`, `QaPlanRun`, `QaStatus`) stay imported from
`coder.shared.schemas.qa` rather than duplicated here — they subclass `CoderResult`,
which is explicitly the base for "every agent reply and node return in the coder
workflow" and is read generically by coder's own resolution/repair-loop machinery
(`blocked`, `actionable`). Cloning them into a neutral module would either fork that
machinery or leave the clones unused; importing them is the smaller, honest dependency
until a second family needs a verdict shape `CoderResult` cannot express.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from ostler import Ostler, model
from ostler.qa import runbook, stack

from workhorse_workflows.coder.shared.schemas.qa import QaPlanRun, QaStatus, StackStatus
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.kit.credentials import scoped_envs
from workhorse_workflows.qa.support import QA_PLAN_FILE, notes_for

#: The four states `ostler qa run` is allowed to report, keyed by what it spelled.
#: Anything else is `invalid` — a runner that answered something unrecognized has not
#: established a verdict.
RUN_STATUSES: dict[str, QaStatus] = {
    "passed": "passed",
    "failed": "failed",
    "blocked": "blocked",
    "invalid": "invalid",
}

#: How long a secret's mint recipe gets before it counts as hung rather than slow.
SECRET_MINT_TIMEOUT_S = 60.0


def ensure_stack(
    logger: logging.Logger,
    docs_path: str = "",
    repo_dir: str = "",
) -> StackStatus:
    """Bring the durable QA stack up (or adopt one already serving) before the runner.

    A long-running stack has to start *outside* any agent turn, or the turn's teardown kills
    it mid-build. The lifecycle is `ostler.qa.stack.ensure_stack` and the recipe is
    `ostler.qa.runbook.load_stack`, which reads it off the book's `runbook` node — this
    function is only the outcome's translator.

    An empty manifest is two different answers, split by what the book describes. `none`
    means the book serves something but declares no way to bring it up, and unlike the
    `skip` it replaces it is not a pass: a repo that never authored a runbook used to run
    QA against nothing and say so only in a log line, which is how one story spent an
    entire run's budget discovering it. `unneeded` means the book serves nothing — the
    same `has_served_surface` test the doctor's `runbook-missing` gates on — so the empty
    manifest is the repo's documented topology, not a gap. Collapsing the two was how an
    artifact-only repo got told, every lap, to author a runbook its own doctor said it
    did not need: the setup fixer could not comply, the operator gate could not clear it,
    and the story escalated forever.
    """
    root = find_docs_root(docs_path, repo_dir)
    graph = model.load(root)
    manifest = runbook.load_stack(root, graph=graph, logger=logger)
    if not manifest:
        if not runbook.has_served_surface(graph):
            return StackStatus(
                ready="unneeded",
                notes=("The book serves nothing — no `screen`, no `server` — so an empty "
                       "stack is its documented topology. QA scenarios invoke the repo's "
                       "commands directly; there is nothing to bring up first."),
            )
        return StackStatus(
            ready="none",
            notes=("The book describes a served surface but declares no stack — no stack "
                   "`runbook` node and no `walkthrough: true` server — so QA would run "
                   "against nothing. Author the runbook that brings it up; `ostler doctor` "
                   "reports this as `runbook-missing`."),
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


def run_qa_plan(
    logger: logging.Logger,
    spec_dir: str = "",
    docs_path: str = "",
    repo_dir: str = "",
    only: list[str] | None = None,
    plan_file: str | None = None,
) -> QaPlanRun:
    """Execute the QA plan through ostler and normalize its four-state outcome.

    `plan_file`, when given, overrides the default `<spec_dir>/qa_plan.py` path — the
    live-audit lane's compiled-from-the-book fallback writes its plan under a scratch run
    directory outside the book tree (never back into `docs/specs`) and passes that path
    here rather than an authored spec dir's default location.

    The returncode is deliberately ignored: `failed` and `blocked` are answers the runner
    is *supposed* to give, and both exit non-zero. The status comes off the payload, and
    only an unrecognized one becomes `invalid`.

    Before the run, the book's runbook `secrets:` (if any) are minted and set in the
    process environment for the duration of `Ostler(...).qa_run` only — see
    `_mint_qa_secrets`. `qa_run` executes the plan **in this process**, so a `secret(...,
    from_env=...)` in the plan reads whatever this scope just set; nothing shells out for
    the plan itself, so there is no other boundary to cross the value at.

    `only`, when given, narrows the run to those scenario ids — a real, scored subset
    (`Ostler.qa_run`'s `only` without a `label` still writes `qa-evidence.json`), not the
    unpublished dry run `only` is paired with elsewhere. A targeted re-run passes the
    claims whose ledger fingerprint moved; `None` runs the whole plan, unchanged from
    before this parameter existed.
    """
    docs_root = find_docs_root(docs_path, repo_dir)
    plan = plan_file if plan_file is not None else str(Path(spec_dir) / QA_PLAN_FILE)
    manifest = runbook.load_stack(docs_root, logger=logger)
    minted, error = _mint_qa_secrets(manifest.get("secrets") or {}, docs_root, logger)
    if error:
        logger.warning("QA secret refresh failed: %s", error)
        return QaPlanRun(status="blocked", notes=f"QA secret refresh failed: {error}")
    with scoped_envs(minted):
        outcome = Ostler(docs_root).qa_run(plan, spec=spec_dir, only=only)
    status = RUN_STATUSES.get(outcome.status.lower(), "invalid")
    notes = notes_for(outcome, f"Ostler QA run returned {status}.")
    logger.info("ostler qa run for %s returned status=%s", spec_dir, status)
    return QaPlanRun(status=status, notes=notes, ostler=outcome.data)


__all__ = ["ensure_stack", "run_qa_plan"]
