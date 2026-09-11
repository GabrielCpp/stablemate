"""Item-level verdict memo: work already judged is not judged again.

A packet receipt is bound to the packet's digest, so one edited bullet in a book of
three hundred documents rebuilds one packet and re-buys every verdict in it. This module
remembers each verdict on its own — per claim, per candidate — in the persistent
:mod:`ostler.index`, and lets the packet builder ask, before any reviewer sees it, which
items already have an answer.

What a verdict is a function of decides what its key is. A claim's verdict depends on
the claim, on the candidates it could bind to and on the excerpts the reviewer read; a
candidate's depends on the candidate, on the claims that could cover it and on the same
excerpts. So a claim is keyed on its own digest plus the **candidate pool** of its packet,
a candidate on its own digest plus the **claim pool**, and both on the review contract
and the **context digest**. Editing one claim keeps every other claim's memo (their pool
is the source, unchanged) and drops every candidate's (their pool changed) — which is
exactly which judgements the edit could have moved.

Line numbers are deliberately absent from every digest. A claim that moved down a page is
the same claim, a candidate under an added import is the same candidate, and the ids
both carry are content-derived already. Book evidence spans are stored as offsets inside
their context and rebased on recall, so a shifted context still hits.

A packet is then rebuilt from what missed: the missed claims need every candidate, since
support may sit in an unchanged one, while missed candidates alone need only the claims.
The reviewer's reply to that reduced packet is merged back over the recalled verdicts,
validated against the full packet, and remembered under the full packet's pools — so the
next pass is a whole hit and costs no turn.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from ostler.behavior import (
    _check_candidate_verdict, _check_claim_verdict, packet_digest, validate_verdicts,
)
from ostler.behavior_models import (
    AuditPacket, AuditReport, AuditVerdicts, BehaviorEvidence, BehaviorModel, BookClaim,
    BookEvidenceRef, CandidateVerdict, ClaimVerdict,
)
from ostler.index import IndexStore, _sha

#: The namespace label of every memo entry, so a verdict can never collide with a parse
#: product that happened to agree about its material.
NAMESPACE = "behavior-verdict"


def claim_digest(claim: BookClaim) -> str:
    """The claim as the reviewer judged it: identity, obligation and citations, no line."""
    return _sha(*(part.encode("utf-8") for part in (
        claim.id, claim.node, claim.path, claim.kind, claim.text, claim.title, *claim.citations)))


def candidate_digest(candidate: BehaviorEvidence) -> str:
    """The candidate as the reviewer judged it: no positions and no whole-file digest."""
    return _sha(*(part.encode("utf-8") for part in (
        candidate.id, candidate.path, candidate.symbol, candidate.kind, candidate.text,
        candidate.snippet, candidate.framework, *candidate.conditions)))


def _source_parts(packet: AuditPacket) -> list[str]:
    parts: list[str] = []
    for context in packet.source_context:
        parts += ("source", context.path, context.symbol, context.text)
    for support in packet.support_context:
        parts += ("support", support.path, support.text)
    return parts


def _book_parts(packet: AuditPacket, node: str | None) -> list[str]:
    parts: list[str] = []
    for book in packet.book_context:
        if node is None or book.node == node:
            parts += ("book", book.node, book.path, book.text)
    return parts


def claim_context_digest(packet: AuditPacket, claim: BookClaim) -> str:
    """What the reviewer read beside a claim: the source excerpts and the claim's own node.

    Another node's excerpt in the same packet is there for another claim; an edit to it
    does not move this claim's verdict, so it is not in this claim's key.
    """
    return _sha(*(part.encode("utf-8") for part in (*_source_parts(packet), *_book_parts(packet, claim.node))))


def candidate_context_digest(packet: AuditPacket) -> str:
    """What the reviewer read beside a candidate: the source excerpts and every book excerpt.

    A candidate's book evidence may land in any node of the packet, so all of them are in
    its key; positions are not, since the evidence is stored relative to its node.
    """
    return _sha(*(part.encode("utf-8") for part in (*_source_parts(packet), *_book_parts(packet, None))))


def _pool(digests: list[str]) -> str:
    return _sha(*(digest.encode("utf-8") for digest in sorted(digests)))


class MemoRecall(BehaviorModel):
    """What the memo already knew about one packet, as verdicts bound to its current ids."""

    claims: tuple[ClaimVerdict, ...] = ()
    candidates: tuple[CandidateVerdict, ...] = ()

    def covers(self, packet: AuditPacket) -> bool:
        claim_ids = {verdict.id for verdict in self.claims}
        candidate_ids = {verdict.id for verdict in self.candidates}
        return (all(claim.id in claim_ids for claim in packet.claims)
                and all(candidate.id in candidate_ids for candidate in packet.candidates))


class VerdictMemo:
    """Per-item verdicts under one review contract, in the index of one repo."""

    def __init__(self, store: IndexStore, contract_digest: str) -> None:
        self.store = store
        self.contract_digest = contract_digest

    # -- keys ---------------------------------------------------------------
    def keys(self, packet: AuditPacket) -> tuple[dict[str, str], dict[str, str]]:
        """Claim id → key and candidate id → key, for every item in *packet*."""
        claim_pool = _pool([claim_digest(claim) for claim in packet.claims])
        candidate_pool = _pool([candidate_digest(candidate) for candidate in packet.candidates])
        claims = {claim.id: self.store.content_key(
            NAMESPACE, "claim", self.contract_digest, claim_digest(claim), candidate_pool,
            claim_context_digest(packet, claim))
            for claim in packet.claims}
        context = candidate_context_digest(packet)
        candidates = {candidate.id: self.store.content_key(
            NAMESPACE, "candidate", self.contract_digest, candidate_digest(candidate), claim_pool, context)
            for candidate in packet.candidates}
        return claims, candidates

    # -- recall -------------------------------------------------------------
    def recall(self, packet: AuditPacket) -> MemoRecall:
        """The verdicts the memo holds for *packet*'s items; a damaged entry is a miss."""
        claim_keys, candidate_keys = self.keys(packet)
        claims: list[ClaimVerdict] = []
        candidates: list[CandidateVerdict] = []
        candidate_ids = {candidate.id for candidate in packet.candidates}
        for claim in packet.claims:
            stored = self.store.get_key(claim_keys[claim.id])
            verdict = _claim_from(claim.id, stored, candidate_ids)
            if verdict is not None:
                claims.append(verdict)
        contexts = {book.node: book.start_line for book in packet.book_context}
        for candidate in packet.candidates:
            stored = self.store.get_key(candidate_keys[candidate.id])
            verdict = _candidate_from(candidate.id, stored, contexts)
            if verdict is not None:
                candidates.append(verdict)
        return MemoRecall(claims=tuple(claims), candidates=tuple(candidates))

    # -- remember -----------------------------------------------------------
    def remember(self, packet: AuditPacket, report: AuditReport) -> int:
        """Store every verdict of *report* under *packet*'s pools; the count written."""
        if report.packet_digest != packet.digest:
            raise ValueError("report was validated against another packet")
        claim_keys, candidate_keys = self.keys(packet)
        contexts = {book.node: book.start_line for book in packet.book_context}
        written = 0
        for claim in report.verdicts.claims:
            self.store.put_key(claim_keys[claim.id], {
                "status": claim.status, "explanation": claim.explanation,
                "candidate_ids": list(claim.candidate_ids)})
            written += 1
        for candidate in report.verdicts.candidates:
            self.store.put_key(candidate_keys[candidate.id], {
                "status": candidate.status, "explanation": candidate.explanation,
                "book_evidence": [
                    {"node": ref.node, "start": ref.start_line - contexts[ref.node],
                     "end": ref.end_line - contexts[ref.node]}
                    for ref in candidate.book_evidence]})
            written += 1
        return written


