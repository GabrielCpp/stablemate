"""The dev flow's deterministic work: branch the repos, run the gates, read the story's status and sources."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import yaml
from ostler.provenance import story_commits
from workhorse import gates
from workhorse_workflows.kit import find_docs_root, find_repo_root
from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared import story_status
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.dev import (
    ChangedFiles,
    DispatchEntry,
    GateList,
    GateOutcome,
    OperatorAnswer,
    StoryStatusCheck,
    StorySource,
    StorySources,
)
from workhorse_workflows.kit import resolve_workspace
from ostler.select import is_done

MAX_GATE_OUTPUT = 4000

GATE_TIMEOUT = 600

GATE_ORDER = ("lint", "test")

AWAITING = "AWAITING_OPERATOR"
ANSWERED = "ANSWERED"
CONSUMED = "CONSUMED"


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
    "changed_files",
    "check_story_status",
    "declared_gates",
    "declared_markers",
    "gate_command",
    "read_operator_context",
    "run_gate",
    "service_declaration",
]
