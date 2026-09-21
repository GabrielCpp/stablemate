"""Genesis's deterministic work: classify the target, make a repo, configure it, check it."""
from __future__ import annotations

import copy
import io
import logging
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from git import Repo
from git.exc import GitError
from ostler import path as okf_path
from ostler.model import find_root
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from ruamel.yaml.scalarstring import ScalarString
from workhorse_workflows.kit import commit_all, head_sha, load_json, run_tool
from workhorse_workflows.coder.shared.contract import service_problems
from workhorse_workflows.coder.shared import stubs
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.genesis import (
    AgentsYml,
    FarrierInstall,
    GenesisReport,
    GitInit,
    Skeleton,
    TargetClassification,
)

ASSISTANTS = ("claude", "codex", "copilot")


def _git_init(target: Path) -> str:
    """`git init` in `target`, or the reason it could not be done."""
    try:
        Repo.init(str(target))
    except GitError as exc:
        return str(exc).strip()
    return ""




@blueprint.node(stub=stubs.classified)
def resolve_genesis_target(
    logger: logging.Logger,
    target: str = "",
    service: str = "",
    service_root: str = "",
    marker: str = "",
    markers: Sequence[str] = (),
) -> TargetClassification:
    """Classify the target before anything mutates it, so genesis is safe to re-run."""
    if not target:
        logger.error("no target directory was provided")
        return TargetClassification(
            note="no target directory was provided; "
                 "pass --params '{\"target\":\"<path>\", ...}'",
        )

    root = Path(target).expanduser().resolve()
    state = _classify(root)
    declared_markers = [m for m in markers if m] or ([marker] if marker else [])

    service_dir = (root / service_root) if service_root else root
    service_state = "existing" if (marker and (service_dir / marker).is_file()) else "absent"

    note = {
        "absent": f"{root} does not exist yet — running full genesis",
        "partial": (f"{root} exists with content but has no agents.yml — running full "
                    f"genesis; nothing already there will be removed"),
        "existing": (f"{root} already has an agents.yml — refreshing config only, "
                     f"not re-scaffolding"),
    }[state]
    if service_root:
        note += (f"; service '{service or service_root}' at {service_root}/ is "
                 f"{service_state} (marker: {marker or '<none declared>'})")
    logger.info("%s", note)
    return TargetClassification(
        ok=True,
        target_dir=str(root),
        target_state=state,
        service_state=service_state,
        service=service,
        markers=declared_markers,
        note=note,
    )


def _classify(target: Path) -> Literal["absent", "partial", "existing"]:
    """Which of the three states the target directory is in, by what is on disk."""
    if (target / "agents.yml").is_file():
        return "existing"
    if not target.exists() or not any(target.iterdir()):
        return "absent"
    return "partial"




@blueprint.node
def genesis_git_init(logger: logging.Logger, target_dir: str = "") -> GitInit:
    """`git init` the target and land one initial commit."""
    if not target_dir:
        return GitInit(note="no target_dir was provided")

    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    if (target / ".git").exists():
        sha = head_sha(target)
        if sha:
            logger.info("%s is already a git repo at %s", target, sha[:8])
            return GitInit(ready=True, initial_commit=sha,
                           note=f"already a git repo (HEAD {sha[:8]})")
        logger.info("%s has .git but an unborn HEAD — landing the initial commit", target)
    else:
        failure = _git_init(target)
        if failure:
            return GitInit(note=f"git init failed: {failure}")

    readme = target / "README.md"
    if not readme.exists():
        readme.write_text(f"# {target.name}\n", encoding="utf-8")

    try:
        commit_all(target, "Initial commit")
    except GitError as exc:
        if not head_sha(target):
            return GitInit(note=f"initial commit failed: {str(exc).strip()}")

    sha = head_sha(target)
    logger.info("initialised %s at %s", target, sha[:8])
    return GitInit(
        ready=True,
        initial_commit=sha,
        note=f"git initialised with an initial commit ({sha[:8]}), no remote configured",
    )