def _claim_from(claim_id: str, stored: Any, candidate_ids: set[str]) -> ClaimVerdict | None:
    if not isinstance(stored, Mapping):
        return None
    try:
        verdict = ClaimVerdict(id=claim_id, status=stored["status"], explanation=stored["explanation"],
                               candidate_ids=tuple(stored["candidate_ids"]))
    except (KeyError, TypeError, ValueError):
        return None
    if not set(verdict.candidate_ids) <= candidate_ids:
        return None
    return verdict


def _candidate_from(candidate_id: str, stored: Any, contexts: Mapping[str, int]) -> CandidateVerdict | None:
    if not isinstance(stored, Mapping):
        return None
    try:
        refs = tuple(BookEvidenceRef(node=ref["node"], start_line=contexts[ref["node"]] + ref["start"],
                                     end_line=contexts[ref["node"]] + ref["end"])
                     for ref in stored["book_evidence"])
        return CandidateVerdict(id=candidate_id, status=stored["status"], explanation=stored["explanation"],
                                book_evidence=refs)
    except (KeyError, TypeError, ValueError):
        return None


def salvage_verdicts(packet: AuditPacket, payload: object) -> tuple[MemoRecall, tuple[str, ...]]:
    """Partition a short or partly wrong reply into what it did answer and what it owes.

    ``validate_verdicts`` is all-or-nothing by design — one omitted id and its
    ``_exact_ids`` check discards every other verdict in the reply. That is the right
    rule for a receipt, and the wrong rule for a recovery: a reply missing one of
    nineteen candidates is eighteen judgements plus a gap, and re-asking the whole
    packet is how the same id gets dropped a second time.

    So this applies exactly the per-item rules ``validate_verdicts`` applies — the two
    ``_check_*`` predicates it shares with it, never a second opinion — and nothing
    whole-reply. A verdict for an id this packet did not supply, or one that fails its
    own rules, is not salvaged; its id joins the owing set instead of raising. The
    cross-item rules are deliberately left out, because they cannot be decided from a
    partial reply — ``merge_verdicts`` re-validates the merged whole against the full
    packet and raises if the result does not hold, so nothing is weakened by salvaging
    optimistically here.

    Returns the recall to reduce the packet against, and the ids still owing, sorted.
    """
    if packet.digest != packet_digest(packet):
        raise ValueError("packet content digest does not match its contents")
    verdicts = AuditVerdicts.model_validate(payload)
    claim_ids = {claim.id for claim in packet.claims}
    candidate_ids = {candidate.id for candidate in packet.candidates}
    claims: dict[str, ClaimVerdict] = {}
    for claim in verdicts.claims:
        if claim.id not in claim_ids or claim.id in claims:
            continue
        try:
            _check_claim_verdict(claim, candidate_ids)
        except ValueError:
            continue
        claims[claim.id] = claim
    candidates: dict[str, CandidateVerdict] = {}
    for candidate in verdicts.candidates:
        if candidate.id not in candidate_ids or candidate.id in candidates:
            continue
        try:
            _check_candidate_verdict(packet, candidate)
        except ValueError:
            continue
        candidates[candidate.id] = candidate
    owing = tuple(sorted((claim_ids - set(claims)) | (candidate_ids - set(candidates))))
    recall = MemoRecall(
        claims=tuple(claims[claim.id] for claim in packet.claims if claim.id in claims),
        candidates=tuple(candidates[c.id] for c in packet.candidates if c.id in candidates),
    )
    return recall, owing


