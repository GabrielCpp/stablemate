"""Deterministic changed-code to OKF obligation mapping."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from unidiff.patch import PatchSet
from unidiff.errors import UnidiffParseError

from ostler import graph as graph_mod
from ostler import locators as locators_mod
from ostler import acts as acts_mod
from ostler import checks as checks_mod
from ostler import inventory, markdown, path as path_mod, refs as refs_mod, registry, syntax
from ostler.model import Graph, _parse_ui_nodes, load
from ostler import reach
from ostler import routes as routes_mod
from ostler.qa import captures as captures_mod
from ostler.qa import fixtures as fixtures_mod
from ostler.qa.compile import annotate_deferred_obligations
from ostler.qa.outcome import QaOutcome
from ostler.qa.source_context import SourceRepository
from ostler.source_snapshots import source_fingerprint

#: The last-resort declaration shape, for a language with no parser and no entry in
#: `inventory` — and for a Python file `ast` could not read. Declared in
#: `.agent-checks.toml` for that reason: it is the fallback, never the first answer.
_SYMBOL_RE = re.compile(
    r"^\s*(?:async\s+)?(?:def|class|function|func|fn)\s+([A-Za-z_$][\w$]*)"
    r"|^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*="
)
_AC_RE = re.compile(r"^(?:AC\s*)?(\d+)\s*[:.)-]\s*(.+)$", re.IGNORECASE)
#: The file suffixes a `tests:` bullet may cite. A membership test, not an alternation baked
#: into a pattern: `Path.suffix` already knows where a suffix begins, and the set is the whole
#: of what this reader needs to decide.
#:
#: This used to read `verify:`, back when a node's declared verification *was* the name of a
#: test. It is not: `verify:` now declares the observation that fulfils the node's obligations
#: (`ostler.checks`), and a test citation moved to `tests:`, which mints no obligation and is
#: read by one consumer — the regression node's failure attribution, which needs a test path
#: and can do nothing with an observation.
_CITABLE_SUFFIXES = frozenset(
    f".{ext}"
    for ext in (
        "py tsx ts jsx js go mjs cjs yaml yml dart java kt kts rs sh bash sql rb php cs swift"
        " feature"
    ).split()
)

#: How many nodes must cite one `code:` symbol before the citation stops localizing the
#: change. Two nodes citing one symbol is a well-written book, not a fan-out — an endpoint
#: documenting the wire contract and a concept documenting the domain rule, both honestly
#: grounded in the one function that implements them. Both are at risk when it changes, and
#: demoting them left a story whose only changed file was that symbol owing nothing at all.
#: What the demotion is for is the container: the page component every panel is documented
#: against, where adding one control marked a dozen unrelated claims changed.
_CONTAINER_FANOUT = 3

#: Bullets the relation fixpoint joins nodes on. A node naming the same consistency group,
#: persistence store, event or idempotency key as an already-selected node is pulled in.
RELATION_KEYS = (
    "consistency",
    "consistency rule",
    "consistency group",
    "persistence",
    "event",
    "concurrency",
    "idempotency",
)

#: The reason kind the fixpoint stamps for each of those bullets.
_RELATION_REASON_KINDS = frozenset(key.replace(" ", "-") for key in RELATION_KEYS)

#: Bullets naming an event by name rather than describing an invariant. Their whole value is
#: already the subject, so they pool with the parsed subjects below and an emitter joins its
#: consumer without either bullet being rewritten.
_EVENT_KEYS = ("emits", "consumes")

#: The optional leading identifier on a relation bullet: `booking-record — a confirmed booking
#: is written through the ledger`. Two nodes are talking about the same record when they name
#: it, and prose alone never says so — every `persistence:` value in the benchmark corpus is a
#: unique sentence, so an equality join over the prose matches nothing and the relation rules
#: are silently inert. The head shape is narrow (lowercase identifier, em dash, space either
#: side) so an existing sentence cannot claim a subject by accident; a value without one has
#: none and joins nothing, which is today's behaviour made explicit rather than incidental.
#: What a node reached only by the one-hop rule is owed live evidence for: the bullets naming
#: the thing it shares — the record, the event, the lock — and nothing else. Its node-level
#: contract is owed alongside these, minted apart from them.
_SHARED_INVARIANT_KEYS = frozenset(RELATION_KEYS) | frozenset(_EVENT_KEYS)

_RELATION_SUBJECT_RE = re.compile(r"^([a-z0-9][a-z0-9._-]*)\s+—\s+(\S.*)$", re.DOTALL)

#: How many nodes one relation subject may bind before it is worth a look. Warned about, never
#: capped: a record legitimately shared by five screens is legitimately owed by all five, and a
#: silent cap would report full coverage of a set it had quietly trimmed. What a large count
#: usually means is a subject named too broadly — `database` rather than the record.
_RELATION_FANOUT = 6

#: Reason kinds that reach a node *navigationally* — by containment or by a graph link —
#: and so say nothing about whether the change can break it. Being the parent of a touched
#: node, or a flow that routes through one, is not a way to be broken by it: a single edited
#: file otherwise drags in every flow that links to every contract it owns. A node held
#: solely by these stays in the packet as context and is not owed live evidence.
_CLOSURE_REASON_KINDS = frozenset(
    {
        "contains-impacted-node",
        "flow-links-contract",
        "flow-contract-closure",
        "graph-closure",
        "judgment-context",
    }
)

#: Reason kinds that reach a node by *co-binding*: it names the same consistency group,
#: persistence subject, event or idempotency key as a node already selected. Unlike the
#: navigational kinds above, this is real relatedness — those bullets are the invariants a
#: change breaks when a story is split, and the node holding one is exactly the screen
#: nobody re-proved.
#:
#: They are still context-only *here*, and the reason is the fixpoint below (`while
#: related:`) rather than relatedness as such. That loop recomputes its selection every lap,
#: so one shared subject chains transitively across a whole persistence island: a
#: seven-criterion story came out owing live proof across sixty-seven documents, 194 of its
#: obligations held by `event-consumer` alone. What is owed instead is one hop — see
#: `_relation_owed`, which joins from the *required* set rather than from the closure and
#: stamps `relation-of-required`, a kind deliberately in neither of these two sets.
_COBINDING_REASON_KINDS = frozenset({"event-consumer", "event-producer"}) | _RELATION_REASON_KINDS

#: What `_is_required` subtracts: reach that is not, on its own, evidence the change can
#: break the node.
_CONTEXT_ONLY_REASON_KINDS = _CLOSURE_REASON_KINDS | _COBINDING_REASON_KINDS

#: Bullets that name how to address a node in a running UI. Lifted onto the obligation so a
#: planner writing a browser locator reads them there rather than re-deriving them from the
#: sibling `role:`/`name:` obligations it happens to have been handed.
#:
#: `states`, `exclusive-with`, `on`, `trigger` and `does` are carried verbatim and uninterpreted
#: alongside the original set — the book's grammar for partitioning a screen's `visible(...)`
#: bullets into more than one compiled scenario (a component present only in a named
#: arrangement, a pair that can never share a scenario, and an `## Interactions` row's subject/
#: action/destination). `compile.py` reads these to partition; nothing here interprets them.
#:
#: Derived from `BulletKey.locator`, not a second hand-maintained tuple: a key that is a locator
#: on one type and something else on another (`selector:` also names how an `environment` is
#: chosen) is still read correctly, because `_locators` below filters by the node's own declared
#: keys before it ever consults this set.
_LOCATOR_KEYS = tuple(sorted(registry.LOCATOR_KEYS))
#: Bullet key to packet key, for the few whose bullet spelling (a markdown-hyphen convention)
#: is not a legal identifier a compiled plan would want to spell as a dict key.
_LOCATOR_KEY_RENAME = {"exclusive-with": "exclusiveWith"}


def _sort_key(obligation_id: str) -> list[tuple[int, int | str]]:
    """Order obligation ids so `…:raises:10` follows `…:raises:2`.

    The trailing `:{index}` a value-level obligation carries is a number, and sorting the
    id as one string puts the tenth case between the first and the second. That is only
    cosmetic until a bullet packs enough cases to reach ten — then the packet a planner
    reads presents them out of order, and a reviewer citing "the third case" means a
    different obligation than the planner counted.
    """
    return [(1, int(part)) if part.isdigit() else (0, part) for part in obligation_id.split(":")]


@dataclass(frozen=True)
class ChangedUnit:
    path: str
    base_path: str
    head_path: str
    status: str
    base_lines: tuple[int, ...]
    head_lines: tuple[int, ...]
    base_symbols: tuple[str, ...]
    head_symbols: tuple[str, ...]
    repository: str = ""
    surface: str = ""
    source_root: str = ""


def _source_ref(repository: str, path: str, symbol: str = "") -> str:
    return refs_mod.render_code_ref(refs_mod.CodeRef(repository, path, symbol))


def _ref_owns_change(value: str, change: ChangedUnit) -> bool:
    """Whether one owning citation names either side of a changed source file."""
    try:
        cited = refs_mod.parse_code_ref(value)
    except ValueError:
        return False
    return (
        cited.repository == change.repository
        and cited.path in {change.base_path, change.head_path}
    )


def _book_root(root: Path, features_root: str) -> str:
    """The book's own root, relative to *root*, when `--features-root` names a nested book.

    The derivation lives in `path.book_prefix_in`, which carries the reasoning: the same
    fact the runbook reader needs to resolve a `working-directory: .` against the system a
    book describes rather than against the checkout it was read from.

    `--source-root` is deliberately kept out of this: its job is attribution for
    `_surface_owner`, and bending it into a rebase target would make a book's portability
    depend on the caller repeating a mapping the book already implies.
    """
    return path_mod.book_prefix_in(root, features_root)


def book_files(root: Path, features_root: str) -> list[dict[str, str]]:
    """Every `*.md` file under the book at *features_root*, with its path and sha256.

    Paths are relative to the book directory (`root / features_root`) and the list is
    sorted, so two runs against the same tree agree byte-for-byte. This is the evidence
    `qa/plan.py`'s book-drift check recomputes against: it diffs the recorded list here
    against a fresh call on the current tree and names exactly which files moved.
    """
    book_dir = root / features_root if features_root else root
    files: list[dict[str, str]] = []
    if not book_dir.is_dir():
        return files
    for path in book_dir.rglob("*.md"):
        if not path.is_file():
            continue
        rel = path.relative_to(book_dir).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append({"path": rel, "sha256": digest})
    files.sort(key=lambda item: item["path"])
    return files


def story_file_record(root: Path, story_file: Path | None) -> dict[str, str] | None:
    """The packet's record of the story file its `story` and `acceptanceCriteria` keys were
    derived from — `None` when there was no story file to derive them from.

    `qa/plan.py` recomputes this at validate time the same way it recomputes `bookFiles`: it
    hashes the file named here again and refuses a packet whose story moved underneath it,
    because `acceptanceCriteria` is load-bearing in validate and a stale set would otherwise
    be graded against silently.
    """
    if story_file is None or not story_file.is_file():
        return None
    try:
        rel = story_file.resolve().relative_to(root).as_posix()
    except ValueError:
        rel = story_file.resolve().as_posix()
    digest = hashlib.sha256(story_file.read_bytes()).hexdigest()
    return {"path": rel, "sha256": digest}


def _book_relative(path: str, book_root: str) -> str:
    """*path* (relative to `root`) rebased onto `book_root`; unchanged outside it."""
    if not book_root or not path:
        return path
    prefix = f"{book_root}/"
    return path[len(prefix):] if path.startswith(prefix) else path


def _matching_refs(refs: set[str], cited: list[str]) -> list[str]:
    """Citations in *cited* that name something in *refs*, tolerant of symbol spelling.

    A citation and an extracted symbol may spell a qualified method differently — Go's
    `(*Server).handleCreate` next to a book's `Server.handleCreate` — so the symbol halves
    are compared part-wise via :func:`ostler.inventory.symbol_parts`, the same tolerance
    grounding already applies. The citation's own spelling is reported: the book's grammar
    wins over whatever the front end happens to emit.
    """
    parsed_refs = []
    for value in refs:
        try:
            parsed_refs.append(refs_mod.parse_code_ref(value))
        except ValueError:
            continue
    matches: list[str] = []
    for value in cited:
        try:
            citation = refs_mod.parse_code_ref(value)
        except ValueError:
            continue
        if any(
            citation.repository == ref.repository
            and citation.path == ref.path
            and inventory.symbol_parts(citation.symbol) == inventory.symbol_parts(ref.symbol)
            for ref in parsed_refs
        ):
            matches.append(value)
    return sorted(dict.fromkeys(matches))


#: The git empty-tree object, present in every repository without needing a commit —
#: diffing against it is how `book_context` reads every currently-grounded node as
#: directly reached, with no real revision required on either side.
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def book_context(
    root: Path,
    *,
    source_roots: dict[str, list[str]] | None = None,
    features_root: str = "",
    repositories: Sequence[SourceRepository] = (),
) -> dict[str, Any]:
    """Every obligation the book currently owns — no story, no diff, nothing to be proportional to.

    `build_context` maps a `base..head` code diff onto the graph so a story's packet stays
    proportional to what that story touched; that is the right shape when a story exists.
    A book documenting an already-existing app with no authored story has no diff to be
    proportional to, and "book is plan source" (measured against a real book, see
    `audit_one_spec`) means the book's own current content is what a live audit owes
    evidence for, not nothing.

    This is `build_context` against `EMPTY_TREE_SHA..WORKTREE`: every path the book cites
    reads as freshly added, so every grounded node the diff-directness test in `_is_required`
    already applies is required exactly as if the whole tree had just been written — which,
    from "no prior story reached it", it structurally has. No new obligation-selection logic
    is added; this only supplies the diff endpoints a whole-book scan has none of otherwise.
    """
    return build_context(
        root,
        base=EMPTY_TREE_SHA,
        head="WORKTREE",
        source_roots=source_roots,
        features_root=features_root,
        repositories=repositories,
    )


def _navigation(head_graph: Graph) -> dict[str, dict[str, Any]]:
    """Every surface's derived screen reachability, keyed by surface (Option C, Amendment 1).

    Computed once at context-build time from `reach.py`'s existing navigation-derivation
    logic — `compile.py` reads this section rather than calling `reach` or touching a live
    `Graph` itself. Surface-keyed even for a single-surface book: `{surface: reachability(...)}`
    with exactly one key is not a special case, it is the general shape with one entry.

    A surface with no screen nodes gets a zeroed-out stub instead of a `reach.reachability`
    call, because that call requires a root screen to start from and a screen-less surface
    (a pure HTTP/CLI surface) has none — that is not a finding, it is a surface this compiler
    does not address by navigation at all (Condition 1). A surface *with* screens but no
    resolvable root (`reach.UnknownStart` — no screen's `route:` is the root path) is a real
    book gap, reported as every one of that surface's screens being unreachable rather than
    raised as an exception that would take context-building down with it.

    Every entry also carries `entryUrl` — the surface's `scheme://host[:port]`, read off its
    `server`/`runbook` nodes by `reach.entry_origin` — for `compile.py` to resolve a `target(...)`'s
    `base_url` from the book instead of one CLI flag applied to every surface alike. A book whose
    sources disagree (`reach.ConflictingEntryOrigin`) does not fail context-building either: `entryUrl`
    stays `None` and the conflict is recorded under `entryUrlError`, the same shape `UnknownStart`
    already gets. `entryUrlError` is read: `compile.py` gaps that surface `conflicting-entry-origin`
    rather than falling back to `--base-url`, which answers a book stating no address and does not
    adjudicate between two the book does state. Doctor reports it against the surface as well.

    Every entry also carries `driver` — the driver of the runbook that exercises this surface
    (§4.1's D1), read off its `runbook` node(s) by `reach.surface_driver` — for `compile.py`'s
    dispatch table to key on "who performs this step" instead of inferring it from which check
    a `does:` bullet happens to declare. Several runbooks naming the same surface through
    `surfaces:` with different `driver:` values is normal, not a defect — a lint runbook and a
    browser runbook and an IaC runbook can all be correct about the same surface — so the one
    that stands for the surface is the one marked `walkthrough: true`, the same way `root_path`
    picks a server; a sole runbook stands in for it unmarked. A book with no runbook covering the
    surface leaves `driver` `None` with no error recorded. A book with several runbooks and none
    marked (`reach.UndeclaredWalkthroughRunbook`), or with several *marked* runbooks that still
    disagree (`reach.ConflictingSurfaceDriver`), also leaves `driver` `None`, and records why
    under `driverError` — the same shape `entryUrlError` already gets — plus which of the two
    under `driverErrorKind` (`"undeclared-walkthrough-runbook"` or `"conflicting-surface-driver"`),
    so `compile.py` and the doctor can tell the two apart. A step whose driver the book does not
    determine is not defaulted, it becomes a gap.

    Every entry also carries `bundleId` — the mobile package/bundle id of the runbook that
    exercises this surface, read off its `runbook` node(s) by `reach.surface_bundle_id` the same
    way `driver` is — for `compile.py` to address a Maestro flow's real app instead of a
    placeholder. A book with no runbook stating one leaves `bundleId` `None` with no error
    recorded; several unmarked runbooks that disagree, or several *marked* ones that still
    disagree, also leave it `None` and record why under `bundleIdError` plus which of the two
    under `bundleIdErrorKind` (`"undeclared-walkthrough-runbook"` or
    `"conflicting-surface-bundle-id"`), the same shape `driverError`/`driverErrorKind` already get.

    Every entry also carries `launchScreen` — the screen `launch-screen:` names on the runbook
    that exercises this surface, read off it by `reach.surface_launch_screen` the same way
    `bundleId` is — for `compile.py` to know which screen a cold `launchApp` actually opens on,
    since Maestro's own `- launchApp` names no screen and the book otherwise has no way to say
    one. A book with no runbook stating one leaves `launchScreen` `None` with no error recorded;
    several unmarked runbooks that disagree, or several *marked* ones that still disagree, also
    leave it `None` and record why under `launchScreenError` plus which of the two under
    `launchScreenErrorKind` (`"undeclared-walkthrough-runbook"` or
    `"conflicting-surface-launch-screen"`), the same shape `bundleIdError`/`bundleIdErrorKind`
    already get.
    """
    dump = graph_mod.build(head_graph)
    surfaces = sorted({n["surface"] for n in dump["nodes"] if n.get("surface")})
    navigation: dict[str, dict[str, Any]] = {}
    for surface in surfaces:
        surface_dump = graph_mod.subset(dump, surface)
        try:
            driver = reach.surface_driver(dump, surface)
            driver_error = None
            driver_error_kind = None
        except reach.ConflictingSurfaceDriver as exc:
            driver = None
            driver_error = str(exc)
            driver_error_kind = "conflicting-surface-driver"
        except reach.UndeclaredWalkthroughRunbook as exc:
            driver = None
            driver_error = str(exc)
            driver_error_kind = "undeclared-walkthrough-runbook"
        try:
            bundle_id = reach.surface_bundle_id(dump, surface)
            bundle_id_error = None
            bundle_id_error_kind = None
        except reach.ConflictingSurfaceBundleId as exc:
            bundle_id = None
            bundle_id_error = str(exc)
            bundle_id_error_kind = "conflicting-surface-bundle-id"
        except reach.UndeclaredWalkthroughBundleIdRunbook as exc:
            bundle_id = None
            bundle_id_error = str(exc)
            bundle_id_error_kind = "undeclared-walkthrough-runbook"
        try:
            launch_screen = reach.surface_launch_screen(dump, surface)
            launch_screen_error = None
            launch_screen_error_kind = None
        except reach.ConflictingSurfaceLaunchScreen as exc:
            launch_screen = None
            launch_screen_error = str(exc)
            launch_screen_error_kind = "conflicting-surface-launch-screen"
        except reach.UndeclaredWalkthroughLaunchScreenRunbook as exc:
            launch_screen = None
            launch_screen_error = str(exc)
            launch_screen_error_kind = "undeclared-walkthrough-runbook"
        # `root_path` needs *driver* before it can be asked: a `mobile` surface has no path
        # grammar to state a root path in (`routes.is_path_addressed`), and asking without
        # driver would get today's web-shaped default back regardless of what this surface
        # actually is.
        root_path, _server = reach.root_path(surface_dump, driver)
        screens = reach.screens_of(surface_dump)
        try:
            entry_url = reach.entry_origin(dump, surface)
            entry_url_error = None
        except reach.ConflictingEntryOrigin as exc:
            entry_url = None
            entry_url_error = str(exc)
        if not screens:
            navigation[surface] = {
                "start": "",
                "surface": surface,
                "rootPath": root_path,
                "entryUrl": entry_url,
                "driver": driver,
                "bundleId": bundle_id,
                "launchScreen": launch_screen,
                "counts": {
                    "screens": 0, "reachable": 0, "unreachable": 0, "undeclared": 0, "nav_edges": 0,
                },
                "routes": {},
                "unreachable": [],
                "undeclared": [],
            }
            if entry_url_error is not None:
                navigation[surface]["entryUrlError"] = entry_url_error
            if driver_error is not None:
                navigation[surface]["driverError"] = driver_error
                navigation[surface]["driverErrorKind"] = driver_error_kind
            if bundle_id_error is not None:
                navigation[surface]["bundleIdError"] = bundle_id_error
                navigation[surface]["bundleIdErrorKind"] = bundle_id_error_kind
            if launch_screen_error is not None:
                navigation[surface]["launchScreenError"] = launch_screen_error
                navigation[surface]["launchScreenErrorKind"] = launch_screen_error_kind
            continue
        try:
            navigation[surface] = reach.reachability(head_graph, surface=surface, driver=driver)
            navigation[surface]["rootPath"] = root_path
            navigation[surface]["entryUrl"] = entry_url
            navigation[surface]["driver"] = driver
            navigation[surface]["bundleId"] = bundle_id
            navigation[surface]["launchScreen"] = launch_screen
        except reach.UnknownStart as exc:
            navigation[surface] = {
                "start": "",
                "surface": surface,
                "rootPath": root_path,
                "entryUrl": entry_url,
                "driver": driver,
                "bundleId": bundle_id,
                "launchScreen": launch_screen,
                "counts": {
                    "screens": len(screens), "reachable": 0,
                    "unreachable": len(screens), "undeclared": 0, "nav_edges": 0,
                },
                "routes": {},
                "unreachable": sorted(screens),
                "undeclared": [],
                "error": str(exc),
            }
        if entry_url_error is not None:
            navigation[surface]["entryUrlError"] = entry_url_error
        if driver_error is not None:
            navigation[surface]["driverError"] = driver_error
            navigation[surface]["driverErrorKind"] = driver_error_kind
        if bundle_id_error is not None:
            navigation[surface]["bundleIdError"] = bundle_id_error
            navigation[surface]["bundleIdErrorKind"] = bundle_id_error_kind
        if launch_screen_error is not None:
            navigation[surface]["launchScreenError"] = launch_screen_error
            navigation[surface]["launchScreenErrorKind"] = launch_screen_error_kind
    return navigation


def build_context(
    root: Path,
    *,
    base: str,
    head: str = "WORKTREE",
    source_roots: dict[str, list[str]] | None = None,
    features_root: str = "",
    story_file: Path | None = None,
    exclude_paths: Iterable[str] = (),
    repositories: Sequence[SourceRepository] = (),
) -> dict[str, Any]:
    """Map a `base..head` code diff onto the OKF graph and return the obligation packet.

    `exclude_paths` are repo-relative paths to drop from the diff before anything is
    obligated on them. It exists for the `head="WORKTREE"` caller: the worktree is not a
    commit, so it can hold work that belongs to whoever left it there rather than to the
    change under examination, and only that caller can tell the two apart.
    """
    root = root.resolve()
    excluded_paths = {str(path) for path in exclude_paths}
    # Repo-relative on purpose: this one is handed to `git ls-tree`, which pathspecs against
    # the work tree, not the filesystem. Empty means "wherever this repo configures its book",
    # which ostler answers — spelling `docs/features` here would read the wrong tree in a repo
    # that moved it.
    features_root = path_mod.resolve_features_root(features_root, root)
    source_roots = source_roots or {}
    book_root = _book_root(root, features_root)
    book_files_list = book_files(root, features_root)
    story_file_record_value = story_file_record(root, story_file)
    current = load(root, root_overrides={"features": features_root})
    base_graph = _graph_at_revision(root, base, features_root)
    head_graph = current if head == "WORKTREE" else _graph_at_revision(root, head, features_root)
    excluded_doc_roots = {
        path.resolve().relative_to(root).as_posix()
        for path in current.doc_roots.values()
        if path.resolve().is_relative_to(root)
    }
    base_nodes, base_edges, base_ends, base_scopes, base_details = _serialized_graph(base_graph)
    head_nodes, head_edges, head_ends, head_scopes, head_details = _serialized_graph(head_graph)
    nodes_by_id = _merge_snapshot_nodes(base_nodes, head_nodes)
    # Head wins per node, as `_merge_snapshot_nodes` does for the nodes themselves; a node
    # only the base graph still holds keeps the scope it had there.
    node_scopes = {**base_scopes, **head_scopes}
    # A path the book declares under `config:` is a production unit by declaration. The
    # non-production and generated-unit filters below are heuristics over the path alone —
    # a `Pulumi.<stack>.yaml` is dropped as stack config, which is the right default for a
    # file nobody documented — and a node that names the file has overruled the heuristic
    # for that file: the deploy token committed in the clear lives in exactly such a file,
    # and the filter is what made it unreachable. The filters themselves stay pure.
    declared_config = {
        item
        for node in nodes_by_id.values()
        for item in refs_mod.code_refs(node.get("bullets", {}).get("config"))
    }
    repository_rows: list[dict[str, Any]] = []
    repositories_by_id = {repository.id: repository for repository in repositories}
    health: list[dict[str, Any]] = []
    if repositories:
        changes_all: list[ChangedUnit] = []
        seen_repositories: set[str] = set()
        for repository in repositories:
            if repository.id in seen_repositories:
                raise ValueError(f"duplicate source repository id {repository.id!r}")
            seen_repositories.add(repository.id)
            checkout = Path(repository.checkout).resolve()
            roots: dict[str, list[str]] = {}
            for scope in repository.scopes:
                roots.setdefault(scope.surface, []).append(scope.root)
            for change in _changed_units(checkout, repository.base, repository.head, roots):
                changes_all.append(replace(
                    change,
                    repository=repository.id,
                    surface=_surface_owner(change.path, roots),
                    source_root=str(checkout),
                ))
            repository_rows.append({
                "id": repository.id,
                "base": repository.base,
                "baseSha": _git(checkout, "rev-parse", "--verify",
                                f"{repository.base}^{{commit}}").strip(),
                "head": repository.head,
                "headSha": (None if repository.head == "WORKTREE" else
                            _git(checkout, "rev-parse", "--verify",
                                 f"{repository.head}^{{commit}}").strip()),
                "headAnchorSha": (_git(checkout, "rev-parse", "HEAD").strip()
                                   if repository.head == "WORKTREE" else None),
                "sourceFingerprint": source_fingerprint(repository),
                "scopes": [scope.model_dump(mode="json") for scope in repository.scopes],
            })
    else:
        changes_all = _changed_units(root, base, head, source_roots)

    changes = [
        change
        for change in changes_all
        if change.path not in excluded_paths
        and (change.repository or not any(
            change.path == prefix or change.path.startswith(prefix.rstrip("/") + "/")
            for prefix in excluded_doc_roots
        ))
        and (
            _source_ref(change.repository, change.path) in declared_config
            or (
                not _is_non_production_path(change.path)
                and not _is_generated_unit(Path(change.source_root) if change.source_root else root,
                                           change)
            )
        )
    ]

    direct_reasons: dict[str, list[dict[str, str]]] = {}
    changed_code: list[dict[str, Any]] = []
    for change in changes:
        # `--source-root` and `_surface_owner` stay in `root`'s frame (its whole job is
        # attribution against those CLI-declared prefixes) — only the book-facing paths
        # below are rebased onto the book's own root.
        change_book_root = "" if change.repository else book_root
        book_path = _book_relative(change.path, change_book_root)
        book_base_path = _book_relative(change.base_path, change_book_root)
        book_head_path = _book_relative(change.head_path, change_book_root)
        refs = {
            *(
                _source_ref(change.repository, book_base_path, symbol)
                for symbol in change.base_symbols
                if change.base_path
            ),
            *(
                _source_ref(change.repository, book_head_path, symbol)
                for symbol in change.head_symbols
                if change.head_path
            ),
        }
        book_change = replace(change, path=book_path, base_path=book_base_path, head_path=book_head_path)
        changed_code.append(
            {
                "path": change.path,
                "repository": change.repository,
                "id": _source_ref(change.repository, change.path),
                "basePath": change.base_path,
                "headPath": change.head_path,
                "status": change.status,
                "baseLines": list(change.base_lines),
                "headLines": list(change.head_lines),
                "baseSymbols": list(change.base_symbols),
                "headSymbols": list(change.head_symbols),
            }
        )
        mapped = change.status == "deleted"
        for node_id, node in nodes_by_id.items():
            # Every owning key the node's type declares is read — `code:` everywhere it is
            # declared, `openapi:` on a server or endpoint, `file:` on a format, `config:` on
            # an environment or a format — so a node
            # documented against a schema or a fixture file is reached when that file
            # changes, without a second `code:` citation repeating the path. Which keys own
            # is the registry's call (`BulletKey.owns`), not a list kept here.
            bullets = node.get("bullets", {})
            owned_file = False
            for key in registry.owning_keys(str(node.get("type", ""))):
                cited = refs_mod.code_refs(bullets.get(key))
                exact = _matching_refs(refs, cited)
                if exact:
                    mapped = True
                    for ref in exact:
                        direct_reasons.setdefault(node_id, []).append(
                            {"kind": "changed-code", "ref": ref, "key": key}
                        )
                elif not owned_file and any(
                    _ref_owns_change(item, book_change)
                    for item in cited
                ):
                    # One file-owner reason per node and change, whichever key cited it
                    # first: citing the same path under `code:` and `openapi:` is one
                    # owner, not two, so the shared-file count below stays honest.
                    mapped = owned_file = True
                    direct_reasons.setdefault(node_id, []).append(
                        {
                            "kind": "file-owner",
                            "ref": _source_ref(change.repository, book_path),
                            "key": key,
                        }
                    )
        if not mapped:
            surface = change.surface or _surface_owner(change.path, source_roots)
            surface_nodes = [
                node_id
                for node_id, node in nodes_by_id.items()
                if surface and node.get("surface") == surface
            ]
            if surface_nodes:
                mapped = True
                for node_id in surface_nodes:
                    direct_reasons.setdefault(node_id, []).append(
                        {
                            "kind": "surface-owner",
                            "ref": f"{surface}:{_source_ref(change.repository, book_path)}",
                        }
                    )
            else:
                health.append(
                    {
                        "kind": "unmapped-change",
                        "severity": "error",
                        "path": _source_ref(change.repository, book_path),
                        "message": "changed production unit has no exact symbol, file, or surface owner",
                    }
                )

    # A bare-file `code:` citation says "this node is documented against that file". It
    # localizes a change to the node only while the node is the file's *sole* owner. A
    # global stylesheet or a shared module is cited by every node that renders through it,
    # so one edited line makes all of them file-owned — and none of that is evidence the
    # change touched any particular one. Which of those citations are shared is a property
    # of the whole change set, so it is known here and not inside the loop above.
    #
    # A `code:` citation of an exact *symbol* stops localizing for the same reason, but not
    # at the same count — a symbol is a far better anchor than a bare file, so it takes
    # `_CONTAINER_FANOUT` nodes rather than two. A container — a toolbar component owning a
    # dozen documented controls, a page component owning every panel on it — is the honest
    # anchor for each of them, so editing it to render one new control marks all twelve
    # changed. A story that added a publish button was charged with proving undo, redo, the
    # heading toggles and the list toggles, which is a plan the change cannot justify and no
    # planner can write. Below that count the citation is still evidence: an endpoint and a
    # concept both grounded in one function are two true readings of it, and a change to it
    # can break either.
    file_owners: dict[str, set[str]] = {}
    symbol_owners: dict[str, set[str]] = {}
    # Owners are counted per node whatever key cited the path, so a node naming one file
    # under two owning keys is one owner.
    for node_id, reasons in direct_reasons.items():
        for reason in reasons:
            if reason["kind"] == "file-owner":
                file_owners.setdefault(reason["ref"], set()).add(node_id)
            elif reason["kind"] == "changed-code":
                symbol_owners.setdefault(reason["ref"], set()).add(node_id)
    # `_CONTAINER_FANOUT`/`> 1` are meant to count *families* citing a path, not nodes — a
    # three-arm interaction split under D51 (`extends:`) is one documented control, so all
    # three arms must collapse to one owner before either count runs, rather than manufacture
    # three distinct owners out of one control and never demote it. Ordinary sibling
    # components that merely share a `parent:` page are *not* one family for this count —
    # each is its own owner, which is what lets the fan-out and shared-file thresholds below
    # actually measure fan-out rather than hide it behind the page they happen to share. The
    # threshold itself is untouched: a bare file is a weaker anchor than an exact symbol, so
    # it still demotes at 2 owning families rather than `_CONTAINER_FANOUT`.
    shared_files = {
        ref
        for ref, owners in file_owners.items()
        if len({_family_root(node_id, owners, nodes_by_id) for node_id in owners}) > 1
    }
    shared_symbols = {
        ref
        for ref, owners in symbol_owners.items()
        if len({_family_root(node_id, owners, nodes_by_id) for node_id in owners})
        >= _CONTAINER_FANOUT
    }

    # Containment and graph links broaden impact without lexical inference.
    impacted = set(direct_reasons)
    for node_id in list(impacted):
        parent = nodes_by_id.get(node_id, {}).get("parent")
        while parent and parent in nodes_by_id:
            if parent not in impacted:
                direct_reasons.setdefault(parent, []).append(
                    {"kind": "contains-impacted-node", "ref": node_id}
                )
            impacted.add(parent)
            parent = nodes_by_id[parent].get("parent")
    edges = base_edges | head_edges
    end_edges = base_ends | head_ends
    flows = {node_id for node_id, node in nodes_by_id.items() if node.get("type") == "flow"}
    journeys = set(impacted & flows)
    for source, target in edges:
        if source in flows and target in impacted:
            journeys.add(source)
            direct_reasons.setdefault(source, []).append(
                {"kind": "flow-links-contract", "ref": target}
            )
    contracts = impacted - flows
    for source, target in edges:
        # A flow target is somebody else's journey, never this closure's contract. The two
        # sets are disjoint by construction one line up, and `_obligations` relies on it:
        # it runs once per member, and a node in both is walked twice. Only the *base*
        # obligation carries the role in its id (`:contract` vs `:end-state`), so the
        # collision surfaces on the bullet-derived ones — a flow filed both ways emits
        # `:start:1` and `:end:1` twice, `validate_context` reports duplicate ids, and the
        # documentation gate hands the author a rework brief for a defect that is not in
        # the book and that no amount of writing can clear.
        if source in journeys and target in nodes_by_id and target not in flows:
            contracts.add(target)
            direct_reasons.setdefault(target, []).append(
                {"kind": "flow-contract-closure", "ref": source}
            )

    relation_keys = RELATION_KEYS
    related = True
    while related:
        related = False
        selected = contracts | journeys
        emitted = {
            value
            for node_id in selected
            for value in _values(nodes_by_id[node_id].get("bullets", {}).get("emits"))
        }
        consumed = {
            value
            for node_id in selected
            for value in _values(nodes_by_id[node_id].get("bullets", {}).get("consumes"))
        }
        relation_values = {
            _relation_join_key(value)
            for node_id in selected
            for key in relation_keys
            for value in _values(nodes_by_id[node_id].get("bullets", {}).get(key))
        }
        for node_id, node in nodes_by_id.items():
            if node_id in selected:
                continue
            bullets = node.get("bullets", {})
            reasons: list[dict[str, str]] = []
            for value in _values(bullets.get("consumes")):
                if value in emitted:
                    reasons.append({"kind": "event-consumer", "ref": value})
            for value in _values(bullets.get("emits")):
                if value in consumed:
                    reasons.append({"kind": "event-producer", "ref": value})
            for key in relation_keys:
                for value in _values(bullets.get(key)):
                    join = _relation_join_key(value)
                    if join in relation_values:
                        reasons.append({"kind": key.replace(" ", "-"), "ref": join})
            if reasons:
                (journeys if node.get("type") == "flow" else contracts).add(node_id)
                direct_reasons.setdefault(node_id, []).extend(reasons)
                related = True

    # A `detail:` edge from a selected node is the author's own pointer to the concept
    # holding the selection rule for that implementation. The concept rides along as
    # judgment context — pulled with a closure-kind reason so it is never owed live
    # evidence — and its rule/prefers/deprecates bullets are attached to the pointing
    # node's obligations, where the reviewer choosing between implementations reads them.
    detail_edges = base_details | head_details
    judgment_by_node: dict[str, list[dict[str, Any]]] = {}
    for source, target in sorted(detail_edges):
        if source not in contracts and source not in journeys:
            continue
        concept = nodes_by_id.get(target)
        if not concept or concept.get("type") != "concept":
            continue
        bullets = concept.get("bullets", {})
        judgment_by_node.setdefault(source, []).append(
            {
                "concept": target,
                "title": concept.get("title") or target,
                "rules": _values(bullets.get("rule")),
                "prefers": _values(bullets.get("prefers")),
                "deprecates": _values(bullets.get("deprecates")),
            }
        )
        if target not in contracts and target not in journeys:
            contracts.add(target)
            direct_reasons.setdefault(target, []).append({"kind": "judgment-context", "ref": source})

    selected = contracts | journeys
    verification_index: list[dict[str, Any]] = []
    for node_id, node in sorted(nodes_by_id.items()):
        for ref in _verification_refs(node):
            verification_index.append(
                {"node": node_id, "ref": ref, "path": _code_path(ref), "impacted": node_id in selected}
            )
    verification_refs = [
        {"node": item["node"], "ref": item["ref"], "path": item["path"]}
        for item in verification_index
        if item["impacted"]
    ]
    grounded: set[str] = set()
    for node_id in sorted(selected):
        node = nodes_by_id[node_id]
        for normalized in refs_mod.code_refs(node.get("bullets", {}).get("code")):
            if not _grounding_for_ref(
                root, base, head, normalized, repositories_by_id, book_root
            ):
                health.append(
                    {
                        "kind": "dangling-grounding",
                        "severity": "error",
                        "node": node_id,
                        "ref": normalized,
                        "message": "code grounding resolves in neither base nor head",
                    }
                )
            else:
                grounded.add(node_id)
        # Not "this node cites no test": a test citation is diagnostic (`tests:`, read by
        # regression attribution) and proves nothing about the product. What is worth a warning
        # is an impacted contract's normative claim that names no observation, because a
        # scenario written against it is then free to assert something weaker than the claim.
        # A check names no subject, so its subject is its position — the run of normative
        # bullets it sits under, which `registry.attributed_checks` binds it to, the engine
        # `compile_plan` reads for its own `checksDeclared`/`no-verify-declared` split — so
        # coverage is a fact per claim, not per node: one `verify:` above one claim leaves
        # every sibling claim on the same node uncovered. Only for a type that *has* a
        # `verify:` key, which is every authorable type but `step` (whose `verify:` observes
        # the step, not the product) and `untyped` (which declares no keys at all).
        node_type = str(node.get("type", ""))
        node_bullets = node.get("bullets", {})
        combiners = {int(pos): str(word) for pos, word in (node.get("combiners") or {}).items()}
        _, checks_per_bullet = registry.attributed_checks(
            node_type, node.get("bulletOrder") or [], combiners
        )
        if registry.check_keys(node_type):
            for key in registry.normative_keys(node_type):
                for index in range(1, len(_values(node_bullets.get(key))) + 1):
                    if not checks_per_bullet.get((key, index)):
                        health.append(
                            {
                                "kind": "missing-declared-check",
                                "severity": "warning",
                                "node": node_id,
                                "key": key,
                                "message": (
                                    f"impacted contract's `{key}:` claim declares no "
                                    "`verify:` check to fulfil it"
                                ),
                            }
                        )
    demoted_symbols: frozenset[str] | set[str] = shared_symbols
    required_contracts = {
        node_id
        for node_id in contracts
        if _is_required(node_id, direct_reasons, grounded, shared_files, shared_symbols)
    }
    if not required_contracts:
        # A story whose diff reached a grounded node and which nevertheless owes nothing is
        # reporting a bug in this filter, not a story with nothing to prove: the trial is
        # handed an empty evidence map and every seeded defect comes back "not owed by this
        # trial". So when the fan-out demotion is what emptied the set, take the demotion
        # back rather than ship a packet that asks for nothing. Only `shared_symbols` is
        # relaxed — a bare-file citation localizes nothing at any count, which is why
        # `shared_files` is not — and the finding is a warning rather than a silent repair,
        # because the floor firing means `_CONTAINER_FANOUT` was wrong for this book.
        floored = {
            node_id
            for node_id in contracts
            if _is_required(node_id, direct_reasons, grounded, shared_files, frozenset())
        }
        if floored:
            required_contracts = floored
            demoted_symbols = frozenset()
            health.append(
                {
                    "kind": "shared-symbol-floor",
                    "severity": "warning",
                    "message": (
                        "every changed symbol is cited by enough nodes to be demoted, which"
                        " would leave this change owing no live evidence at all; the"
                        " demotion was dropped and the changed-code reasons kept"
                    ),
                }
            )
    # One hop out from what the diff reached, along a named relation subject. This is the
    # story split the whole packet exists to catch: change the shape of a persisted record
    # and update the screen that displays it, and the screen that *creates* that record is
    # bound to the same record, untouched by the diff, and never re-proved — so the app ships
    # broken across the two stories and nothing in the run says so.
    #
    # One hop from `required_contracts`, not from the closure. The fixpoint above recomputes
    # its selection every lap, so a single shared subject chains across a whole persistence
    # island; that is what once made a seven-criterion story owe live proof against
    # sixty-seven documents. Hopping from the required set instead is bounded by
    # construction: a node pulled in this way is never itself hopped from.
    #
    # `relation-of-required` is in neither context-only set, so `_is_required` needs no change
    # to honour it — and its `grounded` gate still applies, so a node with nothing built
    # behind it is still not owed live proof.
    #
    # What such a node owes is the invariant it shares, not the whole surface it happens to
    # document. The sibling endpoint that writes the same record can be broken by a change to
    # the record's shape; its own `422` body and its own auth rule cannot, and owing them
    # would make every story re-prove each of its neighbours end to end. So a node reached
    # only by the hop is owed live evidence for its relation bullets and its contract, and
    # keeps the rest as context.
    reached_by_the_diff = set(required_contracts)
    required_subjects = {
        subject for node_id in required_contracts for subject in _named_subjects(nodes_by_id[node_id])
    }
    if required_subjects:
        hopped = False
        for node_id in sorted(contracts - required_contracts):
            for subject in sorted(_named_subjects(nodes_by_id[node_id]) & required_subjects):
                direct_reasons.setdefault(node_id, []).append(
                    {"kind": "relation-of-required", "ref": subject}
                )
                hopped = True
        if hopped:
            required_contracts = {
                node_id
                for node_id in contracts
                if _is_required(node_id, direct_reasons, grounded, shared_files, demoted_symbols)
            }
        for subject in sorted(required_subjects):
            owners = sorted(
                node_id for node_id, node in nodes_by_id.items() if subject in _named_subjects(node)
            )
            if len(owners) > _RELATION_FANOUT:
                health.append(
                    {
                        "kind": "relation-fanout",
                        "severity": "warning",
                        "ref": subject,
                        "message": (
                            f"relation subject `{subject}` binds {len(owners)} nodes; a change"
                            " reaching any of them owes live evidence for all of them, which"
                            " usually means the subject is named more broadly than the record"
                        ),
                    }
                )
    fixture_provides = _fixture_provides_index(nodes_by_id)
    fixture_undetermined = _fixture_undetermined_index(nodes_by_id)
    obligations = [
        obligation
        for node_id in sorted(contracts)
        for obligation in _obligations(
            nodes_by_id[node_id],
            direct_reasons.get(node_id, []),
            journey=False,
            required=node_id in required_contracts,
            owed_keys=None if node_id in reached_by_the_diff else _SHARED_INVARIANT_KEYS,
            scope=node_scopes.get(node_id, ()),
            judgment=judgment_by_node.get(node_id),
            fixture_provides=fixture_provides,
            fixture_undetermined=fixture_undetermined,
            resolve_locator=_locator_resolver(head_graph, nodes_by_id, nodes_by_id[node_id]),
            nodes_by_id=nodes_by_id,
        )
    ] + [
        obligation
        for node_id in sorted(journeys)
        for obligation in _obligations(
            nodes_by_id[node_id],
            direct_reasons.get(node_id, []),
            journey=True,
            required=_journey_is_required(
                node_id, direct_reasons, required_contracts, end_edges
            ),
            scope=node_scopes.get(node_id, ()),
            judgment=judgment_by_node.get(node_id),
            fixture_provides=fixture_provides,
            fixture_undetermined=fixture_undetermined,
            resolve_locator=_locator_resolver(head_graph, nodes_by_id, nodes_by_id[node_id]),
            nodes_by_id=nodes_by_id,
        )
    ]
    obligations.sort(key=lambda item: _sort_key(str(item["id"])))
    # A `same-as:` family collapses several members' obligations onto one id (`_obligations`'
    # docstring), so more than one call above can mint the same id — one per member that
    # states the underlying claim. One member wins every index, rather than the survivors
    # being a mixture: `same-as-disagreement` refuses a book whose family states a normative
    # key two ways, so every member's value list for a kind holds the same values, and this
    # sort is stable, so the member that came first pre-sort is first at every index it
    # mints. What survives is that one member's list whole.
    seen_obligation_ids: set[str] = set()
    deduped_obligations: list[dict[str, Any]] = []
    for obligation in obligations:
        obligation_id = str(obligation["id"])
        if obligation_id in seen_obligation_ids:
            continue
        seen_obligation_ids.add(obligation_id)
        deduped_obligations.append(obligation)
    obligations = deduped_obligations
    navigation = _navigation(head_graph)
    cli_binaries = _cli_binaries(nodes_by_id)
    return {
        "version": 2 if repositories else 1,
        "available": bool(nodes_by_id),
        "base": base,
        "head": head,
        # The aim. Every later stage reads this packet and none of them is told on its own
        # argv which book the run is about, so a stage that needs the answer either repeats
        # a flag the caller must keep in sync or guesses from its cwd. This is the one place
        # the aim was ever known.
        "featuresRoot": features_root,
        "bookFiles": book_files_list,
        "storyFile": story_file_record_value,
        "changedCode": changed_code,
        **({"changedUnits": changed_code, "repositories": repository_rows} if repositories else {}),
        "directNodes": [
            {"node": node_id, "reasons": direct_reasons[node_id]}
            for node_id in sorted(direct_reasons)
        ],
        "contracts": sorted(contracts),
        "journeys": sorted(journeys),
        "journeyNodes": sorted(journeys),
        "verificationRefs": verification_refs,
        "verificationIndex": verification_index,
        "navigation": navigation,
        # A `command` obligation's `run:` names only the arguments (`ostler.acts`'s `invoke`)
        # — the executable is the owning `cli` **file** node's `binary:`, stated once where the
        # book already says it rather than repeated in every `argv`. `compile.py` resolves a
        # `run:` obligation's tool by looking its `source` (the shared file path) up here,
        # rather than re-walking the graph it no longer has once the packet leaves this
        # process — a `cli` node with no `binary:` value is simply absent, so a `run:` on that
        # file is uncompilable (`_cli_binaries` below).
        "cliBinaries": cli_binaries,
        # Each screen file's `route:`, read by the same function the vet driver reads it
        # with. The driver decides whether a photographed page is the screen the book
        # named by comparing that route against a URL; the compiler decides whether that
        # comparison could be made at all. Two readers, one question — so one function,
        # and the compiler gets the answer through the packet rather than a second regex.
        "screenRoutes": routes_mod.screen_routes(head_graph),
        "healthFindings": health,
        "story": _story_identity(story_file),
        "acceptanceCriteria": _acceptance_criteria(story_file),
        "obligations": obligations,
    }


#: The whole-book verification table, split out of the agent-facing packet. It carries one
#: row per `verify:` ref in the entire feature graph — impacted or not — because
#: `_attribute_failures` classifies a failing test as "outside-impact" rather than
#: "unattributed" only when it can find a non-impacted owner. That makes it the largest
#: member of the packet by far and the least useful to a reader: on a nine-epic book it was
#: 61% of a 676 KB file that a planning agent reads in full. The reader keeps
#: `verificationRefs` — the impacted subset — and the machine reads this beside it.
VERIFICATION_INDEX_FILE = "qa-okf-verification-index.json"


def write_context(packet: dict[str, Any], spec_dir: Path) -> tuple[Path, Path]:
    spec_dir.mkdir(parents=True, exist_ok=True)
    json_path = spec_dir / "qa-okf-context.json"
    md_path = spec_dir / "qa-okf-context.md"
    reader_packet = {key: value for key, value in packet.items() if key != "verificationIndex"}
    (spec_dir / VERIFICATION_INDEX_FILE).write_text(
        json.dumps(packet.get("verificationIndex", []), indent=2) + "\n", encoding="utf-8"
    )
    json_path.write_text(json.dumps(reader_packet, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_context(reader_packet), encoding="utf-8")
    return json_path, md_path


#: The two obligation sections. They are headings rather than a suffix on each line because the
#: distinction decides whether a planner owes a scenario, and a suffix could not carry it: a
#: requirement is rendered verbatim, wraps where the book wrapped it, and put the marker on a
#: continuation line — so `grep '- \`okf:'` and `grep 'context only'` disagreed, and a planning
#: agent that derived its owed set per-line derived the wrong one. Under a heading the class of an
#: entry is positional, which no amount of wrapping can move.
OWED_HEADING = "## Obligations — owed live evidence"
CONTEXT_HEADING = "## Context — reached by closure, not owed evidence"


def render_obligations(
    obligations: Sequence[dict[str, Any]], *, locators: bool = True
) -> list[str]:
    """Render one obligation section, or `- (none)` when it is empty."""
    if not obligations:
        return ["- (none)"]
    lines: list[str] = []
    for obligation in obligations:
        lines.append(f"- `{obligation['id']}`: {obligation['requirement']}")
        if locators:
            for key, values in sorted(obligation.get("locators", {}).items()):
                lines.append(f"  - {key}: {'; '.join(values)}")
            repeat = obligation.get("repeat")
            if repeat:
                parts = [f"one per `{repeat['onePer']}`"]
                if repeat.get("binds"):
                    parts.append("binds " + ", ".join(f"`{b}`" for b in repeat["binds"]))
                if repeat.get("uniqueBy"):
                    parts.append(f"unique by `{repeat['uniqueBy']}`")
                if repeat.get("variants"):
                    variants = repeat["variants"]
                    parts.append(
                        f"variants `{variants['path']}` = " + " | ".join(variants["values"])
                    )
                lines.append(f"  - repeated: {'; '.join(parts)}")
        # Not under the `locators` flag: judgment and unspecified are prose context, wanted
        # wherever the obligation is rendered, not a UI-locator detail a caller may strip.
        for entry in obligation.get("judgment", []):
            rules = "; ".join(entry.get("rules", []))
            lines.append(f"  - judgment: `{entry['concept']}`" + (f" — {rules}" if rules else ""))
            for preferred in entry.get("prefers", []):
                lines.append(f"    - prefers: {preferred}")
            for deprecated in entry.get("deprecates", []):
                lines.append(f"    - deprecates: {deprecated}")
        for entry in obligation.get("unspecified", []):
            lines.append(f"  - unspecified (resolved by design): {entry['text']}")
    return lines


def select_obligations(
    packet: dict[str, Any],
    *,
    required: bool | None = None,
    node: str = "",
    kind: str = "",
    offset: int = 0,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Filter and page the obligation list, returning `(page, total_matched)`.

    The packet is written once and read many times, and on a large book it is read by an agent
    that cannot hold it: the closure is deliberately broad, so a story owing 25 obligations
    ships beside 151 it only needs for context, and the JSON carrying both is a few hundred
    kilobytes. Reading it whole truncates, and the reader falls back to re-deriving the split by
    hand. Selecting a slice is the same information at a size a reader can actually take in, so
    this is a query over the built packet rather than another way to build one — `build_context`
    walks the diff and the graph and takes the better part of a minute; a filter must not.

    `node` matches as a substring of the obligation's node path, not a glob: the caller is
    usually typing a surface prefix at a shell, where a `*` needs quoting to survive.
    """
    matched = [
        item
        for item in packet.get("obligations", [])
        if (required is None or bool(item.get("required", True)) is required)
        and (not node or node in str(item.get("node", "")))
        and (not kind or str(item.get("kind", "")) == kind)
    ]
    window = matched[offset:] if limit is None else matched[offset : offset + limit]
    return window, len(matched)


def render_context(packet: dict[str, Any]) -> str:
    lines = [
        "---",
        f"type: {registry.spec_type_for('qa-okf-context.md')}",
        "---",
        "# QA OKF Context",
        "",
        f"- Base: `{packet.get('base', '')}`",
        f"- Head: `{packet.get('head', '')}`",
        f"- Available: `{str(packet.get('available', False)).lower()}`",
        "",
        "## Changed Code",
        "",
    ]
    for change in packet.get("changedCode", []):
        symbols = sorted(set(change.get("baseSymbols", []) + change.get("headSymbols", [])))
        lines.append(f"- `{change['path']}` ({change['status']}): {', '.join(symbols) or 'file scope'}")
    if not packet.get("changedCode"):
        lines.append("- (none)")
    obligations = packet.get("obligations", [])
    owed = [item for item in obligations if item.get("required", True)]
    context_only = [item for item in obligations if not item.get("required", True)]
    lines.extend(["", OWED_HEADING, ""])
    lines.extend(render_obligations(owed))
    lines.extend(["", CONTEXT_HEADING, ""])
    lines.extend(render_obligations(context_only))
    lines.extend(["", "## Health Findings", ""])
    for finding in packet.get("healthFindings", []):
        lines.append(f"- **{finding['kind']}** `{finding.get('path', '')}`: {finding['message']}")
    if not packet.get("healthFindings"):
        lines.append("- (none)")
    return "\n".join(lines) + "\n"


def validate_context(packet: Any) -> list[str]:
    if not isinstance(packet, dict):
        return ["context must be a JSON object"]
    problems: list[str] = []
    version = packet.get("version")
    if version not in (1, 2):
        problems.append("context.version must be 1 or 2")
    if not isinstance(packet.get("available"), bool):
        problems.append("context.available must be boolean")
    for field in ("changedCode", "directNodes", "contracts", "journeys", "journeyNodes", "verificationRefs", "healthFindings", "obligations"):
        if not isinstance(packet.get(field), list):
            problems.append(f"context.{field} must be a list")
    if version == 2:
        for field in ("changedUnits", "repositories"):
            if not isinstance(packet.get(field), list):
                problems.append(f"context.{field} must be a list")
    if "verificationIndex" in packet and not isinstance(packet["verificationIndex"], list):
        problems.append("context.verificationIndex must be a list")
    if "navigation" in packet and not isinstance(packet["navigation"], dict):
        problems.append("context.navigation must be an object")
    seen: set[str] = set()
    for item in packet.get("obligations", []):
        if not isinstance(item, dict) or not item.get("id"):
            problems.append("every obligation must be an object with an id")
            continue
        if item["id"] in seen:
            problems.append(f"duplicate obligation id '{item['id']}'")
        seen.add(item["id"])
    return problems


def cmd_context(
    root: Path,
    spec_dir: Path,
    *,
    base: str,
    head: str = "WORKTREE",
    source_roots: dict[str, list[str]] | None = None,
    features_root: str = "",
    story_file: Path | None = None,
    exclude_paths: Iterable[str] = (),
    repositories: Sequence[SourceRepository] = (),
) -> QaOutcome:
    """Build the obligation packet, write it into *spec_dir*, and report the outcome.

    Every failure that reaches this is data-shaped: a diff git cannot produce, a book
    that will not load, a spec directory that cannot be written. Catching it here rather
    than in each caller is the whole point of the function — `cli.py` and the coder
    workflow had hand-copied the identical `except` around `build_context`.
    """
    try:
        packet = build_context(
            root,
            base=base,
            head=head,
            source_roots=source_roots or {},
            features_root=features_root,
            story_file=story_file,
            exclude_paths=exclude_paths,
            repositories=repositories,
        )
        # The reference compiler's own account of which obligations it could and could not
        # discharge, and why, stamped onto the packet it hands on — so `validate_v2` reads
        # that account instead of re-deriving "unhandled" from a set difference blind to it
        # (see `annotate_deferred_obligations`).
        story_name = str(packet.get("story", "") or "story")
        annotate_deferred_obligations(packet, story=story_name)
        json_path, md_path = write_context(packet, spec_dir)
    except (OSError, RuntimeError, ValueError) as exc:
        return QaOutcome(ok=False, message=str(exc), status="invalid",
                         data={"status": "invalid", "message": str(exc)})
    ok = not any(f.get("severity") == "error" for f in packet.get("healthFindings", []))
    return QaOutcome(ok=ok, message=f"wrote {json_path} and {md_path}", data=packet)


def cmd_context_validate(spec_dir: Path) -> QaOutcome:
    """Read `qa-okf-context.json` out of *spec_dir* and validate it.

    An unreadable or unparseable file is one more entry in `problems` rather than a
    raise: to the caller asking "does this packet hold", a file that is not there and a
    packet that is malformed are the same answer.
    """
    context_file = spec_dir / "qa-okf-context.json"
    try:
        packet = json.loads(context_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems = [str(exc)]
    else:
        problems = validate_context(packet)
    status = "passed" if not problems else "invalid"
    return QaOutcome(
        ok=not problems,
        message=("Context is valid." if not problems
                 else "Context validation failed:\n"
                      + "\n".join(f"  - {p}" for p in problems)),
        status=status,
        data={"status": status, "problems": problems},
    )


def _graph_at_revision(root: Path, revision: str, features_root: str) -> Graph:
    """The base-side graph at `revision`, built from every `.md` file under `features_root`.

    An empty `Graph` is a legitimate answer — `book_context` asks for one on purpose when
    `base` is the empty tree — so this cannot return one on faith the way `_revision_text`
    returns `""`. It asks `_revision_holds`, its companion here exactly as it is `_changed_units`'s,
    whether `features_root` exists at `revision` at all: absent there is the ordinary case
    of a features root added or renamed between base and head, and yields the empty graph
    silently. Present but unreadable is different — `ls-tree` named a path whose blob the
    object store cannot produce, which is corruption, not a mode this function should
    disguise as "nothing to graph" — and that raises instead.

    `ls-tree` runs `-z` so a NUL, not a shell-quoted newline or tab, separates entries: a
    quoted filename otherwise fails `.endswith(".md")` before `git show` is ever tried and
    the file vanishes from the graph with no signal at all.
    """
    current = load(root)
    graph = Graph(
        root=root,
        org_name=current.org_name,
        profile=current.profile,
        doc_roots={**current.doc_roots, "features": root / features_root},
    )
    if not _revision_holds(root, revision, features_root):
        return graph
    result = _git(root, "ls-tree", "-r", "-z", "--name-only", revision, "--", features_root)
    entries = [entry for entry in result.split("\0") if entry]
    for rel in sorted(entry for entry in entries if entry.endswith(".md")):
        try:
            text = _git(root, "show", f"{revision}:{rel}")
        except RuntimeError as exc:
            raise RuntimeError(
                f"{revision} lists {rel} under {features_root} but its blob is unreadable: {exc}"
            ) from exc
        graph.ui_nodes.extend(_parse_ui_nodes(markdown.split(text), root / rel, root))
    return graph


def _serialized_graph(
    graph: Graph,
) -> tuple[
    dict[str, dict[str, Any]],
    set[tuple[str, str]],
    set[tuple[str, str]],
    dict[str, tuple[str, ...]],
    set[tuple[str, str]],
]:
    """The nodes, every resolved edge, the flow destinations, each node's repeat scope, and
    the `detail:` edges.

    The last member exists because the general edge set discards `via`: a `detail:` edge is
    the documented pointer from a competing node to the concept holding its selection rule,
    and the packet wants exactly those edges back so the concept can ride along as judgment
    context. Lifted here, where `via` is still on the item, rather than re-resolved later.

    The third member is what tells a journey's destination apart from a step along the way,
    and it is read off the `end:` bullet rather than off each edge's `via`. `via` keeps the
    *first* bullet an href appeared under, so a walk that passes through its own destination
    — `steps:` naming `tally export` before `end:` names it again — attributes that edge to
    `steps` and leaves the flow with no end at all. The bullet's own links have no such
    ambiguity, and `_journey_is_required` is the only reader that needs the distinction, so
    it is derived here rather than changing what `via` means for every other caller.

    Where the `end:` is prose — "the holder's list holds exactly the one claim they filed" —
    the destination is the walk's last link. A flow's edges come out in document order, so
    that is the last thing the journey touches before it is over, and it is the node a story
    has to own to be the one that delivered the journey rather than one step of it.
    """
    data = graph_mod.build(graph)
    nodes = {item["id"]: item for item in data["nodes"]}
    edges = {(item["from"], item["to"]) for item in data["edges"] if item.get("to")}
    details = {
        (item["from"], item["to"])
        for item in data["edges"]
        if item.get("to") and item.get("via") == "detail"
    }
    ends: set[tuple[str, str]] = set()
    for item in data["nodes"]:
        if item.get("type") != "flow":
            continue
        walked = [edge for edge in item.get("edges", []) if edge.get("to")]
        end = item.get("bullets", {}).get("end")
        values = end if isinstance(end, list) else [end]
        hrefs = {
            href
            for value in values
            if value
            for _text, href in markdown.extract_refs(str(value)).links
        }
        named = [edge for edge in walked if edge.get("href") in hrefs]
        ends.update((item["id"], edge["to"]) for edge in named or walked[-1:])
    return nodes, edges, ends, locators_mod.scopes(data), details


def _in_book(path: str, offset: str) -> str | None:
    """*path*, spelled from the repository top level, rebased onto the book root *offset*
    names — or `None` when *path* falls outside the book root entirely.

    `offset` is `""` when the book root *is* the repository top level, in which case every
    path is already in the book's frame. Otherwise it is the book root's own path from the
    top level, with a trailing `/`, and a top-level path that does not start with it names a
    change the book does not cover — not an error, just not this book's to own.
    """
    if not offset:
        return path
    return path[len(offset):] if path.startswith(offset) else None


def _changed_units(
    root: Path,
    base: str,
    head: str,
    source_roots: dict[str, list[str]],
) -> list[ChangedUnit]:
    toplevel = Path(_git(root, "rev-parse", "--show-toplevel").strip()).resolve()
    resolved_root = root.resolve()
    offset = (
        "" if resolved_root == toplevel
        else f"{resolved_root.relative_to(toplevel).as_posix()}/"
    )
    args = ["diff", "--find-renames", "--unified=0", base]
    if head != "WORKTREE":
        args.append(head)
    configured = sorted({path for paths in source_roots.values() for path in paths})
    if configured:
        args.extend(["--", *configured])
    diff = _git(root, *args)
    units: dict[str, dict[str, Any]] = {}
    for patched in _patch_set(diff):
        old_top = patched.source_file.removeprefix("a/")
        new_top = patched.target_file.removeprefix("b/")
        book_path = _in_book(new_top if new_top != "/dev/null" else old_top, offset)
        if book_path is None:
            continue
        unit = units.setdefault(
            book_path, {"base": set(), "head": set(), "old": old_top, "new": new_top}
        )
        for hunk in patched:
            unit["base"].update(range(hunk.source_start, hunk.source_start + hunk.source_length))
            unit["head"].update(range(hunk.target_start, hunk.target_start + hunk.target_length))
    name_args = ["diff", "--find-renames", "--name-status", base]
    if head != "WORKTREE":
        name_args.append(head)
    if configured:
        name_args.extend(["--", *configured])
    for line in _git(root, *name_args).splitlines():
        fields = line.split("\t")
        status_code = fields[0]
        if status_code.startswith("R") and len(fields) >= 3:
            old_top, new_top = fields[1], fields[2]
        elif len(fields) >= 2:
            old_top = "/dev/null" if status_code == "A" else fields[1]
            new_top = "/dev/null" if status_code == "D" else fields[1]
        else:
            continue
        book_path = _in_book(new_top if new_top != "/dev/null" else old_top, offset)
        if book_path is None:
            continue
        units.setdefault(book_path, {"base": set(), "head": set(), "old": old_top, "new": new_top})
    if head == "WORKTREE":
        untracked_args = ["ls-files", "--others", "--exclude-standard"]
        if configured:
            untracked_args.extend(["--", *configured])
        for book_path in _git(root, *untracked_args).splitlines():
            top_path = f"{offset}{book_path}"
            text = _working_text(toplevel, top_path)
            units.setdefault(
                book_path,
                {
                    "base": set(),
                    "head": set(range(1, len(text.splitlines()) + 1)),
                    "old": "/dev/null",
                    "new": top_path,
                },
            )
    output: list[ChangedUnit] = []
    for book_path, item in sorted(units.items()):
        base_text = _revision_text(toplevel, base, item["old"])
        head_text = (
            _working_text(toplevel, item["new"])
            if head == "WORKTREE"
            else _revision_text(toplevel, head, item["new"])
        )
        # A side with a real (non-`/dev/null`) path that turns out not to exist at all is not
        # the same state as a side that exists and reads empty — the first is a path this scan
        # resolved wrong, the second is `_revision_text`/`_working_text` correctly reporting a
        # compiled artifact, a binary asset, or an empty file. Only the second is nothing to
        # cite and no behaviour to verify, the same failure mode `_is_generated_unit` exists to
        # prevent; the first must not be silently folded into it. A *deleted source* file is
        # not caught by either check: its base side still reads as text, and losing a
        # documented symbol is a real obligation.
        base_missing = item["old"] not in ("", "/dev/null") and not _revision_holds(
            toplevel, base, item["old"]
        )
        head_missing = item["new"] not in ("", "/dev/null") and not (
            (toplevel / item["new"]).is_file()
            if head == "WORKTREE"
            else _revision_holds(toplevel, head, item["new"])
        )
        if not base_text and not head_text and not base_missing and not head_missing:
            continue
        status = "modified"
        if item["old"] == "/dev/null":
            status = "added"
        elif item["new"] == "/dev/null":
            status = "deleted"
        elif item["old"] != item["new"]:
            status = "renamed"
        book_old = "" if item["old"] == "/dev/null" else (_in_book(item["old"], offset) or "")
        book_new = "" if item["new"] == "/dev/null" else (_in_book(item["new"], offset) or "")
        output.append(
            ChangedUnit(
                path=book_path,
                base_path=book_old,
                head_path=book_new,
                status=status,
                base_lines=tuple(sorted(item["base"])),
                head_lines=tuple(sorted(item["head"])),
                base_symbols=tuple(_symbols_for_lines(base_text, item["base"], book_old)),
                head_symbols=tuple(_symbols_for_lines(head_text, item["head"], book_new)),
            )
        )
    return output


def _patch_set(diff: str) -> PatchSet:
    """The diff, parsed. A malformed patch yields no units rather than a traceback.

    `unidiff` replaces a hand-written `@@ -a,b +c,d @@` matcher plus a pair of `--- `/`+++ `
    line prefixes, which between them carried the file's identity in loop-scoped variables:
    a hunk header appearing before any `+++ ` line — a stray `@@` in a *deleted line's own
    content*, which `--unified=0` still emits — indexed `units` with whatever path the
    previous file left behind, and raised `KeyError` on the very first diff. The parser knows
    a hunk body from a hunk header, so the association is structural.
    """
    try:
        return PatchSet(diff)
    except UnidiffParseError:
        return PatchSet("")


def _symbols_for_lines(text: str, lines: set[int], path: str = "") -> list[str]:
    """The symbols whose bodies span any of *lines* — the diff's changed units.

    The extents come from `ostler.inventory`, which parses every language it knows. That is
    what makes a symbol's *extent* real: a node knows where its body ends, so a hunk landing
    in the middle of a function is attributed to that function. The line scan this replaced
    knew only where each declaration *started* and assumed it ran until the next one began, so
    a nested declaration swallowed its neighbours' hunks and a trailing comment belonged to
    whatever was above it.

    An extensionless file is read as Python, as it always has been; a language no front end
    knows still falls back to the one-line scan below, because a wrong attribution there is
    better than none.
    """
    if not text or not lines:
        return []
    suffix = Path(path).suffix
    grammar = syntax.language_for(path) or ("python" if suffix == "" else None)
    if grammar is not None:
        symbols = inventory.extents(path, text, language=grammar)
    else:
        text_lines = text.splitlines()
        declarations = [
            (number, match.group(1) or match.group(2) or "")
            for number, line in enumerate(text_lines, start=1)
            if (match := _SYMBOL_RE.match(line))
        ]
        symbols = [
            (
                start,
                declarations[index + 1][0] - 1
                if index + 1 < len(declarations)
                else len(text_lines),
                name,
            )
            for index, (start, name) in enumerate(declarations)
        ]
    found: set[str] = set()
    for line in lines:
        containing = [item for item in symbols if item[0] <= line <= item[1]]
        if containing:
            found.add(max(containing, key=lambda item: item[0])[2])
    return sorted(found)


def _revision_text(root: Path, revision: str, path: str) -> str:
    """The blob's text at `revision`, or "" — the same answer `_working_text` gives for a file
    it cannot decode, so the two sides of a diff agree about what "unreadable" means.

    Binary is not an exotic input here: a repo that committed a compiled artifact and then
    deleted it puts that blob on the base side of the very first diff, and `git show` streams
    its bytes. Decoding those strictly used to raise straight out of `build_context`, so one
    stray executable in the change set voided the whole obligation packet.
    """
    if not path or path == "/dev/null":
        return ""
    try:
        blob = _git_bytes(root, "show", f"{revision}:{path}")
    except RuntimeError:
        return ""
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def _working_text(root: Path, path: str) -> str:
    """The working tree's text at `path`, or "" when it is absent or not decodable as UTF-8.

    The empty string is deliberate and is the same answer `_revision_text` gives for the
    other side of a diff, so the two agree about what "unreadable" means and a binary file
    does not read as a file that changed. It is not a claim that the file is missing:
    existence is asked of the filesystem by `_grounding_exists`, precisely so a `code:`
    bullet citing a binary or undecodable file stays satisfiable rather than becoming
    permanently ungrounded.
    """
    candidate = root / path
    try:
        return candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _revision_holds(root: Path, revision: str, path: str) -> bool:
    """Whether `revision` has a blob at `path` — asked of the bytes, never of their decoding."""
    if not path or path == "/dev/null":
        return False
    try:
        _git_bytes(root, "cat-file", "-e", f"{revision}:{path}")
    except RuntimeError:
        return False
    return True


def _grounding_exists(root: Path, base: str, head: str, ref: refs_mod.CodeRef) -> bool:
    path, symbol = ref.path, ref.symbol
    # Existence is asked of the filesystem and the object store, not of `_revision_text` /
    # `_working_text`. Those answer "" for a file they cannot decode as UTF-8, and reading
    # that as "not there" made a `code:` bullet citing any *binary* file permanently
    # unsatisfiable — a `.docx` test fixture, a golden PNG, a compiled sample. The book was
    # right and the gate refused it, so the only rewrite that cleared the finding was
    # deleting a true citation. Same shape as the `inventory.declares` note below: a probe
    # that cannot represent the answer reports the wrong one.
    present = _revision_holds(root, base, path) or (
        (root / path).is_file() if head == "WORKTREE" else _revision_holds(root, head, path)
    )
    if not present:
        return False
    if not symbol or not path.endswith(".py"):
        return True
    texts = [
        text
        for text in (
            _revision_text(root, base, path),
            _working_text(root, path) if head == "WORKTREE" else _revision_text(root, head, path),
        )
        if text
    ]
    # `inventory.declares`, not `_symbols_for_lines`: the two answer different questions and
    # only the first one is grounding's. `_symbols_for_lines` attributes a *diff hunk* to the
    # declaration whose body spans it, so it can only ever report classes and functions — a
    # module-level constant has no body to span. Asking it whether a name exists therefore
    # made every `code:` bullet naming a constant permanently unsatisfiable: the citation was
    # reported dangling in both base and head, and no rewrite of the book could clear it.
    return any(inventory.declares(path, text, symbol) for text in texts)


def _grounding_for_ref(
    root: Path,
    base: str,
    head: str,
    ref: str,
    repositories: dict[str, SourceRepository],
    book_root: str = "",
) -> bool:
    """Ground one citation in the docs repository or its named source repository.

    A book-relative citation (no `repository:`) is grounded against `root`'s own git
    tree, which is rooted above the book whenever `--features-root` names a nested book —
    so its path is rebased onto `root` first, the same rebase the changed-code join
    applies. A repository-scoped citation already names a path inside that repository's
    own checkout, which has no book nested inside it, so it is left alone.
    """
    try:
        parsed = refs_mod.parse_code_ref(ref)
    except ValueError:
        return False
    if not parsed.repository:
        if book_root:
            parsed = replace(parsed, path=f"{book_root}/{parsed.path}")
        return _grounding_exists(root, base, head, parsed)
    repository = repositories.get(parsed.repository)
    if repository is None:
        return False
    local_ref = replace(parsed, repository="")
    return _grounding_exists(
        Path(repository.checkout).resolve(),
        repository.base,
        repository.head,
        local_ref,
    )


def _git_bytes(root: Path, *args: str) -> bytes:
    """Raw stdout. Never `text=True`: git's output is only text by convention — `show` streams
    a blob verbatim, and `diff` inlines the bytes of any file git guessed was text — so a
    strict decode inside `subprocess` raises `UnicodeDecodeError` from wherever git was called
    rather than from a place that can decide what an undecodable file means."""
    result = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if result.returncode:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(stderr or f"git {' '.join(args)} failed")
    return result.stdout


def _git(root: Path, *args: str) -> str:
    """Decoded leniently: every caller but `_revision_text` wants path lists or hunk headers,
    which are ASCII, and would rather see a replacement character inside one line of a diff
    than lose the whole listing. `_revision_text` decodes strictly off `_git_bytes` instead,
    because there "undecodable" has a meaning — no symbols — and "" is how it is spelled."""
    return _git_bytes(root, *args).decode("utf-8", errors="replace")


def _values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)] if value else []


def relation_subject(value: str) -> tuple[str | None, str]:
    """Split a relation bullet into the subject it names and the claim it makes.

    The subject is what two nodes can be found to share; the prose is what a planner reads
    and what the obligation keeps as its `requirement`, unchanged from before subjects
    existed. A bullet with no subject yields `None` and its own text.
    """
    match = _RELATION_SUBJECT_RE.match(value.strip())
    if match is None:
        return None, value.strip()
    return match.group(1), match.group(2).strip()


def _relation_join_key(value: str) -> str:
    """What the fixpoint compares two relation bullets on: the subject, or the whole value."""
    subject, _ = relation_subject(value)
    return subject if subject is not None else value.strip()


def _cli_binaries(nodes_by_id: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Every `cli` file node's declared `binary:`, keyed by the file `path` its `command`
    sections share.

    A `command` section's own `path` is the owning file's (`_node_dict` in `graph.py`: several
    section nodes share one file's `path`), so a `run:` obligation minted off that section can
    be matched back to its file's `binary:` by that same path — no parent walk needed, and no
    reason to widen the obligation packet with a `binary` field per obligation when one dict
    keyed by path says it once per file.

    A `cli` node with an empty `binary:` bullet is omitted, not mapped to `""`: `- binary:` is
    scaffolded onto every `cli` node whether authored or not, so presence of the *key* proves
    nothing — only a non-empty *value* does (`_values`, not `key in bullets`).
    """
    binaries: dict[str, str] = {}
    for node in nodes_by_id.values():
        if node.get("type") != "cli" or node.get("kind") != "file":
            continue
        values = _values(node.get("bullets", {}).get("binary"))
        if values and values[0].strip():
            binaries[str(node["path"])] = values[0].strip()
    return binaries


def _named_subjects(node: dict[str, Any]) -> set[str]:
    """Every subject this node names, pooled across the relation and event bullets.

    Pooled deliberately, as the fixpoint already pools its relation values: `persistence:
    booking-record` on the concept and `consistency: booking-record` on the endpoint are
    talking about the same record, and an `emits:` is answered by a `consumes:`. Only named
    subjects — prose that names nothing is not evidence two nodes are related, however
    similar the two sentences happen to read.
    """
    bullets = node.get("bullets", {})
    subjects = {
        subject
        for key in RELATION_KEYS
        for value in _values(bullets.get(key))
        if (subject := relation_subject(value)[0]) is not None
    }
    for key in _EVENT_KEYS:
        for value in _values(bullets.get(key)):
            subject, _ = relation_subject(value)
            subjects.add(subject if subject is not None else value.strip())
    return {subject for subject in subjects if subject}


def _merge_snapshot_nodes(
    base: dict[str, dict[str, Any]],
    head: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Head wins; base contributes only the nodes head no longer has.

    Two cases, different in kind. A node in **both** snapshots is one node observed twice,
    and its bullets are read from head — the revision under test. A node in base **alone**
    is one the change deleted, carried through whole so the packet can still describe what
    went away.

    Bullets are replaced, never pooled. Unioning a changed bullet's values puts a value in
    the packet that *no revision of the book states*: the locator compiler reads the first
    value and would address the element by the name it carried **before** the edit — making
    a book repair invisible to the run meant to verify it — and `normative_claims` counts
    the pooled list and mints an obligation for a claim nobody made.
    """
    merged = {node_id: {**node, "bullets": dict(node.get("bullets", {}))} for node_id, node in base.items()}
    for node_id, node in head.items():
        combined = {**merged.get(node_id, {}), **node}
        combined["bullets"] = dict(node.get("bullets", {}))
        merged[node_id] = combined
    return merged


def _code_path(value: str) -> str:
    return refs_mod.ref_path(refs_mod.normalize_ref(value))


def _as_ref(candidate: str) -> str:
    """``path`` or ``path::name`` when ``candidate`` opens with a citable file, else ``""``.

    Split, not matched: ``::`` is the separator the grammar declares, and everything after it
    is the name — commas, parentheses, ``>`` and all. The only test applied to the left half is
    that it looks like one path with a suffix we cite, which `Path` answers.
    """
    path, separator, symbol = candidate.strip().partition("::")
    path, symbol = path.strip(), symbol.strip()
    if not path or path.split() != [path] or Path(path).suffix.lower() not in _CITABLE_SUFFIXES:
        return ""
    return f"{path}::{symbol}" if separator and symbol else path


def _verification_refs(node: dict[str, Any]) -> list[str]:
    """Every test a node's ``tests:`` bullets cite, as ``path`` or ``path::name``.

    Backticked refs are read span by span off the markdown parser, because the span boundary is
    the only thing that says where a test *name* ends — and these names contain commas, dashes
    and parentheses. Reading the raw bullet with one regex truncated them at the first comma,
    and the truncated name then matched no test, so the grounding gate told a correctly-cited
    book its citation did not exist. That is a tool failing to parse the book, which this
    package treats as the tool's defect, not the book's.

    A bullet citing *without* backticks has no such boundary, so a comma still has to close a
    ref there. That reading stays lossy on purpose — it is the reason to write the backticks.
    """
    refs: list[str] = []
    for value in _values(node.get("bullets", {}).get("tests")):
        spans = markdown.all_code_spans(value)
        if spans:
            found = [_as_ref(span) for span in spans]
        else:
            # No spans: each comma-separated chunk holds at most one ref, which starts at the
            # first word naming a citable file and runs to the end of the chunk.
            found = []
            for chunk in value.split(","):
                words = chunk.split()
                starts = (i for i, w in enumerate(words) if _as_ref(w.partition("::")[0]))
                index = next(starts, None)
                found.append("" if index is None else _as_ref(" ".join(words[index:])))
        refs.extend(ref for ref in found if ref)
    return list(dict.fromkeys(refs))


def _surface_owner(path: str, roots: dict[str, list[str]]) -> str:
    matches = [
        (len(prefix.rstrip("/")), surface)
        for surface, prefixes in roots.items()
        for prefix in prefixes
        if prefix.rstrip("/") in ("", ".")
        or path == prefix.rstrip("/")
        or path.startswith(prefix.rstrip("/") + "/")
    ]
    return max(matches)[1] if matches else ""


def _is_non_production_path(path: str) -> bool:
    candidate = path.lower()
    parts = Path(candidate).parts
    non_production_dirs = {
        "test",
        "tests",
        "__tests__",
        "testdata",
        "__snapshots__",
        "snapshots",
        "fixtures",
        "fixture",
        "golden",
        "goldens",
        # QA's own scaffolding. A mock backend, a stub server or a fixture harness exists to
        # make a test runnable; it carries no user-observable behaviour of its own. Treated as
        # production it gets modelled in the book as features, and then every story that so
        # much as touches a mock owes live proof of the mock — QA verifying its own harness
        # instead of the product it was pointed at.
        "mocks",
        "__mocks__",
        "stubs",
        "harness",
        "harnesses",
    }
    if any(part in non_production_dirs for part in parts[:-1]):
        return True
    # Same reasoning, for the directories that name their purpose rather than sit under a
    # conventional folder — `tools/qa-mock-backends/`, `mock-server/`, `qa-fixtures/`.
    if any(
        part.startswith(("qa-mock", "mock-", "mock_", "qa-fixture", "fake-", "fake_"))
        or part.endswith(("-mocks", "-mock-backends", "-fixtures"))
        for part in parts[:-1]
    ):
        return True
    name = parts[-1] if parts else candidate
    if name.startswith("test_") or name.endswith(("_test.py", "_test.go")):
        return True
    if any(token in name for token in (".test.", ".spec.")):
        return True
    if name.endswith(".md") and not any(part in {"prompts", "templates"} for part in parts[:-1]):
        return True
    if name.endswith((".lock", ".rst")) or name in {
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "uv.lock",
        "readme.md",
        "changelog.md",
        "license.md",
    }:
        return True
    # Build, dependency-manifest, and tooling-config files. No feature Concept owns these
    # and none should: they carry no user-observable behaviour for QA to verify. Left in,
    # they fail the documentation gate as "unmapped production units" — which is exactly what
    # blocked the first greenfield coder story, whose diff legitimately touched go.mod/go.sum/
    # a Makefile/Pulumi config alongside the real code. Dependency manifests specifically are
    # NOT ignored elsewhere by design (a version bump can change behaviour), but they have no
    # OKF owner, so they belong here for the ownership gate.
    build_config_names = {
        "makefile",
        "dockerfile",
        ".gitignore",
        ".dockerignore",
        "go.mod",
        "go.sum",
        "go.work",
        "go.work.sum",
        "package.json",
        "tsconfig.json",
        "vite.config.ts",
        "pubspec.yaml",
        "pubspec.lock",
        "analysis_options.yaml",
        ".mockery.yaml",
    }
    if name in build_config_names:
        return True
    # Pulumi stack config (Pulumi.yaml, Pulumi.<stack>.yaml).
    if name.startswith("pulumi.") and name.endswith((".yaml", ".yml")):
        return True
    # Log files. Nothing writes one on purpose as a production unit; what lands in a working
    # tree is a tool's debug output — a Firebase/Firestore emulator's `*-debug.log` is the
    # case that reached us, dropped into the repo root by the QA stack the gate itself starts.
    if name.endswith(".log"):
        return True
    # The agent toolchain's own footprint inside a client repo: farrier writes `agents.yml` and
    # the `.agents/` tree, and a coder run historically left a `qa-stack.yml` beside them. These
    # say how the repo is built and tested *by us* and never what it does for a user, so no
    # feature Concept can own them — and unlike a Makefile they are not even the repo's own
    # scaffolding, they are ours.
    #
    # Left in, the ownership gate reports them as unmapped production units, and the only move
    # left to an agent that must clear the gate is to invent a contract node for them in the
    # product's feature docs. A greenfield run did exactly that: it added a `#tooling` section
    # to `docs/features/api/http/api.md` owning `qa-stack.yml` and friends, which cleared the
    # error and bought a permanent `missing-declared-check` warning in exchange — a contract
    # that can never declare an observation, because a stack manifest is not a product surface.
    #
    # `qa-stack.yml` stays listed though nothing writes one any more: the declaration moved
    # into the book as an `ops`-context `runbook` node (`ostler/docs/okf-runbook.md`), which is
    # precisely the shape the objection above points at — an ops node is not a product surface,
    # so it never reaches this gate. A repo carrying the old file from before the move should
    # still not be told to invent a contract node for it.
    #
    # Root-scoped on purpose: a nested `agents.yml` is somebody's product file, not ours.
    if len(parts) == 1 and name in {"agents.yml", "qa-stack.yml"}:
        return True
    # The same footprint, at any depth: `okf_builder`'s coverage node writes
    # `.source-inventory.json` *into the source root it scanned*, so there is one per code tree
    # and no root-scoping to lean on. The dotted name is unambiguous enough to stand alone.
    if name == ".source-inventory.json":
        return True
    # CI and agent-tooling dotfile trees. `.opencode/opencode-loop/` records the operator
    # loop's own sessions inside the target repo; grounding those as product contracts is
    # the same unwinnable category as `.agents/` run artifacts.
    #
    # `.claude/` and `.githooks/` join them for the same reason and were found the same way.
    # farrier installs the skill bundles under `.claude/skills/`, and several of them carry
    # executable `scripts/check_*.py`; `make hooks` points `core.hooksPath` at `.githooks/`.
    # Both are real code by every syntactic test, which is why they reach this function at
    # all — and neither is the product. A greenfield story that merely had the toolchain
    # installed after its base commit drew six `unmapped-change` errors naming a skill's
    # own linter, and the only move left to an agent that must clear the gate is to write a
    # feature contract for our check scripts in the client's book.
    return bool(
        parts and parts[0] in {".github", ".gitlab", ".agents", ".opencode", ".claude", ".githooks"}
    )


#: How a code generator announces itself. Go standardized the wording and everything that
#: emits Go copies it — protoc, oapi-codegen, mockery, sqlc, ent — and enough tools in other
#: ecosystems copied it too that matching the sentence beats keeping a table of generators.
_GENERATED_MARKER = re.compile(r"^\s*(?://|#|/\*|--|<!--)\s*Code generated .*DO NOT EDIT", re.M)

#: Filename conventions that say the same thing without a marker line, by ecosystem.
_GENERATED_SUFFIXES = (
    ".gen.go",
    ".pb.go",
    ".pb.gw.go",
    ".gen.ts",
    ".gen.tsx",
    ".generated.ts",
    ".g.dart",
    ".gr.dart",
    ".gen.dart",
    ".freezed.dart",
    "_pb2.py",
    "_pb2_grpc.py",
    "_generated.go",
    "_generated.py",
    "_generated.ts",
)

#: Directories whose whole contents are machine-authored.
_GENERATED_DIRS = {"mocks", "__mocks__", "generated", "node_modules", "vendor"}

#: How much of a file to read looking for the marker. It is a header line by convention —
#: the point of the marker is that an editor sees it first — so this is generous already,
#: and bounded because the files it runs against are exactly the enormous ones.
_MARKER_SCAN_BYTES = 4096


def _is_generated_unit(root: Path, change: ChangedUnit) -> bool:
    """Is this changed unit machine-authored, and therefore owned by its generator?

    Generated code is production code — it ships, it serves traffic — but it is not a
    *documentable* unit, and treating it as one is what makes the coder's documentation gate
    unwinnable. `oapi-codegen` alone contributed 26 symbols to one benchmark story's diff,
    among them `UnescapedCookieParamError` and `TooManyValuesForParamError`; grounding those
    means writing OKF nodes for a code generator's internal error types and calling them
    product contracts. The author cannot do it honestly, so it burns every rework pass and
    the story fails on a demand no correct answer satisfies. The contract these files encode
    lives in the thing they were generated *from* — the OpenAPI document, the proto, the
    interface the mock stands in for — and that source is in the diff too, as a real unit.

    Same reasoning as `_is_non_production_path` and the same remedy, kept separate because
    the categories are different: that one is scaffolding that never runs, this one runs and
    is simply not authored by a person.

    The marker scan reads the **worktree**, so a packet built between two revisions relies on
    the naming conventions alone. That is why the conventions are listed rather than left to
    the marker: they cover the generators that dominate real diffs, and a miss here is only
    ever conservative — the unit stays production and the author is asked to ground it.
    """
    lowered = change.path.lower()
    parts = Path(lowered).parts
    if any(part in _GENERATED_DIRS for part in parts[:-1]):
        return True
    if lowered.endswith(_GENERATED_SUFFIXES):
        return True
    # A deletion carries the `/dev/null` sentinel rather than a path; joining it onto `root`
    # would read straight out of the repo, and there is no head file to sniff either way.
    if not change.head_path or Path(change.head_path).is_absolute():
        return False
    try:
        with (root / change.head_path).open("rb") as handle:
            head = handle.read(_MARKER_SCAN_BYTES).decode("utf-8", "replace")
    except OSError:
        return False
    return bool(_GENERATED_MARKER.search(head))


def _is_required(
    node_id: str,
    direct_reasons: dict[str, list[dict[str, str]]],
    grounded: set[str],
    shared_files: frozenset[str] | set[str] = frozenset(),
    shared_symbols: frozenset[str] | set[str] = frozenset(),
) -> bool:
    """Whether this node's obligations are owed live evidence, or are only context.

    Three conditions, all from the book rather than from inference. The node must be
    *grounded* — at least one `code:` ref that resolves in base or head — because a node
    whose `code:` is empty documents something nobody has built yet, and a QA plan cannot
    exercise a route or a component that has no implementation. And it must be reached by
    the diff directly rather than only by graph closure, because the closure is deliberately
    broad: a single edited file drags in every flow that links to every contract it owns.
    Demanding live proof for the whole closure is what made the packet grow faster than the
    change did.

    The third is the same argument one level down, for the reach that is *not* closure. A
    `file-owner` reason is a bare-file citation with no symbol behind it, so it points at
    the node only as precisely as the file belongs to it. When several nodes cite the same
    file the citation stops localizing anything — an edit to a global stylesheet owed live
    proof for every component documented against it, which is a plan the change cannot
    justify and the planner cannot write. Those nodes stay in the packet as context; a node
    the diff also reached by an exact symbol keeps its own reason and stays required.

    A `changed-code` reason is demoted on the same test but at a higher count. An exact
    symbol localizes better than a bare file, so two nodes citing one is a book written
    well rather than a citation gone vague — the endpoint stating the wire contract and the
    concept stating the domain rule, both grounded in the function that implements them,
    both breakable by a change to it. It takes `_CONTAINER_FANOUT` owners before the
    citation reads as a container: the toolbar that owns every control documented against
    it, which marks all of them changed when one new control is added.
    """
    kinds = {
        reason.get("kind", "")
        for reason in direct_reasons.get(node_id, [])
        if not (reason.get("kind") == "file-owner" and reason.get("ref") in shared_files)
        and not (reason.get("kind") == "changed-code" and reason.get("ref") in shared_symbols)
    }
    return node_id in grounded and bool(kinds - _CONTEXT_ONLY_REASON_KINDS)


def _journey_is_required(
    node_id: str,
    direct_reasons: dict[str, list[dict[str, str]]],
    required_contracts: set[str],
    end_edges: set[tuple[str, str]],
) -> bool:
    """Whether this flow is owed live evidence, or is only context.

    Not `_is_required`. That rule asks whether the diff reached the node directly and
    whether the node is *grounded* — and a flow carries no `code:` bullet at all, so it can
    never be grounded and the answer was structurally `False` for every flow in every repo.
    The two metrics that measure a plan against its journeys have therefore never had a
    denominator to divide by.

    What makes a flow owed is one hop away: the story is proven against a contract, and the
    flow is the document that says where in the product that contract is reached from and
    what state the operator is left in. So a flow is required when it links a contract that
    is itself required — the same diff-directness test, read through the link that made the
    flow part of this packet. A flow reached only via context-only contracts stays context,
    which is what keeps one edited endpoint from owing a walk of every journey it appears in.

    The link has to be the `end:` one, and that is not a narrowing for tidiness. A journey's
    obligation is its *end state*, and a story that builds a step in the middle of a walk
    cannot reach it: a CLI story that ships `init` and `add` would owe an end state only
    `export` produces, in a story where `export` does not exist yet. The story that delivers
    the destination is the one that can walk the whole thing, and it is the one asked to.

    An `end:` that names a whole document is satisfied by a required section *inside* it,
    because that is where a screen's requiredness actually lands: a flow ends at
    `screens/policy-detail.md` while the story's diff is grounded in
    `policy-detail.md#policy-summary`, and reading those as different destinations left
    every journey in the corpus context-only. Containment is one level and one direction —
    a document takes its anchors, an anchor takes nothing — so an `end:` naming a section
    still means that section, and a story ending elsewhere in the same file is not
    conscripted into walking it.

    Reaching the destination is necessary and not sufficient, because two journeys routinely
    end on the same screen: `create-policy` and `edit-policy` both finish at the policy
    detail, so the story that builds that screen reaches the end of both while implementing
    one. So the story must also ground a required contract the flow reaches *somewhere other
    than its end* — the field it fills, the button it presses, the screen it passes through.
    That is the part of a walk a story either built or did not, and it is what tells the
    journey this story delivered apart from the one that merely shares its last screen.

    Where the `end:` is prose rather than a link, the walk's last link stands in for it (see
    `_serialized_graph`), so both readings apply to every flow and neither has an exemption to
    be reasoned about separately.
    """
    reasons = [
        reason
        for reason in direct_reasons.get(node_id, [])
        if reason.get("kind") == "flow-links-contract"
        and _reaches_a_required_contract(str(reason.get("ref") or ""), required_contracts)
    ]
    reaches_the_end = any((node_id, reason.get("ref")) in end_edges for reason in reasons)
    walks_the_route = any((node_id, reason.get("ref")) not in end_edges for reason in reasons)
    return reaches_the_end and walks_the_route


def _reaches_a_required_contract(ref: str, required_contracts: set[str]) -> bool:
    """The linked node is required, or — for a whole document — some section of it is."""
    if ref in required_contracts:
        return True
    if "#" in ref:
        return False
    return any(contract.startswith(f"{ref}#") for contract in required_contracts)


#: What a check row carries about a `(locator)` argument, resolved against the book at packet
#: time. `node` is the `component`/`interaction` the argument names and `""` when it names
#: none; `locators` is that node's own `role:`/`name:`/`selector:`, so a compiler can point a
#: driver at what the *check* names without re-walking the graph — and without being free to
#: resolve the reference differently from the doctor rule that passed the book.
LocatorTarget = dict[str, Any]


def _parse_checks(
    values: list[str],
    resolve: Callable[[str], LocatorTarget] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for value in values:
        parsed = checks_mod.parse_check(value)
        if not isinstance(parsed, checks_mod.CheckCall):
            continue
        row: dict[str, Any] = {"call": parsed.text(), "name": parsed.name, "args": parsed.args}
        if resolve is not None:
            located = {
                param.name: resolve(str(parsed.args[param.name]))
                for param in checks_mod.CHECK_BY_NAME[parsed.name].params
                if param.locator and param.name in parsed.args
            }
            if located:
                row["locates"] = located
        rows.append(row)
    return rows


def _unparsed_checks(values: list[str]) -> list[dict[str, Any]]:
    """The `verify:` bullets among *values* the parser read and refused, with its own account.

    Carried, not dropped, for the reason `_unparsed_fixtures` above is: `_parse_checks` builds a
    row only from a value that parsed, so downstream a node that declared no observation and a
    node whose observation nobody could read arrive identically — with no `checksDeclared` — and
    `compile_plan` gaps the second `no-verify-declared`, *"the book declares no check for this
    obligation to prove"*, at an author who declared one. `ostler doctor` does refuse the bullet
    by name (`unparsed-check`), which makes this worse rather than better: the two readers then
    disagree in writing about the same bullet, and the one that decides whether to emit code is
    the one holding the wrong account.

    The refusal's own `kind` rides along with its sentence because a refusal *classifies* — a
    test reference written under `verify:` is not a typo in an argument — and `parse_check` is
    the only thing that looked. Re-deriving either here is how the message and the suggestion
    came to contradict each other in `doctor` once already.
    """
    rows: list[dict[str, Any]] = []
    for value in values:
        parsed = checks_mod.parse_check(value)
        if isinstance(parsed, checks_mod.Refusal):
            rows.append({"value": value, "kind": parsed.kind, "problem": parsed.message})
    return list({row["value"]: row for row in rows}.values())


def _locator_resolver(
    graph: Graph, nodes_by_id: dict[str, dict[str, Any]], node: dict[str, Any]
) -> Callable[[str], LocatorTarget]:
    """Resolve this node's check locators against the book, the way `doctor` resolves them.

    Bound to one node because a `#anchor` is relative to the document it was written in. The
    empty `node` for an argument that names nothing is deliberate and is not a filtered-out
    row: `compile_plan` owes a gap for it, and a check row that simply omitted the field would
    be indistinguishable from one whose check takes no locator at all.
    """
    origin = graph.root / str(node.get("path", ""))

    def resolve(value: str) -> LocatorTarget:
        located = locators_mod.located_node(graph, value, origin)
        if located is None:
            return {"node": "", "locators": {}}
        serialized = nodes_by_id.get(located.id)
        return {
            "node": located.id,
            "locators": _locators(serialized) if serialized is not None else {},
        }

    return resolve


def _dedup_checks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list({row["call"]: row for row in rows}.values())


def _fixture_provides_index(nodes_by_id: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    """Every book fixture's own `provides:` keys, plus every one reachable through `needs:`.

    Keyed by the fixture node's stem — the same name a `fixture:`/`needs:` bullet cites and
    `_parse_fixtures` records as `row["name"]` — so a caller holding a fixture row can look its
    reachable keys up without re-walking the graph. Each entry is spelled `<owner>.<key>`, the
    same `@<node>.<key>` shape a reference uses: a fixture `needs:` another only composes its
    state, it does not relabel it, so a reference to `@needed-fixture.key` still names the
    fixture that actually declared it, not the one that pulled it in. `compile_plan` is the
    caller: it needs to know every reference a scenario's arranged fixtures resolve, including
    one supplied only by a fixture *that* fixture `needs:`.
    """
    resolved = _fixture_provides_closure(nodes_by_id)
    return {name: sorted(ref for ref, _ in pairs) for name, pairs in resolved.items()}


def _fixture_undetermined_index(nodes_by_id: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    """Every reachable `provides:` key whose *source* the book left undetermined, by fixture stem.

    A fact is observed — `from:` a step, `read:` a path in its stdout — or asserted by the
    fixture's own construction with `is:`. An entry declaring neither, or declaring both, says
    nothing a harness can act on, and the harness aborts the whole scenario when it reaches one.
    So this is what `compile_plan` gaps on: *undetermined ⇒ do not emit executable code*. It
    rides the same `needs:` closure as the keys themselves, because arranging a fixture runs the
    fixtures it needs, and their extraction aborts just as hard.

    `ostler doctor` reports the same condition per entry as `undetermined-provided-fact`. The two
    are not redundant: the doctor tells an author their book is under-specified, and this tells a
    compiler which obligations it must refuse rather than compile into a scenario that dies.
    """
    resolved = _fixture_provides_closure(nodes_by_id)
    return {name: sorted(ref for ref, bad in pairs if bad) for name, pairs in resolved.items()}


def _fixture_provides_closure(
    nodes_by_id: dict[str, dict[str, Any]],
) -> dict[str, set[tuple[str, bool]]]:
    """`{fixture stem: {(`<owner>.<key>`, source-undetermined), ...}}` over the `needs:` closure."""
    fixtures = {node_id: node for node_id, node in nodes_by_id.items() if node.get("type") == "fixture"}
    provides: dict[str, set[tuple[str, bool]]] = {}
    needs: dict[str, set[str]] = {}
    for node_id, node in fixtures.items():
        keys: set[tuple[str, bool]] = set()
        entries = node.get("entries", {}).get("provides") or []
        stated = {}
        for entry in entries:
            head = str(entry.get("headline", "")).partition("—")[0].split()
            if head:
                stated[head[0]] = entry.get("properties") or {}
        for value in _values(node.get("bullets", {}).get("provides")):
            head = value.partition("—")[0].split()
            if not head:
                continue
            properties = stated.get(head[0], {})
            observed = bool(_property_text(properties.get("from")))
            asserted = bool(_property_text(properties.get("is")))
            keys.add((head[0], observed == asserted))
        provides[node_id] = keys
        needs[node_id] = {
            edge["to"] for edge in node.get("edges", [])
            if edge.get("via") == "needs" and edge.get("to") in fixtures
        }

    closure: dict[str, set[tuple[str, bool]]] = {}

    def resolve(node_id: str, seen: frozenset[str]) -> set[tuple[str, bool]]:
        if node_id in closure:
            return closure[node_id]
        if node_id in seen:
            return set()
        owner = Path(node_id).stem
        pairs = {(f"{owner}.{key}", bad) for key, bad in provides.get(node_id, ())}
        for dep in needs.get(node_id, ()):
            pairs |= resolve(dep, seen | {node_id})
        closure[node_id] = pairs
        return pairs

    return {Path(node_id).stem: resolve(node_id, frozenset()) for node_id in fixtures}


def _property_text(value: object) -> str:
    """One serialized entry property as its text — the JSON-side twin of `Entry.property_text`.

    The graph node dict is JSON, so the `Entry` that knows how to flatten its own property is
    gone by the time a packet reader sees it; only the `str | list[str]` it carried survives.
    """
    if isinstance(value, list):
        return " ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip() if value is not None else ""


def _parse_captures(values: list[str]) -> list[dict[str, Any]]:
    """The `capture: <name> from <json path | UI locator>` declarations among *values*.

    Deduped on name. A bullet that does not parse yields no row here and is carried instead
    by `_unparsed_captures` below — the division of labour `_parse_fixtures`/`_parse_checks`
    keep, and for the same reason: dropped, it is the same absent row as a node that declared
    no capture, and the damage surfaces on a later bullet whose `$name` then resolves against
    nothing at all.
    """
    rows: list[dict[str, Any]] = []
    for value in values:
        parsed = captures_mod.parse_bullet(value)
        if isinstance(parsed, captures_mod.CaptureDecl):
            rows.append({"name": parsed.name, "from": parsed.source})
    return list({row["name"]: row for row in rows}.values())


def _unparsed_captures(values: list[str]) -> list[dict[str, Any]]:
    """The `capture:` bullets among *values* the parser read and refused, with its own account.

    Deduped on the bullet text, not on a name — a refused bullet has no name, which is the
    whole of what is wrong with it.
    """
    rows: list[dict[str, Any]] = []
    for value in values:
        parsed = captures_mod.parse_bullet(value)
        if isinstance(parsed, str):
            rows.append({"value": value, "problem": parsed})
    return list({row["value"]: row for row in rows}.values())


def _parse_acts(
    values: list[str],
    resolve: Callable[[str], LocatorTarget] | None = None,
) -> list[dict[str, Any]]:
    """The acts among *values*, in document order, each with its locator arguments resolved.

    Order is load-bearing here in a way it is not for fixtures, and that is why these rows are
    deduped on the canonical call text rather than collapsed on a name: filling `name-field`
    and then `quantity-field` is two performances, and `fill` twice on the same field is a
    correction the author wrote on purpose. `_parse_fixtures` may key on `(name, args)` because
    running the same fixture twice reaches the same state; performing the same act twice does
    not.

    `locates` mirrors `_parse_checks` exactly. An act's locator is a reference into the book
    (F17), so the packet carries what it resolved to, and an argument that resolves to nothing
    keeps its empty row rather than vanishing — `compile_plan` owes a gap for it, and a row
    that dropped the field would be indistinguishable from an act that takes no locator.
    """
    rows: list[dict[str, Any]] = []
    for value in values:
        parsed = acts_mod.parse_act(value)
        if not isinstance(parsed, acts_mod.ActCall):
            continue
        row: dict[str, Any] = {"call": parsed.text(), "name": parsed.name, "args": parsed.args}
        if resolve is not None:
            located = {
                param.name: resolve(parsed.args[param.name])
                for param in acts_mod.ACT_BY_NAME[parsed.name].params
                if param.locator and param.name in parsed.args
            }
            if located:
                row["locates"] = located
        rows.append(row)
    return list({row["call"]: row for row in rows}.values())


def _unparsed_acts(values: list[str]) -> list[dict[str, Any]]:
    """The `arrange:` bullets among *values* the act parser read and refused, with its account.

    Carried for the reason `_unparsed_checks` and `_unparsed_fixtures` are: downstream, a
    bullet nobody wrote and a bullet that did not parse are the same absent row, and the one
    reader that decides whether to emit code must not gap *"nothing arranges this"* at an
    author who arranged it and mistyped. The refusal's `kind` rides along because a refusal
    classifies — a bare fixture name written under `arrange:` is a misfiled bullet, not a typo
    in an argument — and `parse_act` is the only thing that looked.
    """
    rows: list[dict[str, Any]] = []
    for value in values:
        parsed = acts_mod.parse_act(value)
        if isinstance(parsed, checks_mod.Refusal):
            rows.append({"value": value, "kind": parsed.kind, "problem": parsed.message})
    return list({row["value"]: row for row in rows}.values())


def _parse_fixtures(
    values: list[str],
    fixture_provides: dict[str, list[str]] | None = None,
    fixture_undetermined: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """The declared arrangements among *values*, in order, deduped on name and arguments.

    A bullet that does not parse yields no row here and is carried instead by
    `_unparsed_fixtures` below, which says why the packet cannot simply drop it.
    `fixture_provides` — a book fixture's own
    keys plus its `needs:` closure, each spelled `<owner>.<key>` — rides along on each row so
    `compile_plan` can tell what an arrangement makes available without re-walking the graph.
    """
    rows: list[dict[str, Any]] = []
    for value in values:
        parsed = fixtures_mod.parse_bullet(value)
        if isinstance(parsed, fixtures_mod.FixtureRef):
            row = {"name": parsed.name, "args": list(parsed.args), "provides": parsed.provides}
            keys = (fixture_provides or {}).get(parsed.name)
            if keys:
                row["providesKeys"] = keys
            # …and of those, the ones whose source the book left undetermined. Carried
            # separately rather than dropped from `providesKeys`, because the two answer
            # different questions: what this arrangement makes available, and what about it
            # `compile_plan` must refuse to emit code for.
            undetermined = (fixture_undetermined or {}).get(parsed.name)
            if undetermined:
                row["providesUndetermined"] = undetermined
            rows.append(row)
    return list({(row["name"], tuple(row["args"])): row for row in rows}.values())


def _unparsed_fixtures(values: list[str]) -> list[dict[str, Any]]:
    """The `fixture:` bullets among *values* the parser read and rejected, with its sentence.

    Carried, not dropped. `_parse_fixtures` above builds a row only from a value that parsed,
    and for years this function did not exist, on the stated ground that the packet says what
    the book successfully declared and `ostler doctor` says what it tried to. That division
    holds for a reader that reports to an author and fails for the one reader that has to
    decide whether to emit code: downstream, a bullet nobody wrote and a bullet that did not
    parse are the same absent row. So a flow whose `fixture:` bullet had a typo in it was
    gapped `unarranged-journey` — *"add a `fixture:` naming the arrangement"* — at an author
    who had added one, and the advice was to do the thing already done.

    The parser is the only reader that saw the text fail, so its own sentence rides along
    rather than being re-derived here from the value. `compile_plan` turns each of these into
    an `unparsed-fixture` gap and compiles nothing for the obligation, because the state its
    claim is documented in is undetermined and undetermined does not become executable.
    """
    rows: list[dict[str, Any]] = []
    for value in values:
        parsed = fixtures_mod.parse_bullet(value)
        if isinstance(parsed, str):
            rows.append({"value": value, "problem": parsed})
    return list({row["value"]: row for row in rows}.values())


def _no_arrangement_stated(values: list[str]) -> bool:
    """True when one of *values* is a `fixture:` bullet stating this node arranges nothing.

    Carried beside `fixturesDeclared` rather than folded into it, because the two answer
    different questions and a compiler needs both: the rows say what is arranged, and this
    says whether an empty list of rows is a decision or a silence. Collapsing them would
    give a node that decided it needs no arrangement the same packet as a node whose author
    never looked — which is the state `unarranged-journey` was added to keep apart.
    """
    return any(
        isinstance(fixtures_mod.parse_bullet(value), fixtures_mod.NoArrangement)
        for value in values
    )


def _locators(node: dict[str, Any]) -> dict[str, list[str]]:
    declared = registry.declared_keys(node.get("type", ""))
    bullets = node.get("bullets", {})
    return {
        _LOCATOR_KEY_RENAME.get(key, key): _values(bullets.get(key))
        for key in _LOCATOR_KEYS
        if key in declared and _values(bullets.get(key))
    }


def _extends_target(
    node: dict[str, Any], nodes_by_id: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any] | None, bool]:
    """The base node an `extends:` arm inherits its control identity from (D51).

    Returns `(target, malformed)`. `target` is the resolved node when `extends:` names one
    that exists and shares this node's type — an interaction arm extends an interaction, an
    invocation arm an invocation, never across the two. `malformed` is True when `extends:`
    was stated but the target is missing or of the wrong type, which `_obligations` stamps
    onto the obligation for `compile.py` to turn into a gap, mirroring
    `unresolved-precondition`. A node with no `extends:` edge at all returns `(None, False)`
    — plain absence, not a defect.

    Nothing here is restricted to the two arm types: `component` and `concept` declare
    `extends:` too, and all four node-type pages define it the same way — "this node is a
    specialization of that one". What differs is what a *caller* does with the base. D51's
    call site in `_obligations` gates on `("interaction", "invocation")` because inheriting a
    **control identity** — `on:`, `trigger:`, `role:`, `name:`, `keyboard:` — is a fact about
    an arm, and a component inherits no such thing. `_family_root` asks a different question
    — "is this one documented thing or two?" — which every specialization answers the same
    way, so it gates on nothing.
    """
    to_ids = [
        edge.get("to")
        for edge in node.get("edges") or []
        if edge.get("via") == "extends" and edge.get("to")
    ]
    if not to_ids:
        return None, False
    target = nodes_by_id.get(str(to_ids[0]))
    if target is None or target.get("type") != node.get("type"):
        return None, True
    return target, False


def _same_as_targets(
    node: dict[str, Any], nodes_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """The nodes *node*'s `same-as:` bullet resolves to, in document order.

    Unlike `extends:`, `same-as:` is multi-valued — the motivating case is one shared
    control documented on several screens, so a node can name two or three siblings at
    once — and it carries no type restriction: the claim is "this is the same documented
    thing", not "this is a narrower version of that type". A dangling target is dropped
    here rather than flagged; that is `unresolved-relation`'s finding, not this reader's.
    """
    return [
        target
        for edge in node.get("edges") or []
        if edge.get("via") == "same-as" and edge.get("to")
        for target in [nodes_by_id.get(str(edge["to"]))]
        if target is not None
    ]


def _same_as_component(node_id: str, nodes_by_id: dict[str, dict[str, Any]]) -> frozenset[str]:
    """Every node id reachable from *node_id* by following declared `same-as:` edges,
    *node_id* included.

    `same-as:` is a symmetric claim — doctor's `one-way-same-as` requires the reciprocal
    bullet on both ends — so in a conformant book each edge is discoverable from either
    side by following only forward edges: A's own `same-as:` names B and B's own
    `same-as:` names A back, so a walk that starts at A reaches B by A's edge and a walk
    that starts at B reaches A by B's edge. That is what makes this BFS return the *same*
    set of ids regardless of which member of the family it starts from — the property
    `_family_root` needs to pick one deterministic root for a family of any size, rather
    than land on a different node depending on which member a caller happened to ask
    about first. A one-way declaration (a doctor-flagged defect) can make the two starting
    points disagree; that is an accepted consequence of the underlying book being wrong,
    not of this walk.
    """
    seen = {node_id}
    frontier = [node_id]
    while frontier:
        current = frontier.pop()
        node = nodes_by_id.get(current)
        if node is None:
            continue
        for target in _same_as_targets(node, nodes_by_id):
            target_id = str(target["id"])
            if target_id not in seen:
                seen.add(target_id)
                frontier.append(target_id)
    return frozenset(seen)


def _document_of(node_id: str) -> str:
    """The document part of a node id — everything ahead of its first `#`.

    Distinct from `drivers._document`, which parses an *obligation* id (`okf:`-prefixed,
    `.md`-suffixed head required) and reads `""` for one that names no document at all. A
    node id always names a document; there is no degenerate case to guard here.
    """
    return node_id.split("#", 1)[0]


def _linked_surface(
    node: dict[str, Any], value: Any, nodes_by_id: dict[str, dict[str, Any]]
) -> str:
    """The surface of the node *value*'s own links point at — "" when they point at none.

    A `flow` is not performed by anything: it orders steps that are. So the surface its own
    `start:`/`end:` claims are observed on is a property of the nodes those bullets name, not of
    the directory the flow file happens to sit in — a journey a user walks out of a mobile app
    and finishes in a browser ends on the web surface whichever book records it. `surface` is
    what `compile.py` keys the owning `driver:` off, so stamping the linked node's surface is
    what lets a crossing journey's end-state be observed by a driver that can see it.

    Read off the bullet's own links rather than off `edges`' `via`, for the reason
    `_serialized_graph` gives: `via` keeps the *first* bullet an href appeared under, so a flow
    whose `end:` names the screen its `start:` already named has that edge attributed to `start`
    and no `end` edge at all. The href is unambiguous where the attribution is not.
    """
    hrefs = {
        href
        for item in _values(value)
        for _text, href in markdown.extract_refs(item).links
    }
    if not hrefs:
        return ""
    for edge in node.get("edges") or []:
        target_id = edge.get("to")
        if not target_id or edge.get("href") not in hrefs:
            continue
        target = nodes_by_id.get(str(target_id))
        if target and target.get("surface"):
            return str(target["surface"])
    return ""


def _journey_steps(
    node: dict[str, Any], nodes_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, str]]:
    """The nodes a flow's `steps:` names, in the order the book wrote them.

    A journey's claim is about what the sequence produced, so the sequence is part of the
    claim and has to reach the stage that would walk it. Until this existed the packet said
    only that a flow *links* these nodes: every `steps:` target arrived as one more
    `flow-links-contract` entry under `reasons`, in a set, indistinguishable from what
    `start:`, `end:` and `fixture:` named. A set of links is not a sequence, and a compiler
    handed one cannot perform a journey — it can only assert the end state on arrival, in a
    world the steps never ran in, which is exactly what `compile.py`'s flow branch refuses
    to do.

    Read off the bullet's own links rather than off `edges`' `via`, for the reason
    `_linked_surface` and `_serialized_graph` both give: `via` keeps the *first* bullet an
    href appeared under, so a flow whose `steps:` walks back through the screen its `start:`
    already named loses that step entirely. The href is unambiguous where the attribution is
    not; `edges` is consulted only to recover the node id an href already resolved to.

    Each step carries its own `nodeType` and `surface`, because those are what D1's dispatch
    table keys on: a step is performed by whatever drives the surface *it* lives on, not the
    one the flow's `end:` is observed on. A step whose link resolves to nothing is kept with
    an empty `ref` rather than dropped — dropping it would hand the next stage a shorter walk
    that still looks complete, and a journey compiled one step short asserts its end state in
    a world it did not reach. An absence is not an event.
    """
    resolved = {
        str(edge["href"]): str(edge["to"])
        for edge in node.get("edges") or []
        if edge.get("to") and edge.get("href")
    }
    walk: list[dict[str, str]] = []
    for item in _values(node.get("bullets", {}).get("steps")):
        for _text, href in markdown.extract_refs(item).links:
            target_id = resolved.get(href, "")
            target = nodes_by_id.get(target_id, {}) if target_id else {}
            walk.append({
                "ref": target_id,
                "href": href,
                "nodeType": str(target.get("type") or ""),
                "surface": str(target.get("surface") or ""),
            })
    return walk


def _family_root(node_id: str, owners: set[str], nodes_by_id: dict[str, dict[str, Any]]) -> str:
    """The declared-family root *node_id* belongs to among *owners*, for `_CONTAINER_FANOUT`.

    Walks exactly three kinds of declared structure to one root, the three questions that
    settle whether two nodes are independent implementations or one: a `same-as:` claim —
    this node and the node it names are one documented thing, rendered or reached in more
    than one place, the
    *declared* answer to the question the fan-out count used to guess at from citation
    counting alone — an `extends:` base case — a three-arm split says "these nodes are one
    documented control", a narrower, type-matched version of the same claim — and a section
    node's containing file (`path#anchor` collapses to `path`) — a file plus its own `###`
    subsections is one documented surface, not several. All three say "this is not a second
    thing, it is the first thing described again," so all members must count as one family
    before the fan-out count runs, the same way a citation nobody's own arm makes
    distinguishing still counts as one control rather than three.

    The `extends:` walk is type-agnostic, because doctor's exclusion is: it asks only
    whether an `extends:` edge lands inside the group, and all four types that own the key
    — `concept`, `component`, `interaction`, `invocation` — define it as specialization.
    Gating this walk on the two arm types instead would have counted a component and the
    component it specializes as two fan-out owners where doctor counts them as one family,
    which is the whole thing this helper exists to avoid.

    `same-as:` is resolved differently from `extends:` because it is multi-valued — the
    motivating case is one shared control documented on several screens, so a node can name
    several siblings at once — which makes "follow the target" ambiguous: which of several
    edges is *the* next hop depends on document order, and a walk that picks one arbitrarily
    can land two members of the same family on two different roots. So rather than following
    a single edge, this collapses *every* node reachable over declared `same-as:` edges
    (`_same_as_component`, transitively, in both directions as declared) into one
    deterministic representative — `min()` of the ids — before trying `extends:` or
    containment. `min()` is arbitrary but total and id-derived, so every member of the
    family computes the same representative independent of where the walk started, which is
    the only property this needs: a root that's the same for the whole family, not a
    "correct" one.

    The containment walk only collapses onto a file id that is itself one of *owners* —
    mirroring doctor.py's membership check (`b.id.startswith(f"{a.id}#")` where `a` is
    also one of the citing nodes) rather than every section sharing a file. Sibling
    components that merely share a `parent:` page, with no file-level citation of their
    own, are *not* collapsed: three buttons on one screen citing the screen's renderer
    are three distinct fan-out owners, not one, because the screen itself never cites
    the symbol — collapsing them would hide genuine fan-out rather than guard against a
    false one. Undeclared sprawl — unrelated nodes that each happen to cite the same
    symbol with no edge between them — does not collapse either: only an edge the book
    itself stated walks the chain.
    """
    seen: set[str] = set()
    current = node_id
    while current not in seen:
        seen.add(current)
        same_as_root = min(_same_as_component(current, nodes_by_id))
        if same_as_root != current:
            current = same_as_root
            continue
        node = nodes_by_id.get(current)
        if node is not None:
            target, _malformed = _extends_target(node, nodes_by_id)
            if target is not None:
                current = str(target["id"])
                continue
        file_id, sep, _anchor = current.partition("#")
        if sep and file_id in owners:
            current = file_id
            continue
        break
    return current


def _repeat(node: dict[str, Any], scope: tuple[str, ...]) -> dict[str, Any] | None:
    """The compiled repeat contract for a node in a `one-per:` scope, or None.

    Everything a planner needs to sample the family is lifted here — the iteration variable,
    the compiled name-template segments, the bindable holes, and the declared distinctness and
    variant axes — so `qa plan` can hold a scenario to concrete instances without re-reading
    the book. A node outside any repeated scope gets no block, which keeps the packet
    byte-identical for every book that never declares `one-per:`.
    """
    own = locators_mod.repeat_of(node)
    scope = scope or ((own,) if own else ())
    if not scope:
        return None
    repeat: dict[str, Any] = {"onePer": scope[-1], "binds": []}
    located = locators_mod.locator_for(node, scope=scope)
    if located["strategy"] == "template":
        repeat.update(
            {
                "template": located["template"],
                "iterates": located["iterates"],
                "segments": located["segments"],
                "binds": located["binds"],
            }
        )
    unique = locators_mod.unique_by_of(node)
    if unique:
        repeat["uniqueBy"] = unique
    variants = locators_mod.variants_of(node)
    if variants:
        repeat["variants"] = variants
    return repeat


def _obligations(
    node: dict[str, Any],
    reasons: list[dict[str, str]],
    *,
    journey: bool,
    required: bool = True,
    owed_keys: frozenset[str] | None = None,
    scope: tuple[str, ...] = (),
    judgment: list[dict[str, Any]] | None = None,
    fixture_provides: dict[str, list[str]] | None = None,
    fixture_undetermined: dict[str, list[str]] | None = None,
    resolve_locator: Callable[[str], LocatorTarget] | None = None,
    nodes_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Mint one obligation per normative bullet, plus the node-level contract.

    `owed_keys` narrows what a *required* node owes live evidence for. It is `None` for a node
    the change reached, which owes all of it; it names the relation keys for a node reached
    only by sharing a subject with one, which is at risk through the record they share and not
    through the refusal shapes it documents on its own account.

    An obligation id is minted off *node*'s `same-as:` family representative
    (`min(_same_as_component(node["id"], nodes_by_id))`), not off `node["id"]` itself — the
    family is the relation to collapse on, because `same-as:` is the book's own claim that
    several occurrences are one documented thing, and `doctor`'s `same-as-disagreement` check
    (b5762af3) refuses a book where the family disagrees on a `registry.normative_keys` value,
    which is what makes collapsing the *requirement* sound: nothing discharges a claim no
    member actually made. It is the requirement alone that check polices. The per-occurrence
    fields on `base` — `surface`, `locators`, `source` — are the representative's, and
    `locator:` is normative on no type, so a family whose members are looked at differently
    (two surfaces, two locators for one control) keeps one way of observing it and drops the
    rest silently. Every family in the corpus today is single-surface and agrees on its
    locator; a cross-surface family needs this to carry occupancy the way
    `occurrenceDocuments` does below, not a representative. `_family_root` is deliberately not used here — it also folds in `extends:` (a
    specialization, whose narrower claim a base case's evidence must not silently discharge)
    and file/section containment (a different question about `_CONTAINER_FANOUT`'s fan-out
    count) — neither belongs in "is this the same documented fact".

    This function still runs once per member: every occurrence keeps minting its own
    obligations from its own bullets, so a member that states a key its siblings leave silent
    (legal — `same-as:` exists precisely so a repeat can be written cheaply) still contributes
    that obligation, under the family id. Nothing here merges the *nodes*; the collapse is
    entirely in what id two calls to this function produce, and it is `build_context`'s
    dedupe-by-id, after sorting, that turns byte-identical requirements written on several
    occurrences into one obligation.

    `nodes_by_id` is `None` only for callers with no graph context (there are none among
    `context.py`'s own callers today, both of which already pass it); such a caller gets the
    pre-collapse behavior, minting straight off `node["id"]`.

    `occurrenceDocuments` carries the other half of what the collapse costs a consumer: once
    an id names a family rather than one occurrence, the id itself can no longer answer "on
    which document does this obligation sit" — a `_covers_in`-shaped narrowing that used to
    parse the document out of the id would silently start answering for the representative's
    document only, which is exactly the defect this field exists to prevent. It is every
    `<document>` part of the family (`_same_as_component`, not `_family_root` — see above),
    sorted, and it is always present and never empty: a node in no family still occupies its
    own document, so the field degrades to that one entry rather than being omitted, and a
    consumer that reads it never needs a fallback for the solo case.
    """
    family = (
        _same_as_component(str(node["id"]), nodes_by_id)
        if nodes_by_id is not None
        else frozenset({str(node["id"])})
    )
    representative = min(family)
    occurrence_documents = sorted({_document_of(member) for member in family})
    suffix = "end-state" if journey else "contract"
    base = {
        "id": f"okf:{representative}:{suffix}",
        "kind": "journey" if journey else "contract",
        "node": node["id"],
        "occurrenceDocuments": occurrence_documents,
        # D1's dispatch table keys on the link-target node's *type* (interaction, endpoint,
        # command, invocation/method, screen) crossed with the owning surface's `driver:` —
        # compile.py reads this rather than re-deriving it from `checksDeclared`, which is
        # what let two `does:` bullets on the same node compile under two different drivers.
        "nodeType": node.get("type", ""),
        "source": node["path"],
        # The key into `packet["navigation"]` this node's screen route lives under (Option C /
        # Amendment 1) — a screen-addressed obligation is compiled by looking up
        # `navigation[surface].routes[source]`, and this is how compile.py finds that surface
        # without re-deriving it from the path the way `graph.py`'s own surface inference does.
        "surface": node.get("surface") or "",
        "requirement": node.get("title") or node["id"],
        "required": required,
        "evidenceRequired": "live" if required else "context",
        "reasons": reasons or [{"kind": "graph-closure", "ref": node["id"]}],
    }
    # A journey's end-state is observed at the node its `end:` names, so that node's surface is
    # the one whose `driver:` can see it — see `_linked_surface`.
    if nodes_by_id is not None and node.get("type") == "flow":
        end_surface = _linked_surface(node, node.get("bullets", {}).get("end"), nodes_by_id)
        if end_surface:
            base["surface"] = end_surface
        # The journey itself, ordered. Rides on `base`, so every obligation this flow mints
        # carries the same walk — a flow's `start:`, `end:` and its own `verify:` are all
        # claims about what these steps did, and each of them needs the sequence to be
        # discharged by anything other than an arrival.
        walk = _journey_steps(node, nodes_by_id)
        if walk:
            base["steps"] = walk
    locators = _locators(node)
    if nodes_by_id is not None and node.get("type") in ("interaction", "invocation"):
        extends_target, extends_malformed = _extends_target(node, nodes_by_id)
        if extends_target is not None:
            # Own bullets win: an arm states its own `when:`/`does:` and, when it has one, its
            # own `role:`/`name:`; only what it left silent is filled from the base case (D51).
            locators = {**_locators(extends_target), **locators}
        elif extends_malformed:
            base["extendsUnresolved"] = True
    if locators:
        base["locators"] = locators
    repeat = _repeat(node, scope)
    if repeat:
        base["repeat"] = repeat
    # Per bullet, not per node. A node-level list credits every obligation the node mints with
    # every check the node declares, so one discriminating call covers a sibling claim that
    # nothing observes — the claim rides on an assertion that was never about it. The book
    # already writes each check under the claim it observes; `registry.attributed_checks` reads it.
    # A nested claim list that said its children are alternatives binds a check to none of them:
    # a check written for one branch refutes the others, so fanning it out would file a
    # refutation as a proof. `registry._attributed` applies it; this is where the word reaches it.
    combiners = {int(pos): str(word) for pos, word in (node.get("combiners") or {}).items()}
    contract, per_bullet = registry.attributed_checks(
        str(node.get("type", "")), node.get("bulletOrder") or [], combiners
    )
    # The claims whose nested list never said how its children combine. Stamped rather than
    # dropped: the obligation is real and a planner still has to read it, but nothing may emit
    # an assertion against it, because the check written above it observes either all of these
    # children or exactly one of them and the book does not say which. `compile_plan` turns the
    # stamp into a gap; the predicate lives in `registry` so it cannot drift from the rule
    # `doctor` refuses the book with.
    undetermined = {
        claim
        for group in registry.undetermined_claims(
            str(node.get("type", "")), node.get("bulletOrder") or [], combiners).values()
        for claim in group
    }
    contract_rows = _dedup_checks(_parse_checks(contract, resolve_locator))
    if contract_rows:
        base["checksDeclared"] = contract_rows
    contract_unparsed = _unparsed_checks(contract)
    if contract_unparsed:
        base["checksUnparsed"] = contract_unparsed
    # A fixture written above every claim arranges the state the node as a whole is documented
    # in, so it rides on `base` and reaches every obligation minted below — see
    # `registry.attributed_fixtures` for why that differs from how a leading check is filed.
    node_fixtures, fixtures_per_bullet = registry.attributed_fixtures(
        str(node.get("type", "")), node.get("bulletOrder") or [], combiners
    )
    ambient = _parse_fixtures(node_fixtures, fixture_provides, fixture_undetermined)
    if ambient:
        base["fixturesDeclared"] = ambient
    ambient_unparsed = _unparsed_fixtures(node_fixtures)
    if ambient_unparsed:
        base["fixturesUnparsed"] = ambient_unparsed
    ambient_nothing = _no_arrangement_stated(node_fixtures)
    if ambient_nothing:
        base["arrangesNothing"] = True
    # The other arrangement family, bound by the same rule and read by a different parser. A
    # `when:` over what the user typed is state no fixture can reach, so the acts that
    # establish it are the only account of the world the claim below is about — carried here
    # rather than left to the compiler to infer from prose.
    node_acts, acts_per_bullet = registry.attributed_acts(
        str(node.get("type", "")), node.get("bulletOrder") or [], combiners
    )
    ambient_acts = _parse_acts(node_acts, resolve_locator)
    if ambient_acts:
        base["actsDeclared"] = ambient_acts
    ambient_acts_unparsed = _unparsed_acts(node_acts)
    if ambient_acts_unparsed:
        base["actsUnparsed"] = ambient_acts_unparsed
    # Unlike a fixture, a capture belongs to the one bullet whose action produces it — it does
    # not ride ambient on every obligation the node mints, so the per-bullet half is the only
    # one that yields `capturesDeclared`, the same shape `attributed_checks` yields.
    captures_contract, captures_per_bullet = registry.attributed_captures(
        str(node.get("type", "")), node.get("bulletOrder") or [], combiners
    )
    # A *refusal* is not a capture, though, and that asymmetry is deliberate: the contract half
    # is dropped above because a node-level capture credits no bullet's action, but a bullet the
    # parser could not read is an observation about the node's own text, and the node-level
    # obligation is where the node's own text lands. Dropped here too, it would be reported by
    # nobody — which is the defect this stamping exists to close. The per-bullet branch below
    # pops it back off each copy, so it rides once rather than on every obligation the node mints.
    contract_captures_unparsed = _unparsed_captures(captures_contract)
    if contract_captures_unparsed:
        base["capturesUnparsed"] = contract_captures_unparsed
    # Where each normative bullet actually sits on the page. `obligations` is later sorted by
    # `_sort_key`, which orders by id — alphabetical on the key name, not by where the author
    # wrote it — so a producer walk that wants the book's own order (a capture read before the
    # reference that consumes it, say) needs this stamped independently of that resort.
    #
    # `bullet_order`'s own ordinal (`row[2]`) is a position within *this node's* section — it
    # resets for every node, so it is only comparable between obligations minted here. A scenario
    # can owe evidence for several nodes that share one file (`by_source` groups by path, and a
    # book runs several `### id` sections per file), so the node's own file-absolute heading line
    # goes in front of it: two nodes never share a line, and within one node the line is constant,
    # leaving the bullet ordinal to break the tie exactly as it did before.
    node_line = int(node.get("line") or 0)
    doc_position: dict[tuple[str, int], int] = {}
    _seen = {key: 0 for key in registry.normative_keys(str(node.get("type", "")))}
    for row in node.get("bulletOrder") or []:
        row_key = str(row[0])
        if row_key in _seen:
            _seen[row_key] += 1
            doc_position[(row_key, _seen[row_key])] = int(row[2])
    base["docPosition"] = [node_line, -1]
    output = [base]
    for key in registry.normative_keys(str(node.get("type", ""))):
        for index, requirement in enumerate(_values(node.get("bullets", {}).get(key)), start=1):
            obligation = {
                **base,
                "id": f"okf:{representative}:{key.replace(' ', '-')}:{index}",
                "kind": key.replace(" ", "-"),
                "requirement": requirement,
                "docPosition": [node_line, doc_position.get((key, index), 0)],
            }
            # The claim a planner reads is the prose alone, exactly as it read before subjects
            # existed. The subject is lifted to its own field so the obligation says what it is
            # about rather than leaving the reader to parse an em dash out of the sentence.
            if key in RELATION_KEYS or key in _EVENT_KEYS:
                subject, prose = relation_subject(requirement)
                obligation["requirement"] = prose
                if subject is not None:
                    obligation["subject"] = subject
            # Each of a flow's own claims is observed at the node its own bullet names — a
            # journey that starts on one surface and ends on another owes its two claims to two
            # drivers, and only the bullet says which.
            if nodes_by_id is not None and node.get("type") == "flow":
                linked = _linked_surface(node, requirement, nodes_by_id)
                if linked:
                    obligation["surface"] = linked
            if (key, index) in undetermined:
                obligation["claimCombiner"] = "unstated"
            if required and owed_keys is not None and key not in owed_keys:
                obligation["required"] = False
                obligation["evidenceRequired"] = "context"
            rows = _dedup_checks(
                _parse_checks(per_bullet.get((key, index), []), resolve_locator))
            if rows:
                obligation["checksDeclared"] = rows
            else:
                obligation.pop("checksDeclared", None)
            refused = _unparsed_checks(per_bullet.get((key, index), []))
            if refused:
                obligation["checksUnparsed"] = refused
            else:
                obligation.pop("checksUnparsed", None)
            arranged = _parse_fixtures(
                fixtures_per_bullet.get((key, index), []), fixture_provides, fixture_undetermined)
            combined = list({(row["name"], tuple(row["args"])): row
                             for row in [*ambient, *arranged]}.values())
            if combined:
                obligation["fixturesDeclared"] = combined
            else:
                obligation.pop("fixturesDeclared", None)
            unparsed = list({row["value"]: row for row in [
                *ambient_unparsed,
                *_unparsed_fixtures(fixtures_per_bullet.get((key, index), [])),
            ]}.values())
            if unparsed:
                obligation["fixturesUnparsed"] = unparsed
            else:
                obligation.pop("fixturesUnparsed", None)
            if ambient_nothing or _no_arrangement_stated(
                fixtures_per_bullet.get((key, index), [])
            ):
                obligation["arrangesNothing"] = True
            else:
                obligation.pop("arrangesNothing", None)
            # Ambient first, then this claim's own: the acts run in the order the book wrote
            # them, and an act above every claim was written to run before all of them.
            performed = list({row["call"]: row for row in [
                *ambient_acts,
                *_parse_acts(acts_per_bullet.get((key, index), []), resolve_locator),
            ]}.values())
            if performed:
                obligation["actsDeclared"] = performed
            else:
                obligation.pop("actsDeclared", None)
            refused_acts = list({row["value"]: row for row in [
                *ambient_acts_unparsed,
                *_unparsed_acts(acts_per_bullet.get((key, index), [])),
            ]}.values())
            if refused_acts:
                obligation["actsUnparsed"] = refused_acts
            else:
                obligation.pop("actsUnparsed", None)
            captures = _parse_captures(captures_per_bullet.get((key, index), []))
            if captures:
                obligation["capturesDeclared"] = captures
            else:
                obligation.pop("capturesDeclared", None)
            refused_captures = _unparsed_captures(captures_per_bullet.get((key, index), []))
            if refused_captures:
                obligation["capturesUnparsed"] = refused_captures
            else:
                obligation.pop("capturesUnparsed", None)
            output.append(obligation)
    # Attached after the loop on purpose: `base` *is* the node-level obligation already in
    # `output`, and the per-bullet `{**base}` copies were taken before this line — so the
    # judgment and unspecified context ride once, on the node-level row, instead of being
    # duplicated onto every bullet the node mints.
    if judgment:
        base["judgment"] = judgment
    unspecified = [
        {
            "text": value,
            "citation": next((href for _t, href in markdown.extract_refs(value).links), ""),
        }
        for value in _values(node.get("bullets", {}).get("unspecified"))
    ]
    if unspecified:
        base["unspecified"] = unspecified
    return output


def _acceptance_criteria(story_file: Path | None) -> list[dict[str, str]]:
    if story_file is None or not story_file.is_file():
        return []
    doc = markdown.split(story_file.read_text(encoding="utf-8"))
    criteria: list[dict[str, str]] = []
    sections = (
        ("Acceptance Criteria", "ac", "functional"),
        ("Non-Functional Acceptance Criteria", "nfac", "non-functional"),
    )
    for heading, prefix, category in sections:
        section = doc.find_section(heading)
        if section is None:
            continue
        for index, bullet in enumerate(section.bullets, start=1):
            text = bullet.text.strip()
            match = _AC_RE.match(text)
            number, requirement = (match.group(1), match.group(2)) if match else (str(index), text)
            criteria.append({
                "id": f"{prefix}:{number}",
                "requirement": requirement,
                "kind": "behavioral",
                "category": category,
            })
    return criteria


def _story_identity(story_file: Path | None) -> dict[str, str]:
    if story_file is None or not story_file.is_file():
        return {}
    frontmatter = markdown.split(story_file.read_text(encoding="utf-8")).frontmatter or {}
    values = {
        "id": str(frontmatter.get("id") or ""),
        "externalKey": str(frontmatter.get("externalKey") or ""),
        "slug": str(frontmatter.get("slug") or story_file.parent.name),
    }
    return {key: value for key, value in values.items() if value}
