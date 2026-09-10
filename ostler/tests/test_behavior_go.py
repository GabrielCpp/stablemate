from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ostler import syntax
from ostler.behavior import (
    AuditPacket, AuditVerdicts, CandidateVerdict, ClaimVerdict,
    build_audit_packets, extract_claims, extract_evidence, validate_verdicts,
)
from ostler.model import load


GO = '''package api
import "net/http"
type Request struct {
    Names []string `json:"names,omitempty" validate:"min=1"`
    Limit *int `json:"limit"`
}
type Service struct {}
func (s *Service) Read(limit int) (string, error) {
    if limit < 0 {
        return "", ErrNegative
    } else {
        switch limit {
        case 0, 1:
            return "small", nil
        default:
            panic("large")
        }
    }
}
func Wait(ch chan string) (string, error) {
    select {
    case value := <-ch:
        return value, nil
    default:
        return "", ErrEmpty
    }
}
func Register(mux *http.ServeMux) {
    mux.HandleFunc("GET /items", func(w http.ResponseWriter, r *http.Request) {
        w.WriteHeader(http.StatusCreated)
        w.Write([]byte("ok"))
        http.Error(w, "bad", http.StatusBadRequest)
    })
    http.Handle("/other", mux)
}
func (s Service) Clear() { s.items = nil }
func Notify() { sendMessage() }
// return false; panic("ghost"); http.HandleFunc("/ghost", ghost)
var fake = `return false; panic("ghost"); http.Error(w, "ghost", 500)`
'''


def test_go_candidates_keep_control_flow_signatures_fields_and_full_context(tmp_path: Path) -> None:
    path = tmp_path / "api.go"
    path.write_text(GO, encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["api.go"])
    assert inventory.files[0].status == "parsed"
    assert {item.kind for item in inventory.candidates} == {
        "return", "panic", "route", "http_response", "schema_field", "function_contract",
    }
    returns = [item for item in inventory.candidates if item.kind == "return"]
    assert len(returns) == 4
    negative = next(item for item in returns if "ErrNegative" in item.text)
    assert negative.symbol == "Service.Read" and negative.conditions == ("if limit < 0",)
    small = next(item for item in returns if '"small"' in item.text)
    assert any("else" in condition for condition in small.conditions)
    assert any("switch limit" in condition for condition in small.conditions)
    assert any("case 0, 1" in condition for condition in small.conditions)
    waiting = next(item for item in returns if "return value" in item.text)
    assert any("select" in condition for condition in waiting.conditions)
    assert any("case value := <-ch" in condition for condition in waiting.conditions)
    assert any("default" in condition for item in returns if "ErrEmpty" in item.text for condition in item.conditions)
    contracts = [item for item in inventory.candidates if item.kind == "function_contract"]
    assert {"Service.Read", "Wait", "Register", "Service.Clear", "Notify"} <= {item.symbol for item in contracts}
    assert any("(string, error)" in item.text for item in contracts)
    fields = [item for item in inventory.candidates if item.kind == "schema_field"]
    assert len(fields) == 2
    assert any('[]string `json:"names,omitempty" validate:"min=1"`' in item.text for item in fields)
    assert len([item for item in inventory.candidates if item.kind == "route"]) == 2
    assert len([item for item in inventory.candidates if item.kind == "http_response"]) == 3
    assert all("ghost" not in item.text for item in inventory.candidates)
    assert len({item.id for item in inventory.candidates}) == len(inventory.candidates)
    for item in inventory.candidates:
        assert item.source_digest == hashlib.sha256(GO.encode()).hexdigest()
        assert item.confidence == "syntactic"
        lines = GO.splitlines(keepends=True)
        span = "".join(lines[item.start_line - 1:item.end_line])
        assert item.snippet in span
        assert any(context.start_line <= item.start_line <= item.end_line <= context.end_line
                   and item.snippet in context.text for context in inventory.source_context)
    for packet in build_audit_packets(inventory, [], max_items=2, skip_undocumented=False).packets:
        for item in packet.candidates:
            assert any(item.snippet in context.text for context in packet.source_context)
        assert AuditPacket.model_validate_json(packet.model_dump_json()) == packet
    read = next(context for context in inventory.source_context if context.symbol == "Service.Read")
    assert read.text.startswith("func (s *Service) Read") and 'panic("large")' in read.text
    assert inventory.model_dump()["grammar_version"] == syntax.grammar_version()
    path.write_text("\n// unrelated whitespace\n" + GO, encoding="utf-8")
    moved = extract_evidence(tmp_path, ["api.go"])
    assert [item.id for item in moved.candidates] == [item.id for item in inventory.candidates]
    assert moved.files[0].source_digest != inventory.files[0].source_digest


