"""Which book nodes own a change: the reasons a node is selected, and the families that cite each changed file and symbol."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from ostler import inventory, refs as refs_mod


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


@dataclass(frozen=True, slots=True)
class OwnerNode:
    """What one node can own a change by: the surface it sits on, and the code each of its owning bullets cites."""

    surface: str
    citations: Mapping[str, tuple[str, ...]]


class ReasonKind(StrEnum):
    """Why a node is selected into the context."""

    BOOK_CLAIM = "book-claim"
    CHANGED_CODE = "changed-code"
    FILE_OWNER = "file-owner"
    SURFACE_OWNER = "surface-owner"
    CONTAINS_IMPACTED_NODE = "contains-impacted-node"
    FLOW_LINKS_CONTRACT = "flow-links-contract"
    FLOW_CONTRACT_CLOSURE = "flow-contract-closure"
    GRAPH_CLOSURE = "graph-closure"
    JUDGMENT_CONTEXT = "judgment-context"
    EVENT_CONSUMER = "event-consumer"
    EVENT_PRODUCER = "event-producer"
    RELATION_OF_REQUIRED = "relation-of-required"
    CONSISTENCY = "consistency"
    CONSISTENCY_RULE = "consistency-rule"
    CONSISTENCY_GROUP = "consistency-group"
    PERSISTENCE = "persistence"
    EVENT = "event"
    CONCURRENCY = "concurrency"
    IDEMPOTENCY = "idempotency"


@dataclass(frozen=True, slots=True)
class Reason:
    """Why one node is selected: how, what it points at, and the bullet key that cites it."""

    kind: ReasonKind
    ref: str
    key: str = ""

    def row(self) -> dict[str, str]:
        """The reason as the packet lists it."""
        return {"kind": self.kind.value, "ref": self.ref, **({"key": self.key} if self.key else {})}


def relation_reason_kind(key: str) -> ReasonKind:
    """The reason kind a shared relation bullet key selects a node by."""
    return ReasonKind(key.replace(" ", "-"))


@dataclass(frozen=True, slots=True)
class UnmappedChange:
    """A changed production unit no node owns by symbol, file or surface."""

    path: str

    def row(self) -> dict[str, str]:
        """The change as the packet's health lists it."""
        return {
            "kind": "unmapped-change",
            "severity": "error",
            "path": self.path,
            "message": "changed production unit has no exact symbol, file, or surface owner",
        }


@dataclass(frozen=True, slots=True)
class MappedChanges:
    """Each node's reasons for owning a change, the changes nothing owns, and the owners of each changed file and symbol."""

    reasons: dict[str, list[Reason]]
    unmapped: list[UnmappedChange]
    file_owners: dict[str, set[str]]
    symbol_owners: dict[str, set[str]]


@dataclass(frozen=True, slots=True)
class CitingFamilyCounts:
    """How many declared families cite each changed file and each changed symbol."""

    files: Mapping[str, int]
    symbols: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class SharedCitations:
    """The changed files and symbols whose owners are context rather than required."""

    files: frozenset[str] = frozenset()
    symbols: frozenset[str] = frozenset()


FamilyRoot = Callable[[str, set[str]], str]

CONTAINER_FANOUT = 3


def shared_citations(citing: CitingFamilyCounts) -> SharedCitations:
    """The files and symbols cited by many families, so a change to a shared helper does not owe live evidence for every node."""
    return SharedCitations(
        frozenset(ref for ref, count in citing.files.items() if count > 1),
        frozenset(ref for ref, count in citing.symbols.items() if count >= CONTAINER_FANOUT),
    )


def no_demotion(_citing: CitingFamilyCounts) -> SharedCitations:
    """No file or symbol, for a whole-book context that has no change to be proportional to."""
    return SharedCitations()


def source_ref(repository: str, path: str, symbol: str = "") -> str:
    return refs_mod.render_code_ref(refs_mod.CodeRef(repository, path, symbol))