def reduce_packet(packet: AuditPacket, recall: MemoRecall) -> AuditPacket | None:
    """The packet a reviewer still has to read, or ``None`` when the memo covers it all.

    A missed claim keeps every candidate in front of the reviewer, because the one that
    supports it may be a candidate whose own verdict hit. Missed candidates alone keep
    every claim for the same reason in the other direction. Nothing missed is a whole
    hit, and the packet whose every item missed is returned as it is.
    """
    if recall.covers(packet):
        return None
    hit_claims = {verdict.id for verdict in recall.claims}
    hit_candidates = {verdict.id for verdict in recall.candidates}
    claims = tuple(claim for claim in packet.claims if claim.id not in hit_claims)
    missed_candidates = tuple(candidate for candidate in packet.candidates if candidate.id not in hit_candidates)
    candidates = packet.candidates if claims else missed_candidates
    if len(claims) == len(packet.claims) and len(candidates) == len(packet.candidates):
        return packet
    reduced = packet.model_copy(update={
        "claims": claims, "candidates": candidates,
        "omitted_claims": packet.omitted_claims + len(packet.claims) - len(claims),
        "omitted_candidates": packet.omitted_candidates + len(packet.candidates) - len(candidates),
        "limitations": (*packet.limitations,
                        "Reduced packet: items with a memoized verdict are omitted; judge what is present."),
        "digest": ""})
    return reduced.model_copy(update={"digest": packet_digest(reduced)})


