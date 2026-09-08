from __future__ import annotations

from pathlib import Path
import hashlib

import pytest

from pydantic import ValidationError

from ostler.behavior import (
    AuditPacket, AuditVerdicts, BookClaim, BookClaims, BookEvidenceRef, CandidateVerdict,
    ClaimVerdict, build_audit_packets, exported_symbol, extract_book, extract_claims,
    extract_evidence, validate_verdicts,
)
from ostler.behavior_models import BookContext, SourceContext, SourceExcerpt
from ostler.model import load


def test_python_candidates_preserve_defaults_branches_and_schema(tmp_path: Path) -> None:
    source = (
        "class Request(BaseModel):\n    limit: int = 20\n\n"
        "@router.get('/items', status_code=201)\n"
        "def items(limit=20, *, active=True):\n"
        "    parser.add_argument('--limit', type=int, default=20)\n"
        "    if limit < 0:\n        raise ValueError('negative')\n"
        "    else:\n        return {'limit': limit}\n"
    )
    path = tmp_path / "api.py"
    path.write_text(source, encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["api.py"])
    assert {item.kind for item in inventory.candidates} == {
        "schema_field", "route", "function_default", "argparse_option", "raise", "return",
    }
    raised = next(item for item in inventory.candidates if item.kind == "raise")
    assert raised.conditions == ("if limit < 0",)
    assert raised.symbol == "items" and raised.start_line == 8
    returned = next(item for item in inventory.candidates if item.kind == "return")
    assert returned.conditions == ("else of (limit < 0)",)
    assert next(item for item in inventory.candidates if item.kind == "schema_field").text == "limit: int = 20"
    assert all(item.source_digest == inventory.files[0].source_digest for item in inventory.candidates)
    assert all(item.confidence == "syntactic" for item in inventory.candidates)
    path.write_text("# moved without changing declarations\n" + source, encoding="utf-8")
    moved = extract_evidence(tmp_path, ["api.py"])
    assert [item.id for item in moved.candidates] == [item.id for item in inventory.candidates]
    assert moved.files[0].source_digest != inventory.files[0].source_digest


