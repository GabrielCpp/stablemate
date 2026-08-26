"""The docs flow's deterministic work: is there a book, how do we read the diff, does it hold.

Ports `detect-okf-docs.py`, `classify-documentation-context.py` and
`verify-story-documentation.py`. The `emit(...)`/`sys.exit(0)` pairs become returned models
and the JSON-encoded `source_roots` becomes a `list[str]`; nothing else changes.

`verify_story_documentation` is the load-bearing one and the reason the flow exists in this
shape. A documentation author can claim it documented a story without touching the OKF nodes
the diff actually implicated, and no prompt mandate catches that. This does: it takes the
diff-to-OKF packet the builder wrote, and for every changed production unit demands *direct*
grounding — an exact `path::symbol` reason, or file ownership when the change carried no
symbols. A unit covered only by a broad surface owner is a documentation gap, not coverage.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from git.exc import GitError
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
from workhorse_workflows.kit import open_repo

#: Where the diff-to-OKF obligation packet lands, relative to the story's spec dir.
CONTEXT_FILE = "qa-okf-context.json"

#: Files whose presence means "this repo is managed by an OKF graph". An `ostler*` file is
#: conclusive on sight; an `agents.yml` counts only when it carries an `organization` block,
#: since every repo the coder touches has one of those for unrelated reasons.
CONFIG_FILES = ("ostler.yml", "ostler.yaml", "agents.yml", ".agents.yml")

#: Doc kinds whose *directory existing* means the same thing without any configuration at
#: all. Named by kind rather than by path so the probe follows a repo that moved them:
#: `ostler.path` turns each into the directory this repo actually configures.
MANAGED_KINDS = ("epics", "features")

#: The reason kinds that make a doc node *directly* implicated by the diff, as opposed to
#: implicated through the surface it happens to sit under.
DIRECT_KINDS = {"changed-code", "file-owner", "surface-owner"}

#: Doctor codes suppressed in semantic mode: without a local worktree there is no diff to
#: resolve a code reference against, so a dangling one is the mode's normal state.
SEMANTIC_SUPPRESSED = {"dangling-code-ref", "missing-code-symbol"}

#: Above this many characters a rendered note stops being a prompt and starts being a file.
#: The gate spills the doctor-error list to `DOCTOR_ERRORS_FILE` and points at it instead of
#: dropping errors, so the repair turn always has the whole set; `docs.flow._prompt_note` is
#: the backstop for a note that reaches it oversized anyway.
MAX_PROMPT_NOTE_CHARS = 12000

#: Where an over-long doctor-error list lands, relative to the story's spec dir.
DOCTOR_ERRORS_FILE = "doctor-errors.txt"

# One malformed pattern can mint dozens of findings whose messages are long. Truncating the
# *message* keeps every error on the list; truncating the list would not.
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
    """Whether *ref* is grounded outright, or by a declaration that lexically encloses it.

    A qualified symbol — `useTransientValue.timerRef`, `Outer.inner`, `Panel.render` — names
    something *inside* a unit the book can document. Requiring a `code:` bullet per nested
    name is a demand no book can meet, because the nested name has no documentable surface
    of its own: the author would be writing a bullet for a local variable. Grounding the
    owner is the honest claim, and it is a strictly stronger one — it says what the enclosing
    unit now does, which is what a change to its body actually altered.

    The walk is over the ancestors the qualified name already encodes, so it needs no view of
    the syntax tree and no per-language rule. One consequence worth naming: Go spells a
    value-receiver method `Owner.Method`, which is dotted without being nested, so grounding
    the type will satisfy its methods. Pointer receivers (`(*Owner).Method`) do not roll up,
    since no book ref is spelled `(*Owner)`.
    """
    path, _, symbol = ref.partition("::")
    parts = symbol.split(".")
    return any(f"{path}::{'.'.join(parts[:depth])}" in exact for depth in range(1, len(parts) + 1))


def ungrounded_refs(packet: dict[str, Any], inherited: set[str]) -> list[str]:
    """The changed production references the book does not directly own yet.

    The gate's arithmetic, lifted out of the gate so the *author* can be handed the same
    list before it writes anything. Both callers must compute it identically: an author
    told one set and failed against another is the loop this list exists to end. It is
    also why nothing here re-derives the packet — one mapper, one join, two readers.

    `inherited` is `untouched_since`'s verdict: paths already dirty at story start whose
    bytes have not moved, which this story is not charged for.
    """
    exactly_grounded, file_grounded = _grounded_paths(packet)
    ungrounded: list[str] = []
    for change in packet.get("changedCode", []):
        if not isinstance(change, dict):
            continue
        if change.get("status") == "deleted":
            # Documenting the absence of something is not documentation — a deletion is
            # satisfied on its own, with no `code:` bullet required. Mirrors
            # `ostler.qa.context`'s `mapped = change.status == "deleted"`.
            continue
        base_path = str(change.get("basePath", ""))
        head_path = str(change.get("headPath", ""))
        candidates = {str(change.get("path", "")), base_path, head_path} - {""}
        if candidates and candidates <= inherited:
            # Every name this change goes by was already dirty at story start and has not
            # moved since — another story's abandoned work, not this one's.
            continue
        base_symbols = set(change.get("baseSymbols", []))
        head_symbols = set(change.get("headSymbols", []))
        required = {
            *(f"{base_path}::{symbol}" for symbol in base_symbols if base_path),
            *(f"{head_path}::{symbol}" for symbol in head_symbols if head_path),
        }
        if base_symbols | head_symbols:
            ungrounded.extend(
                sorted(ref for ref in required if not _is_grounded(ref, exactly_grounded))
            )
        elif candidates.isdisjoint(
            {ref.partition("::")[0] for ref in exactly_grounded} | file_grounded
        ):
            ungrounded.append(str(change.get("path", "<unknown>")))
    return ungrounded


def _affected_doc_nodes(packet: dict[str, Any], author_nodes: list[str]) -> set[str]:
    """Every doc node this story touched: what the diff implicated, plus what the author said.

    The union is deliberate. The packet knows what the code changed and the author knows what
    it *meant*, and a doctor error on either is this story's problem.
    """
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
    """Which lines of each doc file this story's own edits landed on.

    The story's doc work is what stands between `HEAD` and the worktree, the same contract
    `snapshot_worktree_state` documents. `None` for a path means *undecidable* — git could
    not be read, or the file is untracked and therefore new in its entirety — and every
    consumer here reads `None` as "charge the story for all of it".
    """
    unknown: dict[str, set[int] | None] = {path: None for path in paths}
    if not paths:
        return {}
    try:
        repo = open_repo(root)
        base = Path(str(repo.working_tree_dir)).resolve()
        rels = {(root / path).resolve().relative_to(base).as_posix(): path for path in paths}
        untracked = set(repo.untracked_files)
        tracked = sorted(rel for rel in rels if rel not in untracked)
        diff = repo.git.diff("-U0", "HEAD", "--", *tracked) if tracked else ""
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
        # `@@ -a,b +c,d @@` — only the post-image range matters, since a finding is reported
        # against the file as it stands now. A pure deletion has `d == 0`; it moved no line
        # the doctor can be looking at, so it contributes nothing.
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
    """Does this doctor finding land on a node this story is responsible for?

    What keeps the gate from failing a story for pre-existing errors elsewhere in the book.
    A finding with no line is attributed to the whole file; one with a line is attributed to
    the innermost UI node that starts at or above it, and then up its parent chain — because
    a finding inside a child node is a finding against every node that contains it.

    A *file* named as affected used to absorb every finding in it, which is how a story that
    edited four bullets near the top of a long document was charged with a `missing-placement`
    on a dialog 250 lines below that it had never read. So a bare file grants ownership only
    of the anchors this story's own edits actually reached: `touched` carries the lines it
    moved, and an anchor is this story's when one of them falls inside its span. Naming an
    anchor outright still owns it whatever the diff says — the author's word is the stronger
    claim, and the packet's own nodes come in the same way.

    Undecidable cases resolve to `True`, including a `touched` this function was not given.
    This gate is fail-closed: a finding it cannot place is a finding it does not get to
    dismiss.
    """
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
    """Every affected doctor error, one per line, with nothing omitted.

    This used to hand over the first twelve and tell the turn to "rerun the gate for the
    next batch", which is a loop by construction: a story with 124 findings of one shape
    cost ten laps to clear a list one turn could have walked. The repair prompt now owns
    the iteration — it re-runs `ostler doctor` itself until the affected nodes are clean —
    and that only works if it is holding the whole set.
    """
    return "ostler doctor errors:\n" + "\n".join(
        _doctor_error_note(item) for item in doctor_errors
    )


def _spill_doctor_errors(spec_root: Path, note: str, logger: logging.Logger) -> Path | None:
    """Write the full error list beside the story's spec, so the note can just point at it.

    Overwritten every pass: the file is this pass's reading, and a stale one read as current
    is worse than none. Returns `None` when it could not be written, and then the caller
    keeps the inline note — an oversized prompt is survivable, a silently shortened worklist
    is not.
    """
    path = spec_root / DOCTOR_ERRORS_FILE
    try:
        spec_root.mkdir(parents=True, exist_ok=True)
        path.write_text(note + "\n", encoding="utf-8")
    except OSError as exc:
        logger.info("could not write %s (%s)", path, exc)
        return None
    return path


def _clear_doctor_errors(spec_root: Path, logger: logging.Logger) -> None:
    """Remove a previous pass's spill file, so nothing points at a list that no longer holds."""
    try:
        (spec_root / DOCTOR_ERRORS_FILE).unlink(missing_ok=True)
    except OSError as exc:
        logger.info("could not remove %s (%s)", spec_root / DOCTOR_ERRORS_FILE, exc)


