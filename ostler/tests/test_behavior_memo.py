"""The verdict memo: an item judged once under one contract is not judged again.

The memo is keyed on content, never on position, and on the pool of counterparts a
verdict was made against. So a line shift hits, an edited claim misses on its own and on
every candidate (their pool changed), an edited source misses everything in its file, and
a changed review contract misses everything.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler.behavior import build_audit_packets, extract_evidence, validate_verdicts
from ostler.behavior_models import (
    AuditPacket, AuditVerdicts, BookClaim, BookContext, BookEvidenceRef, CandidateVerdict, ClaimVerdict,
)
from ostler.behavior_memo import VerdictMemo, merge_verdicts, reduce_packet
from ostler.index import IndexStore

SOURCE = "def items():\n    return 20\n\ndef total():\n    return 0\n"
CONTRACT = "contract-a"


def packet_for(tmp_path: Path, *, source: str = SOURCE, limit_text: str = "Returns 50", book_line: int = 1) -> AuditPacket:
    (tmp_path / "api.py").write_text(source, encoding="utf-8")
    items = BookContext(node="items", path="docs/items.md", start_line=book_line, end_line=book_line + 1,
                        text=f"# Items\n- {limit_text}\n", source_digest="d")
    totals = BookContext(node="totals", path="docs/items.md", start_line=book_line + 2, end_line=book_line + 3,
                         text="# Totals\n- Total starts empty\n", source_digest="d")
    claims = [
        BookClaim(id="claim:limit", node="items", path="docs/items.md", line=book_line + 1, kind="rule",
                  text=limit_text, citations=("api.py::items",), context=(items,)),
        BookClaim(id="claim:total", node="totals", path="docs/items.md", line=book_line + 3, kind="rule",
                  text="Total starts empty", citations=("api.py::total",), context=(totals,)),
    ]
    prepared = build_audit_packets(extract_evidence(tmp_path, ["api.py"]), claims)
    assert len(prepared.packets) == 1
    return prepared.packets[0]


def judged(packet: AuditPacket) -> AuditVerdicts:
    by_symbol = {candidate.symbol: candidate for candidate in packet.candidates}
    context = next(book for book in packet.book_context if book.node == "totals")
    return AuditVerdicts(
        claims=(ClaimVerdict(id="claim:limit", status="contradicted", explanation="Returns 20.",
                             candidate_ids=(by_symbol["items"].id,)),
                ClaimVerdict(id="claim:total", status="supported", explanation="Returns 0.",
                             candidate_ids=(by_symbol["total"].id,))),
        candidates=(CandidateVerdict(id=by_symbol["items"].id, status="missing", explanation="Book says 50."),
                    CandidateVerdict(id=by_symbol["total"].id, status="covered", explanation="Documented.",
                                     book_evidence=(BookEvidenceRef(node="totals", start_line=context.start_line + 1,
                                                                    end_line=context.start_line + 1),))),
    )


@pytest.fixture
def memo(tmp_path: Path) -> VerdictMemo:
    return VerdictMemo(IndexStore(tmp_path, directory=tmp_path / "index"), CONTRACT)


def remember(memo: VerdictMemo, packet: AuditPacket) -> int:
    return memo.remember(packet, validate_verdicts(packet, judged(packet)))


def test_a_whole_hit_reproduces_the_report_without_a_reviewer(tmp_path: Path, memo: VerdictMemo) -> None:
    packet = packet_for(tmp_path)
    assert remember(memo, packet) == 4
    recall = memo.recall(packet)
    assert recall.covers(packet)
    assert reduce_packet(packet, recall) is None
    assert merge_verdicts(packet, recall, None).verdicts == validate_verdicts(packet, judged(packet)).verdicts


def test_an_empty_memo_hands_back_the_packet_unchanged(tmp_path: Path, memo: VerdictMemo) -> None:
    packet = packet_for(tmp_path)
    recall = memo.recall(packet)
    assert not recall.claims and not recall.candidates
    assert reduce_packet(packet, recall) is packet


def test_an_edited_claim_misses_itself_and_every_candidate(tmp_path: Path, memo: VerdictMemo) -> None:
    remember(memo, packet_for(tmp_path))
    edited = packet_for(tmp_path, limit_text="Returns 20")
    recall = memo.recall(edited)
    assert {verdict.id for verdict in recall.claims} == {"claim:total"}
    assert recall.candidates == ()
    reduced = reduce_packet(edited, recall)
    assert reduced is not None
    assert [claim.id for claim in reduced.claims] == ["claim:limit"]
    assert len(reduced.candidates) == len(edited.candidates)
    assert reduced.omitted_claims == edited.omitted_claims + 1
    assert reduced.digest != edited.digest


def test_an_edited_source_misses_everything_in_its_file(tmp_path: Path, memo: VerdictMemo) -> None:
    remember(memo, packet_for(tmp_path))
    edited = packet_for(tmp_path, source=SOURCE.replace("return 20", "return 50"))
    recall = memo.recall(edited)
    assert recall.claims == () and recall.candidates == ()


def test_a_line_shift_still_hits_and_rebases_book_evidence(tmp_path: Path, memo: VerdictMemo) -> None:
    remember(memo, packet_for(tmp_path))
    shifted = packet_for(tmp_path, source="# a comment\n\n" + SOURCE, book_line=11)
    recall = memo.recall(shifted)
    assert recall.covers(shifted)
    covered = next(verdict for verdict in recall.candidates if verdict.status == "covered")
    assert covered.book_evidence == (BookEvidenceRef(node="totals", start_line=14, end_line=14),)
    merge_verdicts(shifted, recall, None)


def test_another_contract_misses(tmp_path: Path, memo: VerdictMemo) -> None:
    packet = packet_for(tmp_path)
    remember(memo, packet)
    other = VerdictMemo(memo.store, "contract-b")
    assert not other.recall(packet).covers(packet)


def test_a_reduced_reply_merges_over_the_recall_and_is_remembered_whole(tmp_path: Path, memo: VerdictMemo) -> None:
    remember(memo, packet_for(tmp_path))
    edited = packet_for(tmp_path, limit_text="Returns 20")
    recall = memo.recall(edited)
    reduced = reduce_packet(edited, recall)
    assert reduced is not None
    items = next(candidate for candidate in reduced.candidates if candidate.symbol == "items")
    total = next(candidate for candidate in reduced.candidates if candidate.symbol == "total")
    reply = AuditVerdicts(
        claims=(ClaimVerdict(id="claim:limit", status="supported", explanation="Returns 20.", candidate_ids=(items.id,)),),
        candidates=(CandidateVerdict(id=items.id, status="covered", explanation="Documented now."),
                    CandidateVerdict(id=total.id, status="implementation_detail", explanation="Seen without its claim.")))
    validate_verdicts(reduced, reply)
    with pytest.raises(ValueError, match="missing IDs"):
        validate_verdicts(edited, reply)
    report = merge_verdicts(edited, recall, reply)
    by_id = {verdict.id: verdict for verdict in report.verdicts.candidates}
    assert by_id[items.id].status == "covered"
    assert by_id[total.id].status == "covered", "the recalled supported claim links it"
    assert {verdict.id: verdict.status for verdict in report.verdicts.claims} == {"claim:limit": "supported", "claim:total": "supported"}
    memo.remember(edited, report)
    assert memo.recall(edited).covers(edited)


def test_a_damaged_entry_is_a_miss(tmp_path: Path, memo: VerdictMemo) -> None:
    packet = packet_for(tmp_path)
    remember(memo, packet)
    claim_keys, _ = memo.keys(packet)
    memo.store.put_key(claim_keys["claim:limit"], {"status": "supported"})
    memo.store.put_key(claim_keys["claim:total"], "not a verdict")
    assert memo.recall(packet).claims == ()
