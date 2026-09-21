"""The docs flow's deterministic work: is there a book, how do we read the diff, does it hold."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

import yaml
from git.exc import GitError, InvalidGitRepositoryError, NoSuchPathError
from ostler import Ostler, path as okf_path
from ostler.model import Graph
from ostler import refs as refs_mod
from workhorse.pyflow import Workflow
from workhorse_workflows.kit import find_docs_root, load_json
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.docs import (
    ContextClassification,
    DocumentationGate,
    DocumentationObligations,
    OkfDetection,
)
from workhorse_workflows.coder.shared.worktree import untouched_since
from workhorse_workflows.kit import open_repo, trunk_base

CONTEXT_FILE = "qa-okf-context.json"

CONFIG_FILES = ("ostler.yml", "ostler.yaml", "agents.yml", ".agents.yml")

MANAGED_KINDS = ("epics", "features")

DIRECT_KINDS = {"changed-code", "file-owner", "surface-owner"}

SEMANTIC_SUPPRESSED = {"dangling-code-ref", "missing-code-symbol"}

MAX_PROMPT_NOTE_CHARS = 12000

DOCTOR_ERRORS_FILE = "doctor-errors.txt"

MAX_DOCTOR_ERROR_MESSAGE_CHARS = 400


def _grounded_paths(packet: dict[str, Any]) -> tuple[set[str], set[str]]:
    """The packet's direct-grounding evidence: exact `path::symbol` refs, and owned files."""
    exact: set[str] = set()
    files: set[str] = set()
    for item in packet.get("directNodes", []):
        if not isinstance(item, dict):
            continue
        for reason in item.get("reasons", []):
            if not isinstance(reason, dict):
                continue
            ref = str(reason.get("ref", ""))
            if reason.get("kind") == "changed-code":
                exact.add(refs_mod.normalize_ref(ref))
            elif reason.get("kind") == "file-owner":
                files.add(ref)
    return exact, files


def _is_grounded(ref: str, exact: set[str]) -> bool:
    """Whether *ref* is grounded outright, or by a declaration that lexically encloses it."""
    path, _, symbol = ref.partition("::")
    parts = symbol.split(".")
    return any(f"{path}::{'.'.join(parts[:depth])}" in exact for depth in range(1, len(parts) + 1))


def ungrounded_refs(packet: dict[str, Any], inherited: set[str]) -> list[str]:
    """The changed production references the book does not directly own yet."""
    exactly_grounded, file_grounded = _grounded_paths(packet)
    ungrounded: list[str] = []
    changes = packet.get("changedUnits") or packet.get("changedCode", [])
    for change in changes:
        if not isinstance(change, dict):
            continue
        if change.get("status") == "deleted":
            continue
        base_path = str(change.get("basePath", ""))
        head_path = str(change.get("headPath", ""))
        candidates = {str(change.get("path", "")), base_path, head_path} - {""}
        if candidates and candidates <= inherited:
            continue
        base_symbols = set(change.get("baseSymbols", []))
        head_symbols = set(change.get("headSymbols", []))
        repository = str(change.get("repository", ""))

        def qualified(path: str, symbol: str = "") -> str:
            ref = f"repo://{repository}/{path}" if repository else path
            return f"{ref}::{symbol}" if symbol else ref

        required = {
            *(qualified(base_path, symbol) for symbol in base_symbols if base_path),
            *(qualified(head_path, symbol) for symbol in head_symbols if head_path),
        }
        if base_symbols | head_symbols:
            ungrounded.extend(
                sorted(ref for ref in required if not _is_grounded(ref, exactly_grounded))
            )
        elif {qualified(path) for path in candidates}.isdisjoint(
            {ref.partition("::")[0] for ref in exactly_grounded} | file_grounded
        ):
            ungrounded.append(qualified(str(change.get("path", "<unknown>"))))
    return ungrounded


def _affected_doc_nodes(packet: dict[str, Any], author_nodes: list[str]) -> set[str]:
    """Every doc node this story touched: what the diff implicated, plus what the author said."""
    nodes = {
        str(item.get("node", ""))
        for item in packet.get("directNodes", [])
        if isinstance(item, dict)
        and any(
            isinstance(reason, dict) and reason.get("kind") in DIRECT_KINDS
            for reason in item.get("reasons", [])
        )
    }
    nodes.update(author_nodes)
    return {node for node in nodes if node}


