"""The dev flow's deterministic work: validate, dispatch, branch, iterate, gate.

Ports `validate-plan-context.py`, `resolve-impl-context.py`, `branch-code-repos.py`,
`select-next-layer.py`, `run-lint.py` and the *consume* half of `await_operator.py`.

**`await_operator.py` is not ported; its state machine is split in two.** The 280 lines of
ctypes inotify that made up the wait are replaced by the driver's `Await`, which polls a
path portably and is the whole reason that script existed. What is left is the half a node
still has to do: read the file the operator answered in, take the `SCOPE:` line off it, and
flip `STATUS: ANSWERED` to `CONSUMED` so a later re-block re-arms instead of looping forever
on a stale answer. That is `read_operator_context` below. The *decision* the script's
`STATUS:` line encoded — answered, or still awaiting — moves into the flow, because the
driver's `Await` waits unconditionally and would otherwise block on a resolution that had
already happened; that is the same split `author` and `surveyor` settled on.

**`plan-context.json` is written here and read nowhere that produced it.** `record_plan`
projects the checkpointed `PlanResult` onto disk; the dispatch nodes take that same value as
an argument and only fall back to reading the file when the caller is not the run that
produced it (QA on a later run, the fix lane, docs). The file is the artifact other readers
were built against — `ostler artifact vet`, a human in the spec dir — not the flow's channel.

Two things the scripts did with paths are kept exactly, and one is worth naming.
`validate-plan-context.py` and `select-next-layer.py` resolve `<spec_dir>/plan-context.json`
against `find_repo_root(repo_dir)` while `branch-code-repos.py` resolves it against
`find_docs_root(docs_path, repo_dir)` — a real disagreement that is inert in practice, because `prepare_story`
hands every flow an **absolute** `spec_dir` and joining an absolute path onto either root
yields the same file. The nodes keep their script's root so a standalone run with a relative
spec dir still behaves as it did.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

import yaml
from workhorse import gates
from workhorse_workflows.kit import find_docs_root, find_repo_root, load_json
from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared import story_status
from workhorse_workflows.coder.shared.contract import service_problems
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.dev import (
    BranchOutcome,
    ChangedFiles,
    DispatchEntry,
    GateList,
    GateOutcome,
    ImplContext,
    LayerPick,
    OperatorAnswer,
    PlanFixture,
    PlanSummary,
    PlanValidation,
    QaRunEntry,
    StoryStatusCheck,
    lift_fixture,
)
from workhorse_workflows.kit import (
    build_dispatch_list,
    checkout,
    current_branch,
    get_affected_repos,
    local_branch_exists,
    resolve_workspace,
)
from ostler import Ostler
from ostler.select import is_done

#: Cap on the gate output threaded into the fix agent's context. The tail carries the
#: findings; the head is usually the command echo.
MAX_GATE_OUTPUT = 4000

#: Seconds a service's gate command gets before it is called failed.
GATE_TIMEOUT = 600

#: The gates the dev lane runs after every implement and repair turn, cheapest first. A
#: repo declares the commands; this tuple is only the order they are asked in, and a gate
#: no service declares costs nothing to ask about.
GATE_ORDER = ("lint", "test")

#: The three states `<story-folder>/context.md` can be in. The `STATUS:`/`SCOPE:` header that
#: says which one is read and written through `workhorse.gates`, shared with groom on the
#: other side of the gate; these names are this file's own vocabulary.
AWAITING = "AWAITING_OPERATOR"
ANSWERED = "ANSWERED"
CONSUMED = "CONSUMED"


def _spec_dir(spec_dir: str, root: Path) -> Path:
    """A spec dir as an absolute path, taken relative to `root` unless already absolute."""
    path = Path(spec_dir)
    return path if path.is_absolute() else root / path


def _spec_relative(plan_file: str, spec_abs: Path | None, root: Path | None) -> str:
    """`plan_file` as the spec-relative path it is declared to be, under either reading.

    The field means "relative to the spec dir", and `plan-story.md` says so — but the turn
    that fills it has just *written* `docs/specs/<story>/plan.md`, and a planner holding
    that repo-relative string in its hand hands the same string back. The two readings name
    the same file on disk, so the disagreement is about notation and nothing else. It was
    not free: in benchmark run `c1` it cost a 203 s high-power re-planning lap whose whole
    output was one string rewritten into another string for the same file, and the errors it
    was sent came from two checkers at once — this module's own, and `ostler artifact vet`'s
    (`artifact/kinds.py`), which resolves the field the same way. Normalising here fixes
    both, because ostler vets the projection Python writes.

    Only a path that resolves to a file *inside* the spec dir is repaired. One that points
    anywhere else is passed through verbatim, so the check downstream still fails on it and
    the error still names what the planner actually wrote.
    """
    if not plan_file or spec_abs is None or root is None:
        return plan_file
    if (spec_abs / plan_file).is_file():
        return plan_file
    candidate = Path(plan_file)
    # Both sides are resolved before they are compared: `story.py` hands the spec dir over
    # already resolved while the repo root arrives as it was given, so on any tree reached
    # through a symlink (a `/tmp` checkout, a worktree) the two would not share a prefix and
    # a repairable path would fall through to the error.
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if not resolved.is_file():
        return plan_file
    try:
        return resolved.relative_to(spec_abs.resolve()).as_posix()
    except ValueError:
        return plan_file


def plan_document(
    plan: dict[str, Any],
    repos: dict[str, dict],
    spec_abs: Path | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """The plan-context mapping, built from a `PlanResult` and the resolved workspace.

    One function, because there are two consumers of the same derivation: the projection
    written to disk and the dispatch decoded in memory. They cannot be allowed to disagree
    — the whole point of Python owning the document is that there is one of it.

    Repo names are canonicalized case-insensitively against the workspace keys. The planner
    tends to emit the human-facing project name ("Acme") while the key is the folder name
    ("acme"), and repairing that is strictly better than routing a symptom-only error back
    to a model that re-authors the same casing from the title-cased branding in its prompt.

    `plan_file` is repaired for the same reason and under the same rule — see
    `_spec_relative`. Both repairs need the spec dir and the repo root; without them the
    values pass through, which is what a caller that has neither wants.
    """
    canon_by_lower = {name.lower(): name for name in repos}

    def canon(repo_name: str) -> str:
        return repo_name if repo_name in repos else canon_by_lower.get(repo_name.lower(), repo_name)

    def entry(svc: Any) -> dict[str, Any]:
        svc = dict(svc or {})
        svc["repo"] = canon(str(svc.get("repo", "")))
        if "plan_file" in svc:
            svc["plan_file"] = _spec_relative(str(svc.get("plan_file", "")), spec_abs, root)
        return svc

    services = [entry(svc) for svc in plan.get("services") or []]
    order = [
        f"{canon(str(item).split('::', 1)[0])}::{str(item).split('::', 1)[1]}"
        if "::" in str(item)
        else str(item)
        for item in plan.get("implementation_order") or []
    ]
    return {
        "services": services,
        "implementation_order": order,
        "shared_packages": [entry(pkg) for pkg in plan.get("shared_packages") or []],
        "verification_setup": _verification_setup(plan),
        "fixtures": _fixtures(plan),
    }


def _verification_setup(doc: dict[str, Any]) -> dict[str, Any]:
    """The story's `## Verification setup`, under either spelling.

    The field was `qa_stack` until it was renamed off its near-homograph with the
    then-`qa-stack.yml` file, which named something else entirely (the stack declaration,
    since moved into the book's `runbook` node). The old key is still read
    because `plan-context.json` documents written before the rename are on disk in every
    run directory a resume might land in, and a resume that silently lost the fixture list
    would hand QA a story it could not stand up — the one failure this projection exists
    to prevent. Nothing writes the old key; this only reads it.
    """
    return doc.get("verification_setup") or doc.get("qa_stack") or {}


def _fixtures(doc: dict[str, Any]) -> list[dict[str, str]]:
    """The story's declared fixtures, from the typed field or nested in the setup block.

    Two spellings for one thing, and both are on disk: the planner has been writing
    `fixtures:` inside `## Verification setup` since before the field existed, and every
    `plan-context.json` written that way is still what some resume validates against. A
    bare string is the fixture's name — the lift `PlanFixture` gives it, repeated here
    because this projection reads raw documents rather than the model. An entry with prose
    and no name is kept: it is a real arrangement the story needs, and dropping it told the
    QA planner the story had declared nothing at all.
    """
    raw = doc.get("fixtures")
    if not isinstance(raw, list):
        setup = _verification_setup(doc)
        raw = setup.get("fixtures")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, str):
            out.append({"name": "", "provides": "", **lift_fixture(item)})
        elif isinstance(item, dict):
            out.append(
                {"name": str(item.get("name", "")), "provides": str(item.get("provides", ""))}
            )
    return [item for item in out if item["name"] or item["provides"]]


def _plan_context(
    plan: dict[str, Any] | None, spec_dir: str, root: Path, repos: dict[str, dict],
    logger: logging.Logger,
) -> tuple[dict[str, Any], bool]:
    """The plan document and whether it had to be read off disk.

    The producing run passes the checkpointed `PlanResult`; a lane that did not produce it
    — QA on a later run, the fix flow, docs — reads the projection. The second return value
    is "there was nothing to read either", which is what the dispatcher's repo-root fallback
    keys on.
    """
    if plan:
        spec_abs = _spec_dir(spec_dir, root) if spec_dir else None
        return plan_document(plan, repos, spec_abs, root), False
    path = _spec_dir(spec_dir, root) / "plan-context.json" if spec_dir else None
    on_disk = load_json(path, "plan-context.json", logger) if path else {}
    return on_disk, path is None or not path.exists()


def _dispatched_plan_problems(
    doc: dict[str, Any], repos: dict[str, dict], spec_abs: Path
) -> list[str]:
    """Every plan file the dispatcher will hand an implementer, opened to prove it is there.

    The dispatch list is the authority rather than the `services` block, because they are
    not the same set: a service marked `new_service` still gets a layer, and a plan naming
    no service at all still gets the repo-root fallback layer — both of which used to walk
    past this check and reach the implement turn with a plan that did not exist.

    Opened, not `exists()`-ed, because the failure the implementer sees is a read: a
    directory, a broken symlink and a file nobody may read all pass an existence check and
    none of them is a plan.
    """
    problems: list[str] = []
    for entry in build_dispatch_list(doc, repos, fallback=not (doc.get("services") or [])):
        plan_file = entry.get("plan_file") or "plan.md"
        try:
            (spec_abs / plan_file).read_text(encoding="utf-8")
        except OSError as exc:
            problems.append(
                f"{entry['service']}: plan file '{plan_file}' is not readable in the spec "
                f"dir ({exc.strerror or exc})"
            )
    return problems


@blueprint.node
def record_plan(
    logger: logging.Logger,
    plan: dict[str, Any] | None = None,
    spec_dir: str = "",
    repo_dir: str = "",
    workspace_file: str = "",
) -> PlanValidation:
    """Write the plan-context projection, and answer whether the plan is implementable.

    Two jobs, one node, because the second is a check on the first: the document Python
    writes is the document Python then validates, so a plan cannot pass a check run against
    a different copy of itself. The *shape* is no longer checked at all — the turn returns a
    `PlanResult` and a malformed one is a parse retry against the model, not a workflow
    state with a rework lap of its own.

    What is left is semantic, and none of it is knowable from the schema: the declared path
    exists in the resolved workspace, it carries the marker file its type implies, its plan
    file was written to the spec dir, and the build order references services the plan
    actually declares. A failure routes back to the planner with the errors as its brief
    rather than letting an unimplementable plan reach the implementer.

    A plan naming no services is a single-service story and is valid — the dispatcher falls
    back to a repo-root layer.
    """
    if not spec_dir:
        return PlanValidation(status="invalid", errors=["spec_dir argument is empty"])

    root = find_repo_root(repo_dir)
    spec_abs = _spec_dir(spec_dir, root)
    repos = resolve_workspace(workspace_file, repo_dir)
    doc = plan_document(plan or {}, repos, spec_abs, root)

    spec_abs.mkdir(parents=True, exist_ok=True)
    (spec_abs / "plan-context.json").write_text(
        json.dumps(doc, indent=2) + "\n", encoding="utf-8"
    )
    logger.info("wrote plan-context.json projection (%d service(s))", len(doc["services"]))

    services = doc["services"]
    # Every plan file an implementer will be handed, checked here rather than where it is
    # read: this is the deterministic gate the planner loops back to, and a plan file that
    # was never written is exactly what it is for.
    errors: list[str] = _dispatched_plan_problems(doc, repos, spec_abs)
    if not services:
        return PlanValidation(
            status="invalid" if errors else "valid", errors=errors, document=doc
        )

    # The published artifact contract, applied to what we just wrote. It is no longer
    # policing an agent's typing — it is the one check that catches this writer drifting
    # from the schema every *other* reader of the file was built against.
    #
    # `status == "error"` means the contract could not be evaluated at all, which is not
    # the same answer as "no problems" — it is reported rather than swallowed, so a plan
    # never passes on a check that never ran.
    vetted = Ostler(root).artifact_vet("plan-context", spec_dir)
    if vetted.data.get("error"):
        errors.append(f"[ostler] plan-context could not be vetted ({vetted.data['error']}).")
    errors.extend(f"[ostler] {p}" for p in vetted.data.get("problems", []))

    declared = {f"{svc.get('repo', '')}::{svc.get('path', '')}" for svc in services}
    for item in doc["implementation_order"]:
        if item not in declared:
            known = ", ".join(sorted(declared))
            errors.append(
                f"implementation_order names '{item}', which is not a declared service "
                f"(declared: {known})"
            )

    for svc in services:
        repo_name = svc.get("repo", "")
        svc_path = svc.get("path", "")
        label = f"{repo_name}::{svc_path}"

        if repo_name not in repos:
            valid = ", ".join(sorted(repos)) or "<none>"
            errors.append(f"{label}: repo '{repo_name}' not found in workspace (valid: {valid})")
            continue

        repo_info = repos[repo_name]
        if svc.get("new_service"):
            # The directory will be scaffolded during implementation.
            logger.info("%s: new_service=true — skipping path existence check", label)
            continue

        markers = repo_info.get("service_markers", [])
        # Shared with `validate_genesis` — the same assertion genesis must satisfy as a
        # postcondition is the one the planner must satisfy as a precondition.
        problems = service_problems(Path(repo_info["path"]) / svc_path, markers, label)
        if problems:
            errors.extend(problems)
            continue

    return PlanValidation(
        status="invalid" if errors else "valid", errors=errors, document=doc
    )


def _package_label(item: Any) -> str:
    """One shared package as the `repo::path` string the QA prompts render.

    A string arrives from a legacy projection on disk and is passed through; the structured
    form is what a `PlanResult` carries.
    """
    if isinstance(item, dict):
        repo, path = str(item.get("repo", "")), str(item.get("path", ""))
        return f"{repo}::{path}" if repo and path else repo or path
    return str(item)


def read_plan_text(spec_dir: str, plan_file: str, logger: logging.Logger) -> str:
    """The layer's plan as content, inlined into the implement turn rather than read by it.

    The implementer is handed a plan, not a filename: how the planning lane split the work
    across services and what it called each file is planning-side mechanics, and reading
    the file back costs the turn a serial tool call before the first edit.

    It does not degrade. A plan file that is missing here means the step that was supposed
    to write it did not, and the honest answer to that is to stop: the fallback this used
    to take handed the implementer a prompt naming a path it could not read either, and
    what came back was a turn that had invented the work.

    `record_plan` is the gate that catches this before an implementer is paid for it, and
    the dev lane runs it over the whole dispatch list. Reaching the exception below is a
    defect in the lane that got here without one.
    """
    path = Path(spec_dir) / (plan_file or "plan.md")
    logger.debug("inlining the plan at %s", path)
    return path.read_text(encoding="utf-8")


@blueprint.node
def resolve_impl_context(
    logger: logging.Logger,
    spec_dir: str = "",
    target_env: str = "local",
    docs_path: str = "",
    repo_dir: str = "",
    workspace_file: str = "",
    plan: dict[str, Any] | None = None,
) -> ImplContext:
    """Decode the approved plan against the workspace into everything downstream needs.

    `plan` is the producing run's checkpointed `PlanResult`; a lane that did not produce it
    reads the projection off the spec dir instead. Deterministic and side-effect-free, and
    deliberately degrading: nothing on either channel yields empty lists (logged) so the
    implementer falls back to reading the plan text, rather than a hard failure that aborts
    the run.

    Two roots, never conflated. `find_repo_root(repo_dir)` is the *orchestrating* repo, whose
    workspace file names the code repos; `find_docs_root(docs_path, repo_dir)` is the *docs*
    repo, which may be a different directory, may not be a git repo, and may not have an
    `agents.yml`.

    Which coding standards bind is deliberately not decided here. It was, once — service
    `type` matched against skill tags, the winners read off disk and pasted into the
    implement turn — and that selection is language-blind in a way no amount of tag
    curation fixes: one service can mix languages, so the binding standard is a property of
    the file under edit and is chosen at the moment of the edit. The installed skill index
    already does that, adjacent to the work and re-loadable, rather than as a blob at the
    top of a long turn that fades from attention exactly as the edits it was for arrive.
    """
    root = find_repo_root(repo_dir)
    docs_root = find_docs_root(docs_path, repo_dir)

    repos = resolve_workspace(workspace_file, repo_dir)
    plan_ctx, plan_ctx_absent = _plan_context(plan, spec_dir, root, repos, logger)

    services = plan_ctx.get("services") or []

    # Fall back to a single repo-root dispatch whenever the plan names no services —
    # whether plan-context.json is absent OR present in the legacy flat form. Without this
    # a serviceless plan-context yields an empty dispatch list and the per-service loop
    # degenerates to nothing.
    dispatch = [
        DispatchEntry(**entry)
        for entry in build_dispatch_list(
            plan_ctx, repos, fallback=plan_ctx_absent or not services
        )
    ]

    # One QA brief per service that has one: infra and docs layers have nothing to exercise,
    # and `-local` skills are irrelevant when the run targets anything but local.
    qa_run_plan = [
        QaRunEntry(
            service=entry.service,
            label=entry.label,
            qa_mode=entry.qa_mode,
            qa_skill=skills[0] if skills else "",
            qa_skills=skills,
        )
        for entry in dispatch
        if entry.type not in ("terraform", "docs")
        for skills in [
            [s for s in entry.qa_skills if target_env == "local" or not s.endswith("-local")]
        ]
    ]

    affected_repos = get_affected_repos(plan_ctx, repos)
    affected_repo_paths = [repos[name]["path"] for name in affected_repos if name in repos]
    # Every dispatch's cwd is one service repo; the story, spec and plan files always live
    # in the docs root, which is not necessarily one of the plan's affected services and may
    # not even be a workspace folder. Grant it explicitly, or a backend with a per-repo path
    # sandbox can write its own service repo and gets "permission denied" on the story it
    # was told to implement.
    if str(docs_root) not in affected_repo_paths:
        affected_repo_paths = [str(docs_root), *affected_repo_paths]

    # One repository source root per affected surface, so shared implementation changed by
    # a service is not hidden from `ostler qa context`.
    qa_source_roots: list[str] = []
    for entry in dispatch:
        surface = (entry.repo or entry.service).strip()
        source_path = entry.cwd.strip()
        if not surface or not source_path:
            continue
        source_root = f"{surface}={source_path}"
        if source_root not in qa_source_roots:
            qa_source_roots.append(source_root)

    return ImplContext(
        qa_run_plan=qa_run_plan,
        verification_setup=_verification_setup(plan_ctx),
        fixtures=[PlanFixture(**item) for item in _fixtures(plan_ctx)],
        shared_packages=[_package_label(item) for item in plan_ctx.get("shared_packages") or []],
        dispatch_list=dispatch,
        affected_repos=affected_repos,
        affected_repo_paths=affected_repo_paths,
        qa_source_roots=qa_source_roots,
    )


@blueprint.node
def plan_summary(
    logger: logging.Logger,
    spec_dir: str = "",
    repo_dir: str = "",
    workspace_file: str = "",
) -> PlanSummary:
    """The plan's structure, rendered for a turn in a lane that did not plan it.

    The review, QA, fix and docs lanes each ran after — often long after — the run that
    planned the story, so they read the projection. They read it *here*, once, in Python,
    and their prompts are handed the rendering: a prompt that names a file is a prompt that
    has to be right about where the file is, and it is a tool call spent re-deriving what
    the workflow already knows.

    A missing or empty projection renders blank rather than failing. A single-service story
    legitimately declares no services, and no lane's turn is worth failing over the absence
    of a summary of nothing.
    """
    root = find_repo_root(repo_dir)
    repos = resolve_workspace(workspace_file, repo_dir)
    plan_ctx, _ = _plan_context(None, spec_dir, root, repos, logger)

    services = plan_ctx.get("services") or []
    if not services:
        return PlanSummary()

    lines = ["Services this story changes (from the plan):"]
    for svc in services:
        label = f"{svc.get('repo', '')}::{svc.get('path', '')}"
        plan_file = svc.get("plan_file", "") or "plan.md"
        lines.append(f"- {label} (type: {svc.get('type', '')}) — plan: {plan_file}")
    order = plan_ctx.get("implementation_order") or []
    if order:
        lines.append("Build order: " + " → ".join(str(item) for item in order))
    shared = [_package_label(item) for item in plan_ctx.get("shared_packages") or []]
    if shared:
        lines.append("Shared packages: " + ", ".join(shared))
    verification_setup = _verification_setup(plan_ctx)
    if verification_setup:
        lines.append("Verification setup: " + json.dumps(verification_setup))
    # Named on their own line, above the JSON they may also appear inside: these are the
    # only part of the setup a QA plan *calls*, and `qa.fixture()` takes the name exactly.
    # A name a turn had to dig out of a dumped object is a name it can paraphrase.
    fixtures = _fixtures(plan_ctx)
    declared = [item for item in fixtures if item["name"]]
    if declared:
        lines.append(
            "Declared fixtures: "
            + ", ".join(
                f"{item['name']} ({item['provides']})" if item["provides"] else item["name"]
                for item in declared
            )
        )
    # Said apart from the declared names, because the two are acted on differently: a name
    # is called, an arrangement is built. Reported as one list, a QA turn calls the prose,
    # finds no such fixture, and sets about inventing declarations for sentences.
    described = [item["provides"] for item in fixtures if not item["name"]]
    if described:
        lines.append("Arrangements this story described without declaring: " + "; ".join(described))
    return PlanSummary(text="\n".join(lines))


def _branch_repo(repo_path: Path, repo_name: str, branch: str, logger: logging.Logger) -> str:
    """Put one repo on `branch`: `branched`, `already_on_branch` or `skipped`."""
    if not (repo_path / ".git").exists():
        logger.warning("%s: not a git repo, skipping", repo_name)
        return "skipped"
    if current_branch(repo_path) == branch:
        logger.info("%s: already on %s", repo_name, branch)
        return "already_on_branch"
    if local_branch_exists(repo_path, branch):
        checkout(repo_path, branch)
        logger.info("%s: checked out existing %s", repo_name, branch)
    else:
        checkout(repo_path, branch, create=True)
        logger.info("%s: created %s", repo_name, branch)
    return "branched"


@blueprint.node
def branch_code_repos(
    logger: logging.Logger,
    spec_dir: str = "",
    branch: str = "",
    docs_path: str = "",
    repo_dir: str = "",
    workspace_file: str = "",
    plan: dict[str, Any] | None = None,
) -> BranchOutcome:
    """Put every code repo the plan names onto the story branch.

    Runs after planning, when the affected-repo list is authoritative — the docs repo was
    branched much earlier, when it was the only thing the run knew about. Idempotent: a repo
    already on the branch is left alone, and one that is not a git repo is skipped rather
    than failing the run.
    """
    docs_root = find_docs_root(docs_path, repo_dir)
    repos = resolve_workspace(workspace_file, repo_dir)
    plan_ctx, _ = _plan_context(plan, spec_dir, docs_root, repos, logger)

    if not branch:
        if (docs_root / ".git").exists():
            branch = current_branch(docs_root)
        else:
            branch = "main"
            logger.warning(
                "docs root %s is not a git repo and no branch given — defaulting to 'main'",
                docs_root,
            )

    branched: list[str] = []
    already: list[str] = []
    for repo_name in get_affected_repos(plan_ctx, repos):
        repo_path = Path(repos[repo_name]["path"])
        if repo_path == docs_root:
            continue  # the docs repo is already on the right branch
        result = _branch_repo(repo_path, repo_name, branch, logger)
        if result == "branched":
            branched.append(repo_name)
        elif result == "already_on_branch":
            already.append(repo_name)

    return BranchOutcome(branched=branched, already_on_branch=already)


@blueprint.node
def select_next_layer(
    logger: logging.Logger,
    spec_dir: str = "",
    index: int = -1,
    repo_dir: str = "",
    workspace_file: str = "",
    plan: dict[str, Any] | None = None,
) -> LayerPick:
    """The next service to implement, or "the dispatch list is exhausted".

    `index` is the position of the last completed layer, `-1` before the first.

    **An empty `services` means different things on the two channels, and both are meant.**
    A planning turn that named none is a single-service story — there was nothing to
    enumerate — so the value channel dispatches the one repo-root layer, which is the same
    fallback `resolve_impl_context` applies to it. A projection *on disk* naming none is a
    plan that deliberately dispatches nothing, which is how a documents-only fix reaches its
    check turn without an implement turn in front of it.

    The nonconforming-schema halt this node used to carry is gone with the shape it guarded
    against. Python writes the projection now, so "the planner emitted a document with no
    `services` key" is not a state a run can be in.
    """
    root = find_repo_root(repo_dir)
    repos = resolve_workspace(workspace_file, repo_dir)
    plan_ctx, plan_ctx_absent = _plan_context(plan, spec_dir, root, repos, logger)
    planned_none = plan is not None and not (plan.get("services") or [])
    dispatch = build_dispatch_list(plan_ctx, repos, fallback=plan_ctx_absent or planned_none)

    total = len(dispatch)
    nxt = index + 1
    if nxt < total:
        return LayerPick(
            has_layer=True,
            index=nxt,
            layer=DispatchEntry(**dispatch[nxt]),
            dispatch_count=total,
        )
    return LayerPick(index=index, dispatch_count=total)


def _services_config(repo_dir: str = "") -> dict[str, dict]:
    """The orchestrating repo's `services:` block — what each service type declares.

    ```yaml
    services:
      <type-or-service>: {test: "…", lint: "…", smoke: "…", codegen: "…"}
    ```

    The repo owns this. Which command exercises a service, and whether a missing test is a
    defect, is a property of the service and not of the workflow — a workflow that guessed
    `make test` would be right in this repo and wrong in the next one, which is the same
    class of assumption invariant 1 forbids in the prompts.
    """
    cfg_path = find_repo_root(repo_dir) / "agents.yml"
    if not cfg_path.exists():
        return {}
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    block = cfg.get("services") or (cfg.get("workflow") or {}).get("services") or {}
    if not isinstance(block, dict):
        return {}
    return {str(k): v for k, v in block.items() if isinstance(v, dict)}


def service_keys(service: str = "", service_type: str = "") -> list[str]:
    """The `services:` keys this layer answers to, narrowest first.

    The dispatch identifies a layer as `<repo>::<path>`, which is unambiguous and which
    nobody writes in `agents.yml`: a repo names its services the way its own directories
    do — `api`, `web`, `worker`. So the id is decomposed, and the directory it points at
    (and that directory's own name, for a nested `services/api`) are keys in their own
    right, before the type is tried at all.
    """
    path = service.partition("::")[2]
    keys: list[str] = []
    for key in (service, path, Path(path).name if path else "", service_type):
        candidate = key.strip().strip("/")
        if candidate and candidate not in keys:
            keys.append(candidate)
    return keys


def service_declaration(
    service: str = "", service_type: str = "", repo_dir: str = ""
) -> dict:
    """One service's declared block, looked up by service name and then by type.

    Name first: a monorepo with two services of the same type may run different commands
    in each, and the narrower key is the one that can say so.
    """
    block = _services_config(repo_dir)
    for key in service_keys(service, service_type):
        entry = block.get(key)
        if isinstance(entry, dict):
            return entry
    return {}


def service_dir(cwd: str | Path, service: str = "") -> Path:
    """Where one service's declared commands run: its own directory, not its repo's.

    The dispatch hands every state the *repo* checkout as `cwd`, and for an agent turn
    that is right — a story spans the repo, and the implementer has to be able to see all
    of it. A gate declared under `services.<name>` is the narrower thing. `api`'s
    `go test ./...` is written the way `api/Makefile` writes it, and from the repo root it
    does not fail the story, it fails to run at all: "directory prefix . does not contain
    main module". The repair turn is then handed an error about the harness and asked to
    fix the code, which is how a green story reached the operator gate thirteen turns in.

    The service id carries the directory (`<repo>::api`), so this is derivable rather than
    guessed, and it agrees with `workspace.service_roots` by construction — that is where
    the plan's `path` came from. A repo that is one service (`<repo>::`, `<repo>::.`) and
    a path that is not there resolve back to `cwd` unchanged.
    """
    root = Path(cwd).expanduser()
    path = service.partition("::")[2].strip().strip("/")
    if not path or path == ".":
        return root
    candidate = root / path
    return candidate if candidate.is_dir() else root


def _lint_override(service: str, cwd: Path, repo_dir: str = "") -> str:
    """The legacy `lint:` map — an explicit lint command keyed by service or directory.

    Predates `services:` and is still honoured, below it: a repo that wrote this map is
    already running the gate it names, and moving the key would turn its gate off.
    """
    if not service:
        return ""
    cfg_path = find_repo_root(repo_dir) / "agents.yml"
    if not cfg_path.exists():
        return ""
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return ""
    lint_map = cfg.get("lint") or (cfg.get("workflow") or {}).get("lint") or {}
    if not isinstance(lint_map, dict):
        return ""
    return str(lint_map.get(service) or lint_map.get(cwd.name) or "").strip()


def _has_make_target(cwd: Path, target: str) -> bool:
    """Whether this service's Makefile defines `target`."""
    if not (cwd / "Makefile").exists() and not (cwd / "makefile").exists():
        return False
    try:
        probe = subprocess.run(
            ["make", "-n", target], cwd=cwd, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


def gate_command(
    gate: str, service: str, service_type: str, cwd: Path, repo_dir: str = ""
) -> str:
    """The command this service declares for one gate, or `""` when it declares none.

    Resolution, most specific first: the `services:` block, then the legacy `lint:` map,
    then the convention `make <gate>` when the service's Makefile actually defines that
    target. A service that answers none of the three has not adopted the gate, and an
    unadopted gate is skipped rather than guessed at — a guessed command that fails is
    indistinguishable, to every state downstream, from a real regression.
    """
    declared = service_declaration(service, service_type, repo_dir).get(gate)
    if isinstance(declared, str) and declared.strip():
        return declared.strip()
    if gate == "lint":
        legacy = _lint_override(service, cwd, repo_dir)
        if legacy:
            return legacy
    if _has_make_target(cwd, gate):
        return f"make {gate}"
    return ""


@blueprint.node
def declared_gates(
    logger: logging.Logger,
    cwd: str = "",
    service: str = "",
    service_type: str = "",
    repo_dir: str = "",
) -> GateList:
    """Which gates will run after the turn about to be taken — for the turn to be told.

    The prose this replaces told every implementer to run the tests and the linter and
    called it MANDATORY, in a repo that may have neither. What a turn actually needs to
    know is what the machine will check afterwards, and that is one line of fact: either
    the commands, or an honest "nothing declared" — which is the same information the
    prose was pretending to give, minus the pretence.
    """
    if not cwd or not Path(cwd).expanduser().is_dir():
        return GateList()
    where = service_dir(cwd, service)
    commands = {
        gate: gate_command(gate, service, service_type, where, repo_dir)
        for gate in GATE_ORDER
    }
    declared = {gate: cmd for gate, cmd in commands.items() if cmd}
    if not declared:
        logger.info("%s declares no gate command — nothing will be run after the turn", service)
        return GateList(text="(nothing declared)")
    # Where, when it is not the checkout the turn is sitting in. A turn told
    # `test: go test ./...` and nothing else will run it from the repo root, watch it fail
    # for a reason that has nothing to do with its code, and start repairing the code.
    root = Path(cwd).expanduser()
    at = "" if where == root else f" (run in `{where.relative_to(root)}/`)"
    return GateList(
        gates=list(declared),
        commands=list(declared.values()),
        text=", ".join(f"{gate}: `{cmd}`" for gate, cmd in declared.items()) + at,
    )


@blueprint.node
def declared_markers(
    logger: logging.Logger, repo_dir: str = "", workspace_file: str = ""
) -> GateList:
    """The marker files each repo says identify a service directory — for the planner.

    The planner has to answer "which directories are services here", and what it used to be
    handed was a list of four: a Go module file, a `package.json`, a `pubspec.yaml`, a
    Pulumi or Terraform entry point. A repo whose services are marked any other way had to
    argue with that list, and a repo with only one of those layers was told about three that
    do not exist — both of which the repo can simply say (invariant 1), and one of which it
    already does, in `workspace.service_markers`.

    Rendered as one line per repo, or an empty `text` when nothing is declared, which the
    prompt reads as "go and look at `agents.yml` yourself" rather than as a list of nothing.
    """
    repos = resolve_workspace(workspace_file, repo_dir)
    lines = [
        f"- **{name}** (`{info.get('path', '')}`): "
        + ", ".join(f"`{marker}`" for marker in markers)
        for name, info in sorted(repos.items())
        if (markers := info.get("service_markers") or [])
    ]
    if not lines:
        logger.info("no repo in this workspace declares service_markers")
        return GateList()
    return GateList(text="\n".join(lines))


@blueprint.node
def run_gate(
    logger: logging.Logger,
    cwd: str = "",
    service: str = "",
    gate: str = "lint",
    service_type: str = "",
    repo_dir: str = "",
) -> GateOutcome:
    """Run one of a service's declared gate commands and report whether it passed.

    The deterministic half of every gate the dev lane runs: the command is the repo's, the
    verdict is Python's, and the output is what the repair turn is handed. `skipped` is the
    opt-out — a service adopts a gate by declaring it, and one that has not is never
    falsely failed.
    """
    if not cwd:
        logger.info("no cwd given — skipping the %s gate", gate)
        return GateOutcome(gate=gate, status="skipped", reason="no cwd given")

    if not Path(cwd).expanduser().is_dir():
        logger.warning("cwd does not exist: %s", cwd)
        return GateOutcome(gate=gate, status="skipped", reason=f"cwd does not exist: {cwd}")

    where = service_dir(cwd, service)
    command = gate_command(gate, service, service_type, where, repo_dir)
    if not command:
        logger.info("%s declares no %s command in %s — skipping", service, gate, where)
        return GateOutcome(
            gate=gate,
            status="skipped",
            reason=f"no {gate} command declared for {service or where.name}",
        )

    try:
        result = subprocess.run(
            command,
            cwd=where,
            shell=True,
            capture_output=True,
            text=True,
            timeout=GATE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.warning("%s command '%s' timed out after %ss", gate, command, GATE_TIMEOUT)
        return GateOutcome(
            gate=gate,
            status="dirty",
            command=command,
            output=f"{gate} timed out after {GATE_TIMEOUT}s",
            reason="timeout",
        )
    except OSError as exc:
        logger.warning("%s command '%s' could not be launched: %s", gate, command, exc)
        return GateOutcome(
            gate=gate,
            status="skipped",
            command=command,
            output=str(exc),
            reason=f"{gate} command could not be launched",
        )

    if result.returncode == 0:
        logger.info("%s clean for %s", gate, where)
        return GateOutcome(
            gate=gate, status="clean", command=command, reason=f"{gate} passed"
        )

    output = (result.stdout + result.stderr).strip()
    if len(output) > MAX_GATE_OUTPUT:
        output = "…(truncated)…\n" + output[-MAX_GATE_OUTPUT:]
    logger.warning("%s dirty for %s (exit %s)", gate, where, result.returncode)
    return GateOutcome(
        gate=gate,
        status="dirty",
        command=command,
        output=output,
        reason=f"{gate} exited {result.returncode}",
    )


@blueprint.node
def check_story_status(
    logger: logging.Logger,
    docs_path: str = "",
    slug: str = "",
    epic: str = "",
    story_path: str = "",
    repo_dir: str = "",
) -> StoryStatusCheck:
    """Whether the turn just taken stamped the story finished. A shape gate, like the rest.

    The Status line is parsed, not read — story selection is what parses it — so the rule
    that only a QA-verified run may write a done status is a machine-checkable claim and is
    checked here rather than argued for in the prompt. The value comes back through the same
    reader the stamp writes with (`story_status.current`), so a status hidden in prose is not
    one and a frontmatter status is.

    A violation is `dirty` and routes exactly as a red lint gate does: another repair lap
    while the budget holds, then the operator. Nothing here rewrites the line — the turn that
    wrote it is the turn that has to unwrite it, and a gate that silently repaired its own
    subject would leave the next turn believing the rule does not bind.
    """
    root = find_docs_root(docs_path, repo_dir)
    written = story_status.current(root, slug, epic=epic, story_path=story_path).strip()
    if not is_done(written):
        return StoryStatusCheck(status="clean", written=written)
    logger.warning(
        "the story's Status reads %r, which marks it finished, before QA has run", written
    )
    return StoryStatusCheck(status="dirty", written=written)


@blueprint.node
def changed_files(logger: logging.Logger, cwd: str = "", story_slug: str = "") -> ChangedFiles:
    """Which files this story has already written in one service checkout.

    The re-seed for a recycled conversation — see `ChangedFiles`. Three halves, really, and
    each is found differently: what is *modified* in the tree is a plain diff, what is
    *new* in the tree is untracked and so is in no diff at all, and what has been committed
    is found by the `Story:` trailer every prompt in this lane is required to write. The
    trailer rather than a branch comparison because the base branch is not something this
    node is given, and a story branch carrying two stories would otherwise report the first
    one's files as this one's.

    The untracked half is not a nicety. Nothing in this lane commits before the gates run,
    and a new file — which is what a new test *is* — appears in `git diff HEAD` never. A
    recycled conversation re-seeded without it is told the test it just wrote does not
    exist. `--exclude-standard` keeps build output and other ignored noise out.

    Degrades to empty on anything unexpected. It is a courtesy to the next turn, which reads
    the code itself when told nothing; a service that is not a git checkout must not fail the
    lane over it.
    """
    if not cwd or not Path(cwd).expanduser().is_dir():
        return ChangedFiles()
    commands = [["diff", "--name-only", "HEAD"], ["ls-files", "--others", "--exclude-standard"]]
    if story_slug:
        commands.append(
            ["log", "--name-only", "--pretty=format:", f"--grep=Story: {story_slug}"]
        )
    found: list[str] = []
    for args in commands:
        try:
            done = subprocess.run(
                ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.info("could not list changed files in %s: %s", cwd, exc)
            break
        if done.returncode == 0:
            found += [line.strip() for line in done.stdout.splitlines() if line.strip()]
    return ChangedFiles(paths=sorted(set(found)))


@blueprint.node
def read_operator_context(logger: logging.Logger, story_path: str = "") -> OperatorAnswer:
    """Take the operator's answer off `<story-folder>/context.md` and consume it.

    The half of `await_operator.py`'s state machine a node still has to do. `STATUS:
    ANSWERED` is flipped to `CONSUMED` so a later re-block re-arms with follow-up questions
    instead of looping forever on the same stale answer — the one piece of that script that
    was never about waiting.

    It is reached only from a state that has already established the block is resolved: the
    resolver said `answered`, or the driver's `Await` returned because the file was touched.
    So a file that carries no `STATUS:` line at all still counts as answered — that is the
    hand-written answer an operator leaves without touching the marker, which the script's
    "no recognizable STATUS line" arm re-armed and waited on only because it could not tell
    a fresh block from a resolved one. Here the caller already knows.
    """
    ctx = paths.story_context_path(story_path)
    if not ctx.exists():
        logger.warning("no operator context at %s — treating the block as unanswered", ctx)
        return OperatorAnswer()

    content = ctx.read_text(encoding="utf-8")
    if gates.status_of(content) == ANSWERED:
        ctx.write_text(gates.set_status(content, CONSUMED), encoding="utf-8")
        logger.info("consumed the operator's answer in %s", ctx)

    # Only `epic` is honoured; anything else, blank included, reworks just this story.
    scope = "epic" if gates.scope_of(content) == "epic" else "story"
    return OperatorAnswer(answered=True, scope=scope, content=content)


__all__ = [
    "branch_code_repos",
    "changed_files",
    "check_story_status",
    "declared_gates",
    "declared_markers",
    "gate_command",
    "plan_document",
    "plan_summary",
    "read_operator_context",
    "read_plan_text",
    "record_plan",
    "resolve_impl_context",
    "run_gate",
    "select_next_layer",
    "service_declaration",
]