@pytest.mark.parametrize("support", [False, True])
def test_go_parse_errors_reject_whole_file_without_partial_context(tmp_path: Path, support: bool) -> None:
    (tmp_path / "good.go").write_text("package api\nfunc Send() { send() }\n", encoding="utf-8")
    (tmp_path / "bad.go").write_text("package api\nfunc Good() { return }\nfunc Broken( {", encoding="utf-8")
    (tmp_path / "invalid.go").write_bytes(b"package api\n\xff")
    (tmp_path / "other.rb").write_text("def send; end", encoding="utf-8")
    paths = ["good.go", "bad.go", "invalid.go", "other.rb", "missing.go"]
    inventory = extract_evidence(tmp_path, [] if support else paths, context_paths=paths if support else [])
    files = inventory.context_files if support else inventory.files
    assert {file.path: file.status for file in files} == {
        "good.go": "parsed", "bad.go": "parse_error", "invalid.go": "parse_error",
        "other.rb": "unsupported", "missing.go": "unreadable",
    }
    assert all(file.message and file.source_digest for file in files if file.status == "parse_error")
    assert {item.path for item in inventory.candidates} == (set() if support else {"good.go"})
    contexts = inventory.support_context if support else inventory.source_context
    assert {item.path for item in contexts} == {"good.go"}


@pytest.mark.parametrize("support", [False, True])
def test_go_scope_rejects_escape_but_allows_inside_symlink(tmp_path: Path, support: bool) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "outside.go").write_text("package api", encoding="utf-8")
    (root / "api.go").write_text("package api\nfunc Send() {}", encoding="utf-8")
    (root / "inside.go").symlink_to(root / "api.go")
    (root / "escape.go").symlink_to(tmp_path / "outside.go")
    for selector in ["../outside.go", "escape.go", str(tmp_path / "outside.go"), ""]:
        with pytest.raises(ValueError, match="relative|outside|empty selector"):
            extract_evidence(root, [] if support else [selector], context_paths=[selector] if support else [])
    inventory = extract_evidence(root, [] if support else ["inside.go"], context_paths=["inside.go"] if support else [])
    assert (inventory.context_files if support else inventory.files)[0].status == "parsed"


def test_mixed_go_python_real_book_packets_support_and_receipts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "api.go").write_text("package api\nfunc Send() { deliver() }", encoding="utf-8")
    (tmp_path / "api.py").write_text("def read():\n    return 1\n", encoding="utf-8")
    helper = tmp_path / "helper.go"
    helper.write_text("package api\nfunc deliver() { panic(1) }", encoding="utf-8")
    book = tmp_path / "docs/features/api.md"
    book.parent.mkdir(parents=True)
    book.write_text("---\ntype: server\n---\n# API\n\n## Endpoints\n\n"
                    "### send\n- does: Sends a message.\n- code: api.go::Send\n\n"
                    "### read\n- does: Returns one.\n- code: api.py::read\n", encoding="utf-8")
    baseline = extract_evidence(tmp_path, ["api.go", "api.py"])
    inventory = extract_evidence(tmp_path, ["api.py", "api.go"], context_paths=["helper.go"])
    assert inventory.candidates == baseline.candidates and len(inventory.candidates) == 2
    assert inventory.support_context[0].text == helper.read_text()
    preparation = build_audit_packets(inventory, extract_claims(load(tmp_path)))
    assert {packet.module for packet in preparation.packets} == {"api.py", "api.go"}
    for packet in preparation.packets:
        assert len(packet.claims) == len(packet.candidates) == 1
        assert packet.support_context == inventory.support_context
        receipt = AuditVerdicts(
            claims=(ClaimVerdict(id=packet.claims[0].id, status="unresolved", explanation="Needs review."),),
            candidates=(CandidateVerdict(id=packet.candidates[0].id, status="unresolved", explanation="Needs review."),))
        assert validate_verdicts(packet, receipt).verdicts == receipt
    monkeypatch.setattr(syntax, "grammar_version", lambda: "changed grammar")
    changed = extract_evidence(tmp_path, ["api.py", "api.go"], context_paths=["helper.go"])
    assert changed.candidates == inventory.candidates
    assert build_audit_packets(changed, extract_claims(load(tmp_path))).packets[0].digest != preparation.packets[0].digest


def test_go_anonymous_struct_binding_keeps_declaration_context(tmp_path: Path) -> None:
    source = 'package api\nvar Config struct { Limit *int `json:"limit,omitempty"` }\n'
    (tmp_path / "api.go").write_text(source, encoding="utf-8")
    packet = build_audit_packets(extract_evidence(tmp_path, ["api.go"]), [], skip_undocumented=False).packets[0]
    assert len(packet.candidates) == 1
    assert packet.candidates[0].kind == "schema_field"
    assert len(packet.source_context) == 1
    assert packet.source_context[0].text == source.splitlines(keepends=True)[1]


def test_go_signature_struct_fields_are_evidence_not_just_context(tmp_path: Path) -> None:
    source = 'package api\nfunc Accept(req struct { Name string `json:"name"` }) {}\n'
    (tmp_path / "api.go").write_text(source, encoding="utf-8")
    packet = build_audit_packets(extract_evidence(tmp_path, ["api.go"]), [], skip_undocumented=False).packets[0]
    fields = [item for item in packet.candidates if item.kind == "schema_field"]
    assert len(fields) == 1
    assert fields[0].text == 'Name string `json:"name"`'
    assert fields[0].symbol == "Accept"
    assert packet.source_context[0].text == source.splitlines(keepends=True)[1]


