"""`ostler backfill plan` — the stale set that says what a book owes its code."""

from __future__ import annotations

import json
from pathlib import Path

from ostler import backfill, coverage, doctor
from ostler.cli import main
from ostler.model import Graph, load

from conftest import write

SOURCE = """\
def alpha(value):
    return value + 1


def beta(value):
    return value * 2
"""


def _inventory(root: Path, units: list[dict]) -> Path:
    """A source inventory in the `inventory_source` node's shape."""
    path = root / "inventory.json"
    path.write_text(json.dumps({
        "version": 1, "sourceRoot": "api", "repoRoot": str(root), "excludes": [],
        "units": units, "operational": [], "errors": [],
    }), encoding="utf-8")
    return path


def _symbol(path: str, symbol: str) -> dict:
    return {"kind": "symbol", "path": path, "symbol": symbol, "code": f"{path}::{symbol}"}


def _book(root: Path, *code_refs: str) -> Graph:
    bullets = "\n".join(f"- code: `{ref}`" for ref in code_refs)
    write(root / "docs/features/api/concepts/thing.md",
          "---\ntype: concept\nslug: thing\ntitle: Thing\n---\n"
          f"# Thing\n\n{bullets}\n\nA thing.\n")
    return load(root)


def _repo(tmp_path: Path, *refs: str) -> Graph:
    """A book citing *refs*, over a two-symbol source file."""
    write(tmp_path / "api/thing.py", SOURCE)
    return _book(tmp_path, *refs)


def _plan(graph: Graph, inventory: Path, **kw) -> backfill.BackfillPlan:
    """The plan, with the impure inputs `cli` would have gathered."""
    return backfill.plan(
        graph, coverage.load_inventory(inventory),
        surface="api", findings=doctor.run(graph, check_schema=False).findings, **kw)


def _reasons(result: backfill.BackfillPlan) -> dict[str, set[str]]:
    return {reason: {row.unit for row in rows} for reason, rows in result.by_reason().items()}



def test_a_book_with_no_watermark_owes_every_symbol_it_does_not_cite(tmp_path: Path) -> None:
    graph = _repo(tmp_path)
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "alpha"),
                                _symbol("api/thing.py", "beta")])
    result = _plan(graph, inv)
    assert _reasons(result)["uncovered"] == {"api/thing.py::alpha", "api/thing.py::beta"}
    assert not result.is_clean


def test_a_book_that_matches_its_code_owes_nothing(tmp_path: Path) -> None:
    graph = _repo(tmp_path, "api/thing.py::alpha", "api/thing.py::beta")
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "alpha"),
                                _symbol("api/thing.py", "beta")])
    result = _plan(graph, inv)
    assert result.units == ()
    assert result.is_clean



def test_a_symbol_moved_to_another_file_suppresses_its_uncovered_row(tmp_path: Path) -> None:
    graph = _repo(tmp_path, "api/thing.py::alpha")
    write(tmp_path / "api/thing.py", "def beta(value):\n    return value * 2\n")
    write(tmp_path / "api/moved.py", "def alpha(value):\n    return value + 1\n")
    inv = _inventory(tmp_path, [_symbol("api/moved.py", "alpha"),
                                _symbol("api/thing.py", "beta")])
    result = _plan(graph, inv)
    reasons = _reasons(result)
    assert reasons["dangling"] == {"api/thing.py::alpha"}
    assert "api/moved.py::alpha" not in reasons["uncovered"]


def test_a_moved_symbols_dangling_row_names_where_it_went(tmp_path: Path) -> None:
    graph = _repo(tmp_path, "api/thing.py::alpha")
    write(tmp_path / "api/thing.py", "def beta(value):\n    return value * 2\n")
    write(tmp_path / "api/moved.py", "def alpha(value):\n    return value + 1\n")
    inv = _inventory(tmp_path, [_symbol("api/moved.py", "alpha"),
                                _symbol("api/thing.py", "beta")])
    result = _plan(graph, inv)
    dangling = result.by_reason()["dangling"]
    assert [row.relocated_to for row in dangling if row.unit == "api/thing.py::alpha"] == [
        "api/moved.py::alpha",
    ]