def test_extraction_keeps_failed_and_empty_files_and_rejects_escape(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text("def broken(:", encoding="utf-8")
    (tmp_path / "empty.py").write_text("import os\n", encoding="utf-8")
    (tmp_path / "app.rb").write_text("a = 1", encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["bad.py", "empty.py", "app.rb", "absent.py"])
    assert {item.path: item.status for item in inventory.files} == {
        "bad.py": "parse_error", "empty.py": "parsed", "app.rb": "unsupported", "absent.py": "unreadable",
    }
    assert next(item for item in inventory.files if item.path == "bad.py").message
    with pytest.raises(ValueError, match="relative|outside"):
        extract_evidence(tmp_path, ["../outside.py"])


def test_claims_use_real_graph_normative_ids_lines_and_citations(tmp_path: Path) -> None:
    docs = tmp_path / "docs/features/api"
    docs.mkdir(parents=True)
    (docs / "items.md").write_text(
        "---\ntype: server\ntitle: API\n---\n\n# API\n\n## Endpoints\n\n### items\n\n"
        "- does: Limit is 50.\n- does: Negative limits are accepted.\n"
        "- code: api.py::items\n- unspecified: Ordering is not promised.\n",
        encoding="utf-8",
    )
    claims = extract_claims(load(tmp_path))
    rules = [claim for claim in claims if claim.kind == "does"]
    assert [claim.id for claim in rules] == [
        "okf:docs/features/api/items.md#items:does:1", "okf:docs/features/api/items.md#items:does:2",
    ]
    assert [claim.line for claim in rules] == [12, 13]
    assert rules[0].citations == ("api.py::items",)
    assert all(claim.kind != "unspecified" for claim in claims)
    assert len(claims) == 2, "Titles are metadata, not synthetic semantic obligations"


def test_large_file_packets_pair_local_evidence_and_claims_without_truncation(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text("def a(x=1):\n    return x\ndef b(y=2):\n    return y\n", encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["api.py"])
    claims = tuple(BookClaim(id=f"claim:{i}", node="node", path="docs/book.md", line=1,
                             kind="rule", text=f"Promise {i}", citations=("api.py::wrong_symbol",)) for i in range(5))
    preparation = build_audit_packets(inventory, claims, max_items=3)
    pairs = {(candidate.id, claim.id) for packet in preparation.packets
             for candidate in packet.candidates for claim in packet.claims}
    assert pairs == {(candidate.id, claim.id) for candidate in inventory.candidates for claim in claims}
    assert all(len(packet.candidates) + len(packet.claims) <= 3 for packet in preparation.packets)
    assert preparation.omitted_candidates == preparation.omitted_claims == 0
    assert preparation == build_audit_packets(inventory, claims, max_items=3)
    with pytest.raises(ValueError, match="max_items"):
        build_audit_packets(inventory, claims, max_items=1)
    with pytest.raises(ValueError, match="max_chars|oversized"):
        build_audit_packets(inventory, claims, max_chars=10)
    without_source = build_audit_packets(extract_evidence(tmp_path, []), claims, max_items=3)
    assert {claim.id for packet in without_source.packets for claim in packet.claims} == {claim.id for claim in claims}
    without_book = build_audit_packets(inventory, [], skip_undocumented=False)
    assert {item.id for packet in without_book.packets for item in packet.candidates} == {item.id for item in inventory.candidates}


def test_packet_count_is_linear_for_100_files_and_claims(tmp_path: Path) -> None:
    paths = [f"module_{i}.py" for i in range(100)]
    for path in paths:
        (tmp_path / path).write_text("def a():\n    return 1\ndef b():\n    return 2\n", encoding="utf-8")
    claims = [BookClaim(id=f"claim:{i}", node="node", path="docs/book.md", line=1,
                        kind="does", text=f"Promise {i}", citations=(f"{path}::wrong_symbol",))
              for i, path in enumerate(paths)]
    preparation = build_audit_packets(extract_evidence(tmp_path, paths), claims)
    assert len(preparation.packets) == 100
    assert sum(len(packet.claims) for packet in preparation.packets) == 100
    assert sum(len(packet.candidates) for packet in preparation.packets) == 200
    for packet in preparation.packets:
        assert {item.path for item in packet.candidates} == {packet.module}
        assert {item.symbol for item in packet.candidates} == {"a", "b"}
        assert packet.scope == (packet.module,)
        assert packet.claims[0].citations == (f"{packet.module}::wrong_symbol",)


def test_normalized_file_binding_keeps_uncited_source_and_ungrounded_book(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    for name in ("a.py", "b.py"):
        (source / name).write_text("def a():\n    return 1\n", encoding="utf-8")
    (source / "uncited.py").write_text("def _a():\n    return 1\n", encoding="utf-8")
    citations = [
        ("`./src/a.py::wrong`, `src\\b.py::other`",),
        (), ("repo://api-service/src/a.py::a",), ("missing.py::a",), ("repo://malformed",),
    ]
    claims = [BookClaim(id=f"claim:{i}", node="node", path="docs/book.md", line=1,
                        kind="does", text=f"Promise {i}", citations=refs) for i, refs in enumerate(citations)]
    preparation = build_audit_packets(extract_evidence(tmp_path, ["src"]), claims)
    # A private, uncited candidate is tier 2: its file holds no review at tier 1.
    assert len(preparation.packets) == 3 and preparation.deferred_candidates == 1
    by_module = {packet.module: packet for packet in preparation.packets if packet.module}
    assert {claim.id for claim in by_module["src/a.py"].claims} == {"claim:0"}
    assert {claim.id for claim in by_module["src/b.py"].claims} == {"claim:0"}
    assert "src/uncited.py" not in by_module
    everything = build_audit_packets(extract_evidence(tmp_path, ["src"]), claims, tier="all")
    uncited = next(p for p in everything.packets if p.module == "src/uncited.py")
    assert not uncited.claims and len(uncited.candidates) == 1
    assert not preparation.undocumented
    book_only = next(packet for packet in preparation.packets if not packet.module)
    assert book_only.model_dump()["group"] == "ungrounded_book"
    assert not book_only.candidates
    assert {claim.id for claim in book_only.claims} == {"claim:1", "claim:2", "claim:3", "claim:4"}
    assert any("search" in note and "unresolved" in note for note in book_only.limitations)


def test_normative_claims_inherit_nearest_same_document_citations_not_titles(tmp_path: Path) -> None:
    docs = tmp_path / "docs/features/api"
    docs.mkdir(parents=True)
    (docs / "items.md").write_text(
        "---\ntype: server\ntitle: API\n---\n\n# API\n\n- code: `server.py::app`\n"
        "\n## Endpoints\n\n### items\n- does: Returns items.\n"
        "\n### other\n- code: `other.py::wrong`\n- does: Returns other items.\n"
        "\n#### method: detail\n- does: Returns a detail.\n",
        encoding="utf-8",
    )
    claims = extract_claims(load(tmp_path))
    assert len(claims) == 3
    by_text = {claim.text: claim for claim in claims}
    assert by_text["Returns items."].citations == ("server.py::app",)
    assert by_text["Returns other items."].citations == ("other.py::wrong",)
    assert by_text["Returns a detail."].citations == ("other.py::wrong",)
    assert by_text["Returns items."].model_dump()["title"] == "items"


def test_directory_selection_prunes_caches_but_explicit_file_selectors_remain_visible(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "api.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    cache = source / "__pycache__"
    cache.mkdir()
    (cache / "api.pyc").write_bytes(b"cached bytecode")
    (source / "loose.pyc").write_bytes(b"bytecode")
    (source / "ui.rb").write_text("a = 1", encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["src"])
    assert {file.path for file in inventory.files} == {"src/api.py", "src/ui.rb"}
    assert any("__pycache__" in note for note in inventory.limitations)
    explicit = extract_evidence(tmp_path, ["src/__pycache__/api.pyc"])
    assert [(file.path, file.status) for file in explicit.files] == [("src/__pycache__/api.pyc", "unsupported")]


def test_empty_scope_empty_directories_and_empty_files_are_explicit(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    (tmp_path / "empty.py").write_text("", encoding="utf-8")
    for paths in ([], ["empty"]):
        inventory = extract_evidence(tmp_path, paths)
        assert not inventory.files and not inventory.candidates
        preparation = build_audit_packets(inventory, [])
        assert any("No source files" in note for note in preparation.packets[0].limitations)
        assert preparation.packets[0].model_dump()["group"] == "empty_scope"
    inventory = extract_evidence(tmp_path, ["empty.py"])
    assert inventory.files[0].status == "parsed"
    packet = build_audit_packets(inventory, [], skip_undocumented=False).packets[0]
    assert packet.module == "empty.py" and not packet.candidates
    assert any("No behavior candidates" in note for note in packet.limitations)
    with pytest.raises(ValueError, match="empty selector"):
        extract_evidence(tmp_path, [""])


@pytest.fixture
def audit_packet(tmp_path: Path) -> AuditPacket:
    (tmp_path / "api.py").write_text("def items():\n    return 20\n", encoding="utf-8")
    claim = BookClaim(id="claim:limit", node="items", path="docs/items.md", line=1,
                      kind="rule", text="Returns 50", citations=("api.py::items",))
    return build_audit_packets(extract_evidence(tmp_path, ["api.py"]), [claim]).packets[0]


def verdicts(packet: AuditPacket) -> AuditVerdicts:
    return AuditVerdicts(
        claims=tuple(ClaimVerdict(id=claim.id, status="contradicted", explanation="Returns 20, not 50.",
                                 candidate_ids=tuple(item.id for item in packet.candidates)) for claim in packet.claims),
        candidates=tuple(CandidateVerdict(id=item.id, status="missing", explanation="Book promises a different value.")
                         for item in packet.candidates),
    )


def test_verdicts_are_external_not_inferred_from_shared_words(audit_packet: AuditPacket) -> None:
    report = validate_verdicts(audit_packet, verdicts(audit_packet).model_dump(mode="json"))
    assert report.verdicts.claims[0].status == "contradicted"
    assert report.verdicts.candidates[0].status == "missing"
    assert report.limitations
    unresolved = AuditVerdicts(claims=(ClaimVerdict(id=audit_packet.claims[0].id, status="unresolved", explanation="Need execution context."),),
                              candidates=(CandidateVerdict(id=audit_packet.candidates[0].id, status="unresolved", explanation="Need owner decision."),))
    assert validate_verdicts(audit_packet, unresolved).verdicts == unresolved


@pytest.mark.parametrize("fault", ["missing", "duplicate", "foreign", "foreign_link", "duplicate_link", "blank", "unsupported_support", "detail_linked"])
def test_verdict_validator_rejects_invalid_receipts(audit_packet: AuditPacket, fault: str) -> None:
    payload = verdicts(audit_packet).model_dump(mode="json")
    if fault == "missing":
        payload["claims"] = []
    elif fault == "duplicate":
        payload["candidates"] *= 2
    elif fault == "foreign":
        payload["claims"][0]["id"] = "foreign"
    elif fault == "foreign_link":
        payload["claims"][0]["candidate_ids"] = ["foreign"]
    elif fault == "duplicate_link":
        payload["claims"][0]["candidate_ids"] *= 2
    elif fault == "blank":
        payload["claims"][0]["explanation"] = "   "
    elif fault == "detail_linked":
        payload["candidates"][0].update(status="implementation_detail", explanation="Private helper.")
    else:
        payload["claims"][0]["status"] = "supported"
        payload["claims"][0]["candidate_ids"] = []
    with pytest.raises(ValueError):
        validate_verdicts(audit_packet, payload)


def test_packet_mutation_and_source_or_book_edits_invalidate_receipts(audit_packet: AuditPacket, tmp_path: Path) -> None:
    receipt = verdicts(audit_packet)
    changed_claim = audit_packet.claims[0].model_copy(update={"text": "Returns 20"})
    tampered = audit_packet.model_copy(update={"claims": (changed_claim,)})
    with pytest.raises(ValueError, match="digest"):
        validate_verdicts(tampered, receipt)
    (tmp_path / "api.py").write_text("def items():\n    return 50\n", encoding="utf-8")
    current = build_audit_packets(extract_evidence(tmp_path, ["api.py"]), audit_packet.claims).packets[0]
    assert validate_verdicts(audit_packet, receipt).packet_digest != current.digest, "a source edit re-keys the receipt"
    with pytest.raises(ValueError, match="foreign IDs"):
        validate_verdicts(current, receipt)


def test_covered_candidate_cannot_link_only_contradicted_claims(audit_packet: AuditPacket) -> None:
    payload = verdicts(audit_packet).model_dump(mode="json")
    payload["candidates"][0]["status"] = "covered"
    with pytest.raises(ValueError, match="covered"):
        validate_verdicts(audit_packet, payload)


@pytest.mark.parametrize("claim_status", ["supported", "partial"])
def test_linked_supported_and_partial_reviews_are_preserved(audit_packet: AuditPacket, claim_status: str) -> None:
    payload = verdicts(audit_packet).model_dump(mode="json")
    payload["claims"][0]["status"] = claim_status
    payload["claims"][0]["explanation"] = "External reviewer supplied this judgment."
    payload["candidates"][0]["status"] = "covered"
    report = validate_verdicts(audit_packet, payload)
    assert report.verdicts.claims[0].status == claim_status
    assert report.verdicts.candidates[0].status == "covered"


def test_implementation_detail_requires_a_reason_but_no_book_claim(audit_packet: AuditPacket) -> None:
    payload = verdicts(audit_packet).model_dump(mode="json")
    payload["claims"][0].update(status="unresolved", candidate_ids=[])
    payload["candidates"][0].update(status="implementation_detail", explanation="Private helper; not a public contract.")
    assert validate_verdicts(audit_packet, payload).verdicts.candidates[0].status == "implementation_detail"


def test_async_decorators_positional_only_and_nested_symbols(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        "@dataclass\nclass Config:\n    mode: str\n\n"
        "    @decorated\n    async def run(self, limit=2, /, *, enabled=False):\n"
        "        def inner():\n            return None\n"
        "        return await work()\n",
        encoding="utf-8",
    )
    inventory = extract_evidence(tmp_path, ["api.py"])
    assert {item.text for item in inventory.candidates if item.kind == "function_default"} == {"limit=2", "enabled=False"}
    assert {item.symbol for item in inventory.candidates if item.kind == "return"} == {"Config.run.inner", "Config.run"}
    assert {item.text for item in inventory.candidates if item.kind == "decorator"} == {"dataclass", "decorated"}
    assert next(item for item in inventory.candidates if item.kind == "schema_field").text == "mode: str"


def test_scope_digest_changes_for_unsupported_edits_and_is_checkout_independent(tmp_path: Path) -> None:
    for name in ("one", "two"):
        root = tmp_path / name
        root.mkdir()
        (root / "api.py").write_text("def a():\n    return 1\n", encoding="utf-8")
        (root / "ui.rb").write_text("limit = 1", encoding="utf-8")
    first = extract_evidence(tmp_path / "one", ["api.py", "ui.rb", "absent.py"])
    second = extract_evidence(tmp_path / "two", ["ui.rb", "absent.py", "api.py"])
    assert first == second
    before = build_audit_packets(first, []).packets[0]
    (tmp_path / "one/ui.rb").write_text("limit = 2", encoding="utf-8")
    after = build_audit_packets(extract_evidence(tmp_path / "one", list(first.scope)), []).packets[0]
    assert before.digest != after.digest


def test_packet_shows_side_effect_preceding_return_and_prior_guard(tmp_path: Path) -> None:
    source = (
        "LIMIT = 20\n"
        "sent = []\n"
        "def send(items, limit=LIMIT):\n"
        "    if limit < 0:\n        raise ValueError('negative')\n"
        "    selected = items[:limit]\n"
        "    sent.extend(selected)\n"
        "    return len(selected)\n"
    )
    path = tmp_path / "api.py"
    path.write_text(source, encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["api.py"])
    packet = build_audit_packets(inventory, [], skip_undocumented=False).packets[0]
    assert "sent.extend(selected)" in packet.model_dump_json()
    contexts = packet.source_context
    enclosing = next(context for context in contexts if context.symbol == "send")
    assert enclosing.text == "".join(source.splitlines(keepends=True)[2:])
    assert (enclosing.start_line, enclosing.end_line) == (3, 8)
    assert "if limit < 0:" in enclosing.text
    assert "LIMIT = 20" in "\n".join(context.text for context in contexts)
    assert all(context.source_digest == hashlib.sha256(path.read_bytes()).hexdigest() for context in contexts)
    assert len([context for context in contexts if context.symbol == "send"]) == 1
    assert inventory.source_context == contexts
    receipt = verdicts(packet)
    validate_verdicts(packet, receipt)
    for chunk in build_audit_packets(inventory, [], max_items=2, skip_undocumented=False).packets:
        assert enclosing in chunk.source_context
    path.write_text(source.replace("sent.extend(selected)", "sent.clear()"), encoding="utf-8")
    current_inventory = extract_evidence(tmp_path, ["api.py"])
    assert [item.id for item in current_inventory.candidates] == [item.id for item in inventory.candidates]
    current = build_audit_packets(current_inventory, [], skip_undocumented=False).packets[0]
    assert validate_verdicts(packet, receipt).packet_digest != current.digest, "a context edit re-keys the receipt"


def test_book_context_retains_signature_output_and_neighboring_prose_not_siblings(tmp_path: Path) -> None:
    path = tmp_path / "docs/features/api.md"
    path.parent.mkdir(parents=True)
    text = (
        "---\ntype: server\ntitle: API\n---\n# API\n\n## Endpoints\n\n"
        "### send\n- sig: send(items, limit=20)\n- output: Number of selected items.\n"
        "Algorithm selects the prefix before sending it.\n"
        "```text\n### not a sibling heading\n```\n"
        "- does: Sends selected items.\n- does: Returns their count.\n- code: api.py::send\n\n"
        "### sibling\n" + "Unrelated prose. " * 7000 + "\n"
    )
    path.write_text(text, encoding="utf-8")
    claims = extract_claims(load(tmp_path))
    assert len(claims) == 2, "Signatures and output context are not new obligations"
    packet = build_audit_packets(extract_evidence(tmp_path, []), claims).packets[0]
    assert "send(items, limit=20)" in packet.model_dump_json()
    assert len(packet.book_context) == 1
    context = packet.book_context[0]
    assert context.text == "\n".join(text.splitlines()[8:19]) + "\n"
    assert (context.start_line, context.end_line) == (9, 19)
    assert context.source_digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert "Unrelated prose" not in context.text
    assert all(claim.context == (context,) for claim in claims)
    assert all(not claim.context for claim in packet.claims), "Packet context is deduplicated by node"
    assert AuditPacket.model_validate_json(packet.model_dump_json()) == packet
    receipt = AuditVerdicts(candidates=(), claims=tuple(
        ClaimVerdict(id=claim.id, status="unresolved", explanation="No source selected.") for claim in packet.claims))
    validate_verdicts(packet, receipt)
    path.write_text(text.replace("limit=20", "limit=30"), encoding="utf-8")
    changed = extract_claims(load(tmp_path))
    assert [(claim.id, claim.text) for claim in changed] == [(claim.id, claim.text) for claim in claims]
    current = build_audit_packets(extract_evidence(tmp_path, []), changed).packets[0]
    assert validate_verdicts(packet, receipt).packet_digest != current.digest, "a sibling edit re-keys the receipt"
    path.write_text(text.replace("Unrelated prose.", "Changed sibling."), encoding="utf-8")
    sibling_edit = build_audit_packets(extract_evidence(tmp_path, []), extract_claims(load(tmp_path))).packets[0]
    assert sibling_edit.book_context[0].text == context.text
    assert validate_verdicts(packet, receipt).packet_digest != sibling_edit.digest, "a sibling edit re-keys the receipt"


@pytest.mark.parametrize("side", ["source", "book"])
def test_packet_budget_counts_indivisible_context_without_truncation(tmp_path: Path, side: str) -> None:
    source = "def send():\n    # " + "context " * (1500 if side == "source" else 1) + "\n    return 1\n"
    (tmp_path / "api.py").write_text(source, encoding="utf-8")
    path = tmp_path / "docs/features/api.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\ntype: server\n---\n# API\n\n## Endpoints\n\n### send\n"
                    "- does: Sends items.\n- code: api.py::send\n\n"
                    + "Neighboring prose. " * (1500 if side == "book" else 1) + "\n", encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["api.py"])
    claims = extract_claims(load(tmp_path))
    assert len(claims) == 1
    with pytest.raises(ValueError, match="oversized.*without truncation"):
        build_audit_packets(inventory, claims, max_chars=6000)
    packet = build_audit_packets(inventory, claims).packets[0]
    assert len(packet.model_dump_json()) > 6000
    assert build_audit_packets(inventory, claims, max_chars=len(packet.model_dump_json())).packets == (packet,)


def test_class_field_context_does_not_include_unrelated_methods(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        "@dataclass\nclass Config:\n    \"\"\"Delivery settings.\"\"\"\n    limit: int = 20\n"
        "    def unrelated(self):\n        # " + "large method " * 7000 + "\n        consume(self)\n",
        encoding="utf-8",
    )
    packet = build_audit_packets(extract_evidence(tmp_path, ["api.py"]), [], max_chars=6000, skip_undocumented=False).packets[0]
    assert "Delivery settings." in packet.model_dump_json()
    assert "large method" not in packet.model_dump_json()
    assert any("no candidates" in note.lower() for note in packet.limitations)


def test_explicit_support_context_preserves_helpers_without_minting_candidates(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text("def read(raw):\n    return parse_position(raw)\n", encoding="utf-8")
    helper = tmp_path / "helper.py"
    data = b"import json\r\ndef parse_position(raw):\r\n    try:\r\n        return json.loads(raw)\r\n    except ValueError:\r\n        return None\r\n"
    helper.write_bytes(data)
    baseline = extract_evidence(tmp_path, ["api.py"])
    inventory = extract_evidence(tmp_path, ["api.py"], context_paths=["helper.py", "./helper.py"])
    assert inventory.candidates == baseline.candidates
    assert inventory.files == baseline.files and inventory.scope == baseline.scope
    assert inventory.context_paths == ("helper.py",)
    assert len(inventory.support_context) == 1
    context = inventory.support_context[0]
    assert context.text == data.decode() and context.source_digest == hashlib.sha256(data).hexdigest()
    assert (context.path, context.start_line, context.end_line) == ("helper.py", 1, len(data.splitlines()))
    claims = [BookClaim(id=f"claim:{i}", node="read", path="docs/api.md", line=1,
                        kind="does", text="Reads input", citations=("api.py::read",)) for i in range(3)]
    preparation = build_audit_packets(inventory, claims, max_items=2)
    assert preparation.selected_candidates == len(baseline.candidates)
    assert len(preparation.packets) == len(build_audit_packets(baseline, claims, max_items=2).packets)
    for packet in preparation.packets:
        assert packet.support_context == (context,)
        assert "json.loads(raw)" in packet.model_dump_json()
        assert AuditPacket.model_validate_json(packet.model_dump_json()) == packet
    before = preparation.packets[0]
    receipt = verdicts(before)
    validate_verdicts(before, receipt)
    helper.write_bytes(data.replace(b"return None", b"return {}"))
    current = extract_evidence(tmp_path, ["api.py"], context_paths=inventory.context_paths)
    assert current.candidates == inventory.candidates
    after = build_audit_packets(current, claims, max_items=2).packets[0]
    assert validate_verdicts(before, receipt).packet_digest != after.digest, "a helper edit re-keys the receipt"
    assert any("import closure" in note for note in after.limitations)


@pytest.mark.parametrize("selector", ["../outside.py", "/absolute.py", "link.py", ""])
def test_support_context_rejects_escape_and_empty_selectors(tmp_path: Path, selector: str) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "outside.py").write_text("return_value = 1\n", encoding="utf-8")
    (root / "link.py").symlink_to(tmp_path / "outside.py")
    with pytest.raises(ValueError, match="relative|outside|empty selector"):
        extract_evidence(root, [], context_paths=[selector])


def test_support_context_failures_are_visible_in_every_packet(tmp_path: Path) -> None:
    (tmp_path / "helper.rb").write_text("return 1", encoding="utf-8")
    (tmp_path / "bad.py").write_text("def broken(:", encoding="utf-8")
    (tmp_path / "directory").mkdir()
    inventory = extract_evidence(tmp_path, [], context_paths=["missing.py", "helper.rb", "bad.py", "directory"])
    assert {file.path: file.status for file in inventory.context_files} == {
        "missing.py": "unreadable", "helper.rb": "unsupported", "bad.py": "parse_error", "directory": "unsupported",
    }
    packet = build_audit_packets(inventory, [], skip_undocumented=False).packets[0]
    assert not packet.candidates and not packet.support_context
    for file in inventory.context_files:
        assert any(file.path in note and file.status in note and "unresolved" in note for note in packet.limitations)


def test_support_context_budget_counts_full_file_and_empty_files(tmp_path: Path) -> None:
    helper = tmp_path / "helper.py"
    helper.write_text("", encoding="utf-8")
    empty = extract_evidence(tmp_path, [], context_paths=["helper.py"])
    assert empty.support_context[0].text == ""
    helper.write_text("# " + "context " * 2000 + "\n", encoding="utf-8")
    inventory = extract_evidence(tmp_path, [], context_paths=["helper.py"])
    packet = build_audit_packets(inventory, [], skip_undocumented=False).packets[0]
    assert packet.support_context[0].text == helper.read_text(encoding="utf-8")
    size = len(packet.model_dump_json())
    assert build_audit_packets(inventory, [], max_chars=size).packets == (packet,)
    with pytest.raises(ValueError, match="oversized.*without truncation"):
        build_audit_packets(inventory, [], max_chars=size - 1)


@pytest.fixture
def signature_packet(tmp_path: Path) -> AuditPacket:
    (tmp_path / "api.py").write_text("def review(run_dir=''):\n    return run_dir\n", encoding="utf-8")
    book = tmp_path / "docs/features/api.md"
    book.parent.mkdir(parents=True)
    book.write_text(
        "---\ntype: server\n---\n# API\n\n## Endpoints\n\n### review\n"
        "- sig: review(run_dir='')\n\n- does: Returns the run directory.\n- code: api.py::review\n",
        encoding="utf-8",
    )
    return build_audit_packets(extract_evidence(tmp_path, ["api.py"]), extract_claims(load(tmp_path))).packets[0]


def test_signature_span_covers_default_without_minting_claims(signature_packet: AuditPacket, tmp_path: Path) -> None:
    packet = signature_packet
    payload = verdicts(packet).model_dump(mode="json")
    for claim in payload["claims"]:
        claim.update(status="unresolved", candidate_ids=[])
    for candidate in payload["candidates"]:
        candidate.update(status="unresolved")
    default = next(item for item in packet.candidates if item.kind == "function_default")
    context = packet.book_context[0]
    line = context.start_line + context.text.splitlines().index("- sig: review(run_dir='')")
    target = next(item for item in payload["candidates"] if item["id"] == default.id)
    target.update(status="covered", book_evidence=[{"node": context.node, "start_line": line, "end_line": line}])
    report = validate_verdicts(packet, payload)
    recorded = next(item for item in report.verdicts.candidates if item.id == default.id)
    assert recorded.status == "covered"
    assert recorded.model_dump(mode="json")["book_evidence"] == [{"node": context.node, "start_line": line, "end_line": line}]
    assert len(report.verdicts.candidates) == len(packet.candidates) == 2
    assert len(report.verdicts.claims) == len(packet.claims) == 1
    assert report.verdicts.claims[0].status == "unresolved"
    assert any("not QA proof" in note for note in report.limitations)
    assert AuditVerdicts.model_validate_json(report.verdicts.model_dump_json()) == report.verdicts
    book = tmp_path / context.path
    book.write_text(book.read_text().replace("run_dir=''", "run_dir='other'"), encoding="utf-8")
    current = build_audit_packets(extract_evidence(tmp_path, ["api.py"]), extract_claims(load(tmp_path))).packets[0]
    assert current.candidates == packet.candidates and current.claims == packet.claims
    assert current.digest != report.packet_digest, "a book-context edit re-keys the receipt"


@pytest.mark.parametrize("fault", ["foreign", "before", "after", "reversed", "blank", "duplicate", "missing", "unresolved", "implementation_detail", "claim_link"])
def test_book_evidence_rejects_invalid_spans_and_statuses(signature_packet: AuditPacket, fault: str) -> None:
    packet = signature_packet
    context = packet.book_context[0]
    payload = verdicts(packet).model_dump(mode="json")
    payload["claims"][0].update(status="unresolved", candidate_ids=[])
    for candidate in payload["candidates"]:
        candidate.update(status="unresolved")
    ref = {"node": context.node, "start_line": context.start_line + 1, "end_line": context.start_line + 1}
    target = payload["candidates"][0]
    target.update(status="covered", book_evidence=[ref])
    if fault == "foreign":
        ref["node"] = "foreign"
    elif fault == "before":
        ref.update(start_line=1, end_line=1)
    elif fault == "after":
        ref["end_line"] = context.end_line + 1
    elif fault == "reversed":
        ref["start_line"] = context.start_line + 2
    elif fault == "blank":
        ref.update(start_line=context.start_line + 2, end_line=context.start_line + 2)
    elif fault == "duplicate":
        target["book_evidence"] *= 2
    elif fault == "claim_link":
        payload["claims"][0]["status"] = "supported"
    else:
        target["status"] = fault
    with pytest.raises(ValueError, match="book evidence|candidate links"):
        validate_verdicts(packet, payload)


def test_old_receipt_without_book_evidence_still_validates(audit_packet: AuditPacket) -> None:
    payload = verdicts(audit_packet).model_dump(mode="json")
    for candidate in payload["candidates"]:
        candidate.pop("book_evidence", None)
    report = validate_verdicts(audit_packet, payload)
    assert all(item.model_dump()["book_evidence"] == () for item in report.verdicts.candidates)


def test_two_sections_sharing_a_heading_are_both_audited(tmp_path: Path) -> None:
    """A repeated heading is two nodes at two anchors, so neither claim is dropped.

    They used to share an id — `model.anchor_of` minted it from the heading title alone — and
    `extract_book` skipped every claim under the second, recording a limitation that told the
    operator to repair a `duplicate-container-heading` finding. That code fires only on
    *registered* container headings, so on this shape doctor reported nothing and the named
    repair did not exist. `model.document_anchors` issues the anchor GitHub renders, unique
    within a document, and the skip has nothing left to skip.
    """
    docs = tmp_path / "docs/features/api"
    docs.mkdir(parents=True)
    (docs / "items.md").write_text(
        "---\ntype: server\ntitle: API\n---\n\n# API\n\n## Endpoints\n\n### items\n\n"
        "- does: Limit is 50.\n- code: api.py::items\n\n### items\n\n- does: Limit is 60.\n\n"
        "### other\n\n- does: Ordering is by id.\n- code: api.py::other\n",
        encoding="utf-8",
    )
    (tmp_path / "api.py").write_text("def items():\n    return 50\n\ndef other():\n    return 1\n", encoding="utf-8")
    graph = load(tmp_path)
    book = extract_book(graph)
    assert [claim.node for claim in book.claims] == ["docs/features/api/items.md#items",
                                                     "docs/features/api/items.md#items-1",
                                                     "docs/features/api/items.md#other"]
    assert book.limitations == ()
    preparation = build_audit_packets(extract_evidence(tmp_path, ["api.py"]), book)
    assert len(preparation.packets) >= 1


def test_uncited_file_with_exported_symbols_is_a_finding_not_a_packet(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "public.py").write_text(
        "def _helper():\n    return 0\n\nclass Api:\n    def get(self):\n        return 1\n", encoding="utf-8",
    )
    (source / "private.py").write_text("def _only():\n    return 2\n", encoding="utf-8")
    (source / "empty.py").write_text("x = 1\n", encoding="utf-8")
    (source / "exported.go").write_text(
        "package p\n\ntype thing struct{}\n\nfunc (t thing) Do() int { return 1 }\n\nfunc Run() int { return 2 }\n",
        encoding="utf-8",
    )
    preparation = build_audit_packets(extract_evidence(tmp_path, ["src"]), [])
    assert {packet.module for packet in preparation.packets} == {"src/empty.py"}
    assert preparation.deferred_candidates == 4, "_helper, _only and the unexported type's two on Do"
    found = {file.path: file for file in preparation.undocumented}
    assert set(found) == {"src/public.py", "src/exported.go"}
    assert found["src/public.py"].exported_symbols == ("Api.get",)
    assert found["src/public.py"].first_lines == (6,)
    assert found["src/public.py"].candidate_count == 1, "the tier-1 candidates only; _helper is deferred"
    assert found["src/exported.go"].exported_symbols == ("Run",)
    # The finding is a fact about the book: one citation turns the file back into a packet.
    claim = BookClaim(id="claim:0", node="node", path="docs/book.md", line=1, kind="does",
                      text="Gets", citations=("src/public.py::Api.get",))
    cited = build_audit_packets(extract_evidence(tmp_path, ["src"]), [claim])
    assert {file.path for file in cited.undocumented} == {"src/exported.go"}
    assert any(packet.module == "src/public.py" for packet in cited.packets)


def test_cited_claimless_file_keeps_its_packet(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/public.py").write_text("def get():\n    return 1\n", encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["src"])
    assert build_audit_packets(inventory, BookClaims(claims=())).undocumented
    cited = build_audit_packets(inventory, BookClaims(claims=(), cited_paths=("src/public.py",)))
    assert not cited.undocumented
    assert [packet.group for packet in cited.packets] == ["source_file"]


@pytest.mark.parametrize(("path", "symbol", "expected"), [
    ("a.py", "Api.get", True), ("a.py", "Api._get", False), ("a.py", "_Api.get", False),
    ("a.py", "<module>", False), ("a.go", "Run", True), ("a.go", "thing.Do", False),
    ("a.go", "Thing.Do", True), ("a.go", "Thing.do", False),
])
def test_exported_symbol_rule_per_language(path: str, symbol: str, expected: bool) -> None:
    assert exported_symbol(path, symbol) is expected


def test_tier_one_keeps_cited_and_exported_candidates_and_defers_the_rest(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/svc.py").write_text(
        "def get():\n    return 1\n\ndef _helper():\n    return 2\n\ndef _cited():\n    return 3\n\n"
        "class _Box:\n    def read(self):\n        return 4\n",
        encoding="utf-8",
    )
    (tmp_path / "src/whole.py").write_text("def _all():\n    return 5\n", encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["src"])
    claim = BookClaim(id="claim:0", node="node", path="docs/book.md", line=1, kind="does",
                      text="Reads", citations=("src/svc.py::_cited",))
    book = BookClaims(claims=(claim,), cited_paths=("src/svc.py", "src/whole.py"),
                      cited_symbols=("src/svc.py::_cited", "src/whole.py"))
    first = build_audit_packets(inventory, book)
    by_module = {packet.module: packet for packet in first.packets}
    assert {c.symbol for c in by_module["src/svc.py"].candidates} == {"get", "_cited"}
    # A bare path citation keeps every candidate in that file, private or not.
    assert {c.symbol for c in by_module["src/whole.py"].candidates} == {"_all"}
    assert first.tier == 1 and first.deferred_candidates == 2
    assert first.selected_candidates == len(inventory.candidates) - 2
    assert by_module["src/svc.py"].omitted_candidates == first.selected_candidates - 2
    assert any("2 tier-2 candidates" in limit and "--tier all" in limit
               for limit in by_module["src/svc.py"].limitations)
    assert not any("tier-2" in limit for limit in by_module["src/whole.py"].limitations)
    everything = build_audit_packets(inventory, book, tier="all")
    assert everything.tier == "all" and everything.deferred_candidates == 0
    assert everything.selected_candidates == len(inventory.candidates)
    assert {c.symbol for packet in everything.packets for c in packet.candidates} == {"get", "_cited", "_helper", "_Box.read", "_all"}
    assert not any("tier-2" in limit for packet in everything.packets for limit in packet.limitations)


def test_a_file_of_only_private_uncited_candidates_costs_no_packet_at_tier_one(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/private.py").write_text("def _only():\n    return 2\n", encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["src"])
    prepared = build_audit_packets(inventory, BookClaims(claims=()))
    assert not prepared.undocumented and prepared.deferred_candidates == 1
    assert not prepared.packets
    claim = BookClaim(id="claim:0", node="node", path="docs/book.md", line=1, kind="does",
                      text="Counts", citations=("src/private.py::_only",))
    (packet,) = build_audit_packets(inventory, BookClaims(claims=(claim,), cited_symbols=("src/private.py::_only",))).packets
    assert [c.symbol for c in packet.candidates] == ["_only"]
    # A module-level candidate has no private name: it is tier 1 wherever it sits.
    (tmp_path / "src/top.py").write_text("LIMIT = 2\nif LIMIT < 0:\n    raise ValueError('no')\n", encoding="utf-8")
    top = build_audit_packets(extract_evidence(tmp_path, ["src/top.py"]), BookClaims(claims=()))
    assert [c.symbol for packet in top.packets for c in packet.candidates] == ["<module>"]


def test_claims_citing_only_existing_unselected_files_are_out_of_scope_with_a_root(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("def get():\n    return 1\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("def other():\n    return 2\n", encoding="utf-8")
    claims = [
        BookClaim(id="claim:here", node="n", path="docs/book.md", line=1, kind="does", text="Here",
                  citations=("src/a.py::get",)),
        BookClaim(id="claim:elsewhere", node="n", path="docs/book.md", line=2, kind="does", text="Elsewhere",
                  citations=("other.py::other",)),
        BookClaim(id="claim:gone", node="n", path="docs/book.md", line=3, kind="does", text="Gone",
                  citations=("missing.py::x",)),
        BookClaim(id="claim:mixed", node="n", path="docs/book.md", line=4, kind="does", text="Mixed",
                  citations=("other.py::other", "repo://malformed")),
    ]
    scoped = build_audit_packets(extract_evidence(tmp_path, ["src"]), claims, root=tmp_path)
    assert scoped.out_of_scope_claims == 1 and scoped.selected_claims == 3
    ids = {claim.id for packet in scoped.packets for claim in packet.claims}
    assert ids == {"claim:here", "claim:gone", "claim:mixed"}, "a missing or malformed citation stays a reviewer's"
    assert all(any(note.startswith("1 claims cite only files outside") for note in packet.limitations)
               for packet in scoped.packets)
    unrooted = build_audit_packets(extract_evidence(tmp_path, ["src"]), claims)
    assert unrooted.out_of_scope_claims == 0 and unrooted.selected_claims == 4
    assert not any("outside the selected source scope" in note for packet in unrooted.packets for note in packet.limitations)


def test_a_packet_carries_its_own_file_limitations_not_another_files(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("def a():\n    return 1\n\ndef a_quiet():\n    pass\n", encoding="utf-8")
    (src / "b.py").write_text("def b():\n    return 1\n\ndef b_quiet():\n    pass\n", encoding="utf-8")
    preparation = build_audit_packets(extract_evidence(tmp_path, ["src"]), (), skip_undocumented=False)
    assert any("src/a.py::a_quiet" in note for note in preparation.inventory.limitations)
    by_module = {packet.module: packet for packet in preparation.packets}
    assert any("src/a.py::a_quiet" in note for note in by_module["src/a.py"].limitations)
    assert not any("src/b.py::" in note for note in by_module["src/a.py"].limitations)
    assert any("src/b.py::b_quiet" in note for note in by_module["src/b.py"].limitations)
    assert all(note in by_module["src/a.py"].limitations for note in preparation.inventory.limitations
               if "::" not in note), "the generic extraction limitations stay on every packet"


def test_book_context_is_windowed_around_the_packets_claims(tmp_path: Path) -> None:
    path = tmp_path / "docs/features/api.md"
    path.parent.mkdir(parents=True)
    filler = "".join(f"Prose line {i}.\n" for i in range(120))
    text = ("---\ntype: server\ntitle: API\n---\n# API\n\n## Endpoints\n\n### send\n"
            "- does: Sends items.\n" + filler + "- does: Returns their count.\n" + filler.replace("Prose", "Tail")
            + "- code: api.py::send\n")
    path.write_text(text, encoding="utf-8")
    claims = extract_claims(load(tmp_path))
    assert len(claims) == 2
    whole = claims[0].context[0]
    packet = build_audit_packets(extract_evidence(tmp_path, []), claims, context_lines=10).packets[0]
    assert len(packet.book_context) == 1
    context = packet.book_context[0]
    assert context.start_line == whole.start_line and context.end_line == claims[1].line + 10
    assert context.end_line < whole.end_line, "the prose past the last claim is cut"
    assert context.text == "".join(text.splitlines(keepends=True)[context.start_line - 1:context.end_line])
    assert "Tail line 119." not in context.text
    first_only = build_audit_packets(extract_evidence(tmp_path, []), claims[:1], context_lines=10).packets[0]
    window = first_only.book_context[0]
    assert (window.start_line, window.end_line) == (whole.start_line, claims[0].line + 10)
    wide = build_audit_packets(extract_evidence(tmp_path, []), claims, context_lines=200).packets[0]
    assert wide.book_context == (whole,), "a section inside the window is carried whole"
    receipt = AuditVerdicts(candidates=(), claims=tuple(
        ClaimVerdict(id=claim.id, status="unresolved", explanation="No source selected.") for claim in packet.claims))
    validate_verdicts(packet, receipt)
    with pytest.raises(ValueError, match="context_lines"):
        build_audit_packets(extract_evidence(tmp_path, []), claims, context_lines=0)


def test_a_scoped_read_never_opens_another_service_book(tmp_path: Path) -> None:
    """One service's audit must not fail on another service's documents.

    Two okf-builder runs share a repo and scope themselves to a service each. The scope used
    to be applied to `extract_book`'s *result*, so the read still opened every document in
    `docs/features/**` and matched each node's recorded line against a section start — and a
    sibling run authoring its own book moved those lines underneath the graph, raising here on
    nodes this run was about to discard. Scoping the read is what makes the two runs
    independent; the citation index stays whole-graph, so a symbol cited only from the sibling
    book is still known to be cited.
    """
    for service, symbol in (("api", "items"), ("web", "render")):
        docs = tmp_path / "docs/features" / service
        docs.mkdir(parents=True)
        (docs / f"{service}.md").write_text(
            f"---\ntype: server\ntitle: {service}\n---\n\n# {service}\n\n## Endpoints\n\n### {symbol}\n\n"
            f"- does: It answers.\n- code: {service}.py::{symbol}\n",
            encoding="utf-8",
        )
        (tmp_path / f"{service}.py").write_text(f"def {symbol}():\n    return 1\n", encoding="utf-8")
    graph = load(tmp_path)
    # The sibling run authors its book: every section below the insertion moves down, and the
    # graph in hand still points at the old offsets.
    web = tmp_path / "docs/features/web/web.md"
    web.write_text(web.read_text(encoding="utf-8").replace(
        "# web\n", "# web\n\nA new paragraph.\n\nAnd another one.\n"), encoding="utf-8")

    with pytest.raises(ValueError, match="docs/features/web/web.md#render"):
        extract_book(graph)

    book = extract_book(graph, scope="docs/features/api/")
    assert [claim.node for claim in book.claims] == ["docs/features/api/api.md#items"]
    assert "web.py::render" in book.cited_symbols


def test_last_sections_book_evidence_span_is_citable_to_its_final_line(tmp_path: Path) -> None:
    """The file's last section must not advertise a line its own text does not carry.

    A body ending in a newline splits to one more line than it has, so the final
    section's end_line ran one past the document. A reviewer citing that whole span
    was then rejected as unseen, which parks the audit on an operator gate over a
    packet defect no reviewer can answer.
    """
    path = tmp_path / "docs/features/api.md"
    path.parent.mkdir(parents=True)
    text = (
        "---\ntype: server\ntitle: API\n---\n# API\n\n## Endpoints\n\n"
        "### send\n- does: Sends selected items.\n- code: api.py::send\n\n"
        "### receive\n- does: Receives selected items.\n- code: api.py::receive\n"
    )
    path.write_text(text, encoding="utf-8")
    (tmp_path / "api.py").write_text(
        "def send(items):\n    if not items:\n        raise ValueError('empty')\n    return len(items)\n\n\n"
        "def receive(items):\n    if not items:\n        raise ValueError('empty')\n    return len(items)\n",
        encoding="utf-8")
    packet = build_audit_packets(extract_evidence(tmp_path, ["api.py"]), extract_claims(load(tmp_path))).packets[0]
    last = next(context for context in packet.book_context if context.node.endswith("#receive"))
    assert (last.start_line, last.end_line) == (13, 15)
    assert last.end_line == len(text.splitlines()), "the span stops at the document's last line"
    assert len(last.text.splitlines()) == last.end_line - last.start_line + 1
    covered = CandidateVerdict(id=packet.candidates[0].id, status="covered", explanation="Documented.",
                               book_evidence=(BookEvidenceRef(node=last.node, start_line=last.start_line,
                                                              end_line=last.end_line),))
    receipt = AuditVerdicts(
        candidates=(covered, *(CandidateVerdict(id=candidate.id, status="unresolved", explanation="Not assessed.")
                               for candidate in packet.candidates[1:])),
        claims=tuple(ClaimVerdict(id=claim.id, status="unresolved", explanation="No source selected.")
                     for claim in packet.claims))
    validate_verdicts(packet, receipt)


def test_excerpt_bounds_must_match_the_text_the_excerpt_carries() -> None:
    """An excerpt that advertises a span its own text does not carry cannot be built.

    This is the invariant the last-section defect above broke, hoisted from a docstring
    into the model. Every citation a reviewer can make is bounded by these numbers, so a
    packet that lies about them is unanswerable — the honest reading of the whole span
    is rejected as unseen, and no retry can repair a defect in the question. Refusing it
    here moves that from an operator gate hours later to the extractor that built it.
    """
    with pytest.raises(ValidationError, match=r"lines 1-3 span 3 line\(s\) but the text carries 2"):
        BookContext(node="items", path="docs/items.md", start_line=1, end_line=3,
                    text="# Items\n- Returns 20\n", source_digest="d")
    with pytest.raises(ValidationError, match=r"lines 1-1 span 1 line\(s\) but the text carries 2"):
        SourceContext(path="api.py", symbol="items", start_line=1, end_line=1,
                      text="def items():\n    return 20\n", source_digest="d")
    trailing = BookContext(node="items", path="docs/items.md", start_line=1, end_line=2,
                           text="# Items\n- Returns 20\n", source_digest="d")
    assert trailing.text.endswith("\n"), "a trailing newline closes the last line, it does not open one"
    unterminated = BookContext(node="items", path="docs/items.md", start_line=4, end_line=5,
                               text="# Items\n- Returns 20", source_digest="d")
    assert unterminated.end_line == 5


def test_an_empty_file_excerpt_still_stands_at_line_one() -> None:
    """`SourceExcerpt` widens its text to allow an empty file, and documents line 1 as its bound.

    The line count of "" is zero by any arithmetic, so the validator has to floor at one
    or the shape the extractor emits for an empty file becomes unconstructible.
    """
    assert SourceExcerpt(path="empty.py", start_line=1, end_line=1, text="", source_digest="d").text == ""
    with pytest.raises(ValidationError, match=r"lines 1-2 span 2 line\(s\) but the text carries 1"):
        SourceExcerpt(path="empty.py", start_line=1, end_line=2, text="", source_digest="d")
