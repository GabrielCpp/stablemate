"""``ostler stamp``: write per-citation content-hash digests onto ``code:`` bullets."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from ostler.markdown import split
from ostler.model import Graph, UINode
from ostler.provenance import checkout_for
from ostler.refs import bare_targets, normalize_ref, parse_code_ref
from ostler.registry import EMPTY_TOKENS
from ostler.source_snapshots import SourceCatalog, book_repository

DIGEST_LENGTH = 12

_SPAN = re.compile(r"`(?P<inner>[^`]*)`(?:\s*@(?P<digest>[0-9a-f]{12}))?")

_BARE_DIGEST = re.compile(r"@[0-9a-f]{12}$")


def digest_file(data: bytes) -> str:
    """The stamp for a file's contents."""
    return hashlib.sha256(data).hexdigest()[:DIGEST_LENGTH]


def restamp_leading_code_spans(value: str, digest_for: Callable[[str], str | None]) -> str:
    """Rewrite a ``code:`` bullet's leading run of targets with fresh digests."""
    stripped = value.strip()
    if stripped.lower() in EMPTY_TOKENS:
        return value
    matches = list(_SPAN.finditer(value))
    if matches and not value[:matches[0].start()].strip(" \t\r\n"):
        out: list[str] = []
        pos = 0
        for i, m in enumerate(matches):
            gap = value[pos:m.start()]
            if i and gap.strip(" \t\r\n,"):
                break
            out.append(gap)
            inner = m.group("inner")
            digest = digest_for(inner)
            out.append(f"`{inner}` @{digest}" if digest else m.group(0))
            pos = m.end()
        out.append(value[pos:])
        return "".join(out)
    if matches:
        return value
    return _restamp_bare(value, digest_for)


def _restamp_bare(value: str, digest_for: Callable[[str], str | None]) -> str:
    """`restamp_leading_code_spans`'s fallback for a value with no leading backtick span."""
    out: list[str] = []
    for chunk, _, _ in bare_targets(value):
        core = chunk.strip()
        if not core:
            out.append(chunk)
            continue
        target = _BARE_DIGEST.sub("", core)
        digest = digest_for(target)
        if digest is None:
            out.append(chunk)
            continue
        lead = chunk[:len(chunk) - len(chunk.lstrip())]
        trail = chunk[len(chunk.rstrip()):]
        out.append(f"{lead}{target}@{digest}{trail}")
    return ",".join(out)


@dataclass(frozen=True, slots=True)
class StampResult:
    """What stamping one page did."""

    page: str
    stamped: int
    unresolved: list[str] = field(default_factory=list)
    changed: bool = False


def stamp_page(root: Path, features_root: Path, page: str, *,
                line_ranges: list[tuple[int, int]] | None = None,
                only_targets: dict[tuple[int, int], frozenset[str]] | None = None,
                checkouts: dict[str, Path] | None = None) -> StampResult:
    """Stamp a book page's ``code:`` bullets with their cited files' current digests."""
    path = root / page
    text = path.read_text(encoding="utf-8")
    doc = split(text)
    repository = book_repository(features_root)
    checkout_map = checkouts or {}
    unresolved: list[str] = []
    stamped = 0

    def in_scope(bullet_line_start: int) -> bool:
        if line_ranges is None:
            return True
        absolute = bullet_line_start + doc.body_offset + 1
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
            source_root = root
            if ref.repository and ref.repository != repository:
                checkout = checkout_for(ref.repository, checkout_map, default=repository)
                if checkout is None:
                    unresolved.append(raw_target)
                    return None
                source_root = checkout
            if targets is not None and ref.path not in targets:
                return None
            try:
                source_bytes = (source_root / ref.path).read_bytes()
            except OSError:
                unresolved.append(raw_target)
                return None
            stamped += 1
            return digest_file(source_bytes)
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
            unresolved.append(raw)
            continue
        body_lines[bullet.line_start:bullet.line_end] = new_lines
        changed = True

    if changed:
        doc.replace_body(body_lines)
        path.write_text(doc.render(), encoding="utf-8")

    return StampResult(page=page, stamped=stamped, unresolved=unresolved, changed=changed)


def node_line_range(graph: Graph, node: UINode) -> tuple[int, int]:
    """*node*'s own extent — its heading line up to (exclusive) the next node on its page."""
    siblings = sorted(
        (n.line for n in graph.ui_nodes if n.path == node.path and n.line > node.line),
    )
    end = siblings[0] if siblings else len(node.path.read_text(encoding="utf-8").splitlines()) + 1
    return node.line, end


def stamp_targets(
    graph: Graph, features_root: Path, pairs: Iterable[tuple[str, str]], *,
    checkouts: dict[str, Path] | None = None,
) -> list[StampResult]:
    """Stamp exactly the ``(node, cited-file)`` pairs given — never a node's other citations."""
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
            checkouts=checkouts,
        )
        for rel, ranges in pages.items()
    ]
    if unresolved:
        results.append(StampResult(page="", stamped=0, unresolved=unresolved))
    return results


def _legacy_text_digest(path: Path) -> str | None:
    """The retired catalog builder's own recipe: decode as UTF-8, then hash the *text*."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return hashlib.sha256(text.encode()).hexdigest()[:DIGEST_LENGTH]


def stamp_page_from_catalog(root: Path, page: str, catalog: SourceCatalog) -> StampResult:
    """Migrate a page's ``code:`` bullets onto the digests the whole-book catalog already has."""
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
        catalog_digest = source.content_sha256[:DIGEST_LENGTH]
        if not ref.repository:
            local_path = root / ref.path
            if _legacy_text_digest(local_path) == catalog_digest:
                try:
                    current_bytes = local_path.read_bytes()
                except OSError:
                    return catalog_digest
                return digest_file(current_bytes)
        return catalog_digest

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
