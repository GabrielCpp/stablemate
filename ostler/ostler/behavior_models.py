"""Wire contracts for bounded source/book review, not semantic proofs."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Nonblank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class BehaviorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class BehaviorEvidence(BehaviorModel):
    id: Nonblank
    path: Nonblank
    symbol: Nonblank
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    start_column: int = Field(ge=0)
    end_column: int = Field(ge=0)
    kind: Literal["route", "decorator", "argparse_option", "function_default", "raise", "return", "schema_field", "panic", "http_response", "function_contract"]
    text: Nonblank
    snippet: Nonblank
    conditions: tuple[str, ...] = ()
    source_digest: Nonblank
    confidence: Literal["syntactic"] = "syntactic"
    framework: str = "python"
    exported: bool | None = None
    """The extractor's own verdict on the symbol's visibility, where the name alone cannot say.

    TypeScript exports by an ``export`` keyword and PHP by a visibility modifier, not by
    spelling, so those extractors record the answer here; Python and Go leave it ``None``
    and ``exported_symbol`` reads the name.
    """


class EvidenceFile(BehaviorModel):
    path: Nonblank
    status: Literal["parsed", "unsupported", "parse_error", "unreadable"]
    source_digest: str = ""
    message: str = ""


class FileExcerpt(BehaviorModel):
    """Original text with inclusive file line bounds and a full-file byte digest."""

    path: Nonblank
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    text: str = Field(min_length=1)
    source_digest: Nonblank

    @model_validator(mode="after")
    def _bounds_match_text(self) -> FileExcerpt:
        """Refuse an excerpt that advertises a span its own text does not carry.

        The bounds are what a reviewer cites; the text is what it can see. When they
        disagree the honest citation — the whole excerpt — is rejected downstream as
        "unseen", and no retry can fix it because the packet itself is wrong. Catching
        it here moves that failure from an operator gate hours later to the extractor
        that built the excerpt.

        Lines are counted the way ``str.splitlines`` counts them (a trailing newline
        closes the last line rather than opening a phantom one) but arithmetically, so
        revalidation of a 60k-char excerpt allocates nothing.
        """
        lines = self.text.count("\n") + (0 if self.text.endswith("\n") else 1)
        span = self.end_line - self.start_line + 1
        if span != max(1, lines):
            raise ValueError(
                f"{self.path}: lines {self.start_line}-{self.end_line} span {span} line(s) "
                f"but the text carries {lines}"
            )
        return self


class SourceContext(FileExcerpt):
    symbol: Nonblank


class SourceExcerpt(FileExcerpt):
    """Full explicitly selected support file, not a candidate obligation.

    Empty files retain their byte digest and use line 1 as the empty-file bound.
    """

    text: str


class BookContext(FileExcerpt):
    node: Nonblank


class EvidenceInventory(BehaviorModel):
    version: Literal[1] = 1
    grammar_version: str = ""
    scope: tuple[str, ...]
    files: tuple[EvidenceFile, ...]
    candidates: tuple[BehaviorEvidence, ...]
    limitations: tuple[str, ...]
    excluded_paths: tuple[str, ...] = ()
    source_context: tuple[SourceContext, ...] = ()
    context_paths: tuple[str, ...] = ()
    context_files: tuple[EvidenceFile, ...] = ()
    support_context: tuple[SourceExcerpt, ...] = ()


class BookClaim(BehaviorModel):
    """An authored obligation; title and original node context are not extra claims.

    Packets move ``context`` into their deduplicated ``book_context``, joined by node.
    """

    id: Nonblank
    node: Nonblank
    path: Nonblank
    line: int = Field(ge=1)
    kind: Nonblank
    text: Nonblank
    citations: tuple[str, ...] = ()
    title: str = ""
    context: tuple[BookContext, ...] = ()


class AuditPacket(BehaviorModel):
    """One bounded file-local or ungrounded review, never a completeness verdict.

    ``symbol`` remains empty for file-local packets; candidates retain their symbols.
    ``scope`` names this packet's source file, while the inventory carries selectors.
    Omitted counts describe selected items outside this packet, not discarded work.
    """

    version: Literal[1] = 1
    group: Literal["source_file", "ungrounded_book", "empty_scope"] = "source_file"
    module: str
    symbol: str
    scope: tuple[str, ...]
    inventory_digest: Nonblank
    candidates: tuple[BehaviorEvidence, ...]
    claims: tuple[BookClaim, ...]
    omitted_candidates: int = Field(ge=0)
    omitted_claims: int = Field(ge=0)
    limitations: tuple[str, ...]
    source_context: tuple[SourceContext, ...] = ()
    book_context: tuple[BookContext, ...] = ()
    support_context: tuple[SourceExcerpt, ...] = ()
    digest: str = ""


class BookClaims(BehaviorModel):
    """The book side of a review: its claims, and what it could not mint as one."""

    claims: tuple[BookClaim, ...]
    limitations: tuple[str, ...] = ()
    cited_paths: tuple[Nonblank, ...] = Field(
        default=(), description="Every repo-relative source path some node cites, claim or not")
    cited_symbols: tuple[Nonblank, ...] = Field(
        default=(), description="Every `path::symbol` some node cites; a bare `path` cites the whole file")


class UndocumentedFile(BehaviorModel):
    """A source file with behavior candidates on exported symbols that no book node cites.

    This is a fact about the book, not a question for a reviewer: no packet is built for
    the file until a claim cites it. ``exported_symbols`` lists the symbols the
    language's rule exports, each with the line of its first candidate.
    """

    path: Nonblank
    candidate_count: int = Field(ge=1)
    exported_symbols: tuple[Nonblank, ...] = Field(min_length=1)
    first_lines: tuple[int, ...] = ()


class AuditPreparation(BehaviorModel):
    version: Literal[1] = 1
    status: Literal["prepared"] = "prepared"
    inventory: EvidenceInventory
    packets: tuple[AuditPacket, ...]
    selected_candidates: int
    selected_claims: int
    undocumented: tuple[UndocumentedFile, ...] = ()
    tier: Literal[1, "all"] = 1
    deferred_candidates: int = Field(
        default=0, ge=0, description="Tier-2 candidates (private, uncited symbols) no packet carries at tier 1")
    out_of_scope_claims: int = Field(
        default=0, ge=0, description="Claims whose citations all name existing files outside the selected source")
    omitted_candidates: Literal[0] = 0
    omitted_claims: Literal[0] = 0


class ClaimVerdict(BehaviorModel):
    id: Nonblank
    status: Literal["supported", "contradicted", "partial", "unresolved"]
    candidate_ids: tuple[Nonblank, ...] = ()
    explanation: Nonblank


class BookEvidenceRef(BehaviorModel):
    """Document evidence within this packet, not a new normative obligation."""

    node: Nonblank = Field(description="Exact node ID in packet.book_context; that context binds the document path.")
    start_line: int = Field(ge=1, description="Inclusive first document line within the supplied book context.")
    end_line: int = Field(ge=1, description="Inclusive last document line, at or after start_line.")


class CandidateVerdict(BehaviorModel):
    """One candidate's verdict. Its claim links are the claims that name it, not an echo.

    ``mixed`` is the verdict for a candidate that is *internally used* but
    *observably relevant* to a claim — a private struct field that constrains
    identity comparison, an unexported helper whose return value is part of the
    public response. ``mixed`` candidates may link to claims (typically
    ``partial``) and may not carry book evidence; they are neither fully public
    (``covered``) nor fully internal (``implementation_detail``). The status
    closes the contradiction ``validate_verdicts`` used to reject: a private
    field that a claim legitimately names.
    """

    id: Nonblank
    status: Literal["covered", "missing", "implementation_detail", "mixed", "unresolved"]
    book_evidence: tuple[BookEvidenceRef, ...] = Field(
        default=(), description="Distinct nonblank book spans establishing covered source behavior. Only covered verdicts may supply these; not QA proof.",
    )
    explanation: Nonblank


class AuditVerdicts(BehaviorModel):
    """The reviewer's reply: one verdict per supplied id, links stated once, on the claim.

    The packet digest is deliberately absent. The caller already holds the packet it
    dispatched, so binding the reply to it is the caller's job (`validate_verdicts` takes
    both); asking the model to echo a 64-character digest buys nothing and is one more
    field to get wrong.
    """

    claims: tuple[ClaimVerdict, ...]
    candidates: tuple[CandidateVerdict, ...]


class AuditReport(BehaviorModel):
    version: Literal[2] = 2
    status: Literal["reviewed"] = "reviewed"
    packet_digest: Nonblank = Field(description="The packet these verdicts were validated against.")
    verdicts: AuditVerdicts
    limitations: tuple[str, ...]