def story_touched_lines(
    root: Path, paths: set[str], logger: logging.Logger
) -> dict[str, set[int] | None]:
    """Which lines of each doc file this branch's own edits landed on."""
    unknown: dict[str, set[int] | None] = {path: None for path in paths}
    if not paths:
        return {}
    try:
        repo = open_repo(root)
        base = Path(str(repo.working_tree_dir)).resolve()
        rels = {(root / path).resolve().relative_to(base).as_posix(): path for path in paths}
        untracked = set(repo.untracked_files)
        tracked = sorted(rel for rel in rels if rel not in untracked)
        diff = (
            repo.git.diff("-U0", trunk_base(base), "--", *tracked) if tracked else ""
        )
    except (GitError, OSError, TypeError, ValueError, RuntimeError) as exc:
        logger.info("could not read this story's doc diff at %s (%s)", root, exc)
        return unknown

    touched: dict[str, set[int] | None] = {
        path: (None if rel in untracked else set()) for rel, path in rels.items()
    }
    current: set[int] | None = None
    for raw in diff.splitlines():
        if raw.startswith("+++ b/"):
            current = None
            if (path := rels.get(raw[6:])) is not None:
                current = touched.setdefault(path, set())
            continue
        if not raw.startswith("@@ ") or current is None:
            continue
        after = raw.split(" ")[2]
        start, _, count = after.lstrip("+").partition(",")
        try:
            first, length = int(start), int(count or 1)
        except ValueError:
            return unknown
        current.update(range(first, first + length))
    return touched


def _finding_affects_nodes(
    graph: Graph,
    finding: dict[str, Any],
    affected: set[str],
    touched: dict[str, set[int] | None] | None = None,
) -> bool:
    """Does this doctor finding land on a node this story is responsible for?"""
    path = str(finding.get("path", ""))
    candidates = {node for node in affected if node.partition("#")[0] == path}
    if not candidates:
        return False
    line = int(finding.get("line") or 0)
    if not line:
        return True
    try:
        in_file = sorted(
            (
                node
                for node in graph.ui_nodes
                if node.path.relative_to(graph.root).as_posix() == path
            ),
            key=lambda node: node.line,
        )
    except (OSError, ValueError, RuntimeError):
        return True
    starts = [node for node in in_file if node.line <= line]
    if not starts:
        return True
    owner = starts[-1]
    walk: Any = owner
    while walk is not None:
        if walk.id in candidates:
            return True
        walk = graph.find_ui_node(walk.parent) if walk.parent else None
    if path not in candidates:
        return False
    moved = (touched or {}).get(path, None)
    if moved is None:
        return True
    end = next((node.line for node in in_file if node.line > owner.line), None)
    return any(owner.line <= at and (end is None or at < end) for at in moved)


def _doctor_error_note(item: dict[str, Any]) -> str:
    message = str(item.get("message", ""))
    if len(message) > MAX_DOCTOR_ERROR_MESSAGE_CHARS:
        message = message[:MAX_DOCTOR_ERROR_MESSAGE_CHARS].rstrip() + "..."
    suggestion = item.get("suggestion")
    return (
        f"{item.get('path') or item.get('ref') or '<graph>'}:"
        f"{item.get('line') or 0} [{item.get('code', '?')}] {message}"
        + (f" — expected form: {suggestion}" if suggestion else "")
    )


def _doctor_errors_note(doctor_errors: list[dict[str, Any]]) -> str:
    """Every affected doctor error, one per line, with nothing omitted."""
    return "ostler doctor errors:\n" + "\n".join(
        _doctor_error_note(item) for item in doctor_errors
    )


def _spill_doctor_errors(spec_root: Path, note: str, logger: logging.Logger) -> Path | None:
    """Write the full error list beside the story's spec, so the note can just point at it."""
    path = spec_root / DOCTOR_ERRORS_FILE
    try:
        spec_root.mkdir(parents=True, exist_ok=True)
        path.write_text(note + "\n", encoding="utf-8")
    except OSError as exc:
        logger.info("could not write %s (%s)", path, exc)
        return None
    return path


def _clear_doctor_errors(spec_root: Path) -> None:
    """Remove a previous pass's spill file, so nothing points at a list that no longer holds."""
    (spec_root / DOCTOR_ERRORS_FILE).unlink(missing_ok=True)


