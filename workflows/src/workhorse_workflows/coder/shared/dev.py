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
    PlanSummary,
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


def plan_document(plan: dict[str, Any], repos: dict[str, dict]) -> dict[str, Any]:
    """The plan-context mapping, built from a `PlanResult` and the resolved workspace.

    One function, because there are two consumers of the same derivation: the projection
    written to disk and the dispatch decoded in memory. They cannot be allowed to disagree
    — the whole point of Python owning the document is that there is one of it.

    Repo names are canonicalized case-insensitively against the workspace keys. The planner
    tends to emit the human-facing project name ("Acme") while the key is the folder name
    ("acme"), and repairing that is strictly better than routing a symptom-only error back
    to a model that re-authors the same casing from the title-cased branding in its prompt.
    """
    canon_by_lower = {name.lower(): name for name in repos}

    def canon(repo_name: str) -> str:
        return repo_name if repo_name in repos else canon_by_lower.get(repo_name.lower(), repo_name)

    def entry(svc: Any) -> dict[str, Any]:
        svc = dict(svc or {})
        svc["repo"] = canon(str(svc.get("repo", "")))
        return svc

    services = [entry(svc) for svc in plan.get("services") or []]
    order = [
        f"{canon(str(item).split('::', 1)[0])}::{str(item).split('::', 1)[1]}"
        if "::" in str(item)
        else str(item)
        for item in plan.get("implementation_order") or []
    ]
    instructions: list[str] = []
    for svc in services:
        for skill in svc.get("skills") or []:
            if str(skill) not in instructions:
                instructions.append(str(skill))
    return {
        "services": services,
        "implementation_order": order,
        "shared_packages": [entry(pkg) for pkg in plan.get("shared_packages") or []],
        # Derived, never asked for: it was always the union of the services' skills, and a
        # hand-written union is a hand-written way to disagree with itself.
        "required_instructions": instructions,
        "qa_stack": plan.get("qa_stack") or {},
    }


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
        return plan_document(plan, repos), False
    path = _spec_dir(spec_dir, root) / "plan-context.json" if spec_dir else None
    on_disk = load_json(path, "plan-context.json", logger) if path else {}
    return on_disk, path is None or not path.exists()


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
    doc = plan_document(plan or {}, repos)

    spec_abs.mkdir(parents=True, exist_ok=True)
    (spec_abs / "plan-context.json").write_text(
        json.dumps(doc, indent=2) + "\n", encoding="utf-8"
    )
    logger.info("wrote plan-context.json projection (%d service(s))", len(doc["services"]))

    services = doc["services"]
    if not services:
        return PlanValidation(status="valid", document=doc)

    errors: list[str] = []

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

    Two roots, never conflated. `find_repo_root(repo_dir)` is the *orchestrating* repo, where
    the context manifest and the instruction library live; `find_docs_root(docs_path, repo_dir)`
    is the
    *docs* repo, which may be a different directory, may not be a git repo, and may not have
    an `agents.yml`.
    """
    root = find_repo_root(repo_dir)
    docs_root = find_docs_root(docs_path, repo_dir)

    repos = resolve_workspace(workspace_file, repo_dir)
    plan_ctx, plan_ctx_absent = _plan_context(plan, spec_dir, root, repos, logger)

    manifest = load_json(root / MANIFEST_REL, "context manifest", logger)
    instructions: dict[str, str] = manifest.get("instructions") or {}
    services = plan_ctx.get("services") or []

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
        skills = ", ".join(str(s) for s in svc.get("skills") or []) or "none"
        plan_file = svc.get("plan_file", "") or "plan.md"
        lines.append(f"- {label} (type: {svc.get('type', '')}) — skills: {skills} — plan: {plan_file}")
    order = plan_ctx.get("implementation_order") or []
    if order:
        lines.append("Build order: " + " → ".join(str(item) for item in order))
    shared = [_package_label(item) for item in plan_ctx.get("shared_packages") or []]
    if shared:
        lines.append("Shared packages: " + ", ".join(shared))
    qa_stack = plan_ctx.get("qa_stack") or {}
    if qa_stack:
        lines.append("Verification setup: " + json.dumps(qa_stack))
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
      <type-or-service>: {test: "…", lint: "…", smoke: "…", codegen: "…", tdd: required}
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
    service_dir = Path(cwd).expanduser() if cwd else None
    if service_dir is None or not service_dir.is_dir():
        return GateList()
    commands = {
        gate: gate_command(gate, service, service_type, service_dir, repo_dir)
        for gate in GATE_ORDER
    }
    tdd = tdd_mode(service, service_type, repo_dir)
    declared = {gate: cmd for gate, cmd in commands.items() if cmd}
    if not declared:
        logger.info("%s declares no gate command — nothing will be run after the turn", service)
        return GateList(text="(nothing declared)", tdd=tdd)
    return GateList(
        gates=list(declared),
        commands=list(declared.values()),
        text=", ".join(f"{gate}: `{cmd}`" for gate, cmd in declared.items()),
        tdd=tdd,
    )


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

    service_dir = Path(cwd).expanduser()
    if not service_dir.is_dir():
        logger.warning("cwd does not exist: %s", service_dir)
        return GateOutcome(
            gate=gate, status="skipped", reason=f"cwd does not exist: {service_dir}"
        )

    command = gate_command(gate, service, service_type, service_dir, repo_dir)
    if not command:
        logger.info("%s declares no %s command in %s — skipping", service, gate, service_dir)
        return GateOutcome(
            gate=gate,
            status="skipped",
            reason=f"no {gate} command declared for {service or service_dir.name}",
        )

    try:
        result = subprocess.run(
            command,
            cwd=service_dir,
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
        logger.info("%s clean for %s", gate, service_dir)
        return GateOutcome(
            gate=gate, status="clean", command=command, reason=f"{gate} passed"
        )

    output = (result.stdout + result.stderr).strip()
    if len(output) > MAX_GATE_OUTPUT:
        output = "…(truncated)…\n" + output[-MAX_GATE_OUTPUT:]
    logger.warning("%s dirty for %s (exit %s)", gate, service_dir, result.returncode)
    return GateOutcome(
        gate=gate,
        status="dirty",
        command=command,
        output=output,
        reason=f"{gate} exited {result.returncode}",
    )


def _touched(promised: str, changed: list[str]) -> bool:
    """Whether one promised path is anywhere in the diff.

    Deliberately lenient in both directions: the turn may name a path relative to the
    service while the diff is relative to its repo, or the other way round. A promise the
    gate cannot match becomes a repair lap, and a repair lap spent on a path-prefix
    disagreement is the most expensive way to be pedantic about one.
    """
    promised = promised.strip().lstrip("./")
    if not promised:
        return False
    return any(
        path == promised or path.endswith("/" + promised) or promised.endswith("/" + path)
        for path in (p.strip().lstrip("./") for p in changed)
    )


@blueprint.node
def check_promises(
    logger: logging.Logger,
    cwd: str = "",
    commands: list[str] | None = None,
    files: list[str] | None = None,
    changed: list[str] | None = None,
    already_run: list[str] | None = None,
) -> GateOutcome:
    """Hold the implement turn to the exit conditions it stated before it began.

    This is what makes goal setting worth a turn's tokens. The envelope asks the turn to
    write down what "done" is — which commands will be green, which files will have changed
    — and this node reads that back as a claim rather than as an intention: a command it
    promised is run, a file it promised is looked for in the diff, and a gap is a
    `FailureReport{source: "goal"}` into the same repair loop the declared gates feed.

    `already_run` is what the declared gates just ran clean, so a promise that names one of
    them costs nothing to keep — the alternative is running the test suite twice per layer
    to check a claim the previous node already proved.

    A turn that promised nothing is `skipped`, not failed. The check is a way of believing a
    turn less, not a second place to demand ceremony from it.
    """
    commands = [c.strip() for c in (commands or []) if c and c.strip()]
    files = [f for f in (files or []) if f and f.strip()]
    if not commands and not files:
        logger.info("the turn stated no exit conditions — nothing to hold it to")
        return GateOutcome(gate="goal", status="skipped", reason="no exit conditions stated")

    service_dir = Path(cwd).expanduser() if cwd else None
    if service_dir is None or not service_dir.is_dir():
        return GateOutcome(gate="goal", status="skipped", reason="no service directory")

    proven = {c.strip() for c in (already_run or []) if c and c.strip()}
    for command in commands:
        if command in proven:
            logger.info("promised `%s` was already run clean by a declared gate", command)
            continue
        try:
            result = subprocess.run(
                command,
                cwd=service_dir,
                shell=True,
                capture_output=True,
                text=True,
                timeout=GATE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return GateOutcome(
                gate="goal",
                status="dirty",
                command=command,
                output=f"promised command timed out after {GATE_TIMEOUT}s",
                reason="timeout",
            )
        except (OSError, ValueError) as exc:
            # A command that will not launch is the turn's own claim about its stack, and
            # this node is not the place to adjudicate it — the declared gates are.
            # `ValueError` is the same class of thing one layer earlier: a string the shell
            # was never going to be handed, from a model that free-typed it.
            logger.info("promised command '%s' could not be launched: %s", command, exc)
            continue
        if result.returncode != 0:
            output = (result.stdout + result.stderr).strip()
            if len(output) > MAX_GATE_OUTPUT:
                output = "…(truncated)…\n" + output[-MAX_GATE_OUTPUT:]
            logger.warning("promised `%s` is not green (exit %s)", command, result.returncode)
            return GateOutcome(
                gate="goal",
                status="dirty",
                command=command,
                output=(
                    f"You stated `{command}` would be green when you were done. "
                    f"It exits {result.returncode}.\n\n{output}"
                ),
                reason="a promised command is not green",
            )

    missing = [f for f in files if not _touched(f, changed or [])]
    if missing:
        logger.warning("%d promised file(s) are not in the diff", len(missing))
        return GateOutcome(
            gate="goal",
            status="dirty",
            output=(
                "You stated you would change these files. Nothing in the diff matches "
                "them:\n" + "\n".join(f"- {path}" for path in missing) + "\n\n"
                "Either make the change you described, or say why it turned out to be "
                "unnecessary."
            ),
            reason="a promised file was never touched",
        )
    return GateOutcome(gate="goal", status="clean", reason="the stated exit conditions hold")


#: Service types for which "no test" is an acceptable answer rather than a defect. A
#: directory of prose or of configuration has nothing a test could assert about it, and a
#: gate that failed those would only teach the escape hatch to everybody else.
TDD_EXEMPT_TYPES = ("docs", "config")


def tdd_mode(service: str = "", service_type: str = "", repo_dir: str = "") -> str:
    """What this service declares about tests: `required`, `encouraged` or `off`.

    Off by default, and that is the invariant rather than an opinion about TDD: whether a
    failing test comes first is a property of the service — a stack with no harness yet, an
    infrastructure directory, a docs tree — and the repo is what knows it. A workflow that
    defaulted to `required` would be imposing the belief this key exists to let the repo
    hold.
    """
    declared = service_declaration(service, service_type, repo_dir).get("tdd")
    mode = str(declared or "").strip().lower()
    return mode if mode in ("required", "encouraged", "off") else "off"


@blueprint.node
def tdd_gate(
    logger: logging.Logger,
    cwd: str = "",
    service: str = "",
    service_type: str = "",
    tests_added: list[str] | None = None,
    no_test_reason: str = "",
    changed: list[str] | None = None,
    repo_dir: str = "",
) -> GateOutcome:
    """Check that a change to a service that requires tests actually came with one.

    The argument for TDD with an agent is not that red-green is virtuous; it is that a
    failing test is a concrete, machine-checked target, and that without one "green build"
    and "build that tests nothing" are the same reading. That argument is adopted here as a
    *mechanism*: as prose ("write the test first — MANDATORY") it is exactly the scar tissue
    this lane is shedding, because the model half-complies and nothing can tell.

    What is checked is stack-agnostic on purpose. This node does not know what a test file
    looks like in any language — it reads the paths the turn itself reported under
    `tests_added` and asserts they are really in the diff. A repo's own `test` command,
    declared in `agents.yml` and run by `run_gate`, is what decides whether those tests
    pass; this decides only whether they exist.

    An exemption is a claim, not a flag: `no_test_reason` clears the gate only for a service
    whose declared type has nothing to test, and is otherwise quoted back as the failure.
    """
    mode = tdd_mode(service, service_type, repo_dir)
    if mode == "off":
        return GateOutcome(gate="tdd", status="skipped", reason="this service declares no tdd key")

    reported = [t.strip() for t in (tests_added or []) if t and t.strip()]
    changed = changed or []
    if reported:
        unwritten = [t for t in reported if not _touched(t, changed)]
        if not unwritten:
            return GateOutcome(gate="tdd", status="clean", reason=f"{len(reported)} test file(s)")
        problem = (
            "You reported these test files, and the diff does not contain them:\n"
            + "\n".join(f"- {path}" for path in unwritten)
        )
    elif no_test_reason and service_type in TDD_EXEMPT_TYPES:
        logger.info("%s is a %s service — accepting '%s'", service, service_type, no_test_reason)
        return GateOutcome(gate="tdd", status="clean", reason="exempt service type")
    else:
        problem = (
            "No test covers this change. Add one that fails without it, then make it pass."
            + (f"\n\nYou said: {no_test_reason}" if no_test_reason else "")
        )

    if mode == "encouraged":
        # Logged, not enforced: `encouraged` is what a repo says while its harness is still
        # being built, and failing a story on it would make the honest answer expensive.
        logger.warning("tdd (encouraged) missed in %s: %s", service or cwd, problem)
        return GateOutcome(gate="tdd", status="clean", reason="tdd encouraged — miss logged")
    logger.warning("tdd (required) not satisfied in %s", service or cwd)
    return GateOutcome(
        gate="tdd", status="dirty", output=problem, reason="this service requires tests"
    )


@blueprint.node
def changed_files(logger: logging.Logger, cwd: str = "", story_slug: str = "") -> ChangedFiles:
    """Which files this story has already written in one service checkout.

    The re-seed for a recycled conversation — see `ChangedFiles`. Both halves count, and the
    two are found differently: what is still in the tree is a plain diff, and what has been
    committed is found by the `Story:` trailer every prompt in this lane is required to
    write. The trailer rather than a branch comparison because the base branch is not
    something this node is given, and a story branch carrying two stories would otherwise
    report the first one's files as this one's.

    Degrades to empty on anything unexpected. It is a courtesy to the next turn, which reads
    the code itself when told nothing; a service that is not a git checkout must not fail the
    lane over it.
    """
    if not cwd or not Path(cwd).expanduser().is_dir():
        return ChangedFiles()
    commands = [["diff", "--name-only", "HEAD"]]
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
    "check_promises",
    "declared_gates",
    "gate_command",
    "plan_document",
    "plan_summary",
    "read_operator_context",
    "record_plan",
    "resolve_impl_context",
    "run_gate",
    "select_next_layer",
    "service_declaration",
    "tdd_gate",
    "tdd_mode",
]
