"""The dev flow's deterministic work: validate, dispatch, branch, iterate, gate."""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

import yaml
from ostler.provenance import story_commits
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
    StorySource,
    StorySources,
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

MAX_GATE_OUTPUT = 4000

GATE_TIMEOUT = 600

GATE_ORDER = ("lint", "test")

AWAITING = "AWAITING_OPERATOR"
ANSWERED = "ANSWERED"
CONSUMED = "CONSUMED"


def _spec_dir(spec_dir: str, root: Path) -> Path:
    """A spec dir as an absolute path, taken relative to `root` unless already absolute."""
    path = Path(spec_dir)
    return path if path.is_absolute() else root / path


def _spec_relative(plan_file: str, spec_abs: Path | None, root: Path | None) -> str:
    """`plan_file` as the spec-relative path it is declared to be, under either reading."""
    if not plan_file or spec_abs is None or root is None:
        return plan_file
    if (spec_abs / plan_file).is_file():
        return plan_file
    candidate = Path(plan_file)
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
    """The plan-context mapping, built from a `PlanResult` and the resolved workspace."""
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
    """The story's `## Verification setup`, under either spelling."""
    return doc.get("verification_setup") or doc.get("qa_stack") or {}


def _fixtures(doc: dict[str, Any]) -> list[dict[str, str]]:
    """The story's declared fixtures, from the typed field or nested in the setup block."""
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
    """The plan document and whether it had to be read off disk."""
    if plan:
        spec_abs = _spec_dir(spec_dir, root) if spec_dir else None
        return plan_document(plan, repos, spec_abs, root), False
    path = _spec_dir(spec_dir, root) / "plan-context.json" if spec_dir else None
    on_disk = load_json(path, "plan-context.json", logger) if path else {}
    return on_disk, path is None or not path.exists()


def _dispatched_plan_problems(
    doc: dict[str, Any], repos: dict[str, dict], spec_abs: Path
) -> list[str]:
    """Every plan file the dispatcher will hand an implementer, opened to prove it is there."""
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
    """Write the plan-context projection, and answer whether the plan is implementable."""
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
    errors: list[str] = _dispatched_plan_problems(doc, repos, spec_abs)
    if not services:
        return PlanValidation(
            status="invalid" if errors else "valid", errors=errors, document=doc
        )

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
            logger.info("%s: new_service=true — skipping path existence check", label)
            continue

        markers = repo_info.get("service_markers", [])
        problems = service_problems(Path(repo_info["path"]) / svc_path, markers, label)
        if problems:
            errors.extend(problems)
            continue

    return PlanValidation(
        status="invalid" if errors else "valid", errors=errors, document=doc
    )


def _package_label(item: Any) -> str:
    """One shared package as the `repo::path` string the QA prompts render."""
    if isinstance(item, dict):
        repo, path = str(item.get("repo", "")), str(item.get("path", ""))
        return f"{repo}::{path}" if repo and path else repo or path
    return str(item)


def read_plan_text(spec_dir: str, plan_file: str, logger: logging.Logger) -> str:
    """The layer's plan as content, inlined into the implement turn rather than read by it."""
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
    """Decode the approved plan against the workspace into everything downstream needs."""
    root = find_repo_root(repo_dir)
    docs_root = find_docs_root(docs_path, repo_dir)

    repos = resolve_workspace(workspace_file, repo_dir)
    plan_ctx, plan_ctx_absent = _plan_context(plan, spec_dir, root, repos, logger)

    services = plan_ctx.get("services") or []

    dispatch = [
        DispatchEntry(**entry)
        for entry in build_dispatch_list(
            plan_ctx, repos, fallback=plan_ctx_absent or not services
        )
    ]

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
    if str(docs_root) not in affected_repo_paths:
        affected_repo_paths = [str(docs_root), *affected_repo_paths]

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
    """The plan's structure, rendered for a turn in a lane that did not plan it."""
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
    """Put every code repo the plan names onto the story branch."""
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
            continue
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
    """The next service to implement, or "the dispatch list is exhausted"."""
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
    """The orchestrating repo's `services:` block — what each service type declares."""
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
    """The `services:` keys this layer answers to, narrowest first."""
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
    """One service's declared block, looked up by service name and then by type."""
    block = _services_config(repo_dir)
    for key in service_keys(service, service_type):
        entry = block.get(key)
        if isinstance(entry, dict):
            return entry
    return {}


def service_dir(cwd: str | Path, service: str = "") -> Path:
    """Where one service's declared commands run: its own directory, not its repo's."""
    root = Path(cwd).expanduser()
    path = service.partition("::")[2].strip().strip("/")
    if not path or path == ".":
        return root
    candidate = root / path
    return candidate if candidate.is_dir() else root


