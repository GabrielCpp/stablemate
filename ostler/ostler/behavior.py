"""Public API for preparing bounded two-way behavior reviews and checking receipts.

Extraction supplies candidates, not semantic verdicts. Rebuild packets from current
source and graph before validating persisted receipts. Validation checks the external
review's shape and binding, never whether its explanations are true.
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import posixpath
import tokenize
from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Literal

from ostler import markdown, refs, registry, syntax
from ostler.behavior_go import GoEvidence
from ostler.behavior_models import (
    AuditPacket as AuditPacket, AuditPreparation as AuditPreparation,
    AuditReport as AuditReport, AuditVerdicts as AuditVerdicts,
    BehaviorEvidence as BehaviorEvidence, BookClaim as BookClaim, BookClaims as BookClaims,
    CandidateVerdict as CandidateVerdict, ClaimVerdict as ClaimVerdict,
    EvidenceFile as EvidenceFile, EvidenceInventory as EvidenceInventory,
    BookContext as BookContext, BookEvidenceRef as BookEvidenceRef, SourceContext as SourceContext,
    SourceExcerpt as SourceExcerpt, UndocumentedFile as UndocumentedFile,
)
from ostler.behavior_python import PythonEvidence
from ostler.behavior_tree import TABLES, TreeEvidence
from ostler.model import Graph

_LIMITATIONS = (
    "Python AST and Go/TypeScript/TSX/PHP tree-sitter candidates only; other languages remain unsupported. Twig templates are read by no extractor: the grammar is flat (an end tag is a sibling of its opening tag, not its parent), so enclosure and conditions cannot be read from the tree. No execution, call graph, data flow, inheritance, or semantic proof.",
    "Conditions describe lexical enclosure, not reachability; preceding guards and side effects are not inferred.",
    "Route/decorator, add_argument, and annotated-field framework identities are unresolved; syntax can be implementation detail.",
    "Python extracts explicit decorators, function defaults, raise/return statements, add_argument calls, and class annotated fields.",
    "Go extracts function/method/literal contracts, returns, panic-like calls, net/http-like registration/response calls, and struct fields with literal tags/types. Call bindings, JSON encoding, validation, build tags and interface dispatch are not resolved; similarly named non-HTTP calls may be candidates.",
    "TypeScript/TSX extracts function, method, arrow and class/interface/alias declarations, parameter defaults, return/throw statements, express-like registration/response member calls, and class fields/interface properties. Module bindings, decorators, JSX output, promise rejection and type narrowing are not resolved; similarly named non-HTTP member calls may be candidates. Exportedness follows the export keyword, a re-export clause, and member accessibility.",
    "PHP extracts function, method, closure and arrow-function contracts, parameter defaults, return statements, throw expressions, slim/laravel-like registration and psr-7-like response member calls, and class properties and constants. Namespaces, use imports, traits, attributes, magic methods and exception hierarchies are not resolved; similarly named non-HTTP member calls may be candidates. A top-level declaration is public; a member is public unless a private or protected modifier says otherwise.",
    "Source context retains enclosing functions and declarations. Python class context excludes unrelated methods and retrieves referenced module assignments lexically; Python functions with no candidates are not audited. Go retains full function/method/literal bodies and struct declarations, without resolving package bindings or delegated effects.",
    "Files outside the explicit source scope are not audited. Non-normative same-node book text is context, not additional obligations.",
    "Support context contains only explicitly selected Python, Go, TypeScript or PHP files, not automatic import closure; unselected delegated behavior remains unresolved. Support files do not add candidate obligations.",
    "Citation grouping is retrieval context, not semantic grounding. Reviewers must search source/book across files and sibling packets; use unresolved when local context is insufficient.",
    "Missing means an externally judged omission within the reviewed scope, not absence of a local citation. No packet or receipt asserts global completeness.",
)
_CACHE_DIRECTORIES = frozenset({"__pycache__", ".git", ".venv", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox", "node_modules"})


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def packet_digest(packet: AuditPacket) -> str:
    """The digest a packet carries: its whole content, the digest field itself excluded."""
    return _digest(packet.model_dump(mode="json", exclude={"digest"}))


def extract_evidence(root: Path, paths: Sequence[str], *, context_paths: Sequence[str] = ()) -> EvidenceInventory:
    """Read selected relative files/directories; retain every failed/unsupported file.

    Prefer explicit files or source directories, not a repository root. Directory
    walks prune named cache/environment directories and bytecode; excluded paths are
    recorded. Explicit file selectors still include such files. Empty selector lists
    are allowed for book-only reviews; an empty string is not a root-directory alias.
    Symlinks escaping root are rejected. No source or catalog is written.
    context_paths selects full Python or Go support files for every packet, without adding
    candidates. Directories are unsupported. Failures remain explicit limitations.
    """
    root = root.resolve()
    selected: set[str] = set()
    excluded: set[str] = set()
    empty_selectors: list[str] = []
    support_paths: set[str] = set()
    for raw in context_paths:
        if not raw.strip():
            raise ValueError("empty selector: supply an explicit Python or Go context file")
        path = Path(raw)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"context path must be relative and inside root: {raw}")
        if not (root / path).resolve().is_relative_to(root):
            raise ValueError(f"context path outside root: {raw}")
        support_paths.add(path.as_posix())

    def walk_error(error: OSError) -> None:
        raise error

    for raw in paths:
        if not raw.strip():
            raise ValueError("empty selector: supply an explicit file/directory or [] for a book-only review")
        path = Path(raw)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"source path must be relative and inside root: {raw}")
        target = root / path
        if not target.resolve().is_relative_to(root):
            raise ValueError(f"source path outside root: {raw}")
        entries = [target]
        if target.is_dir():
            entries = []
            for directory, subdirs, filenames in target.walk(on_error=walk_error):
                for name in subdirs[:]:
                    if name in _CACHE_DIRECTORIES:
                        subdirs.remove(name)
                        excluded.add((directory / name).relative_to(root).as_posix())
                for name in filenames:
                    entry = directory / name
                    if entry.suffix in {".pyc", ".pyo"} or entry.is_dir():
                        excluded.add(entry.relative_to(root).as_posix())
                    else:
                        entries.append(entry)
            if not entries:
                empty_selectors.append(path.as_posix())
        for entry in entries:
            if not entry.resolve().is_relative_to(root):
                raise ValueError(f"source path outside root: {entry.relative_to(root)}")
            if not entry.is_dir():
                selected.add(entry.relative_to(root).as_posix())
    files: list[EvidenceFile] = []
    candidates: list[BehaviorEvidence] = []
    source_context: list[SourceContext] = []
    support_context: list[SourceExcerpt] = []
    context_limitations: list[str] = []
    for relative in sorted(selected | support_paths):
        if relative in support_paths and (root / relative).is_dir():
            files.append(EvidenceFile(path=relative, status="unsupported",
                                      message="Support context requires explicit source files, not directories."))
            continue
        try:
            data = (root / relative).read_bytes()
        except OSError as exc:
            files.append(EvidenceFile(path=relative, status="unreadable", message=exc.strerror or type(exc).__name__))
            continue
        digest = hashlib.sha256(data).hexdigest()
        language = syntax.language_for(relative)
        table = TABLES.get(language) if language is not None else None
        if language is None or (language not in {"python", "go"} and table is None):
            files.append(EvidenceFile(path=relative, status="unsupported", source_digest=digest,
                                      message="Only Python, Go, TypeScript, TSX and PHP files have an extractor."))
            continue
        if language != "python":
            try:
                source = data.decode("utf-8")
                tree_root = syntax.parse(language, source)
                if tree_root.has_error:
                    raise SyntaxError(f"{relative}: {language} syntax tree contains errors; no partial evidence extracted")
            except (SyntaxError, UnicodeError) as exc:
                files.append(EvidenceFile(path=relative, status="parse_error", source_digest=digest, message=str(exc)))
                continue
            if relative in selected:
                tree_visitor = GoEvidence(relative, source, digest) if table is None else TreeEvidence(relative, source, digest, table)
                tree_visitor.visit(tree_root)
                candidates.extend(tree_visitor.candidates)
                source_context.extend(tree_visitor.source_context)
            if relative in support_paths:
                support_context.append(SourceExcerpt(path=relative, start_line=1,
                                                     end_line=max(1, len(source.splitlines())),
                                                     text=source, source_digest=digest))
            files.append(EvidenceFile(path=relative, status="parsed", source_digest=digest))
            continue
        try:
            encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
            source = data.decode(encoding)
            tree = ast.parse(source, filename=relative)
        except (SyntaxError, UnicodeError, LookupError) as exc:
            files.append(EvidenceFile(path=relative, status="parse_error", source_digest=digest,
                                      message=str(exc)))
            continue
        if relative in selected:
            visitor = PythonEvidence(relative, source, digest)
            visitor.visit(tree)
            candidates.extend(visitor.candidates)
            source_context.extend(visitor.source_context)
            context_limitations.extend(visitor.limitations)
        if relative in support_paths:
            support_context.append(SourceExcerpt(path=relative, start_line=1,
                                                 end_line=max(1, len(source.splitlines())),
                                                 text=source, source_digest=digest))
        files.append(EvidenceFile(path=relative, status="parsed", source_digest=digest))
    context_files = tuple(file for file in files if file.path in support_paths)
    files = [file for file in files if file.path in selected]
    limitations = (*_LIMITATIONS, *context_limitations,
                   *(f"Support context {file.path}: {file.status}: {file.message} Treat dependent behavior as unresolved."
                     for file in context_files if file.status != "parsed"),
                   "Directory selectors exclude " + ", ".join(sorted(_CACHE_DIRECTORIES)) + "; .pyc/.pyo files and directory symlinks are not traversed. Explicit file selectors override cache exclusions.",
                   *(f"Selector {selector} selected no source files after exclusions." for selector in sorted(empty_selectors)),
                   *(("No source files selected; this is not evidence of source coverage.",) if not files else ()))
    return EvidenceInventory(scope=tuple(sorted({Path(path).as_posix() for path in paths})), files=tuple(files),
                             candidates=tuple(candidates), limitations=limitations, excluded_paths=tuple(sorted(excluded)),
                             source_context=tuple(source_context), context_paths=tuple(sorted(support_paths)),
                             context_files=context_files, support_context=tuple(support_context),
                             grammar_version=syntax.grammar_version() if any(syntax.language_for(path) not in {None, "python"} for path in selected | support_paths) else "")


def extract_claims(graph: Graph) -> tuple[BookClaim, ...]:
    """The claims of `extract_book`, for callers that carry no limitations of their own."""
    return extract_book(graph).claims


def extract_book(graph: Graph, scope: str = "") -> BookClaims:
    """Use the real graph's normative bullets and existing QA obligation ID spelling.

    Titles and original same-node text are context, not synthetic semantic claims.
    Context ends at the first child heading, using the document parser's spans.
    When a node cites no source,
    use the nearest citing containment ancestor in the same document; do not inherit
    across documents or replace an explicit but incorrect citation. Citations guide
    file-local retrieval, never prove support. Locations come from the graph parser.

    `scope` is a repo-relative path prefix that limits which nodes are *read*: only
    documents under it are opened, re-hashed and checked against the graph's line
    numbers. Filtering the returned claims instead is not the same thing — the context
    read below re-reads every node's file off disk and raises when a section has moved
    underneath the graph, so an unscoped read makes one service's audit fail on another
    service's book while a concurrent writer is authoring it. The citation index above
    stays whole-graph on purpose: it answers whether *anything* in the book cites a
    symbol, and narrowing it would demote candidates cited only from a sibling book.
    """
    claims: list[BookClaim] = []
    by_id = {node.id: node for node in graph.ui_nodes}
    # No node id is spelled twice, so no claim is skipped for colliding with one. Two sections
    # sharing a heading used to share an id, and every claim under the second was dropped here
    # with a limitation naming `duplicate-container-heading` — a code that does not fire on the
    # shape that caused it, so the audit reported a repair nobody could make. `model.document_
    # anchors` now issues the anchor GitHub renders, which is unique within a document by
    # construction, and both sections are audited.
    limitations: tuple[str, ...] = ()
    documents: dict[Path, tuple[markdown.MarkdownDoc, str]] = {}
    cited_paths: set[str] = set()
    cited_symbols: set[str] = set()
    for node in graph.ui_nodes:
        for citation in refs.code_refs(node.meta.get("code")):
            try:
                ref = refs.parse_code_ref(citation)
            except ValueError:
                continue
            if not ref.repository:
                path = posixpath.normpath(ref.path)
                cited_paths.add(path)
                cited_symbols.add(f"{path}::{ref.symbol}" if ref.symbol else path)
    for node in sorted(graph.ui_nodes, key=lambda node: node.id):
        owner = node
        visited: set[str] = set()
        citations = tuple(refs.code_refs(owner.meta.get("code")))
        while not citations and owner.parent in by_id and owner.id not in visited:
            visited.add(owner.id)
            owner = by_id[owner.parent]
            if owner.path != node.path:
                break
            citations = tuple(refs.code_refs(owner.meta.get("code")))
        path = node.path.resolve().relative_to(graph.root.resolve()).as_posix()
        if scope and not path.startswith(scope):
            continue
        if not any(key in registry.normative_keys(node.type) for key, _, _ in node.bullet_order):
            continue
        if node.path not in documents:
            data = node.path.read_bytes()
            documents[node.path] = (markdown.split(data.decode("utf-8")), hashlib.sha256(data).hexdigest())
        doc, digest = documents[node.path]
        section = next((section for section in doc.walk_sections()
                        if doc.body_offset + section.line_start + 1 == node.line), None)
        if section is None:
            raise ValueError(f"Cannot locate book context for {node.id}; reload the graph from current documents")
        end = min((child.line_start for child in section.children), default=section.line_end)
        # end_line counts the lines actually supplied rather than trusting section.line_end:
        # a body ending in a newline splits to one more line than it has, so the file's last
        # section would otherwise advertise a line its own text does not carry, and a reviewer
        # citing that span is rejected as unseen.
        text = "".join(doc.body.splitlines(keepends=True)[section.line_start:end])
        context = BookContext(path=path, node=node.id, start_line=node.line,
                              end_line=node.line + max(1, len(text.splitlines())) - 1,
                              text=text, source_digest=digest)
        counts: dict[str, int] = defaultdict(int)
        for key, text, position in node.bullet_order:
            if key not in registry.normative_keys(node.type):
                continue
            counts[key] += 1
            kind = key.replace(" ", "-")
            claims.append(BookClaim(id=f"okf:{node.id}:{kind}:{counts[key]}", node=node.id,
                                    path=path, line=max(1, node.bullet_lines.get(position, node.line)), kind=kind, text=text,
                                    citations=citations, title=node.title, context=(context,)))
    return BookClaims(claims=tuple(claims), limitations=limitations, cited_paths=tuple(sorted(cited_paths)),
                      cited_symbols=tuple(sorted(cited_symbols)))


def exported_symbol(path: str, symbol: str, exported: bool | None = None) -> bool:
    """Whether a candidate's symbol is exported by its language's rule.

    Go exports a capitalized name, and a method is exported only on an exported type.
    Python exports a name with no leading underscore, at every level of nesting. The
    module itself (``<module>``) is never a symbol. This is the tier-1 rule the audit
    reads; a ``__all__`` that re-exports an underscored name is not consulted.
    TypeScript exports by keyword and PHP by modifier, not by spelling, so their extractors
    answer on the candidate (``BehaviorEvidence.exported``) and that answer wins when given.
    """
    if symbol == "<module>":
        return False
    if exported is not None:
        return exported
    parts = symbol.split(".")
    if path.endswith(".go"):
        return all(part[:1].isupper() for part in parts)
    return all(part and not part.startswith("_") for part in parts)


def cited_symbol(path: str, symbol: str, cited_symbols: frozenset[str]) -> bool:
    """Whether the book cites this symbol: by name, by an enclosing name, or by its whole file."""
    if path in cited_symbols:
        return True
    parts = symbol.split(".")
    return any(f"{path}::{'.'.join(parts[:depth])}" in cited_symbols for depth in range(1, len(parts) + 1))


def candidate_tier(path: str, symbol: str, cited_symbols: frozenset[str], exported: bool | None = None) -> Literal[1, 2]:
    """Tier 1 is what the book cites or the language exports; tier 2 is the private rest.

    The builder audits tier 1. Tier 2 — an uncited symbol its language keeps private —
    is reviewed only by ``ostler audit --tier all``: its behavior reaches a caller
    through some tier-1 symbol, and that is where a claim about it is checked. A
    module-level candidate has no name to keep private, so it is always tier 1.
    """
    if symbol == "<module>" or exported_symbol(path, symbol, exported) or cited_symbol(path, symbol, cited_symbols):
        return 1
    return 2


def undocumented_file(path: str, evidence: Sequence[BehaviorEvidence]) -> UndocumentedFile | None:
    """The deterministic finding for a parsed file no claim cites, or None to build packets."""
    first: dict[str, int] = {}
    for item in sorted(evidence, key=lambda item: (item.start_line, item.start_column, item.id)):
        if exported_symbol(path, item.symbol, item.exported):
            first.setdefault(item.symbol, item.start_line)
    if not first:
        return None
    return UndocumentedFile(path=path, candidate_count=len(evidence),
                            exported_symbols=tuple(first), first_lines=tuple(first.values()))


def build_audit_packets(
    inventory: EvidenceInventory, claims: Sequence[BookClaim] | BookClaims, *,
    max_items: int = 80, max_chars: int = 60_000, skip_undocumented: bool = True,
    tier: Literal[1, "all"] = 1, root: Path | None = None, context_lines: int = 40,
) -> AuditPreparation:
    """Prepare file-local review packets without an all-book Cartesian product.

    A `BookClaims` carries the book side's own limitations — the nodes whose claims were
    skipped — and every packet repeats them beside the inventory's, so a reviewer and a
    receipt both know what the book did not put in front of them.

    All symbols in a source file share its citing claims, even when the cited symbol
    is incorrect. Claims without a matching local file go into explicit book-only
    packets; files without citing claims retain all their candidates. Repository-
    qualified citations stay ungrounded: this inventory has no repository mapping.
    A parsed file with candidates on exported symbols that no claim and no book node
    cites (a `BookClaims` carries the book's ``cited_paths``) is a fact a rule can
    compute: it is listed under ``undocumented`` and no packet is built for it, so no
    reviewer turn is spent finding what the book never mentions. A file some node cites
    without a claim still reaches a reviewer, who reports what the book leaves out. A
    file whose candidates all sit on private symbols audits as before, and
    ``skip_undocumented=False`` builds every file's packet regardless.
    At ``tier=1`` (the default) only tier-1 candidates — cited by the book or exported
    by the language's rule (`candidate_tier`) — enter a packet; the rest are counted as
    ``deferred_candidates`` and named in the file's packet limitations (a file left with
    nothing to review builds no packet), and ``tier="all"`` reviews them too. Selected counts describe the tier, not the tree.
    With ``root``, a claim whose every citation names a file that exists under it but is
    outside the selected files is out of this audit's scope: counted as
    ``out_of_scope_claims``, named in every packet's limitations, and sent to no reviewer.
    Without ``root`` such claims stay ungrounded, since nothing can tell them from a
    citation of a file that is gone (the doctor's finding either way).
    A packet carries the generic extraction limitations and its own file's, never another
    file's. Each node's book excerpt is windowed to ``context_lines`` lines on either
    side of the packet's claims in it; a node whose section fits is carried whole.
    Oversized files cross only their own evidence/claim chunks, never other files.
    Per-packet omitted counts name context in sibling packets, not discarded work.
    The preparation's omitted counts are always zero. Item and serialized-character
    limits split packets; the character budget includes all deduplicated excerpts,
    spans and digests. An indivisible oversized context raises instead of truncating.
    Cross-file semantics require reviewer source/book search and unresolved decisions
    when local context cannot settle them. No verdict establishes global completeness.
    """
    if max_items < 2:
        raise ValueError("max_items must be at least 2")
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    if context_lines < 1:
        raise ValueError("context_lines must be positive")
    book_limitations: tuple[str, ...] = ()
    cited_paths: frozenset[str] = frozenset()
    cited_symbols: frozenset[str] = frozenset()
    if isinstance(claims, BookClaims):
        book_limitations = claims.limitations
        cited_paths = frozenset(claims.cited_paths)
        cited_symbols = frozenset(claims.cited_symbols)
        claims = claims.claims
    ordered_claims = tuple(sorted(claims, key=lambda claim: claim.id))
    _exact_ids([claim.id for claim in ordered_claims], {claim.id for claim in ordered_claims}, "input claims")
    _exact_ids([item.id for item in inventory.candidates], {item.id for item in inventory.candidates}, "input candidates")
    grouped: dict[str, list[BehaviorEvidence]] = {file.path: [] for file in inventory.files}
    deferred: dict[str, int] = defaultdict(int)
    for candidate in inventory.candidates:
        if tier == 1 and candidate_tier(candidate.path, candidate.symbol, cited_symbols, candidate.exported) == 2:
            deferred[candidate.path] += 1
            continue
        grouped.setdefault(candidate.path, []).append(candidate)
    selected = len(inventory.candidates) - sum(deferred.values())
    claims_by_file: dict[str, list[BookClaim]] = defaultdict(list)
    out_of_scope = 0
    for claim in ordered_claims:
        matches: set[str] = set()
        elsewhere: list[bool] = []
        for citation in refs.code_refs(list(claim.citations)):
            try:
                ref = refs.parse_code_ref(citation)
            except ValueError:
                # Malformed citations remain visible on the ungrounded claim.
                elsewhere.append(False)
                continue
            path = posixpath.normpath(ref.path)
            if not ref.repository and path in grouped:
                matches.add(path)
            elsewhere.append(not ref.repository and root is not None and (root / path).is_file())
        if not matches and elsewhere and all(elsewhere):
            out_of_scope += 1
            continue
        for module in sorted(matches) if matches else [""]:
            claims_by_file[module].append(claim)
    in_scope = {claim.id for claims_here in claims_by_file.values() for claim in claims_here}
    ordered_claims = tuple(claim for claim in ordered_claims if claim.id in in_scope)
    scope_limitations = ((f"{out_of_scope} claims cite only files outside the selected source scope and are not in "
                          "this audit; select those files to review them.",) if out_of_scope else ())
    file_limitations: dict[str, list[str]] = defaultdict(list)
    generic_limitations: list[str] = []
    for note in inventory.limitations:
        owner = next((file.path for file in inventory.files if note.startswith(f"{file.path}::")), None)
        (file_limitations[owner] if owner else generic_limitations).append(note)
    if "" in claims_by_file or not grouped:
        grouped[""] = []
    inventory_digest = _digest(inventory.model_dump(mode="json"))
    files_by_path = {file.path: file for file in inventory.files}
    packets: list[AuditPacket] = []
    undocumented: list[UndocumentedFile] = []
    for module, evidence in sorted(grouped.items()):
        local_claims = tuple(claims_by_file[module])
        evidence.sort(key=lambda item: (item.start_line, item.start_column, item.id))
        if (skip_undocumented and module in files_by_path and files_by_path[module].status == "parsed"
                and evidence and not local_claims and module not in cited_paths):
            finding = undocumented_file(module, evidence)
            if finding is not None:
                undocumented.append(finding)
                continue
        if deferred[module] and not evidence and not local_claims:
            # Every candidate is tier 2 and nothing cites the file: no review to hold.
            continue
        limitations = (*generic_limitations, *file_limitations[module], *book_limitations, *scope_limitations)
        if module in files_by_path:
            file = files_by_path[module]
            if file.status != "parsed":
                limitations += (f"{file.path}: {file.status}: {file.message}",)
            elif not evidence and not deferred[module]:
                limitations += (f"No behavior candidates extracted from {module}; this is not proof of no behavior.",)
        if deferred[module]:
            limitations += (f"{module}: {deferred[module]} tier-2 candidates (private, uncited symbols) are not in "
                            "this packet; `ostler audit --tier all` reviews them.",)
        if not module and local_claims:
            limitations += ("Ungrounded book-only packet: citations are absent, malformed, foreign, or outside the selected files. Search source before deciding support.",)
        size = max_items // 2 if local_claims else max_items
        claim_size = max_items - size if evidence and local_claims else max_items
        candidate_chunks = [tuple(evidence[i:i + size]) for i in range(0, len(evidence), size)] or [()]
        claim_chunks = [local_claims[i:i + claim_size] for i in range(0, len(local_claims), claim_size)] if local_claims else [()]
        pending = [(candidates, chunk) for candidates in candidate_chunks for chunk in claim_chunks]
        while pending:
            candidates, chunk = pending.pop(0)
            source_context = _outermost_contexts(
                context for context in inventory.source_context if context.path == module
                and any(context.symbol == "<module>" or candidate.symbol == context.symbol
                        or candidate.symbol.startswith(context.symbol + ".") for candidate in candidates))
            book_context = _windowed_book_context(chunk, context_lines)
            packet = AuditPacket(module=module, symbol="", scope=(module,) if module else (),
                                 group="source_file" if module else "ungrounded_book" if local_claims else "empty_scope",
                                 inventory_digest=inventory_digest, candidates=candidates,
                                 claims=tuple(claim.model_copy(update={"context": ()}) for claim in chunk),
                                  source_context=source_context, book_context=book_context,
                                  support_context=tuple(dict.fromkeys(inventory.support_context)),
                                 omitted_candidates=selected - len(candidates),
                                 omitted_claims=len(ordered_claims) - len(chunk), limitations=limitations)
            packet = packet.model_copy(update={"digest": packet_digest(packet)})
            if len(packet.model_dump_json()) <= max_chars:
                packets.append(packet)
            elif len(candidates) > 1:
                half = len(candidates) // 2
                pending[0:0] = [(candidates[:half], chunk), (candidates[half:], chunk)]
            elif len(chunk) > 1:
                half = len(chunk) // 2
                pending[0:0] = [(candidates, chunk[:half]), (candidates, chunk[half:])]
            else:
                raise ValueError(f"oversized packet for {module or 'ungrounded book'}: cannot fit max_chars={max_chars} without truncation")
    return AuditPreparation(inventory=inventory, packets=tuple(packets), undocumented=tuple(undocumented),
                            tier=tier, deferred_candidates=sum(deferred.values()), out_of_scope_claims=out_of_scope,
                            selected_candidates=selected, selected_claims=len(ordered_claims))


def _outermost_contexts(contexts: Iterable[SourceContext]) -> tuple[SourceContext, ...]:
    """*contexts* minus any whose lines another of them already spans, in inventory order.

    An enclosing declaration's excerpt is the text of every declaration nested in it, so a
    packet holding both — a test function and each closure it passes to ``t.Run`` — carried
    the same lines twice or more, and one long function was enough to push a single-candidate
    packet over its budget. Nothing is lost: the reviewer reads the nested lines inside the
    excerpt that survives. Two excerpts over identical lines keep the first, which is the
    enclosing declaration, because the extractors record a declaration before its members.
    """
    kept: list[SourceContext] = []
    ordered = list(contexts)
    for index, context in enumerate(ordered):
        enclosed = any(
            other.path == context.path
            and other.start_line <= context.start_line and context.end_line <= other.end_line
            and (other.start_line, other.end_line) != (context.start_line, context.end_line)
            for other in ordered
        ) or any(
            other.path == context.path and (other.start_line, other.end_line) == (context.start_line, context.end_line)
            for other in ordered[:index]
        )
        if not enclosed:
            kept.append(context)
    return tuple(kept)


def _windowed_book_context(chunk: Sequence[BookClaim], context_lines: int) -> tuple[BookContext, ...]:
    """One excerpt per node, bounded to ``context_lines`` around the chunk's claims in it."""
    by_node: dict[str, tuple[BookContext, list[int]]] = {}
    for claim in chunk:
        for context in claim.context:
            by_node.setdefault(context.node, (context, []))[1].append(claim.line)
    windowed: list[BookContext] = []
    for context, lines in by_node.values():
        start = max(context.start_line, min(lines) - context_lines)
        end = min(context.end_line, max(lines) + context_lines)
        if (start, end) == (context.start_line, context.end_line):
            windowed.append(context)
            continue
        text = "".join(context.text.splitlines(keepends=True)[start - context.start_line:end - context.start_line + 1])
        windowed.append(context.model_copy(update={"start_line": start, "end_line": end, "text": text}))
    return tuple(windowed)


def _exact_ids(actual: Sequence[str], expected: set[str], label: str) -> None:
    if len(actual) != len(set(actual)):
        raise ValueError(f"duplicate IDs in {label}: {actual}")
    if set(actual) != expected:
        raise ValueError(f"{label}: missing IDs {sorted(expected - set(actual))}; foreign IDs {sorted(set(actual) - expected)}")


def _check_claim_verdict(claim: ClaimVerdict, candidate_ids: set[str]) -> None:
    """The rules one claim verdict answers for on its own, apart from the whole reply."""
    _exact_ids(claim.candidate_ids, set(claim.candidate_ids) & candidate_ids, f"links for {claim.id}")
    if claim.status != "unresolved" and not claim.candidate_ids:
        raise ValueError(f"{claim.id}: {claim.status} requires candidate links")


def _check_candidate_verdict(packet: AuditPacket, candidate: CandidateVerdict) -> None:
    """The rules one candidate verdict answers for on its own, apart from the whole reply.

    Every book span it cites has to resolve to exactly one node of this packet's context
    and land on text that context actually carries. What is deliberately *not* here is
    the pair of cross-item rules — covered needs a supporting link, implementation_detail
    forbids one — because neither can be decided from a verdict alone.
    """
    if candidate.book_evidence and candidate.status != "covered":
        raise ValueError(f"{candidate.id}: {candidate.status} cannot carry book evidence")
    if len(candidate.book_evidence) != len(set(candidate.book_evidence)):
        raise ValueError(f"{candidate.id}: duplicate book evidence")
    for ref in candidate.book_evidence:
        contexts = [context for context in packet.book_context if context.node == ref.node]
        if len(contexts) != 1:
            raise ValueError(f"{candidate.id}: book evidence node is absent or ambiguous: {ref.node}")
        context = contexts[0]
        if not context.start_line <= ref.start_line <= ref.end_line <= context.end_line:
            raise ValueError(f"{candidate.id}: book evidence range outside context or reversed: {ref}")
        lines = context.text.splitlines()[ref.start_line - context.start_line:ref.end_line - context.start_line + 1]
        if len(lines) != ref.end_line - ref.start_line + 1 or not "\n".join(lines).strip():
            raise ValueError(f"{candidate.id}: book evidence range is unseen or blank: {ref}")


def validate_verdicts(packet: AuditPacket, payload: object) -> AuditReport:
    """Validate external decisions and links against this exact current packet.

    Raises ValueError (including Pydantic ValidationError) for invalid receipts. A
    valid receipt is an attributed external review, not an ostler semantic judgment.
    Links are stated once, on the claim; a candidate's claim links are derived from the
    claims that name it. Support/contradiction/partial claims require candidate links. Source coverage requires a supported/partial
    claim link or a resolvable book span, which establishes documentation, not QA proof.
    """
    current_digest = packet_digest(packet)
    if packet.digest != current_digest:
        raise ValueError("packet content digest does not match its contents")
    verdicts = AuditVerdicts.model_validate(payload)
    claim_ids = {claim.id for claim in packet.claims}
    candidate_ids = {candidate.id for candidate in packet.candidates}
    _exact_ids([claim.id for claim in verdicts.claims], claim_ids, "claim verdicts")
    _exact_ids([candidate.id for candidate in verdicts.candidates], candidate_ids, "candidate verdicts")
    linked_claims: dict[str, set[str]] = defaultdict(set)
    supported_claims = {claim.id for claim in verdicts.claims if claim.status in {"supported", "partial"}}
    for claim in verdicts.claims:
        _check_claim_verdict(claim, candidate_ids)
        for candidate_id in claim.candidate_ids:
            linked_claims[candidate_id].add(claim.id)
    for candidate in verdicts.candidates:
        links = linked_claims[candidate.id]
        _check_candidate_verdict(packet, candidate)
        if candidate.status == "covered" and not supported_claims & links and not candidate.book_evidence:
            raise ValueError(f"{candidate.id}: covered requires a supported or partial claim link or book evidence")
        if candidate.status == "implementation_detail" and links:
            raise ValueError(f"{candidate.id}: implementation_detail cannot be linked by claims {sorted(links)}")
        # ``mixed`` candidates may link to claims by definition: they are internal AND
        # relevant, and the truthful verdict for a private struct field that bears on
        # a claim's clauses is ``partial claim, mixed candidate``. The cross-item
        # exclusivity rule that once forced the validator to reject this shape is
        # the very contradiction ``mixed`` admits.
    return AuditReport(packet_digest=current_digest, verdicts=verdicts, limitations=(*packet.limitations,
        "Validated book evidence confirms externally reviewed documented source coverage, not QA proof; span resolution does not establish semantic correctness."))