def test_a_repeated_symbol_name_is_not_suppressed(tmp_path: Path) -> None:
    graph = _repo(tmp_path, "api/thing.py::alpha")
    write(tmp_path / "api/thing.py", "def beta(value):\n    return value * 2\n")
    write(tmp_path / "api/moved.py", "def alpha(value):\n    return value + 1\n")
    write(tmp_path / "api/other.py", "def alpha(value):\n    return value + 2\n")
    inv = _inventory(tmp_path, [_symbol("api/moved.py", "alpha"),
                                _symbol("api/other.py", "alpha"),
                                _symbol("api/thing.py", "beta")])
    result = _plan(graph, inv)
    reasons = _reasons(result)
    assert reasons["dangling"] == {"api/thing.py::alpha"}
    assert reasons["uncovered"] == {
        "api/moved.py::alpha", "api/other.py::alpha", "api/thing.py::beta",
    }
    dangling = result.by_reason()["dangling"]
    assert [row.relocated_to for row in dangling] == [""]


def test_a_symbol_renamed_in_place_is_a_dead_citation_and_new_code(tmp_path: Path) -> None:
    graph = _repo(tmp_path, "api/thing.py::alpha")
    write(tmp_path / "api/thing.py", SOURCE.replace("def alpha", "def gamma"))
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "gamma"),
                                _symbol("api/thing.py", "beta")])
    result = _plan(graph, inv)
    reasons = _reasons(result)
    assert reasons["dangling"] == {"api/thing.py::alpha"}
    assert reasons["uncovered"] == {"api/thing.py::gamma", "api/thing.py::beta"}



def test_a_scope_narrows_the_plan_without_widening_it(tmp_path: Path) -> None:
    graph = _repo(tmp_path)
    write(tmp_path / "web/other.py", "def delta():\n    return 0\n")
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "alpha"),
                                _symbol("web/other.py", "delta")])
    result = _plan(graph, inv, scope=("api",))
    assert _reasons(result)["uncovered"] == {"api/thing.py::alpha"}


def test_an_empty_changed_set_is_an_answer_and_an_absent_one_is_not(tmp_path: Path) -> None:
    graph = _repo(tmp_path)
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "alpha")])
    assert _plan(graph, inv, scope=()).units != ()



def test_check_exits_non_zero_on_a_stale_book(tmp_path: Path, capsys) -> None:
    graph = _repo(tmp_path, "api/thing.py::alpha", "api/thing.py::beta")
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "alpha"),
                                _symbol("api/thing.py", "beta")])
    assert coverage.run(graph, surface="api", inventory=inv)["missing"] == []
    write(tmp_path / "api/thing.py", "def beta(value):\n    return value * 2\n")
    argv = ["-C", str(tmp_path), "backfill", "plan", "--surface", "api",
            "--inventory", str(inv), "--check"]
    assert main(argv) == 1
    assert "dangling" in capsys.readouterr().out


def test_the_gate_passes_when_the_book_matches(tmp_path: Path) -> None:
    _repo(tmp_path, "api/thing.py::alpha", "api/thing.py::beta")
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "alpha"),
                                _symbol("api/thing.py", "beta")])
    assert main(["-C", str(tmp_path), "backfill", "plan", "--surface", "api",
                 "--inventory", str(inv), "--check"]) == 0


def test_another_books_broken_bullet_is_not_this_books_work(tmp_path: Path) -> None:
    graph = _repo(tmp_path, "api/thing.py::alpha")
    write(tmp_path / "docs/features/web/concepts/other.md",
          "---\ntype: concept\nslug: other\ntitle: Other\n---\n"
          "# Other\n\n- code: `web/gone.py::vanished`\n\nAnother book.\n")
    graph = load(tmp_path)
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "alpha")])
    assert any(f.code in backfill.DANGLING_CODES
               for f in doctor.run(graph, check_schema=False).findings)
    assert _reasons(_plan(graph, inv))["dangling"] == set()
