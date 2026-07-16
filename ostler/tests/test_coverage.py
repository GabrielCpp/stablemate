"""`ostler coverage` — the join that makes a book's completeness a computed fact.

The builder's stop condition used to be a value the recheck agent emitted about its own work.
These tests pin the instrument that replaces it, and in particular the transitive module rule,
whose non-vacuous clause is the easiest thing here to get subtly, flatteringly wrong.
"""

from __future__ import annotations

import json
from pathlib import Path

from ostler import coverage
from ostler.cli import main
from ostler.model import load

from conftest import write


def _inventory(tmp_path: Path, units: list[dict], **kw) -> Path:
    """A source inventory in `inventory-source.py`'s shape."""
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({
        "version": 1, "sourceRoot": kw.get("sourceRoot", "api"), "repoRoot": str(tmp_path),
        "excludes": kw.get("excludes", []), "units": units, "operational": [],
        "errors": kw.get("errors", []),
    }))
    return path


def _module(path: str) -> dict:
    return {"kind": "module", "path": path, "symbol": "", "code": path}


def _symbol(path: str, symbol: str) -> dict:
    return {"kind": "symbol", "path": path, "symbol": symbol, "code": f"{path}::{symbol}"}


def _book(repo: Path, *code_refs: str):
    """A one-node book citing each of *code_refs*."""
    bullets = "\n".join(f"- code: `{ref}`" for ref in code_refs)
    write(repo / "docs/features/api/concepts/thing.md",
          f"---\ntype: concept\nslug: thing\ntitle: Thing\n---\n# Thing\n\n{bullets}\n\nA thing.\n")
    return load(repo)


# -- the grammar (§4.1) -------------------------------------------------------------------

def test_a_receiver_qualified_citation_matches_the_inventory(tmp_path: Path) -> None:
    # The measured defect: books cite `(*FirebaseClaimsWriter).SetRoleClaims` and the inventory
    # emitted a bare `SetRoleClaims`, so 1136 citations could never match 877 symbols. This is
    # the join that read 35% on a book that was really at 83%.
    ref = "api/internal/claims.go::(*FirebaseClaimsWriter).SetRoleClaims"
    inv = _inventory(tmp_path, [_symbol("api/internal/claims.go",
                                        "(*FirebaseClaimsWriter).SetRoleClaims")])
    result = coverage.run(_book(tmp_path, ref), surface="api", inventory=inv)
    assert result["covered"] == 1
    assert result["missing"] == []


def test_a_citation_is_read_through_its_backticks(tmp_path: Path) -> None:
    inv = _inventory(tmp_path, [_symbol("api/x.go", "Write")])
    result = coverage.run(_book(tmp_path, "api/x.go::Write"), surface="api", inventory=inv)
    assert result["covered"] == 1


def test_a_node_citing_several_code_bullets_covers_each(tmp_path: Path) -> None:
    # A repeated bullet key parses to a list, not a string — a node may anchor several symbols.
    inv = _inventory(tmp_path, [_symbol("api/x.go", "Write"), _symbol("api/x.go", "Read")])
    result = coverage.run(_book(tmp_path, "api/x.go::Write", "api/x.go::Read"),
                          surface="api", inventory=inv)
    assert result["covered"] == 2
    assert result["missing"] == []


def test_an_uncited_symbol_is_missing(tmp_path: Path) -> None:
    inv = _inventory(tmp_path, [_symbol("api/x.go", "Write"), _symbol("api/x.go", "Read")])
    result = coverage.run(_book(tmp_path, "api/x.go::Write"), surface="api", inventory=inv)
    assert result["covered"] == 1
    assert [m["code"] for m in result["missing"]] == ["api/x.go::Read"]


# -- the transitive module rule (§4.3) ----------------------------------------------------

def test_a_fully_symbol_covered_module_is_discharged(tmp_path: Path) -> None:
    # A Go file whose every declared symbol is cited adds nothing the book has not said. On the
    # measured corpus this rule discharged 238 of 282 uncited modules.
    inv = _inventory(tmp_path, [
        _module("api/x.go"), _symbol("api/x.go", "Write"), _symbol("api/x.go", "Read"),
    ])
    result = coverage.run(_book(tmp_path, "api/x.go::Write", "api/x.go::Read"),
                          surface="api", inventory=inv)
    assert result["covered"] == 3
    assert result["missing"] == []
    assert coverage.is_complete(result)


