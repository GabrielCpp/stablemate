"""``ostler stamp``: write per-citation content-hash digests onto ``code:`` bullets.

Replaces the whole-book source catalog (:mod:`ostler.source_snapshots`) with a mark carried
by the citation itself. The catalog snapshotted every cited file into one 2.7 MB document with
no lock, rewritten whole on every repair — a race between concurrent writers, and a freshness
signal so coarse that *any* cited file advancing marked *every* node citing it "fresh", whether
or not that node's own citation had been re-read. A digest on the bullet is scoped to exactly
the file that one bullet cites, and only the bullet's own bytes change when it is restamped.

Whole-**file** granularity only, deliberately: a per-symbol digest would need the same content
inventory the catalog already builds (``ostler.inventory``), and this module does not import it.
A symbol's citation goes stale exactly when its file does — the file is what doctor already
watches for a missing declaration — so there is nothing a finer-grained hash would catch sooner.

Hashing matches :func:`ostler.source_snapshots._snapshot_file`'s recipe exactly — decode the
file as UTF-8 text, then hash the *text*, not the raw bytes — so a digest computed here and one
migrated from the catalog agree for a file nobody has touched.

Only this module writes ``@digest`` suffixes. Nothing else should: doctor reads them, a repair
prompt must never write or edit one, and only okf-builder's turn-finalize path calls ``ostler
stamp`` (on the nodes a turn actually edited, after that turn's own ``doctor --path`` passes).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from ostler.markdown import split
from ostler.model import Graph, UINode
from ostler.refs import normalize_ref, parse_code_ref
from ostler.source_snapshots import SourceCatalog, book_repository

#: 12 hex characters of a sha256 digest — plenty to catch a changed file, short enough to sit
#: in a bullet.
DIGEST_LENGTH = 12

#: A code span never contains a backtick (that is what makes it a span), so — unlike almost
#: everywhere else in this package, see `ostler.markdown`'s module docstring — a regex cannot
#: mis-split one. What still has to match the tokenizer's own rule is *where the leading run
#: ends*: a gap that is not whitespace/comma closes it, same as `leading_code_spans`.
_SPAN = re.compile(r"`(?P<inner>[^`]*)`(?:\s*@(?P<digest>[0-9a-f]{12}))?")


def digest_file(text: str) -> str:
    """The stamp for a file's contents.

    Matches `ostler.source_snapshots._snapshot_file`'s recipe — decode-then-hash, not raw
    bytes — so a digest stamped here and one migrated from the catalog compare equal for a
    file nobody has touched since the catalog was built.
    """
    return hashlib.sha256(text.encode()).hexdigest()[:DIGEST_LENGTH]


def restamp_leading_code_spans(value: str, digest_for: Callable[[str], str | None]) -> str:
    """Rewrite a ``code:`` bullet's leading run of backtick-quoted targets with fresh digests.

    ``digest_for(target)`` is called with each target's own text (backticks and any existing
    ``@digest`` stripped) and returns the digest to stamp, or ``None`` to leave that target
    unstamped. Separators and anything after the leading run — a trailing gloss, prose — are
    returned byte-for-byte unchanged; a value that does not open with a code span is returned
    unchanged entirely.
    """
    matches = list(_SPAN.finditer(value))
    if not matches or value[:matches[0].start()].strip(" \t\r\n"):
        return value
    out: list[str] = []
    pos = 0
    for i, m in enumerate(matches):
        gap = value[pos:m.start()]
        if i and gap.strip(" \t\r\n,"):
            break  # prose between targets — the leading run is over
        out.append(gap)
        inner = m.group("inner")
        digest = digest_for(inner)
        out.append(f"`{inner}`" + (f" @{digest}" if digest else ""))
        pos = m.end()
    out.append(value[pos:])
    return "".join(out)


@dataclass(frozen=True, slots=True)
class StampResult:
    """What stamping one page did."""

    page: str
    stamped: int
    unresolved: list[str] = field(default_factory=list)
    changed: bool = False


def stamp_page(root: Path, features_root: Path, page: str, *,
                line_ranges: list[tuple[int, int]] | None = None,
                only_targets: dict[tuple[int, int], frozenset[str]] | None = None) -> StampResult:
    """Stamp a book page's ``code:`` bullets with their cited files' current digests.

    ``page`` is repo-relative, resolved against ``root``. A target this checkout cannot read —
    a missing file, or a ``repo://`` target naming a repository other than the book's own
    declared one (:func:`ostler.source_snapshots.book_repository`) — is left unstamped rather
    than guessed at; ``unstamped-citation`` is how doctor is meant to surface that, not a
    fabricated digest. Repository-qualified checkouts are not resolved here yet — only the
    graph's own repository (an unqualified ref, or one qualified with the book's own id).

    ``line_ranges``, when given, is a list of ``(start, end)`` 1-based file-line pairs (*end*
    exclusive) — a node's own extent, heading to next heading. Only bullets whose leading line
    falls in one of them are restamped; every other ``code:`` bullet on the page is left byte
    for byte alone. ``None`` restamps the whole page, which is what ``--whole-page`` asks for —
    no okf-builder workflow does; a turn only ever finishes editing specific nodes.

    ``only_targets``, when given, further narrows one of those ranges to the specific cited
    files a caller decided to restamp — a repair turn's regrounding row assigns a citation to
    one file, not to every ``code:`` target the node happens to carry, and restamping the rest
    would mark them freshly-read when nothing re-checked them. Keyed by the same ``(start,
    end)`` tuple as its ``line_ranges`` entry; a range absent from the mapping (or the mapping
    itself being ``None``) is unrestricted, same as today.
    """
    path = root / page
    text = path.read_text(encoding="utf-8")
    doc = split(text)
    repository = book_repository(features_root)
    unresolved: list[str] = []
    stamped = 0

    def in_scope(bullet_line_start: int) -> bool:
        if line_ranges is None:
            return True
        absolute = bullet_line_start + doc.body_offset + 1  # 0-indexed body -> 1-based file
        return any(start <= absolute < end for start, end in line_ranges)

    def allowed_targets(bullet_line_start: int) -> frozenset[str] | None:
        if not only_targets or line_ranges is None:
            return None
        absolute = bullet_line_start + doc.body_offset + 1
        for start, end in line_ranges:
            if start <= absolute < end and (start, end) in only_targets:
                return only_targets[(start, end)]
        return None

    def make_digest_for(targets: frozenset[str] | None) -> Callable[[str], str | None]:
        def digest_for(raw_target: str) -> str | None:
            nonlocal stamped
            normalized = normalize_ref(raw_target)
            try:
                ref = parse_code_ref(normalized)
            except ValueError:
                unresolved.append(raw_target)
                return None
            if ref.repository and ref.repository != repository:
                unresolved.append(raw_target)
                return None
            if targets is not None and ref.path not in targets:
                return None  # not this row's assignment: left exactly as it was, no digest
            try:
                source_text = (root / ref.path).read_text(encoding="utf-8")
            except OSError:
                unresolved.append(raw_target)
                return None
            stamped += 1
            return digest_file(source_text)
        return digest_for

    body_lines = doc.body.split("\n")
    changed = False
    for bullet in doc.walk_bullets():
        if bullet.label != "code":
            continue
        if not in_scope(bullet.line_start):
            continue
        raw = "\n".join(body_lines[bullet.line_start:bullet.line_end])
        key, sep, rest = raw.partition(":")
        if not sep:
            continue
        new_rest = restamp_leading_code_spans(rest, make_digest_for(allowed_targets(bullet.line_start)))
        if new_rest == rest:
            continue
        new_lines = (key + ":" + new_rest).split("\n")
        if len(new_lines) != bullet.line_end - bullet.line_start:
            # A digest never adds or removes a line; a mismatch means the bullet's raw slice
            # was not what was expected (e.g. it nests another list) — leave it alone rather
            # than risk corrupting the file, but say so: a silently-skipped bullet reads as
            # stamped to anyone who only checks `stamped`/`changed`.
            unresolved.append(raw)
            continue
        body_lines[bullet.line_start:bullet.line_end] = new_lines
        changed = True

    if changed:
        doc.replace_body(body_lines)
        path.write_text(doc.render(), encoding="utf-8")

    return StampResult(page=page, stamped=stamped, unresolved=unresolved, changed=changed)


def node_line_range(graph: Graph, node: UINode) -> tuple[int, int]:
    """*node*'s own extent — its heading line up to (exclusive) the next node on its page.

    Mirrors `ostler.cli`'s private `_node_line_range`, the shape `--node` stamping already
    ships with (landed for the CLI in a prior commit); this is the same logic exposed for an
    in-process caller that already holds a loaded `Graph`.
    """
    siblings = sorted(
        (n.line for n in graph.ui_nodes if n.path == node.path and n.line > node.line),
    )
    end = siblings[0] if siblings else len(node.path.read_text(encoding="utf-8").splitlines()) + 1
    return node.line, end


def stamp_targets(
    graph: Graph, features_root: Path, pairs: Iterable[tuple[str, str]],
) -> list[StampResult]:
    """Stamp exactly the ``(node, cited-file)`` pairs given — never a node's other citations.

    Mirrors ``ostler stamp --node <id> --file <path>`` (repeatable), as an in-process call for
    a caller that already holds a loaded `Graph` — okf-builder's turn-finalize step, which must
    not shell out (ostler is called as a library there, never a subprocess). ``pairs`` may name
    the same node more than once, once per file it should stamp; a node id this graph does not
    resolve is reported back via a synthetic result rather than raising, so one bad pair does
    not abort every other stamp the turn is entitled to.
    """
    pages: dict[str, list[tuple[int, int]]] = {}
    only_targets: dict[str, dict[tuple[int, int], set[str]]] = {}
    unresolved: list[str] = []
    for node_id, file_target in pairs:
        node = graph.find_ui_node(node_id)
        if node is None:
            unresolved.append(node_id)
            continue
        rel = node.path.relative_to(graph.root).as_posix()
        node_range = node_line_range(graph, node)
        pages.setdefault(rel, []).append(node_range)
        only_targets.setdefault(rel, {}).setdefault(node_range, set()).add(file_target)
    results = [
        stamp_page(
            graph.root, features_root, rel, line_ranges=ranges,
            only_targets={r: frozenset(t) for r, t in only_targets[rel].items()},
        )
        for rel, ranges in pages.items()
    ]
    if unresolved:
        results.append(StampResult(page="", stamped=0, unresolved=unresolved))
    return results


def stamp_page_from_catalog(root: Path, page: str, catalog: SourceCatalog) -> StampResult:
    """Migrate a page's ``code:`` bullets onto the digests the whole-book catalog already has.

    Stamps with the *catalog's* recorded digest for the cited file, never the file's current
    bytes — a file that has drifted on disk since the catalog was last advanced must show
    `stale-citation` the moment doctor next runs, not look freshly re-read just because
    migration touched its bullet. This is the one caller allowed to do that; everywhere else,
    a stamp is supposed to mean "read as of now."

    Unlike `stamp_page`, this resolves every target the catalog has a row for, including one
    qualified with a repository other than the book's own — the catalog already snapshotted
    those checkouts when it was built, so there is no live checkout to be missing here. A
    target with no catalog row (new since the catalog was last written, or never grounded)
    is left unstamped, same as `stamp_page` leaves an unreadable one — `unstamped-citation`
    or `unreachable-citation` is how doctor surfaces that afterward, not this function.
    """
    path = root / page
    text = path.read_text(encoding="utf-8")
    doc = split(text)
    unresolved: list[str] = []
    stamped = 0

    def digest_for(raw_target: str) -> str | None:
        nonlocal stamped
        normalized = normalize_ref(raw_target)
        try:
            ref = parse_code_ref(normalized)
        except ValueError:
            unresolved.append(raw_target)
            return None
        snapshot = catalog.repository(ref.repository)
        source = (
            next((item for item in snapshot.files if item.path == ref.path), None)
            if snapshot else None
        )
        if source is None:
            unresolved.append(raw_target)
            return None
        stamped += 1
        return source.content_sha256[:DIGEST_LENGTH]

    body_lines = doc.body.split("\n")
    changed = False
    for bullet in doc.walk_bullets():
        if bullet.label != "code":
            continue
        raw = "\n".join(body_lines[bullet.line_start:bullet.line_end])
        key, sep, rest = raw.partition(":")
        if not sep:
            continue
        new_rest = restamp_leading_code_spans(rest, digest_for)
        if new_rest == rest:
            continue
        new_lines = (key + ":" + new_rest).split("\n")
        if len(new_lines) != bullet.line_end - bullet.line_start:
            unresolved.append(raw)
            continue
        body_lines[bullet.line_start:bullet.line_end] = new_lines
        changed = True

    if changed:
        doc.replace_body(body_lines)
        path.write_text(doc.render(), encoding="utf-8")

    return StampResult(page=page, stamped=stamped, unresolved=unresolved, changed=changed)
