"""The dev flow's deterministic work: validate, dispatch, branch, iterate, lint.

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
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.kit import find_docs_root, find_repo_root, load_json
from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared.contract import service_problems
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.dev import (
    BranchOutcome,
    DispatchEntry,
    ImplContext,
    LayerPick,
    LintOutcome,
    OperatorAnswer,
    PlanValidation,
    QaRunEntry,
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

#: Where the orchestrating repo keeps the logical-name → instruction-path manifest.
MANIFEST_REL = ".agents/agents-context.json"

#: Cap on the lint output threaded into the fix agent's context. The tail carries the
#: findings; the head is usually the command echo.
MAX_LINT_OUTPUT = 4000

#: Seconds a service's lint command gets before it is called dirty.
LINT_TIMEOUT = 300

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


@blueprint.node
def validate_plan_context(
    logger: logging.Logger, spec_dir: str = "", repo_dir: str = "", workspace_file: str = ""
) -> PlanValidation:
    """Do the planner's declared service paths point at real services?

    Three checks per service: the path exists in the resolved workspace, it carries the
    marker file its type implies, and its plan file was written to the spec dir. A failure
    routes back to the planner with the errors as its brief rather than letting an
    unimplementable plan reach the implementer.

    A *missing* plan-context.json is a single-service story and is valid. One that **exists
    and declares no services** is a planner schema error, not a single-service story, and is
    rejected with the schema spelled out: waving it through used to skip the whole implement
    stage and send an unimplemented story into review and QA.
    """
    if not spec_dir:
        return PlanValidation(status="invalid", errors=["spec_dir argument is empty"])

    root = find_repo_root(repo_dir)
    spec_abs = _spec_dir(spec_dir, root)

    plan_ctx = load_json(spec_abs / "plan-context.json", "plan-context.json", logger)
    if not plan_ctx:
        return PlanValidation(status="valid")

    services = plan_ctx.get("services")
    if not services:
        return PlanValidation(
            status="invalid",
            errors=[
                "plan-context.json exists but has no 'services' array "
                f"(found keys: {sorted(plan_ctx.keys())}). Rewrite plan-context.json "
                "so it declares every layer to implement as "
                '{"services": [{"repo": "<workspace repo name>", "path": "<service dir, '
                'e.g. api or web>", "type": "<go|react-router|...>", "plan_file": "<plan '
                'file in the spec dir>", "skills": [...]}], '
                '"implementation_order": ["<repo>::<path>", ...]} — '
                "keys like 'touched_layers' are not read by the implementation dispatcher.",
            ],
        )

    repos = resolve_workspace(workspace_file, repo_dir)
    errors: list[str] = []

    # Producer-contract pre-check: `ostler artifact vet plan-context` applies the structural
    # contract (services shape, plan_file existence, order refs) the planner was told to
    # self-check against; workspace-specific repo resolution stays below, because ostler has
    # no workspace context.
    #
    # `status == "error"` means the contract could not be evaluated at all, which is not
    # the same answer as "no problems" — it is reported rather than swallowed, so a plan
    # never passes on a check that never ran.
    vetted = Ostler(root).artifact_vet("plan-context", spec_dir)
    if vetted.data.get("error"):
        errors.append(f"[ostler] plan-context could not be vetted ({vetted.data['error']}).")
    errors.extend(f"[ostler] {p}" for p in vetted.data.get("problems", []))

    # Case-insensitive lookup of the real workspace keys. The planner tends to emit the
    # human-facing project name ("Acme") while the workspace key is the folder name
    # ("acme"); resolve that here rather than routing a symptom-only error back to the
    # model, which re-authors the same casing from the title-cased branding in its prompt.
    # Repair, don't just reject.
    canon_by_lower = {name.lower(): name for name in repos}
    rewrites: dict[str, str] = {}

    def canonicalize(repo_name: str) -> str:
        if repo_name in repos:
            return repo_name
        canon = canon_by_lower.get(repo_name.lower())
        if canon is not None and canon != repo_name:
            rewrites[repo_name] = canon
        return canon if canon is not None else repo_name

    for svc in services:
        repo_name = canonicalize(svc.get("repo", ""))
        svc["repo"] = repo_name  # normalized in place; persisted below if anything changed
        svc_path = svc.get("path", "")
        svc_type = svc.get("type", "")
        plan_file = svc.get("plan_file", "")
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

        markers = ["main.tf"] if svc_type == "terraform" else repo_info.get("service_markers", [])
        # Shared with `validate_genesis` — the same assertion genesis must satisfy as a
        # postcondition is the one the planner must satisfy as a precondition.
        problems = service_problems(Path(repo_info["path"]) / svc_path, markers, label)
        if problems:
            errors.extend(problems)
            continue

        if plan_file and not (spec_abs / plan_file).exists():
            errors.append(f"{label}: plan file '{plan_file}' not found in spec dir")

    # Persist any case normalization so downstream consumers and any re-validation see the
    # canonical key. `services[].repo` was rewritten above; the `repo::path` prefixes in
    # `implementation_order` have to be fixed too.
    if rewrites:
        order = plan_ctx.get("implementation_order")
        if isinstance(order, list):
            plan_ctx["implementation_order"] = [
                _rewrite_order_entry(entry, rewrites) for entry in order
            ]
        (spec_abs / "plan-context.json").write_text(
            json.dumps(plan_ctx, indent=2) + "\n", encoding="utf-8"
        )
        for emitted, canon in sorted(rewrites.items()):
            logger.info("normalized repo '%s' -> '%s' in plan-context.json", emitted, canon)

    return PlanValidation(status="invalid" if errors else "valid", errors=errors)


def _rewrite_order_entry(entry: Any, rewrites: dict[str, str]) -> Any:
    """One `implementation_order` entry with its repo prefix canonicalized."""
    if not isinstance(entry, str) or "::" not in entry:
        return entry
    repo_name, rest = entry.split("::", 1)
    return f"{rewrites.get(repo_name, repo_name)}::{rest}"


@blueprint.node
def resolve_impl_context(
    logger: logging.Logger,
    spec_dir: str = "",
    target_env: str = "local",
    docs_path: str = "",
    repo_dir: str = "",
    workspace_file: str = "",
) -> ImplContext:
    """Decode the approved plan against the workspace into everything downstream needs.

    Deterministic and side-effect-free, and deliberately degrading: a missing or garbled
    plan-context yields empty lists (logged) so the implementer falls back to reading the
    plan text, rather than a hard failure that aborts the run.

    Two roots, never conflated. `find_repo_root(repo_dir)` is the *orchestrating* repo, where
    the context manifest and the instruction library live; `find_docs_root(docs_path, repo_dir)`
    is the
    *docs* repo, which may be a different directory, may not be a git repo, and may not have
    an `agents.yml`.
    """
    root = find_repo_root(repo_dir)
    docs_root = find_docs_root(docs_path, repo_dir)

    plan_ctx_path = _spec_dir(spec_dir, root) / "plan-context.json" if spec_dir else None
    plan_ctx = load_json(plan_ctx_path, "plan-context.json", logger) if plan_ctx_path else {}
    plan_ctx_absent = plan_ctx_path is None or not plan_ctx_path.exists()

    manifest = load_json(root / MANIFEST_REL, "context manifest", logger)
    instructions: dict[str, str] = manifest.get("instructions") or {}
    services = plan_ctx.get("services") or []

    repos = resolve_workspace(workspace_file, repo_dir)

    # Instruction paths from every service's skills, deduplicated in order.
    impl_instruction_paths: list[str] = []
    for svc in services:
        for skill_name in svc.get("skills") or []:
            path = instructions.get(str(skill_name).replace(".", "-"))
            if not path:
                logger.warning("skill '%s' not in repo manifest — skipping", skill_name)
                continue
            if path not in impl_instruction_paths:
                impl_instruction_paths.append(path)

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
        impl_instruction_paths=impl_instruction_paths,
        qa_run_plan=qa_run_plan,
        qa_stack=plan_ctx.get("qa_stack") or {},
        shared_packages=[str(item) for item in plan_ctx.get("shared_packages") or []],
        dispatch_list=dispatch,
        affected_repos=affected_repos,
        affected_repo_paths=affected_repo_paths,
        qa_source_roots=qa_source_roots,
    )


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
) -> BranchOutcome:
    """Put every code repo the plan names onto the story branch.

    Runs after planning, when plan-context.json exists and the affected-repo list is
    authoritative — the docs repo was branched much earlier, when it was the only thing the
    run knew about. Idempotent: a repo already on the branch is left alone, and one that is
    not a git repo is skipped rather than failing the run.
    """
    docs_root = find_docs_root(docs_path, repo_dir)
    plan_ctx = (
        load_json(_spec_dir(spec_dir, docs_root) / "plan-context.json", "plan-context.json", logger)
        if spec_dir
        else {}
    )

    if not branch:
        if (docs_root / ".git").exists():
            branch = current_branch(docs_root)
        else:
            branch = "main"
            logger.warning(
                "docs root %s is not a git repo and no branch given — defaulting to 'main'",
                docs_root,
            )

    repos = resolve_workspace(workspace_file, repo_dir)
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
) -> LayerPick:
    """The next service to implement, or "the dispatch list is exhausted".

    `index` is the position of the last completed layer, `-1` before the first.

    A plan-context that **exists, has no `services` key at all, and yields no dispatch
    records** means the planner wrote a nonconforming schema. `validate_plan_context` rejects
    that shape and routes it back, so reaching this point means the gate was bypassed or
    regressed — and guessing a fallback repo, silently dispatching the wrong layer or
    skipping implementation entirely, is worse than halting. An explicit `"services": []` is
    a legitimate already-exhausted plan (a story touching no code repos) and is not an error.
    """
    root = find_repo_root(repo_dir)
    plan_ctx_path = _spec_dir(spec_dir, root) / "plan-context.json" if spec_dir else None
    plan_ctx = load_json(plan_ctx_path, "plan-context.json", logger) if plan_ctx_path else {}
    plan_ctx_absent = plan_ctx_path is None or not plan_ctx_path.exists()

    repos = resolve_workspace(workspace_file, repo_dir)
    dispatch = build_dispatch_list(plan_ctx, repos, fallback=plan_ctx_absent)

    if not dispatch and plan_ctx and not plan_ctx_absent and "services" not in plan_ctx:
        raise WorkflowFailed(
            f"plan-context.json at {plan_ctx_path} has no usable 'services' entries "
            f"(keys: {sorted(plan_ctx.keys())}). This should have been rejected by the "
            "plan-context validation gate and sent back to the planner; refusing to guess "
            "a dispatch. Fix plan-context.json's schema and resume."
        )

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


def _lint_override(service: str, cwd: Path, repo_dir: str = "") -> str:
    """An explicit lint command for this service from the orchestrating repo's agents.yml.

    Looked up under `lint:` or `workflow.lint:` as a `{service-or-dir: command}` map, by
    service name first and then by the cwd's basename.
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