@blueprint.node
def detect_okf_docs(
    logger: logging.Logger,
    docs_path: str = "",
    features_subdir: str = "",
    repo_dir: str = "",
) -> OkfDetection:
    """Are this run's docs managed by an OKF graph, so documenting the story means anything?

    The cheap pre-gate in front of an agent turn. The coder runs against many repos and most
    do not use ostler; `yes` needs both a sign the repo is managed — a config file, or one of
    the trees ostler owns — and a graph that actually loads. Everything semantic (which
    surfaces the story touched, whether it touched any) is the author's.
    """
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
    """Deterministic local diff mapping, or semantic multi-repo review?

    `local` needs every affected source root to live inside the docs repo's own git worktree,
    because that is the only case where a diff can be mapped onto the graph mechanically. One
    root outside it — or a docs root that is not a worktree at all — and the mapping would be
    partial, which is worse than absent: it would ground some changed units and silently
    leave the rest unchecked. So the whole gate falls back to doctor plus an independent
    review turn instead.

    The returned roots are re-expressed relative to the worktree, which is what
    `ostler qa context` wants.
    """
    docs_root = Path(find_docs_root(docs_path, repo_dir)).resolve()
    try:
        # A bare repo has no working tree at all, and that is the same answer as "not a
        # worktree" below — stated here rather than arriving as a `TypeError` from `Path`.
        working_dir = open_repo(docs_root).working_tree_dir
        worktree = Path(working_dir).resolve() if working_dir else None
    except (GitError, OSError, TypeError, ValueError, RuntimeError):
        worktree = None

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
    author_status: str = "blocked",
    build_status: str = "invalid",
    validation_status: str = "invalid",
    context_mode: str = "local",
    author_nodes: tuple[str, ...] = (),
    repo_dir: str = "",
    preexisting: tuple[str, ...] = (),
) -> DocumentationGate:
    """Fail-closed conformance and direct-grounding gate over one story's OKF update.

    Four things have to hold, and every failure is collected rather than short-circuited so
    the author's rework brief names all of them at once:

    1. the author reports `documented` or `not_required`, and a `documented` claim names the
       nodes it touched;
    2. in local mode, the packet was built and validated;
    3. every changed production unit in the packet is *directly* grounded — its symbols
       carry exact `path::symbol` reasons, or the file itself is owned. Broad surface
       ownership is not coverage, and this is the check the whole gate exists for. It
       reports the ungrounded **references**, since those are what it tests and what the
       author must write back verbatim;
    4. `ostler doctor` reports no errors on any node this story affected — the anchors it
       named, and in a file it named bare, the anchors its own edits reached. See
       `_finding_affects_nodes` for why that last clause is not a loosening.

    `preexisting` is `snapshot_worktree_state`'s reading from before the story's first dev
    turn. Paths in it that still hold the same bytes were somebody else's uncommitted work
    the whole time, so point 3 does not charge this story for them; see `untouched_since`
    for why that subtraction is safe in only one direction.
    """
    docs_root = Path(find_docs_root(docs_path, repo_dir))
    spec = Path(spec_dir)
    spec_root = spec if spec.is_absolute() else docs_root / spec
    nodes = [str(node) for node in author_nodes]
    inherited = untouched_since(docs_root.resolve(), tuple(preexisting))

    problems: list[str] = []
    # The same statement as `problems`, one stable identity per discrete failure. `problems`
    # is prose addressed to the author and its wording is load-bearing; this is the form a
    # later pass can be compared against, which is what turns "three reworks" into "three
    # reworks that closed nothing". Nothing branches on it.
    failures: list[str] = []
    if author_status not in {"documented", "not_required"}:
        problems.append(f"documentation author status is {author_status!r}")
        failures.append("S:author-status")
    if author_status == "documented" and not nodes:
        problems.append("documentation author did not identify affected OKF nodes")
        failures.append("S:author-nodes")
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
        # The *references*, not the files they live in. This gate checks symbols but used
        # to report paths, which made it a loop the author could not exit: it burned every
        # rework pass adding plausible bullets to a file that was already half-grounded,
        # was told the same eight filenames each time, and failed with the same complaint.
        # Naming the missing refs also settles their spelling, which is the other half of
        # the trap — ostler's inventory writes a Go method as `(*Type).Method`, an author
        # writing the natural `Type.Method` grounds nothing, and nothing in a path-level
        # message could ever have revealed that.
        problems.append(
            f"{len(ungrounded)} changed production symbol(s) are not directly grounded. "
            "Add a `code:` bullet naming each of these exactly as written here: "
            + ", ".join(ungrounded)
        )
        # One per reference, verbatim: these identities are the inventory's own spelling
        # and are stable across passes, so comparing two passes' sets is exact here.
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
    # A book that would not load reports no findings, so the comprehension never reaches
    # `okf.graph` — the one call below that would raise the failure a second time.
    doctor_errors = [
        finding
        for finding in report.get("findings", [])
        if isinstance(finding, dict)
        and finding.get("severity") == "error"
        and not (context_mode == "semantic" and finding.get("code") in SEMANTIC_SUPPRESSED)
        and _finding_affects_nodes(okf.graph, finding, affected, touched)
    ]
    if doctor_errors:
        # `suggestion` carries the expected form — the literal bullet the checker would
        # accept — and dropping it left the author to infer a grammar from a complaint about
        # the value it rejected. That is the same trap the ungrounded-symbol message above
        # was widened to escape: a `placement:` bullet was refused twice for prose the
        # message never said was disallowed, while the checker's own
        # `- placement: width 60-100%, x 0-20%` sat unrendered in the finding.
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
            _clear_doctor_errors(spec_root, logger)
        problems.append(note)
        # The message is excluded from the identity on purpose: a doctor error whose prose
        # was reworded is the same defect, and a pass that only changed the wording did not
        # buy anything.
        failures.extend(
            f"E:{item.get('path') or item.get('ref') or '<graph>'}:"
            f"{item.get('line') or 0}:{item.get('code', '?')}"
            for item in doctor_errors
        )
    else:
        _clear_doctor_errors(spec_root, logger)

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
    """The grounding worklist, computed *before* the author turn rather than after it.

    The gate below already derives this list; handing it to the author up front is what
    stops the author deriving it again by hand. It did: a documentation turn was observed
    spending 128 shell calls grepping the book for every changed exported symbol — the
    exact join `ungrounded_refs` computes in one pass over a packet that was already on
    disk. The agent's version is also worse than redundant, because it guesses the
    spelling of a reference the inventory owns.

    Advisory only. Nothing branches on it and a mode or packet it cannot read returns an
    empty list with the reason attached — the gate is still the authority on whether the
    grounding holds, and a worklist that could not be computed must not read as "nothing
    to ground".

    `build_status` is context in `notes`, never a bail-out, for the reason the gate reads
    the packet unconditionally too: `ostler qa context` returns `invalid` precisely when the
    diff carries changes the book does not map yet, which is the case this worklist exists
    to serve. Refusing on it would blank the list exactly when it has something to say.
    """
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
    """Where the OKF feature docs live, as `detect_okf_docs` resolved it in `setup`.

    Read back off the recorded output rather than threaded, so the two lanes that render it
    into a prompt cannot disagree with the detection the run already made.
    """
    return flow.output(detect_okf_docs).features_root


__all__ = [
    "classify_documentation_context",
    "detect_okf_docs",
    "documentation_obligations",
    "features_root",
    "ungrounded_refs",
    "verify_story_documentation",
]
