"""The TypeScript table under the generic tree-sitter visitor, read the way the Go test reads Go."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ostler import syntax
from ostler.behavior import (
    AuditPacket, build_audit_packets, candidate_tier, extract_book, extract_evidence, undocumented_file,
)
from ostler.model import load


TS = '''import express from "express";

export function dispatch(items: string[], sent: string[], limit = 2): { status: string; count: number } {
  if (limit < 0) {
    throw new Error("limit must be nonnegative");
  } else if (items.length === 0) {
    return { status: "empty", count: 0 };
  }
  const selected = items.slice(0, limit);
  sent.push(...selected);
  return { status: "sent", count: selected.length };
}

export class Queue {
  limit: number = 2;
  private hidden = 1;
  #secret = 0;
  push(item: string): boolean {
    switch (item) {
      case "":
        return false;
      default:
        return true;
    }
  }
  private drain() {
    for (const entry of [1]) {
      return entry;
    }
  }
}

export interface Batch { size: number; nested: { deep: number } }
export type Status = { ok: boolean };
type Local = Array<{ inline: number }>;

const app = express();
app.get("/dispatch", (req, res) => {
  res.status(200).json({ ok: true });
});

function notExported(x?: number) { return x ? 1 : 2; }
const _hidden = () => { return 0; };
export const shown = (a = 1) => { try { return a; } catch (e) { throw e; } };
function other() { return 9; }
export { other as aliased };
// return "ghost"; throw new Error("ghost"); app.get("/ghost", ghost)
const fake = `return "ghost"; res.status(500)`;
'''


def test_ts_candidates_keep_control_flow_signatures_fields_and_exports(tmp_path: Path) -> None:
    path = tmp_path / "service.ts"
    path.write_text(TS, encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["service.ts"])
    assert inventory.files[0].status == "parsed"
    assert {item.kind for item in inventory.candidates} == {
        "return", "raise", "route", "http_response", "schema_field", "function_contract", "function_default",
    }
    by_kind = {kind: [item for item in inventory.candidates if item.kind == kind] for kind in
               ("return", "raise", "route", "http_response", "schema_field", "function_contract", "function_default")}
    negative = by_kind["raise"][0]
    assert negative.symbol == "dispatch" and negative.conditions == ("if (limit < 0)",)
    empty = next(item for item in by_kind["return"] if '"empty"' in item.text)
    assert empty.conditions[0] == "else of (limit < 0)" and "if (items.length === 0)" in empty.conditions[1]
    small = next(item for item in by_kind["return"] if "return false" in item.text)
    assert small.symbol == "Queue.push" and small.conditions == ("within switch (item)", 'within case ""')
    drained = next(item for item in by_kind["return"] if "return entry" in item.text)
    assert drained.conditions == ("within for (const entry of [1])",)
    caught = next(item for item in by_kind["raise"] if item.text == "throw e;")
    assert caught.symbol == "shown" and caught.conditions == ("within try", "within catch (e)")
    contracts = {item.symbol: item for item in by_kind["function_contract"]}
    assert set(contracts) == {"dispatch", "Queue.push", "Queue.drain", "<literal:1>", "notExported", "_hidden", "shown", "other"}
    assert contracts["dispatch"].text.startswith("function dispatch(items: string[], sent: string[], limit = 2)")
    assert contracts["Queue.push"].text == "push(item: string): boolean"
    assert contracts["shown"].text == "(a = 1) =>"
    assert {item.text for item in by_kind["function_default"]} == {"limit = 2", "a = 1"}
    # Fields count in a class body, an interface body or a type alias — not in an inline type.
    assert {item.symbol for item in by_kind["schema_field"]} == {
        "Queue.limit", "Queue.hidden", "Queue.#secret", "Batch.size", "Batch.nested", "Status.ok",
    }
    assert len(by_kind["route"]) == 1 and by_kind["route"][0].symbol == "<module>"
    assert [item.text for item in by_kind["http_response"]] == ["res.status(200).json({ ok: true })", "res.status(200)"]
    assert all(item.symbol == "<literal:1>" for item in by_kind["http_response"])
    assert all("ghost" not in item.text for item in inventory.candidates)
    # Exportedness is the keyword, the re-export clause and member accessibility — never the spelling.
    exported = {item.symbol: item.exported for item in inventory.candidates}
    assert exported["dispatch"] and exported["Queue.push"] and exported["Queue.limit"] and exported["shown"]
    assert exported["other"] and exported["Batch.size"] and exported["Status.ok"]
    assert exported["<literal:1>"], "a route handler is what the book describes"
    assert not exported["Queue.drain"] and not exported["Queue.hidden"] and not exported["Queue.#secret"]
    assert not exported["notExported"] and not exported["_hidden"]
    assert exported["<module>"] is None
    assert candidate_tier("service.ts", "notExported", frozenset(), False) == 2
    assert candidate_tier("service.ts", "notExported", frozenset({"service.ts::notExported"}), False) == 1
    finding = undocumented_file("service.ts", inventory.candidates)
    assert finding is not None and set(finding.exported_symbols) == {
        "dispatch", "Queue.limit", "Queue.push", "Batch.size", "Batch.nested", "Status.ok", "<literal:1>", "shown", "other",
    }
    assert len({item.id for item in inventory.candidates}) == len(inventory.candidates)
    for item in inventory.candidates:
        assert item.source_digest == hashlib.sha256(TS.encode()).hexdigest()
        assert item.confidence == "syntactic" and item.framework
        span = "".join(TS.splitlines(keepends=True)[item.start_line - 1:item.end_line])
        assert item.snippet in span
        assert any(context.start_line <= item.start_line <= item.end_line <= context.end_line
                   and item.snippet in context.text for context in inventory.source_context)
    for packet in build_audit_packets(inventory, [], max_items=2, skip_undocumented=False).packets:
        for item in packet.candidates:
            assert any(item.snippet in context.text for context in packet.source_context)
        assert AuditPacket.model_validate_json(packet.model_dump_json()) == packet
    queue = next(context for context in inventory.source_context if context.symbol == "Queue")
    assert queue.text.startswith("export class Queue") or queue.text.startswith("class Queue")
    assert inventory.model_dump()["grammar_version"] == syntax.grammar_version()
    path.write_text("\n// unrelated whitespace\n" + TS, encoding="utf-8")
    moved = extract_evidence(tmp_path, ["service.ts"])
    assert [item.id for item in moved.candidates] == [item.id for item in inventory.candidates]
    assert moved.files[0].source_digest != inventory.files[0].source_digest


def test_tsx_and_javascript_share_the_typescript_table(tmp_path: Path) -> None:
    (tmp_path / "view.tsx").write_text(
        'export function View({ items }: { items: string[] }) {\n'
        '  if (items.length === 0) { return <p>empty</p>; }\n  return <ul>{items.map(i => <li key={i}>{i}</li>)}</ul>;\n}\n',
        encoding="utf-8")
    (tmp_path / "legacy.js").write_text("module.exports.run = function run(n) { if (n) { return 1; } return 0; };\n",
                                        encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["view.tsx", "legacy.js"])
    assert {file.path: file.status for file in inventory.files} == {"view.tsx": "parsed", "legacy.js": "parsed"}
    view = [item for item in inventory.candidates if item.path == "view.tsx"]
    assert [item.kind for item in view] == ["function_contract", "return", "return", "function_contract"]
    assert view[1].conditions == ("if (items.length === 0)",) and view[1].exported
    assert view[3].symbol == "View.<literal:1>" and view[3].exported, "an arrow inside an exported function"
    legacy = [item for item in inventory.candidates if item.path == "legacy.js"]
    assert [item.symbol for item in legacy] == ["run", "run", "run"]
    assert legacy[0].exported is False, "a CommonJS export is not resolved; the book's citation makes it tier 1"


@pytest.mark.parametrize("support", [False, True])
def test_ts_parse_errors_reject_whole_file_without_partial_context(tmp_path: Path, support: bool) -> None:
    (tmp_path / "good.ts").write_text("export function send() { return deliver(); }\n", encoding="utf-8")
    (tmp_path / "bad.ts").write_text("export function good() { return 1; }\nfunction broken( {", encoding="utf-8")
    (tmp_path / "invalid.ts").write_bytes(b"export const x = 1;\n\xff")
    (tmp_path / "style.css").write_text("a { color: red }", encoding="utf-8")
    paths = ["good.ts", "bad.ts", "invalid.ts", "style.css", "missing.ts"]
    inventory = extract_evidence(tmp_path, [] if support else paths, context_paths=paths if support else [])
    files = inventory.context_files if support else inventory.files
    assert {file.path: file.status for file in files} == {
        "good.ts": "parsed", "bad.ts": "parse_error", "invalid.ts": "parse_error",
        "style.css": "unsupported", "missing.ts": "unreadable",
    }
    assert {item.path for item in inventory.candidates} == (set() if support else {"good.ts"})
    contexts = inventory.support_context if support else inventory.source_context
    assert {item.path for item in contexts} == {"good.ts"}


def test_ts_book_claims_bind_to_typescript_symbols(tmp_path: Path) -> None:
    (tmp_path / "service.ts").write_text(TS, encoding="utf-8")
    book = tmp_path / "docs/features/dispatch.md"
    book.parent.mkdir(parents=True)
    book.write_text("---\ntype: concept\n---\n# Dispatch\n\n## Methods\n\n"
                    "### dispatch\n- does: Appends the selected items to sent.\n- code: service.ts::dispatch\n\n"
                    "### hidden\n- does: Returns zero.\n- code: service.ts::notExported\n", encoding="utf-8")
    preparation = build_audit_packets(extract_evidence(tmp_path, ["service.ts"]), extract_book(load(tmp_path)))
    assert [packet.module for packet in preparation.packets] == ["service.ts"]
    packet = preparation.packets[0]
    assert len(packet.claims) == 2
    symbols = {item.symbol for item in packet.candidates}
    assert {"dispatch", "notExported", "Queue.push"} <= symbols, "cited private symbols are tier 1 too"
    assert "_hidden" not in symbols and "Queue.drain" not in symbols
    assert preparation.deferred_candidates == 6, "Queue.drain ×2, Queue.hidden, Queue.#secret, _hidden ×2"