def _has_make_lint(cwd: Path) -> bool:
    """Whether this service's Makefile defines a `lint` target."""
    if not (cwd / "Makefile").exists() and not (cwd / "makefile").exists():
        return False
    try:
        probe = subprocess.run(
            ["make", "-n", "lint"], cwd=cwd, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


@blueprint.node
def run_lint(
    logger: logging.Logger, cwd: str = "", service: str = "", repo_dir: str = ""
) -> LintOutcome:
    """Run one service's lint command and report whether it is clean.

    The deterministic half of the lint gate; the implement agent's own `make lint`
    done-criterion is the other. Command resolution is convention-plus-override: an explicit
    `agents.yml` entry wins, otherwise `make lint` when the service's Makefile defines that
    target, otherwise there is nothing to run and the service is `skipped`. That is what
    makes the gate opt-in — a service adopts it by adding a target or an entry, and one with
    neither is never falsely failed.
    """
    if not cwd:
        logger.info("no cwd given — skipping lint")
        return LintOutcome(status="skipped", reason="no cwd given")

    service_dir = Path(cwd).expanduser()
    if not service_dir.is_dir():
        logger.warning("cwd does not exist: %s", service_dir)
        return LintOutcome(status="skipped", reason=f"cwd does not exist: {service_dir}")

    command = _lint_override(service, service_dir, repo_dir)
    if not command:
        if not _has_make_lint(service_dir):
            logger.info("no lint override and no `make lint` target in %s — skipping", service_dir)
            return LintOutcome(
                status="skipped",
                reason=f"no lint override and no `make lint` target in {service_dir}",
            )
        command = "make lint"

    try:
        result = subprocess.run(
            command,
            cwd=service_dir,
            shell=True,
            capture_output=True,
            text=True,
            timeout=LINT_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.warning("lint command '%s' timed out after %ss", command, LINT_TIMEOUT)
        return LintOutcome(
            status="dirty",
            command=command,
            output=f"lint timed out after {LINT_TIMEOUT}s",
            reason="timeout",
        )
    except OSError as exc:
        logger.warning("lint command '%s' could not be launched: %s", command, exc)
        return LintOutcome(
            status="skipped",
            command=command,
            output=str(exc),
            reason="lint command could not be launched",
        )

    if result.returncode == 0:
        logger.info("lint clean for %s", service_dir)
        return LintOutcome(status="clean", command=command, reason="lint passed")

    output = (result.stdout + result.stderr).strip()
    if len(output) > MAX_LINT_OUTPUT:
        output = "…(truncated)…\n" + output[-MAX_LINT_OUTPUT:]
    logger.warning("lint dirty for %s (exit %s)", service_dir, result.returncode)
    return LintOutcome(
        status="dirty",
        command=command,
        output=output,
        reason=f"lint exited {result.returncode}",
    )


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
    "read_operator_context",
    "resolve_impl_context",
    "run_lint",
    "select_next_layer",
    "validate_plan_context",
]
