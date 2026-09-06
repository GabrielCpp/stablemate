"""Wire contracts for bounded source/book review, not semantic proofs."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

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


class AuditPreparation(BehaviorModel):
    version: Literal[1] = 1
    status: Literal["prepared"] = "prepared"
    inventory: EvidenceInventory
    packets: tuple[AuditPacket, ...]
    selected_candidates: int
    selected_claims: int
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
    id: Nonblank
    status: Literal["covered", "missing", "implementation_detail", "unresolved"]
    claim_ids: tuple[Nonblank, ...] = ()
    book_evidence: tuple[BookEvidenceRef, ...] = Field(
        default=(), description="Distinct nonblank book spans establishing covered source behavior. Only covered verdicts may supply these; not QA proof.",
    )
    explanation: Nonblank


class AuditVerdicts(BehaviorModel):
    packet_digest: Nonblank
    claims: tuple[ClaimVerdict, ...]
    candidates: tuple[CandidateVerdict, ...]


class AuditReport(BehaviorModel):
    version: Literal[1] = 1
    status: Literal["reviewed"] = "reviewed"
    verdicts: AuditVerdicts
    limitations: tuple[str, ...]