@blueprint.node
def detect_okf_docs(
    logger: logging.Logger,
    docs_path: str = "",
    features_subdir: str = "",
    repo_dir: str = "",
) -> OkfDetection:
    """Are this run's docs managed by an OKF graph, so documenting the story means anything?"""
    base = Path(find_docs_root(docs_path, repo_dir))
    sub = Path(features_subdir) if features_subdir else None
    if sub is None:
        requested = okf_path.features_root_in(base)
    else:
        requested = sub if sub.is_absolute() else base / sub

    configured = False
    for name in CONFIG_FILES:
        path = base / name
        if not path.is_file():
            continue
        if name.startswith("ostler"):
            configured = True
            break
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(data, dict) and isinstance(data.get("organization"), dict):
            configured = True
            break

    managed_tree = any(
        path.is_dir()
        for path in (requested, *(okf_path.doc_root_in(base, kind) for kind in MANAGED_KINDS))
    ) or (base / ".agents/templates.yml").is_file()
    if not configured and not managed_tree:
        logger.info("no OKF configuration or features at %s", base)
        return OkfDetection(has_okf="no", reason="no OKF configuration or features tree")

    okf = Ostler(base)
    try:
        _ = okf.graph
    except (OSError, ValueError, RuntimeError):
        logger.error("OKF configuration exists but the graph did not load at %s", base)
        return OkfDetection(
            has_okf="invalid",
            features_root=str(requested),
            reason="OKF configuration exists but the graph did not load",
        )
    features = okf.graph.doc_roots.get("features") or requested
    logger.info("ostler graph loaded and %s exists — has OKF docs", features)
    return OkfDetection(
        has_okf="yes",
        features_root=str(features),
        reason=f"ostler graph loaded and {features} exists",
    )


@blueprint.node
def classify_documentation_context(
    logger: logging.Logger,
    docs_path: str = "",
    source_roots: tuple[str, ...] = (),
    repo_dir: str = "",
) -> ContextClassification:
    """Deterministic local diff mapping, or semantic multi-repo review?"""
    docs_root = Path(find_docs_root(docs_path, repo_dir)).resolve()
    try:
        working_dir = open_repo(docs_root).working_tree_dir
        worktree = Path(working_dir).resolve() if working_dir else None
    except (InvalidGitRepositoryError, NoSuchPathError):
        worktree = None
    except (GitError, OSError, TypeError, ValueError, RuntimeError) as exc:
        logger.warning("could not read the docs worktree at %s (%s)", docs_root, exc)
        return ContextClassification(
            mode="error",
            notes=f"the docs worktree at {docs_root} could not be read: {exc}",
        )

    normalized: list[str] = []
    external: list[str] = []
    for raw in source_roots:
        surface, separator, source = str(raw).partition("=")
        if not separator or not surface.strip() or not source.strip():
            continue
        path = Path(source).resolve()
        if worktree is None or not path.is_relative_to(worktree):
            external.append(str(path))
            continue
        normalized.append(f"{surface.strip()}={path.relative_to(worktree).as_posix() or '.'}")

    mode = "local" if worktree is not None and normalized and not external else "semantic"
    notes = (
        "All affected source roots share the docs Git worktree; deterministic diff mapping "
        "enabled."
        if mode == "local"
        else "Affected sources span repositories or the docs root is not a Git worktree; "
        "doctor plus independent semantic review is authoritative."
    )
    logger.info("documentation context mode=%s", mode)
    return ContextClassification(mode=mode, source_roots=normalized, notes=notes)