@blueprint.node
def write_agents_yml(
    logger: logging.Logger,
    target_dir: str = "",
    service: str = "",
    packs: Sequence[str] = (),
    service_root: str = "",
    markers: Sequence[str] = (),
    workflows: Sequence[str] = ("coder",),
    scaffolds: Sequence[str] = (),
    assistants: Sequence[str] = ("claude",),
    gates: Sequence[str] = (),
) -> AgentsYml:
    """Merge this service into the repo's `agents.yml` — packs, scaffolds, `workspace:`."""
    if not target_dir:
        return AgentsYml(note="no target_dir was provided")
    target = Path(target_dir)
    if not target.is_dir():
        return AgentsYml(note=f"target {target} is not a directory")

    scaffold_ids = [s for s in (entry.partition(":")[0].strip() for entry in scaffolds) if s]

    declared: dict[str, str] = {}
    malformed: list[str] = []
    for pair in gates:
        gate, _, command = pair.partition("=")
        if gate.strip() and command.strip():
            declared[gate.strip()] = command.strip()
        elif pair.strip():
            malformed.append(pair.strip())

    drops: list[str] = []
    unknown = [name for name in assistants if name and name not in ASSISTANTS]
    if unknown:
        drops.append(f"assistant(s) {', '.join(unknown)} dropped — farrier installs "
                     f"{', '.join(ASSISTANTS)} and nothing else")
    if malformed:
        drops.append(f"gate(s) {', '.join(malformed)} dropped — a gate is written "
                     f"'<gate>=<command>' and both halves have to be non-empty")
    if declared and not service:
        drops.append(f"gate(s) {', '.join(sorted(declared))} dropped — a services: block is "
                     f"keyed on a service name and none was passed; re-run with "
                     f"--params '{{\"service\":\"<name>\", ...}}' to declare them")

    repo_name = target.name
    path = target / "agents.yml"

    try:
        source = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError as exc:
        return AgentsYml(note=f"existing agents.yml is unreadable ({exc}); refusing to clobber it")

    yml = _yaml(source)
    data: dict = {}
    if path.is_file():
        try:
            data = yml.load(source) or {}
        except (YAMLError, OSError) as exc:
            return AgentsYml(
                note=f"existing agents.yml is unreadable ({exc}); refusing to clobber it"
            )
        if not isinstance(data, dict):
            return AgentsYml(note="existing agents.yml is not a mapping; refusing to clobber it")

    had_existing = bool(data)
    before = copy.deepcopy(data)
    data.setdefault("repo", {})
    if isinstance(data["repo"], dict):
        data["repo"].setdefault("name", repo_name)

    data.setdefault("agents", {name: name in assistants for name in ASSISTANTS})

    for key, values in (("packs", list(packs)), ("workflows", list(workflows)),
                        ("scaffolds", scaffold_ids)):
        if values:
            _assign_seq(data, key, list(dict.fromkeys([*(data.get(key) or []), *values])))

    if not isinstance(data.get("workspace"), dict):
        data["workspace"] = {}
    workspace = data["workspace"]
    workspace.setdefault("type", "mono")
    for key, values in (("service_roots", [service_root] if service_root else []),
                        ("service_markers", list(markers))):
        if values:
            _assign_seq(workspace, key, list(dict.fromkeys([*(workspace.get(key) or []), *values])))

    if declared and service:
        if not isinstance(data.get("services"), dict):
            data["services"] = {}
        entry = data["services"].setdefault(service, {})
        if isinstance(entry, dict):
            for gate, command in declared.items():
                entry.setdefault(gate, command)

    if data == before and path.is_file():
        note = _with_drops(
            f"agents.yml for repo '{repo_name}' already carries this service; left untouched",
            drops,
        )
        logger.info("%s", note)
        return AgentsYml(path="agents.yml", note=note)

    buf = io.StringIO()
    yml.dump(data, buf)
    path.write_text(buf.getvalue(), encoding="utf-8")
    enabled = ", ".join(sorted(k for k, v in data["agents"].items() if v)) or "<none>"
    note = (f"{'updated' if had_existing else 'wrote'} agents.yml for repo '{repo_name}'"
            f"{f", service '{service}'" if service else ''} "
            f"(packs: {', '.join(packs) or '<none>'}; "
            f"scaffolds: {', '.join(scaffold_ids) or '<none>'}; "
            f"agents: {enabled}; "
            f"service_roots: {', '.join(workspace.get('service_roots') or []) or '<none>'}; "
            f"service_markers: {', '.join(workspace.get('service_markers') or []) or '<none>'}; "
            f"gates: {', '.join(sorted(declared)) or '<none>'})")
    note = _with_drops(note, drops)
    logger.info("%s", note)
    return AgentsYml(written=True, path="agents.yml", note=note)