def merge_verdicts(packet: AuditPacket, recall: MemoRecall, reviewed: AuditVerdicts | None) -> AuditReport:
    """The full packet's report from recalled verdicts and the reduced packet's reply.

    A reviewed item wins over a recalled one. A candidate the reviewer never saw a
    claim for is upgraded to ``covered`` when a recalled supported or partial claim
    links it — the rule ``validate_verdicts`` applies to covered — and an
    ``implementation_detail`` a recalled claim contradicts becomes ``unresolved``, since
    the two verdicts were made on different evidence and neither can stand alone.
    Raises ``ValueError`` when the merge does not validate against *packet*.
    """
    claims: dict[str, ClaimVerdict] = {verdict.id: verdict for verdict in recall.claims}
    candidates: dict[str, CandidateVerdict] = {verdict.id: verdict for verdict in recall.candidates}
    if reviewed is not None:
        claims.update({verdict.id: verdict for verdict in reviewed.claims})
        candidates.update({verdict.id: verdict for verdict in reviewed.candidates})
    links: dict[str, set[str]] = defaultdict(set)
    supporting: dict[str, set[str]] = defaultdict(set)
    for claim in claims.values():
        for candidate_id in claim.candidate_ids:
            links[candidate_id].add(claim.id)
            if claim.status in {"supported", "partial"}:
                supporting[candidate_id].add(claim.id)
    merged: list[CandidateVerdict] = []
    for candidate in packet.candidates:
        verdict = candidates.get(candidate.id)
        if verdict is None:
            raise ValueError(f"{candidate.id}: no recalled or reviewed verdict")
        # ``mixed`` is the verdict that records the contradiction directly — a candidate
        # that is internal AND relevant. A recalled supported or partial claim naming it
        # does not upgrade it to ``covered`` (the visibility half is still partial), and
        # the implementation_detail → unresolved demote that runs for a different
        # contradiction does not apply (mixed already names what it is).
        if verdict.status == "mixed":
            merged.append(verdict)
            continue
        if verdict.status != "covered" and supporting[candidate.id]:
            verdict = verdict.model_copy(update={
                "status": "covered", "book_evidence": (),
                "explanation": f"Covered by {', '.join(sorted(supporting[candidate.id]))}; "
                               f"reviewed apart from that claim as: {verdict.explanation}"})
        elif verdict.status == "implementation_detail" and links[candidate.id]:
            verdict = verdict.model_copy(update={
                "status": "unresolved",
                "explanation": f"Linked by {', '.join(sorted(links[candidate.id]))} without support; "
                               f"reviewed apart from that claim as: {verdict.explanation}"})
        merged.append(verdict)
    ordered_claims = tuple(claims[claim.id] for claim in packet.claims if claim.id in claims)
    return validate_verdicts(packet, AuditVerdicts(claims=ordered_claims, candidates=tuple(merged)))
