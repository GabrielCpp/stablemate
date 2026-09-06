from __future__ import annotations

from pathlib import Path
import hashlib

import pytest

from ostler.behavior import (
    AuditPacket, AuditVerdicts, BookClaim, CandidateVerdict, ClaimVerdict,
    build_audit_packets, duplicate_node_ids, extract_book, extract_claims, extract_evidence,
    validate_verdicts,
)
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
    (tmp_path / "app.ts").write_text("const a = 1;", encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["bad.py", "empty.py", "app.ts", "absent.py"])
    assert {item.path: item.status for item in inventory.files} == {
        "bad.py": "parse_error", "empty.py": "parsed", "app.ts": "unsupported", "absent.py": "unreadable",
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
    without_book = build_audit_packets(inventory, [])
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
    for name in ("a.py", "b.py", "uncited.py"):
        (source / name).write_text("def a():\n    return 1\n", encoding="utf-8")
    citations = [
        ("`./src/a.py::wrong`, `src\\b.py::other`",),
        (), ("repo://api-service/src/a.py::a",), ("missing.py::a",), ("repo://malformed",),
    ]
    claims = [BookClaim(id=f"claim:{i}", node="node", path="docs/book.md", line=1,
                        kind="does", text=f"Promise {i}", citations=refs) for i, refs in enumerate(citations)]
    preparation = build_audit_packets(extract_evidence(tmp_path, ["src"]), claims)
    assert len(preparation.packets) == 4
    by_module = {packet.module: packet for packet in preparation.packets if packet.module}
    assert {claim.id for claim in by_module["src/a.py"].claims} == {"claim:0"}
    assert {claim.id for claim in by_module["src/b.py"].claims} == {"claim:0"}
    assert not by_module["src/uncited.py"].claims
    assert len(by_module["src/uncited.py"].candidates) == 1
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
    (source / "ui.ts").write_text("const a = 1;", encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["src"])
    assert {file.path for file in inventory.files} == {"src/api.py", "src/ui.ts"}
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
    packet = build_audit_packets(inventory, []).packets[0]
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
        packet_digest=packet.digest,
        claims=tuple(ClaimVerdict(id=claim.id, status="contradicted", explanation="Returns 20, not 50.",
                                 candidate_ids=tuple(item.id for item in packet.candidates)) for claim in packet.claims),
        candidates=tuple(CandidateVerdict(id=item.id, status="missing", explanation="Book promises a different value.",
                                         claim_ids=tuple(claim.id for claim in packet.claims)) for item in packet.candidates),
    )


def test_verdicts_are_external_not_inferred_from_shared_words(audit_packet: AuditPacket) -> None:
    report = validate_verdicts(audit_packet, verdicts(audit_packet).model_dump(mode="json"))
    assert report.verdicts.claims[0].status == "contradicted"
    assert report.verdicts.candidates[0].status == "missing"
    assert report.limitations
    unresolved = AuditVerdicts(packet_digest=audit_packet.digest,
                              claims=(ClaimVerdict(id=audit_packet.claims[0].id, status="unresolved", explanation="Need execution context."),),
                              candidates=(CandidateVerdict(id=audit_packet.candidates[0].id, status="unresolved", explanation="Need owner decision."),))
    assert validate_verdicts(audit_packet, unresolved).verdicts == unresolved