def _with_drops(note: str, drops: Sequence[str]) -> str:
    """`note` with whatever this merge threw away appended, one line each."""
    return "\n".join([note, *drops]) if drops else note


def _yaml(source: str = "") -> YAML:
    """Round-trip loader/dumper: comments, key order and flow style survive the merge."""
    y = YAML()
    y.preserve_quotes = True
    y.default_flow_style = False
    y.width = 4096
    seq = _sequence_indent(source)
    y.indent(mapping=2, sequence=seq + 2, offset=seq)
    return y


def _sequence_indent(source: str, default: int = 2) -> int:
    """How far `source` indents a top-level block-sequence item, or `default`."""
    indents = [len(line) - len(line.lstrip(" ")) for line in source.splitlines()
               if line.lstrip(" ").startswith("- ") or line.strip() == "-"]
    return min(indents) if indents else default


def _assign_seq(mapping: dict, key: str, merged: list) -> None:
    """Set `mapping[key]` to `merged`, keeping the existing sequence node when possible."""
    current = mapping.get(key)
    if isinstance(current, list) and list(current) == merged[:len(current)]:
        current.extend(_like(current[0] if current else None, item)
                       for item in merged[len(current):])
        return
    mapping[key] = merged


def _like(sibling, value: str):
    """Return `value` quoted the way `sibling` is quoted."""
    return type(sibling)(value) if isinstance(sibling, ScalarString) else value




@blueprint.node(stub=stubs.built)
def init_skeleton(
    logger: logging.Logger,
    target_dir: str = "",
    service_root: str = "",
    init_cmd: str = "",
    marker: str = "",
) -> Skeleton:
    """Run the stack's native init tooling, then assert it produced the marker."""
    if not target_dir:
        return Skeleton(note="no target_dir was provided")
    target = Path(target_dir)
    if not target.is_dir():
        return Skeleton(note=f"target {target} is not a directory")

    service_dir = (target / service_root) if service_root else target
    service_dir.mkdir(parents=True, exist_ok=True)
    marker_rel = f"{service_root}/{marker}".lstrip("/") if service_root else marker

    if marker and (service_dir / marker).exists():
        logger.info("%s already present — skipping init", marker_rel)
        return Skeleton(
            ok=True,
            marker_path=marker_rel,
            note=f"{marker_rel} already present; native init skipped (idempotent re-run)",
        )

    if not init_cmd:
        return Skeleton(note=(
            f"no init_cmd was provided and {marker_rel or '<no marker>'} does not exist — "
            f"pass the stack's native init command as a flow param, e.g. "
            f"--params '{{\"init_cmd\":\"go mod init example.com/api\",\"marker\":\"go.mod\"}}'"
        ))

    logger.info("running init in %s: %s", service_dir, init_cmd)
    result = subprocess.run(init_cmd, cwd=str(service_dir), shell=True, capture_output=True,
                            text=True, check=False, timeout=900)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return Skeleton(note=f"init_cmd failed ({init_cmd}): {detail}")

    if marker and not (service_dir / marker).exists():
        return Skeleton(note=(
            f"init_cmd succeeded but {marker_rel} was not created. The service is not real "
            f"to validate-plan-context.py without it — check whether the tool wrote into a "
            f"subdirectory of {service_dir}, and adjust service_root or init_cmd."
        ))

    note = f"native init ran in {service_root or '.'}; {marker_rel} present"
    logger.info("%s", note)
    return Skeleton(ok=True, marker_path=marker_rel, note=note)


@blueprint.node(stub=stubs.installed)
def install_farrier(
    logger: logging.Logger,
    target_dir: str = "",
    scaffolds: Sequence[str] = (),
    skip_install: bool = False,
) -> FarrierInstall:
    """Run farrier against the genesis repo: install the packs, then render the scaffolds."""
    if not target_dir:
        return FarrierInstall(note="no target_dir was provided")
    target = Path(target_dir)
    if not target.is_dir():
        return FarrierInstall(note=f"target {target} is not a directory")

    notes: list[str] = []
    if not skip_install:
        result = run_tool(["farrier", "install", "--repo", str(target)], target)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            return FarrierInstall(note=f"farrier install failed: {detail}")
        notes.append("farrier install: adapters + .agents/agents-context.json rendered")

    rendered: list[str] = []
    for entry in (part.strip() for part in scaffolds if part.strip()):
        scaffold_id, _, dir_param = entry.partition(":")
        scaffold_id = scaffold_id.strip()
        args = ["farrier", "scaffold", scaffold_id, "--repo", str(target)]
        if dir_param.strip():
            args += ["--param", f"dir={dir_param.strip()}"]
        result = run_tool(args, target)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            return FarrierInstall(
                scaffolds_rendered=rendered,
                note="\n".join([*notes, f"scaffold '{scaffold_id}' failed: {detail}"]),
            )
        rendered.append(scaffold_id)
        notes.append(f"scaffold '{scaffold_id}' rendered at '{dir_param.strip() or '<default>'}'")

    logger.info("farrier ok: %d scaffold(s) rendered", len(rendered))
    return FarrierInstall(ok=True, scaffolds_rendered=rendered, note="\n".join(notes))




