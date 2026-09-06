"""The PHP table under the generic tree-sitter visitor, read the way the TypeScript test reads TS."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ostler import syntax
from ostler.behavior import (
    AuditPacket, build_audit_packets, candidate_tier, extract_book, extract_evidence, undocumented_file,
)
from ostler.model import load


PHP = '''<?php
namespace App\\Service;

use InvalidArgumentException;

class Queue
{
    public const LIMIT = 2;
    public int $limit = 2;
    private array $hidden = [];
    protected string $_name = "q";

    public function __construct(private int $size = 1)
    {
    }

    public function push(string $item): bool
    {
        switch ($item) {
            case "":
                return false;
            default:
                return true;
        }
    }

    private function drain(): int
    {
        foreach ([1] as $entry) {
            return $entry;
        }
        return 0;
    }

    public static function make(): static
    {
        return new static();
    }
}

interface Batch
{
    public function size(): int;
}

enum Status: string
{
    case Ok = "ok";
}

function dispatch(array $items, array &$sent, int $limit = 2): array
{
    if ($limit < 0) {
        throw new InvalidArgumentException("limit must be nonnegative");
    } elseif (count($items) === 0) {
        return ["status" => "empty", "count" => 0];
    } else {
        $selected = array_slice($items, 0, $limit);
    }
    array_push($sent, ...$selected);
    return ["status" => "sent", "count" => count($selected)];
}

function _hidden(): int
{
    return 0;
}

$shown = function (int $a = 1) {
    try {
        return $a;
    } catch (\\Throwable $e) {
        throw $e;
    }
};

$app->get("/dispatch", function ($request, $response) {
    return $response->withStatus(200)->write("ok");
});

$pick = fn($x) => $x ? 1 : 2;
// return "ghost"; throw new Exception("ghost"); $app->get("/ghost", $ghost)
$fake = "return \\"ghost\\"; \\$response->withStatus(500)";
'''


def test_php_candidates_keep_control_flow_signatures_fields_and_visibility(tmp_path: Path) -> None:
    path = tmp_path / "service.php"
    path.write_text(PHP, encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["service.php"])
    assert inventory.files[0].status == "parsed"
    kinds = ("return", "raise", "route", "http_response", "schema_field", "function_contract", "function_default")
    assert {item.kind for item in inventory.candidates} == set(kinds)
    by_kind = {kind: [item for item in inventory.candidates if item.kind == kind] for kind in kinds}
    negative = next(item for item in by_kind["raise"] if "nonnegative" in item.text)
    assert negative.symbol == "dispatch" and negative.conditions == ("if ($limit < 0)",)
    empty = next(item for item in by_kind["return"] if '"empty"' in item.text)
    assert empty.conditions == ("else of ($limit < 0)", "if (count($items) === 0)")
    small = next(item for item in by_kind["return"] if "return false" in item.text)
    assert small.symbol == "Queue.push" and small.conditions == ("within switch ($item)", 'within case ""')
    drained = next(item for item in by_kind["return"] if "return $entry" in item.text)
    assert drained.symbol == "Queue.drain" and drained.conditions == ("within foreach ([1] as $entry)",)
    caught = next(item for item in by_kind["raise"] if item.text == "throw $e")
    assert caught.symbol == "shown" and caught.conditions == ("within try", "within catch (\\Throwable $e)")
    contracts = {item.symbol: item for item in by_kind["function_contract"]}
    assert set(contracts) == {
        "Queue.__construct", "Queue.push", "Queue.drain", "Queue.make", "Batch.size",
        "dispatch", "_hidden", "shown", "<literal:1>", "pick",
    }
    assert contracts["dispatch"].text.startswith("function dispatch(array $items, array &$sent, int $limit = 2)")
    assert contracts["Queue.push"].text == "public function push(string $item): bool"
    assert contracts["shown"].text == "function (int $a = 1)"
    assert {item.text for item in by_kind["function_default"]} == {"int $limit = 2", "int $a = 1", "private int $size = 1"}
    # Properties, class constants and enum cases count; an interface's method is a contract, not a field.
    assert {item.symbol for item in by_kind["schema_field"]} == {
        "Queue.LIMIT", "Queue.limit", "Queue.hidden", "Queue._name", "Status.Ok",
    }
    assert len(by_kind["route"]) == 1 and by_kind["route"][0].symbol == "<module>"
    assert [item.text for item in by_kind["http_response"]] == [
        '$response->withStatus(200)->write("ok")', "$response->withStatus(200)",
    ]
    assert all(item.symbol == "<literal:1>" for item in by_kind["http_response"])
    assert all("ghost" not in item.text for item in inventory.candidates)
    # Visibility is the modifier for a member and unconditional for a top-level declaration.
    exported = {item.symbol: item.exported for item in inventory.candidates}
    assert exported["dispatch"] and exported["Queue.push"] and exported["Queue.limit"] and exported["Queue.LIMIT"]
    assert exported["Queue.make"] and exported["Batch.size"] and exported["shown"] and exported["pick"]
    assert exported["<literal:1>"], "a route handler is what the book describes"
    assert not exported["Queue.drain"] and not exported["Queue.hidden"] and not exported["Queue._name"]
    assert exported["_hidden"], "PHP has no module privacy: a top-level function is callable from anywhere"
    assert exported["<module>"] is None
    assert candidate_tier("service.php", "Queue.drain", frozenset(), False) == 2
    assert candidate_tier("service.php", "Queue.drain", frozenset({"service.php::Queue.drain"}), False) == 1
    finding = undocumented_file("service.php", inventory.candidates)
    assert finding is not None and set(finding.exported_symbols) == {
        "Queue.LIMIT", "Queue.limit", "Queue.__construct", "Queue.push", "Queue.make", "Batch.size", "Status.Ok",
        "dispatch", "_hidden", "shown", "<literal:1>", "pick",
    }
    assert len({item.id for item in inventory.candidates}) == len(inventory.candidates)
    for item in inventory.candidates:
        assert item.source_digest == hashlib.sha256(PHP.encode()).hexdigest()
        assert item.confidence == "syntactic" and item.framework
        span = "".join(PHP.splitlines(keepends=True)[item.start_line - 1:item.end_line])
        assert item.snippet in span
        assert any(context.start_line <= item.start_line <= item.end_line <= context.end_line
                   and item.snippet in context.text for context in inventory.source_context)
    for packet in build_audit_packets(inventory, [], max_items=2, skip_undocumented=False).packets:
        for item in packet.candidates:
            assert any(item.snippet in context.text for context in packet.source_context)
        assert AuditPacket.model_validate_json(packet.model_dump_json()) == packet
    queue = next(context for context in inventory.source_context if context.symbol == "Queue")
    assert queue.text.startswith("class Queue")
    assert inventory.model_dump()["grammar_version"] == syntax.grammar_version()
    moved_text = PHP.replace("<?php\n", "<?php\n// unrelated comment\n\n", 1)
    path.write_text(moved_text, encoding="utf-8")
    moved = extract_evidence(tmp_path, ["service.php"])
    assert [item.id for item in moved.candidates] == [item.id for item in inventory.candidates]
    assert moved.files[0].source_digest != inventory.files[0].source_digest


def test_twig_is_unsupported_by_design(tmp_path: Path) -> None:
    (tmp_path / "page.twig").write_text("{% if items %}<ul>{% for i in items %}<li>{{ i }}</li>{% endfor %}</ul>"
                                        "{% else %}<p>empty</p>{% endif %}\n", encoding="utf-8")
    inventory = extract_evidence(tmp_path, ["page.twig"])
    assert [(file.path, file.status) for file in inventory.files] == [("page.twig", "unsupported")]
    assert inventory.candidates == () and inventory.source_context == ()
    assert syntax.language_for("page.twig") == "twig", "the grammar exists; the flat tree is why it has no table"


@pytest.mark.parametrize("support", [False, True])
def test_php_parse_errors_reject_whole_file_without_partial_context(tmp_path: Path, support: bool) -> None:
    (tmp_path / "good.php").write_text("<?php\nfunction send() { return deliver(); }\n", encoding="utf-8")
    (tmp_path / "bad.php").write_text("<?php\nfunction good() { return 1; }\nfunction broken( {", encoding="utf-8")
    (tmp_path / "invalid.php").write_bytes(b"<?php\n$x = 1;\n\xff")
    paths = ["good.php", "bad.php", "invalid.php", "missing.php"]
    inventory = extract_evidence(tmp_path, [] if support else paths, context_paths=paths if support else [])
    files = inventory.context_files if support else inventory.files
    assert {file.path: file.status for file in files} == {
        "good.php": "parsed", "bad.php": "parse_error", "invalid.php": "parse_error", "missing.php": "unreadable",
    }
    assert {item.path for item in inventory.candidates} == (set() if support else {"good.php"})
    contexts = inventory.support_context if support else inventory.source_context
    assert {item.path for item in contexts} == {"good.php"}


def test_php_book_claims_bind_to_php_symbols(tmp_path: Path) -> None:
    (tmp_path / "service.php").write_text(PHP, encoding="utf-8")
    book = tmp_path / "docs/features/dispatch.md"
    book.parent.mkdir(parents=True)
    book.write_text("---\ntype: concept\n---\n# Dispatch\n\n## Methods\n\n"
                    "### dispatch\n- does: Appends the selected items to sent.\n- code: service.php::dispatch\n\n"
                    "### drain\n- does: Returns the first entry.\n- code: service.php::Queue.drain\n", encoding="utf-8")
    preparation = build_audit_packets(extract_evidence(tmp_path, ["service.php"]), extract_book(load(tmp_path)))
    assert [packet.module for packet in preparation.packets] == ["service.php"]
    packet = preparation.packets[0]
    assert len(packet.claims) == 2
    symbols = {item.symbol for item in packet.candidates}
    assert {"dispatch", "Queue.drain", "Queue.push"} <= symbols, "cited private symbols are tier 1 too"
    assert "Queue.hidden" not in symbols and "Queue._name" not in symbols
    assert preparation.deferred_candidates == 2, "Queue.hidden, Queue._name"
