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

from ostler import Ostler, graph as graph_mod, model, path as path_mod
from ostler.model import Graph, UINode
from ostler.qa import runbook

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


def _entry_result(
    results: list[dict],
    runbooks: tuple[UINode, ...],
    near: str,
    graph: Graph,
) -> dict:
    """Of a successful bring-up, the result the caller actually needs to drive.

    With one manifest there is only one answer. With several, `near` — the spec under
    audit — says which surface the caller is about to drive, and the manifest whose
    runbook sits in that same surface is the one whose `entry_url` (and process handles)
    the caller wants; every other manifest came up only because the environment needs it
    serving too. Falls back to the last result when `near` is absent or names no surface
    among the runbooks, the same "last one" a single-manifest caller always got.
    """
    if near and len(results) > 1:
        near_path = Path(near)
        features_root = path_mod.features_root(graph)
        near_abs = near_path if near_path.is_absolute() else graph.root / near_path
        target_surface = graph_mod.surface_of(near_abs, features_root)
        if target_surface:
            for result, node in zip(results, runbooks, strict=False):
                if graph_mod.surface_of(node.path, features_root) == target_surface:
                    return result
    return results[-1]


def _merge_secrets(manifests: list[dict]) -> tuple[dict[str, str], str]:
    """Every manifest's mint recipes in one namespace, or the reason there cannot be one.

    A QA run substitutes secrets by bare name into one process environment, so two stack
    runbooks that mint different recipes under one name are asking for two values of a
    single variable and only one of them can be live. Neither is more right than the
    other, so this refuses rather than picking: a run that silently took the first would
    drive the second service with the first service's credential and fail somewhere with
    no mention of a secret.

    The refusal is a debt, not the fix. A name is unique only within the scope that
    issues it, and here two issuing scopes share one flat run namespace — the vocabulary
    has no way to say *whose* secret a name is. It goes when a secret reference can name
    its service; until then this is the honest answer, and it fires only on a book that
    declares the collision.
    """
    secrets: dict[str, str] = {}
    sources: dict[str, str] = {}
    for manifest in manifests:
        source = manifest.get("source", "?")
        for name, recipe in (manifest.get("secrets") or {}).items():
            if name in secrets and secrets[name] != recipe:
                return {}, (
                    f"The stack declares secret {name!r} twice with different mint "
                    f"recipes: {sources[name]} and {source}. A QA run substitutes "
                    "secrets by name into one environment, so it cannot hold both. "
                    "Give them distinct names, or declare one recipe both services use.")
            secrets[name] = recipe
            sources.setdefault(name, source)
    return secrets, ""


def ensure_stack(
    logger: logging.Logger,
    docs_path: str = "",
    repo_dir: str = "",
    near: str = "",
) -> StackStatus:
    """Bring the durable QA stack up (or adopt one already serving) before the runner.

    A long-running stack has to start *outside* any agent turn, or the turn's teardown kills
    it mid-build. The lifecycle is `ostler.qa.runbook.bring_up_stacks` (which owns the
    one-at-a-time, stop-at-the-first-failure bring-up policy) and the recipe is
    `ostler.qa.runbook.load_stacks`, which reads it off the book's `runbook` nodes — this
    function is only the outcome's translator.

    `near` is the filesystem path of the spec under audit. It is passed straight through to
    `load_stacks`, which uses it only to narrow an *ambiguous* selection (several stack
    runbooks across several environments) to the one environment `near`'s surface belongs
    to; it plays no part once a selection has already resolved. This function additionally
    uses it, on a successful multi-manifest bring-up, to pick which manifest's `entry_url`
    to report — see `_entry_result`.

    An empty manifest list is two different answers, split by what the book describes.
    `none` means the book serves something but declares no way to bring it up, and unlike
    the `skip` it replaces it is not a pass: a repo that never authored a runbook used to
    run QA against nothing and say so only in a log line, which is how one story spent an
    entire run's budget discovering it. `unneeded` means the book serves nothing — the
    same `has_served_surface` test the doctor's `runbook-missing` gates on — so the empty
    manifest is the repo's documented topology, not a gap. Collapsing the two was how an
    artifact-only repo got told, every lap, to author a runbook its own doctor said it
    did not need: the setup fixer could not comply, the operator gate could not clear it,
    and the story escalated forever.

    A book with several stack runbooks bound to *one* environment used to be a third
    refusal here — this runner would not pick which one to skip. It no longer refuses:
    `load_stacks` hands back one manifest per runbook and they come up together, in
    document order, the same policy `ostler qa stack up` already used.
    """
    root = find_docs_root(docs_path, repo_dir)
    graph = model.load(root)
    manifests, selection = runbook.load_stacks(
        graph, near=Path(near) if near else None, logger=logger)
    if not manifests:
        if not runbook.has_served_surface(graph):
            return StackStatus(
                ready="unneeded",
                notes=("The book serves nothing — no `screen`, no `server` — so an empty "
                       "stack is its documented topology. QA scenarios invoke the repo's "
                       "commands directly; there is nothing to bring up first."),
            )
        if selection.reason == "ambiguous":
            return StackStatus(
                ready="none",
                notes=(f"The book declares {len(selection.candidates)} stack runbooks "
                       "across several environments and names none, so bring-up would "
                       "have to guess which system to start: "
                       f"{', '.join(selection.candidates)}. Bind the ones that serve one "
                       "system to a shared `environment:` node, or say which one to bring "
                       "up — there is no missing runbook to author here."),
            )
        return StackStatus(
            ready="none",
            notes=("The book describes a served surface but declares no stack — no stack "
                   "`runbook` node and no `server` node — so QA would run "
                   "against nothing. Author the runbook that brings it up; `ostler doctor` "
                   "reports this as `runbook-missing`."),
        )

    results = runbook.bring_up_stacks(manifests, repo_root=str(root), logger=logger)
    last = results[-1]
    if last.get("ready") == "yes":
        chosen = _entry_result(results, selection.runbooks, near, graph)
        common = {
            "app_pid": chosen.get("app_pid", ""),
            "app_pgid": chosen.get("app_pgid", ""),
            "entry_url": chosen.get("entry_url", ""),
            "failed_step": chosen.get("failed_step", ""),
        }
        how = "adopted" if chosen.get("adopted") == "yes" else "brought up"
        where = ", ".join(r.get("entry_url") or "(no entry url)" for r in results)
        plural = "" if len(results) == 1 else f" ({len(results)} services)"
        return StackStatus(
            ready="yes", notes=f"Stack {how} and healthy at {where}{plural}.", **common)

    common = {
        "app_pid": last.get("app_pid", ""),
        "app_pgid": last.get("app_pgid", ""),
        "entry_url": last.get("entry_url", ""),
        "failed_step": last.get("failed_step", ""),
    }
    step = last.get("failed_step", "unknown")
    # The step's own message goes in the notes, because the notes are what the setup
    # fixer is briefed with: told only *which* step failed, it re-derives the failure
    # from scratch — an expensive turn spent rediscovering a line the stack already had.
    error = (last.get("error") or "").strip()
    manifest = last.get("manifest") or {}
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
    docs_graph = model.load(docs_root)
    near = str(docs_root / spec_dir) if spec_dir else ""
    manifests, _selection = runbook.load_stacks(
        docs_graph, near=Path(near) if near else None, logger=logger)
    secrets, collision = _merge_secrets(manifests)
    if collision:
        return QaPlanRun(status="blocked", notes=collision)
    minted, error = _mint_qa_secrets(secrets, docs_root, logger)
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