@blueprint.node(stub=stubs.valid)
def validate_genesis(
    logger: logging.Logger,
    target_dir: str = "",
    service_root: str = "",
    markers: Sequence[str] = (),
) -> GenesisReport:
    """Assert the genesis repo satisfies every precondition the main loop assumes."""
    errors: list[str] = []
    warnings: list[str] = []

    if not target_dir:
        return GenesisReport(errors="no target_dir was provided")
    target = Path(target_dir).resolve()
    if not target.is_dir():
        return GenesisReport(errors=f"target {target} is not a directory")

    if not (target / ".git").exists():
        errors.append(f"no .git at {target} — ostler will bind to an ancestor repo, and "
                      f"branch-author.py cannot cut a branch")
    elif not head_sha(target):
        errors.append(f"{target} has an unborn HEAD (no commit) — there is nothing for a "
                      f"branch to point at")

    bound = _ostler_root(target)
    if bound is None:
        warnings.append("could not import ostler to verify graph binding — skipped that check")
    elif bound != target:
        errors.append(
            f"ostler binds to {bound}, not {target}. Ids would be allocated from that repo's "
            f"registry and docs written into its tree, silently. This is the failure mode "
            f"git_init exists to prevent — check that node ran before any ostler call."
        )

    if service_root:
        errors.extend(service_problems(target / service_root, markers,
                                       f"{target.name}::{service_root}"))

    ctx_path = target / ".agents" / "agents-context.json"
    if not ctx_path.is_file():
        errors.append(f"no {ctx_path.relative_to(target)} — farrier install did not run, so "
                      f"the repo advertises no standards for an implementing turn to load")
    elif not load_json(ctx_path, "agents-context", logger).get("instructions"):
        errors.append(
            f"{ctx_path.relative_to(target)} has an empty 'instructions' map — the "
            f"implementation stage would run with no skills and still report success"
        )

    epics_root = okf_path.epics_root_in(target)
    backlog = okf_path.backlog_path_in(target)
    if not epics_root.is_dir():
        errors.append(f"no {epics_root.name}/ at {epics_root} — ostler infers the 'exploration' "
                      "profile without it, and epic-coverage validation then short-circuits "
                      "and asserts nothing")
    if not backlog.is_file():
        errors.append(
            f"no backlog at {backlog} — coder fix queues and Author story/edit modes require it"
        )

    if not _has_lint_target(target):
        warnings.append("no `lint` target in a Makefile — the coder workflow's lint gate will "
                        "skip rather than fail, so lint findings would go unreported")

    if errors:
        logger.warning("genesis validation failed with %d error(s)", len(errors))
    else:
        logger.info("genesis validation passed%s",
                    f" with {len(warnings)} warning(s)" if warnings else "")
    return GenesisReport(
        valid=not errors, errors="\n".join(errors), warnings="\n".join(warnings)
    )


def _ostler_root(target: Path) -> Path | None:
    """Where ostler *actually* binds when run from `target` — not where we hope it does."""
    try:
        return Path(find_root(target)).resolve()
    except (OSError, ValueError, RuntimeError):
        return None


def _has_lint_target(target: Path) -> bool:
    makefile = next((target / name for name in ("Makefile", "makefile")
                     if (target / name).is_file()), None)
    if makefile is None:
        return False
    return any(line.startswith("lint:") or line.startswith("lint ")
               for line in makefile.read_text(encoding="utf-8").splitlines())


__all__ = [
    "genesis_git_init",
    "init_skeleton",
    "install_farrier",
    "resolve_genesis_target",
    "validate_genesis",
    "write_agents_yml",
]
