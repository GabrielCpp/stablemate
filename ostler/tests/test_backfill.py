"""`ostler backfill plan` — the stale set that says what a book owes its code.

The defect these pin is a book reporting `covered == total` while its citations describe
code from months earlier. Coverage answers "is every symbol cited"; none of it looks at
whether a cited symbol is still the symbol that was read. `dangling` is doctor's verdict
that a citation points at nothing; `uncovered` is the coverage join's misses. A symbol that
moved to another file is the interesting case a plain set difference cannot express: its old
citation is `dangling` and the coverage join would also raise the new location as
`uncovered`, reporting the one edit as two — `_already_documented_elsewhere` is the guard
against that, and only when the symbol's name is unique across the inventory.
"""

from __future__ import annotations

import json
from pathlib import Path

from ostler import backfill, coverage, doctor, source_snapshots
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


# -- the first fill and the steady state ---------------------------------------------------

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


# -- the two cases a set difference cannot express -----------------------------------------

def test_a_symbol_moved_to_another_file_suppresses_its_uncovered_row(tmp_path: Path) -> None:
    # The one edit reads as one row: the old citation is `dangling`, and the new location's
    # `uncovered` row is suppressed because its symbol name uniquely matches it.
    graph = _repo(tmp_path, "api/thing.py::alpha")
    write(tmp_path / "api/thing.py", "def beta(value):\n    return value * 2\n")
    write(tmp_path / "api/moved.py", "def alpha(value):\n    return value + 1\n")
    inv = _inventory(tmp_path, [_symbol("api/moved.py", "alpha"),
                                _symbol("api/thing.py", "beta")])
    result = _plan(graph, inv)
    reasons = _reasons(result)
    assert reasons["dangling"] == {"api/thing.py::alpha"}
    assert "api/moved.py::alpha" not in reasons["uncovered"]


def test_a_repeated_symbol_name_is_not_suppressed(tmp_path: Path) -> None:
    # The name recurs in a third file, so it is not provably the moved symbol — both rows
    # must surface, or the real uncovered work at the third file goes unreported.
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


def test_a_symbol_renamed_in_place_is_a_dead_citation_and_new_code(tmp_path: Path) -> None:
    # Deliberately *two* rows: the old name documents nothing and the new name is documented
    # by nobody, and the two names differ so no suppression applies.
    graph = _repo(tmp_path, "api/thing.py::alpha")
    write(tmp_path / "api/thing.py", SOURCE.replace("def alpha", "def gamma"))
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "gamma"),
                                _symbol("api/thing.py", "beta")])
    result = _plan(graph, inv)
    reasons = _reasons(result)
    assert reasons["dangling"] == {"api/thing.py::alpha"}
    assert reasons["uncovered"] == {"api/thing.py::gamma", "api/thing.py::beta"}


# -- narrowing ------------------------------------------------------------------------------

def test_a_scope_narrows_the_plan_without_widening_it(tmp_path: Path) -> None:
    graph = _repo(tmp_path)
    write(tmp_path / "web/other.py", "def delta():\n    return 0\n")
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "alpha"),
                                _symbol("web/other.py", "delta")])
    result = _plan(graph, inv, scope=("api",))
    assert _reasons(result)["uncovered"] == {"api/thing.py::alpha"}


def test_an_empty_changed_set_is_an_answer_and_an_absent_one_is_not(tmp_path: Path) -> None:
    # `--since` on a branch with no changes must produce an empty plan; git failing to answer
    # at all must produce the whole one. Conflating them is how a scoped run silently does
    # nothing and reports success.
    graph = _repo(tmp_path)
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "alpha")])
    assert _plan(graph, inv, scope=()).units != ()


# -- the gate --------------------------------------------------------------------------------

def test_check_exits_non_zero_on_a_stale_book(tmp_path: Path, capsys) -> None:
    # The inversion the whole change exists for: `ostler coverage` calls this book complete.
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


def test_snapshot_writes_the_watermark_the_next_plan_reads(tmp_path: Path) -> None:
    _repo(tmp_path, "api/thing.py::alpha")
    assert main(["-C", str(tmp_path), "backfill", "snapshot"]) == 0
    catalog = source_snapshots.load_catalog(tmp_path)
    assert catalog is not None
    snapshot = catalog.repository(source_snapshots.SELF_REPOSITORY)
    assert snapshot is not None
    assert snapshot.files[0].digest_of("alpha")


def test_another_books_broken_bullet_is_not_this_books_work(tmp_path: Path) -> None:
    # Doctor reads the whole graph. A plan scoped to one surface that counts another book's
    # dangling citations hands the run a number it cannot act on.
    graph = _repo(tmp_path, "api/thing.py::alpha")
    write(tmp_path / "docs/features/web/concepts/other.md",
          "---\ntype: concept\nslug: other\ntitle: Other\n---\n"
          "# Other\n\n- code: `web/gone.py::vanished`\n\nAnother book.\n")
    graph = load(tmp_path)
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "alpha")])
    assert any(f.code in backfill.DANGLING_CODES
               for f in doctor.run(graph, check_schema=False).findings)
    assert _reasons(_plan(graph, inv))["dangling"] == set()