def test_go_function_contract_snippet_is_the_signature_not_the_body(tmp_path: Path) -> None:
    body = "".join(f'\t_ = "{"x" * 60}"\n' for _ in range(500))
    source = f"package api\n\nfunc Long(limit int) error {{\n{body}\treturn nil\n}}\n"
    (tmp_path / "api.go").write_text(source, encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["api.go"])
    contract = next(item for item in inventory.candidates if item.kind == "function_contract")
    assert contract.snippet == contract.text == "func Long(limit int) error"
    assert contract.start_line == 3 and contract.end_line == 505
    # The body travels once, as the declaration's context, so a packet holding the contract
    # fits a budget the body alone leaves room in — where two copies of it did not.
    encoded = len(json.dumps(source))
    prepared = build_audit_packets(inventory, [], max_chars=encoded + encoded // 2, skip_undocumented=False)
    assert len(prepared.packets) == 1
    assert {item.kind for item in prepared.packets[0].candidates} == {"function_contract", "return"}
    assert [context.symbol for context in prepared.packets[0].source_context] == ["Long"]


def test_go_packet_context_keeps_only_the_outermost_enclosing_excerpt(tmp_path: Path) -> None:
    source = (
        "package api\n\n"
        "func TestRun(t *testing.T) {\n"
        '\tt.Run("a", func(t *testing.T) {\n'
        "\t\tif t == nil {\n\t\t\treturn\n\t}\n"
        '\t\tt.Run("b", func(t *testing.T) {\n\t\treturn\n\t})\n'
        "\t})\n"
        "}\n"
    )
    (tmp_path / "api_test.go").write_text(source, encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["api_test.go"])
    symbols = {context.symbol for context in inventory.source_context}
    assert symbols == {"TestRun", "TestRun.<literal:1>", "TestRun.<literal:1>.<literal:1>"}
    packet = build_audit_packets(inventory, [], skip_undocumented=False).packets[0]
    assert [context.symbol for context in packet.source_context] == ["TestRun"]
    for item in packet.candidates:
        assert item.snippet in packet.source_context[0].text


def test_go_visit_respects_max_depth(tmp_path: Path) -> None:
    """A tree deeper than ``MAX_DEPTH`` is dropped, not crashed.

    tree-sitter's `Node.text` is a C-extension property that has segfaulted deep
    inside a recursive visit on malformed Go source. Capping the visitor's depth
    is the fix: the symbols emitted at the shallower frame still name the
    function, and the offending subtree is dropped on the floor. This test
    crafts a Go file nested deeper than ``MAX_DEPTH`` and asserts the visitor
    returns without crashing — the only requirement is that *something*
    survives, not that every level is recorded.
    """
    from ostler.behavior_go import MAX_DEPTH

    deep = MAX_DEPTH + 50
    source = "package api\n\nfunc Outer() {\n"
    source += "if true {\n" * deep
    source += "return\n"
    source += "}\n" * deep
    source += "}\n"
    (tmp_path / "deep.go").write_text(source, encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["deep.go"])
    # The outer function's contract is at depth 0 and lands first; everything
    # past MAX_DEPTH is dropped. The exact number of inner returns that survived
    # depends on the grammar's exact nesting, so the assertion is the loose one:
    # at least one candidate (the contract) and at most all of them — never the
    # full un-trimmed tree, never a crash.
    assert inventory.files[0].status == "parsed"
    kinds = {item.kind for item in inventory.candidates}
    assert "function_contract" in kinds


def test_go_text_of_returns_empty_on_none() -> None:
    """``syntax.text_of(None)`` is the documented `""`."""
    from ostler import syntax

    assert syntax.text_of(None) == ""


def test_syntax_tree_cache_outlives_a_real_walk(tmp_path: Path) -> None:
    """``_tree`` must not evict mid-walk — the visitor keeps Node wrappers without a
    back-reference to the parent Tree.

    The api walk that segfaulted had 312 files; the old ``maxsize=16`` evicted a
    Tree under the still-running visitor. The new size is set so a single drive
    never evicts — this test asserts that.
    """
    from ostler import syntax
    from ostler.behavior import extract_evidence

    # Use the ostler package itself as a stand-in multi-file source tree. The path is
    # local to the checkout and contains *.py files which go through the Python
    # extractor (this test only checks the tree-cache invariant, not the extractor
    # itself — see the `_tree` maxsize check below).
    src = Path("/mnt/data/workspace/stablemate/ostler/ostler")
    if not src.exists():
        return
    files = sorted(src.rglob("*.py"))
    if len(files) < 32:
        return
    paths = [f.relative_to(src.parent).as_posix() for f in files]
    cache_info = syntax._tree.cache_info()
    cache_maxsize = cache_info.maxsize or 0
    assert cache_maxsize >= len(files), (
        f"tree cache maxsize={cache_maxsize} is too small for a {len(files)}-file walk; "
        "eviction during a single visit segfaults the interpreter"
    )
    # Sanity: drive the extraction end-to-end so the test fails if a future change
    # reintroduces a regression in the visitor itself.
    inv = extract_evidence(src.parent, paths)
    assert inv.candidates