@blueprint.node
def verify_story_documentation(
    logger: logging.Logger,
    docs_path: str = "",
    spec_dir: str = "",
    author_status: Literal["documented", "not_required", "blocked"] = "blocked",
    build_status: Literal["", "passed", "invalid"] = "invalid",
    validation_status: Literal["", "passed", "invalid"] = "invalid",
    context_mode: Literal["local", "semantic"] = "local",
    author_nodes: tuple[str, ...] = (),
    repo_dir: str = "",
    preexisting: tuple[str, ...] = (),
) -> DocumentationGate:
    """Fail-closed conformance and direct-grounding gate over one story's OKF update."""
    docs_root = Path(find_docs_root(docs_path, repo_dir))
    spec = Path(spec_dir)
    spec_root = spec if spec.is_absolute() else docs_root / spec
    nodes = [str(node) for node in author_nodes]
    inherited = untouched_since(docs_root.resolve(), tuple(preexisting))

    problems: list[str] = []
    failures: list[str] = []
    if author_status not in {"documented", "not_required"}:
        problems.append(f"documentation author status is {author_status!r}")
        failures.append("S:author-status")
    if context_mode == "local" and build_status != "passed":
        problems.append("diff-to-OKF context generation did not pass")
        failures.append("S:context-build")
    if context_mode == "local" and validation_status != "passed":
        problems.append("diff-to-OKF context validation did not pass")
        failures.append("S:context-validate")

    packet: dict[str, Any] = {}
    if context_mode == "local":
        packet_path = spec_root / CONTEXT_FILE
        loaded = load_json(packet_path, CONTEXT_FILE, logger)
        if isinstance(loaded, dict) and loaded:
            packet = loaded
        else:
            problems.append(f"cannot read {packet_path}")
            failures.append("S:packet-unreadable")

    ungrounded = ungrounded_refs(packet, inherited)
    if ungrounded:
        problems.append(
            f"{len(ungrounded)} changed production symbol(s) are not directly grounded. "
            "Add a `code:` bullet naming each of these exactly as written here: "
            + ", ".join(ungrounded)
        )
        failures.extend(f"G:{ref}" for ref in ungrounded)

    okf = Ostler(docs_root)
    outcome = okf.doctor()
    report = outcome.data
    if outcome.status == "invalid":
        problems.append(f"ostler {outcome.message}")
        failures.append("S:doctor-unavailable")
    affected = _affected_doc_nodes(packet, nodes)
    touched = story_touched_lines(
        docs_root.resolve(), {node for node in affected if "#" not in node}, logger
    )
    doctor_errors = [
        finding
        for finding in report.get("findings", [])
        if isinstance(finding, dict)
        and finding.get("severity") == "error"
        and not (context_mode == "semantic" and finding.get("code") in SEMANTIC_SUPPRESSED)
        and _finding_affects_nodes(okf.graph, finding, affected, touched)
    ]
    if doctor_errors:
        note = _doctor_errors_note(doctor_errors)
        spilled = (
            _spill_doctor_errors(spec_root, note, logger)
            if len(note) > MAX_PROMPT_NOTE_CHARS
            else None
        )
        if spilled is not None:
            note = (
                f"{len(doctor_errors)} doctor errors affect this story's nodes; the full "
                f"list is in `{spilled}`. Read it, repair every one, and re-run "
                "`ostler doctor` yourself until the affected nodes are clean."
            )
        else:
            _clear_doctor_errors(spec_root)
        problems.append(note)
        failures.extend(
            f"E:{item.get('path') or item.get('ref') or '<graph>'}:"
            f"{item.get('line') or 0}:{item.get('code', '?')}"
            for item in doctor_errors
        )
    else:
        _clear_doctor_errors(spec_root)

    changed = len(packet.get("changedCode", []))
    if problems:
        notes = "; ".join(problems)
        logger.warning("story documentation invalid: %s", notes)
        return DocumentationGate(
            status="invalid",
            notes=notes,
            changed_code_count=changed,
            doctor_error_count=len(doctor_errors),
            failures=failures,
        )
    notes = (
        f"Affected documentation is conformant; {changed} changed production unit(s) have "
        "direct OKF grounding."
    )
    logger.info(notes)
    return DocumentationGate(status="passed", notes=notes, changed_code_count=changed)


@blueprint.node
def documentation_obligations(
    logger: logging.Logger,
    docs_path: str = "",
    spec_dir: str = "",
    context_mode: str = "local",
    build_status: str = "",
    repo_dir: str = "",
    preexisting: tuple[str, ...] = (),
) -> DocumentationObligations:
    """The grounding worklist, computed *before* the author turn rather than after it."""
    if context_mode != "local":
        return DocumentationObligations(
            notes="semantic mode: no diff packet, so no deterministic worklist"
        )
    docs_root = Path(find_docs_root(docs_path, repo_dir))
    spec = Path(spec_dir)
    packet_path = (spec if spec.is_absolute() else docs_root / spec) / CONTEXT_FILE
    packet = load_json(packet_path, CONTEXT_FILE, logger)
    if not packet:
        return DocumentationObligations(notes=f"cannot read {packet_path}")
    refs = ungrounded_refs(packet, untouched_since(docs_root.resolve(), tuple(preexisting)))
    logger.info(
        "%d changed production reference(s) are not grounded yet", len(refs),
        extra={"activity": True},
    )
    build = f"; context build reported {build_status!r}" if build_status else ""
    return DocumentationObligations(
        refs=refs,
        notes=f"{len(refs)} ungrounded reference(s) from {len(packet.get('changedCode', []))} "
        f"changed production unit(s){build}",
    )


def features_root(flow: Workflow) -> str:
    """Where the OKF feature docs live, as `detect_okf_docs` resolved it in `setup`."""
    return flow.output(detect_okf_docs).features_root


__all__ = [
    "classify_documentation_context",
    "detect_okf_docs",
    "documentation_obligations",
    "features_root",
    "ungrounded_refs",
    "verify_story_documentation",
]