def _lint_override(service: str, cwd: Path, repo_dir: str = "") -> str:
    """The legacy `lint:` map — an explicit lint command keyed by service or directory."""
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
    """The command this service declares for one gate, or `""` when it declares none."""
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
    """Which gates will run after the turn about to be taken — for the turn to be told."""
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
    """The marker files each repo says identify a service directory — for the planner."""
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
    """Run one of a service's declared gate commands and report whether it passed."""
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
    """Whether the turn just taken stamped the story finished."""
    root = find_docs_root(docs_path, repo_dir)
    written = story_status.current(root, slug, epic=epic, story_path=story_path).strip()
    if not is_done(written):
        return StoryStatusCheck(status="clean", written=written)
    logger.warning(
        "the story's Status reads %r, which marks it finished, before QA has run", written
    )
    return StoryStatusCheck(status="dirty", written=written)


@blueprint.node
def changed_files(
    logger: logging.Logger, cwd: str = "", story_slug: str = "", story_id: str = ""
) -> ChangedFiles:
    """Which files this story has already written in one service checkout."""
    if not cwd or not Path(cwd).expanduser().is_dir():
        return ChangedFiles()
    commands = [["diff", "--name-only", "HEAD"], ["ls-files", "--others", "--exclude-standard"]]
    if story_slug or story_id:
        greps = [
            f"--grep=Story: {ref}" for ref in dict.fromkeys((story_id, story_slug)) if ref
        ]
        commands.append(["log", "--name-only", "--pretty=format:", *greps])
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


def _story_base(cwd: str, refs: tuple[str, ...]) -> str:
    matching = story_commits(Path(cwd), refs)
    if not matching:
        raise ValueError("no commit carries an exact Story trailer for this story")
    parent = matching[0].get("parent")
    if not parent:
        raise ValueError("the story's earliest commit is the repository root")
    return str(parent)


@blueprint.node
def resolve_story_sources(
    logger: logging.Logger,
    dispatch: tuple[DispatchEntry, ...],
    story_slug: str = "",
    story_id: str = "",
    docs_path: str = "",
    repo_dir: str = "",
) -> StorySources:
    """Resolve each implementation repository to the parent before this story began."""
    docs_root = Path(find_docs_root(docs_path, repo_dir)).resolve()
    dispatch_roots = {
        Path(entry.cwd).resolve() for entry in dispatch if entry.cwd
    }
    if not dispatch_roots or dispatch_roots == {docs_root}:
        return StorySources()
    refs = tuple(dict.fromkeys(ref for ref in (story_id, story_slug) if ref))
    if not refs:
        return StorySources(status="invalid", errors=("the story has no identity",))
    bases: dict[str, tuple[str, str]] = {}
    sources: list[StorySource] = []
    errors: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in dispatch:
        cwd = str(Path(entry.cwd).resolve()) if entry.cwd else ""
        repo_name = (entry.repo or Path(cwd).name).strip()
        surface = (entry.repo or entry.service).strip()
        root = entry.service_path.strip().replace("\\", "/").strip("/") or "."
        if not cwd or not repo_name or not surface:
            errors.append(f"implementation entry {entry.service!r} has no source repository")
            continue
        existing = bases.get(repo_name)
        if existing is not None and existing[0] != cwd:
            errors.append(f"source repository {repo_name!r} resolves to multiple checkouts")
            continue
        if existing is None:
            try:
                base = _story_base(cwd, refs)
            except (OSError, ValueError) as exc:
                errors.append(f"source repository {repo_name!r}: {exc}")
                continue
            bases[repo_name] = (cwd, base)
        else:
            base = existing[1]
        key = (repo_name, surface, root)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            StorySource(
                repo=repo_name,
                checkout=cwd,
                surface=surface,
                root=root,
                base=base,
            )
        )
    if errors:
        logger.warning("story source provenance is invalid: %s", "; ".join(errors))
        return StorySources(status="invalid", errors=tuple(errors))
    return StorySources(sources=tuple(sources))


@blueprint.node
def read_operator_context(logger: logging.Logger, story_path: str = "") -> OperatorAnswer:
    """Take the operator's answer off `<story-folder>/context.md` and consume it."""
    ctx = paths.story_context_path(story_path)
    if not ctx.exists():
        logger.warning("no operator context at %s — treating the block as unanswered", ctx)
        return OperatorAnswer()

    content = ctx.read_text(encoding="utf-8")
    if gates.status_of(content) == ANSWERED:
        ctx.write_text(gates.set_status(content, CONSUMED), encoding="utf-8")
        logger.info("consumed the operator's answer in %s", ctx)

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