def test_a_partially_symbol_covered_module_is_not_discharged(tmp_path: Path) -> None:
    inv = _inventory(tmp_path, [
        _module("api/x.go"), _symbol("api/x.go", "Write"), _symbol("api/x.go", "Read"),
    ])
    result = coverage.run(_book(tmp_path, "api/x.go::Write"), surface="api", inventory=inv)
    assert {m["code"] for m in result["missing"]} == {"api/x.go", "api/x.go::Read"}


def test_a_module_declaring_nothing_needs_a_direct_citation(tmp_path: Path) -> None:
    # THE load-bearing case. Without the `declares at least one symbol` clause the rule is
    # vacuously true for a file that declares nothing — and would discharge exactly the case
    # the module unit exists for: a Twig template with no `{% block %}` renders a screen and
    # must be cited directly. A vacuous rule marks it covered on the strength of having found
    # nothing in it: silence read as evidence.
    inv = _inventory(tmp_path, [_module("legacy/templates/Home.html.twig")])
    result = coverage.run(_book(tmp_path), surface="api", inventory=inv)
    assert result["covered"] == 0
    assert [m["code"] for m in result["missing"]] == ["legacy/templates/Home.html.twig"]
    assert not coverage.is_complete(result)


def test_a_template_cited_directly_is_covered(tmp_path: Path) -> None:
    inv = _inventory(tmp_path, [_module("legacy/templates/Home.html.twig")])
    result = coverage.run(_book(tmp_path, "legacy/templates/Home.html.twig"),
                          surface="api", inventory=inv)
    assert result["covered"] == 1
    assert coverage.is_complete(result)


def test_a_template_with_blocks_is_discharged_by_its_blocks(tmp_path: Path) -> None:
    # A template that DOES declare blocks is an ordinary transitive case — the rule only
    # refuses to fire on a file that declares nothing.
    twig = "legacy/templates/Home.html.twig"
    inv = _inventory(tmp_path, [_module(twig), _symbol(twig, "title"), _symbol(twig, "content")])
    result = coverage.run(_book(tmp_path, f"{twig}::title", f"{twig}::content"),
                          surface="api", inventory=inv)
    assert result["covered"] == 3


def test_the_module_rule_does_not_leak_across_files(tmp_path: Path) -> None:
    inv = _inventory(tmp_path, [
        _module("api/x.go"), _symbol("api/x.go", "Write"),
        _module("api/y.go"), _symbol("api/y.go", "Read"),
    ])
    result = coverage.run(_book(tmp_path, "api/x.go::Write"), surface="api", inventory=inv)
    # x.go is discharged by its own symbol; y.go is not discharged by x.go's.
    assert {m["code"] for m in result["missing"]} == {"api/y.go", "api/y.go::Read"}


# -- waivers (§5.2) -----------------------------------------------------------------------

def test_a_waived_unit_counts_as_covered(tmp_path: Path) -> None:
    inv = _inventory(tmp_path, [_symbol("api/x.go", "parseRequest")])
    waivers = tmp_path / "waivers.json"
    waivers.write_text(json.dumps({"waivers": {
        "api/x.go::parseRequest": "folded into the documented endpoint contract"}}))
    result = coverage.run(_book(tmp_path), surface="api", inventory=inv, waivers=waivers)
    assert result["covered"] == 1
    assert result["waived"] == 1
    assert coverage.is_complete(result)


def test_an_unwaived_unit_does_not_count(tmp_path: Path) -> None:
    inv = _inventory(tmp_path, [_symbol("api/x.go", "parseRequest"),
                                _symbol("api/x.go", "other")])
    waivers = tmp_path / "waivers.json"
    waivers.write_text(json.dumps({"waivers": {"api/x.go::parseRequest": "folded in"}}))
    result = coverage.run(_book(tmp_path), surface="api", inventory=inv, waivers=waivers)
    assert result["covered"] == 1
    assert [m["code"] for m in result["missing"]] == ["api/x.go::other"]


def test_a_missing_waivers_file_is_not_an_error(tmp_path: Path) -> None:
    # Nothing waived yet is the normal state of a fresh book, not a failure.
    inv = _inventory(tmp_path, [_symbol("api/x.go", "Write")])
    result = coverage.run(_book(tmp_path, "api/x.go::Write"), surface="api",
                          inventory=inv, waivers=tmp_path / "nope.json")
    assert result["waived"] == 0
    assert coverage.is_complete(result)


# -- silence is never evidence (§3.3) -----------------------------------------------------