@pytest.mark.parametrize("fault", ["missing", "duplicate", "foreign", "foreign_link", "duplicate_link", "unpaired_link", "blank", "stale", "unsupported_support"])
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
    elif fault == "unpaired_link":
        payload["candidates"][0]["claim_ids"] = []
    elif fault == "blank":
        payload["claims"][0]["explanation"] = "   "
    elif fault == "stale":
        payload["packet_digest"] = "old"
    else:
        payload["claims"][0]["status"] = "supported"
        payload["claims"][0]["candidate_ids"] = []
        payload["candidates"][0]["claim_ids"] = []
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
    with pytest.raises(ValueError, match="digest"):
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
    payload["candidates"][0].update(status="implementation_detail", claim_ids=[], explanation="Private helper; not a public contract.")
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
        (root / "ui.ts").write_text("const limit = 1;", encoding="utf-8")
    first = extract_evidence(tmp_path / "one", ["api.py", "ui.ts", "absent.py"])
    second = extract_evidence(tmp_path / "two", ["ui.ts", "absent.py", "api.py"])
    assert first == second
    before = build_audit_packets(first, []).packets[0]
    (tmp_path / "one/ui.ts").write_text("const limit = 2;", encoding="utf-8")
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
    packet = build_audit_packets(inventory, []).packets[0]
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
    for chunk in build_audit_packets(inventory, [], max_items=2).packets:
        assert enclosing in chunk.source_context
    path.write_text(source.replace("sent.extend(selected)", "sent.clear()"), encoding="utf-8")
    current_inventory = extract_evidence(tmp_path, ["api.py"])
    assert [item.id for item in current_inventory.candidates] == [item.id for item in inventory.candidates]
    current = build_audit_packets(current_inventory, []).packets[0]
    with pytest.raises(ValueError, match="stale"):
        validate_verdicts(current, receipt)


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
    receipt = AuditVerdicts(packet_digest=packet.digest, candidates=(), claims=tuple(
        ClaimVerdict(id=claim.id, status="unresolved", explanation="No source selected.") for claim in packet.claims))
    validate_verdicts(packet, receipt)
    path.write_text(text.replace("limit=20", "limit=30"), encoding="utf-8")
    changed = extract_claims(load(tmp_path))
    assert [(claim.id, claim.text) for claim in changed] == [(claim.id, claim.text) for claim in claims]
    current = build_audit_packets(extract_evidence(tmp_path, []), changed).packets[0]
    with pytest.raises(ValueError, match="stale"):
        validate_verdicts(current, receipt)
    path.write_text(text.replace("Unrelated prose.", "Changed sibling."), encoding="utf-8")
    sibling_edit = build_audit_packets(extract_evidence(tmp_path, []), extract_claims(load(tmp_path))).packets[0]
    assert sibling_edit.book_context[0].text == context.text
    with pytest.raises(ValueError, match="stale"):
        validate_verdicts(sibling_edit, receipt)


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
    packet = build_audit_packets(extract_evidence(tmp_path, ["api.py"]), [], max_chars=6000).packets[0]
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
    with pytest.raises(ValueError, match="stale"):
        validate_verdicts(after, receipt)
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
    (tmp_path / "helper.ts").write_text("return 1", encoding="utf-8")
    (tmp_path / "bad.py").write_text("def broken(:", encoding="utf-8")
    (tmp_path / "directory").mkdir()
    inventory = extract_evidence(tmp_path, [], context_paths=["missing.py", "helper.ts", "bad.py", "directory"])
    assert {file.path: file.status for file in inventory.context_files} == {
        "missing.py": "unreadable", "helper.ts": "unsupported", "bad.py": "parse_error", "directory": "unsupported",
    }
    packet = build_audit_packets(inventory, []).packets[0]
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
    packet = build_audit_packets(inventory, []).packets[0]
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
        candidate.update(status="unresolved", claim_ids=[])
    default = next(item for item in packet.candidates if item.kind == "function_default")
    context = packet.book_context[0]
    line = context.start_line + context.text.splitlines().index("- sig: review(run_dir='')")
    target = next(item for item in payload["candidates"] if item["id"] == default.id)
    target.update(status="covered", book_evidence=[{"node": context.node, "start_line": line, "end_line": line}])
    report = validate_verdicts(packet, payload)
    recorded = next(item for item in report.verdicts.candidates if item.id == default.id)
    assert recorded.status == "covered" and not recorded.claim_ids
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
    with pytest.raises(ValueError, match="stale"):
        validate_verdicts(current, report.verdicts)


@pytest.mark.parametrize("fault", ["foreign", "before", "after", "reversed", "blank", "duplicate", "missing", "unresolved", "implementation_detail", "claim_link"])
def test_book_evidence_rejects_invalid_spans_and_statuses(signature_packet: AuditPacket, fault: str) -> None:
    packet = signature_packet
    context = packet.book_context[0]
    payload = verdicts(packet).model_dump(mode="json")
    payload["claims"][0].update(status="unresolved", candidate_ids=[])
    for candidate in payload["candidates"]:
        candidate.update(status="unresolved", claim_ids=[])
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


def test_duplicate_anchor_claims_are_skipped_and_named(tmp_path: Path) -> None:
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
    assert duplicate_node_ids(graph) == ("docs/features/api/items.md#items",)
    book = extract_book(graph)
    assert [claim.node for claim in book.claims] == ["docs/features/api/items.md#other"]
    assert len(book.limitations) == 1 and "duplicate-container-heading" in book.limitations[0]
    preparation = build_audit_packets(extract_evidence(tmp_path, ["api.py"]), book)
    assert all(book.limitations[0] in packet.limitations for packet in preparation.packets)
    assert len(preparation.packets) >= 1