def ref_owns_change(value: str, change: ChangedUnit) -> bool:
    """Whether one owning citation names either side of a changed source file."""
    try:
        cited = refs_mod.parse_code_ref(value)
    except ValueError:
        return False
    return (
        cited.repository == change.repository
        and cited.path in {change.base_path, change.head_path}
    )


def book_relative(path: str, book_root: str) -> str:
    """*path* (relative to `root`) rebased onto `book_root`; unchanged outside it."""
    if not book_root or not path:
        return path
    prefix = f"{book_root}/"
    return path[len(prefix):] if path.startswith(prefix) else path


def matching_refs(refs: set[str], cited: Sequence[str]) -> list[str]:
    """Citations in *cited* that name something in *refs*, tolerant of symbol spelling."""
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


def surface_owner(path: str, roots: dict[str, list[str]]) -> str:
    matches = [
        (len(prefix.rstrip("/")), surface)
        for surface, prefixes in roots.items()
        for prefix in prefixes
        if prefix.rstrip("/") in ("", ".")
        or path == prefix.rstrip("/")
        or path.startswith(prefix.rstrip("/") + "/")
    ]
    return max(matches)[1] if matches else ""


def citing_family_counts(
    file_owners: Mapping[str, set[str]], symbol_owners: Mapping[str, set[str]], family_root: FamilyRoot
) -> CitingFamilyCounts:
    """Count the declared families whose nodes own each changed file and cite each changed symbol."""

    def family_count(owners: set[str]) -> int:
        return len({family_root(node_id, owners) for node_id in owners})

    return CitingFamilyCounts(
        {ref: family_count(owners) for ref, owners in file_owners.items()},
        {ref: family_count(owners) for ref, owners in symbol_owners.items()},
    )


def _changed_refs(change: ChangedUnit, base_path: str, head_path: str) -> set[str]:
    return {
        *(source_ref(change.repository, base_path, symbol) for symbol in change.base_symbols if change.base_path),
        *(source_ref(change.repository, head_path, symbol) for symbol in change.head_symbols if change.head_path),
    }


def map_changes(
    changes: Sequence[ChangedUnit],
    nodes: Mapping[str, OwnerNode],
    book_root: str,
    source_roots: dict[str, list[str]],
) -> MappedChanges:
    """Map each changed unit to the nodes that cite its symbols, own its file, or own its surface."""
    reasons: dict[str, list[Reason]] = {}
    file_owners: dict[str, set[str]] = {}
    symbol_owners: dict[str, set[str]] = {}
    unmapped: list[UnmappedChange] = []
    for change in changes:
        change_book_root = "" if change.repository else book_root
        book_change = replace(
            change,
            path=book_relative(change.path, change_book_root),
            base_path=book_relative(change.base_path, change_book_root),
            head_path=book_relative(change.head_path, change_book_root),
        )
        refs = _changed_refs(change, book_change.base_path, book_change.head_path)
        owned_ref = source_ref(change.repository, book_change.path)
        mapped = change.status == "deleted"
        for node_id, node in nodes.items():
            owned_file = False
            for key, cited in node.citations.items():
                exact = matching_refs(refs, cited)
                if exact:
                    mapped = True
                    for ref in exact:
                        reasons.setdefault(node_id, []).append(Reason(ReasonKind.CHANGED_CODE, ref, key))
                        symbol_owners.setdefault(ref, set()).add(node_id)
                elif not owned_file and any(ref_owns_change(item, book_change) for item in cited):
                    mapped = owned_file = True
                    reasons.setdefault(node_id, []).append(Reason(ReasonKind.FILE_OWNER, owned_ref, key))
                    file_owners.setdefault(owned_ref, set()).add(node_id)
        if mapped:
            continue
        surface = change.surface or surface_owner(change.path, source_roots)
        surface_nodes = [node_id for node_id, node in nodes.items() if surface and node.surface == surface]
        for node_id in surface_nodes:
            reasons.setdefault(node_id, []).append(Reason(ReasonKind.SURFACE_OWNER, f"{surface}:{owned_ref}"))
        if not surface_nodes:
            unmapped.append(UnmappedChange(owned_ref))
    return MappedChanges(reasons, unmapped, file_owners, symbol_owners)