def test_an_empty_inventory_is_not_a_complete_book(tmp_path: Path) -> None:
    # Stage 0 found `doctor` green on a book that does not exist: referential integrity over
    # zero nodes is vacuously perfect. `covered == total` is vacuously true over zero units the
    # same way. An empty book and a finished one must not share a verdict.
    result = coverage.run(_book(tmp_path), surface="api", inventory=_inventory(tmp_path, []))
    assert result["covered"] == 0
    assert result["total"] == 0
    assert not coverage.is_complete(result)


def test_a_blind_inventory_cannot_ground_a_pass(tmp_path: Path) -> None:
    # A tree whose language the front end cannot read reports units it did not find. Coverage
    # over that is not a measurement, and it must not read as one even at 1/1.
    inv = _inventory(tmp_path, [_symbol("api/x.go", "Write")],
                     errors=["no readable source under legacy/: front end supports …"])
    result = coverage.run(_book(tmp_path, "api/x.go::Write"), surface="api", inventory=inv)
    assert result["covered"] == result["total"] == 1
    assert not coverage.is_complete(result), "an errored inventory must never report complete"
    assert result["errors"]


def test_an_unreadable_inventory_raises_rather_than_reporting_zero(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"nope": 1}')
    try:
        coverage.run(_book(tmp_path), surface="api", inventory=bad)
    except ValueError as exc:
        assert "units" in str(exc)
    else:
        raise AssertionError("an inventory with no `units` list must raise, not report 0/0")


# -- scoping ------------------------------------------------------------------------------

def test_surface_scopes_the_citations_to_one_book(tmp_path: Path) -> None:
    # Two books in one graph (the rewrite scenario): `api`'s citations must not cover `web`'s
    # units. A book is complete on its own evidence.
    write(tmp_path / "docs/features/api/concepts/a.md",
          "---\ntype: concept\nslug: a\ntitle: A\n---\n# A\n\n- code: `api/x.go::Write`\n\nA.\n")
    write(tmp_path / "docs/features/web/concepts/b.md",
          "---\ntype: concept\nslug: b\ntitle: B\n---\n# B\n\n- code: `web/y.ts::Render`\n\nB.\n")
    graph = load(tmp_path)
    inv = _inventory(tmp_path, [_symbol("api/x.go", "Write"), _symbol("web/y.ts", "Render")])

    assert {m["code"] for m in coverage.run(graph, surface="api", inventory=inv)["missing"]} == {
        "web/y.ts::Render"}
    assert {m["code"] for m in coverage.run(graph, surface="web", inventory=inv)["missing"]} == {
        "api/x.go::Write"}
    # Unscoped, both books' citations count.
    assert coverage.is_complete(coverage.run(graph, surface=None, inventory=inv))


# -- the CLI: a gate a `make` target can hold the run to (§13) -----------------------------

def test_cli_exits_nonzero_on_an_incomplete_book(tmp_path: Path, capsys) -> None:
    inv = _inventory(tmp_path, [_symbol("api/x.go", "Write"), _symbol("api/x.go", "Read")])
    _book(tmp_path, "api/x.go::Write")
    code = main(["-C", str(tmp_path), "coverage", "--surface", "api", "--inventory", str(inv)])
    assert code == 1
    out = capsys.readouterr().out
    assert "1/2 units covered (50%)" in out
    assert "api/x.go::Read" in out


def test_cli_exits_zero_on_a_complete_book(tmp_path: Path, capsys) -> None:
    inv = _inventory(tmp_path, [_symbol("api/x.go", "Write")])
    _book(tmp_path, "api/x.go::Write")
    assert main(["-C", str(tmp_path), "coverage", "--surface", "api",
                 "--inventory", str(inv)]) == 0


def test_cli_json_is_the_machines_face(tmp_path: Path, capsys) -> None:
    inv = _inventory(tmp_path, [_symbol("api/x.go", "Write"), _symbol("api/x.go", "Read")])
    _book(tmp_path, "api/x.go::Write")
    main(["-C", str(tmp_path), "coverage", "--surface", "api", "--inventory", str(inv), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["covered"] == 1
    assert data["total"] == 2
    assert [m["code"] for m in data["missing"]] == ["api/x.go::Read"]


def test_cli_reports_an_unreadable_inventory_rather_than_zero(tmp_path: Path, capsys) -> None:
    _book(tmp_path)
    code = main(["-C", str(tmp_path), "coverage", "--inventory", str(tmp_path / "absent.json")])
    assert code == 2, "a missing inventory is a distinct failure, not an incomplete book"
    assert "coverage" in capsys.readouterr().err
