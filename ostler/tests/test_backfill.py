"""`ostler backfill plan` — the stale set that says what a book owes its code.

The defect these pin is a book reporting `covered == total` while its citations describe
code from months earlier. Coverage answers "is every symbol cited"; none of it looks at
whether a cited symbol is still the symbol that was read. That is the watermark's job, and
the interesting cases are the ones a set difference cannot express at all: a symbol that
moved unchanged is re-grounding work, not re-documenting work, and a symbol renamed in
place is *both* a dead citation and new undocumented code.
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


def _plan(graph: Graph, inventory: Path, *, catalog=None, **kw) -> backfill.BackfillPlan:
    """The plan, with the impure inputs `cli` would have gathered."""
    return backfill.plan(
        graph, coverage.load_inventory(inventory), catalog,
        surface="api", findings=doctor.run(graph, check_schema=False).findings, **kw)


def _reasons(result: backfill.BackfillPlan) -> dict[str, set[str]]:
    return {reason: {row.unit for row in rows} for reason, rows in result.by_reason().items()}


# -- the first fill and the steady state ---------------------------------------------------

def test_a_book_with_no_watermark_owes_every_symbol_it_does_not_cite(tmp_path: Path) -> None:
    # The first-fill case: no `sources.json` exists, so nothing can have drifted, and the
    # whole inventory is work.
    graph = _repo(tmp_path)
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "alpha"),
                                _symbol("api/thing.py", "beta")])
    result = _plan(graph, inv, catalog=None)
    assert _reasons(result)["uncovered"] == {"api/thing.py::alpha", "api/thing.py::beta"}
    assert not result.is_clean


def test_a_book_that_matches_its_code_owes_nothing(tmp_path: Path) -> None:
    graph = _repo(tmp_path, "api/thing.py::alpha", "api/thing.py::beta")
    source_snapshots.write_catalog(graph, ())
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "alpha"),
                                _symbol("api/thing.py", "beta")])
    result = _plan(graph, inv, catalog=source_snapshots.load_catalog(tmp_path))
    assert result.units == ()
    assert result.is_clean


# -- drift ---------------------------------------------------------------------------------

def test_editing_one_body_makes_exactly_that_citation_drift(tmp_path: Path) -> None:
    # The whole reason the watermark is per symbol: a file-level digest would requeue every
    # node citing this file, and against a 40-symbol file that is the difference between a
    # five-item run and a three-hundred-item one.
    graph = _repo(tmp_path, "api/thing.py::alpha", "api/thing.py::beta")
    source_snapshots.write_catalog(graph, ())
    write(tmp_path / "api/thing.py", SOURCE.replace("value + 1", "value + 99"))
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "alpha"),
                                _symbol("api/thing.py", "beta")])
    result = _plan(graph, inv, catalog=source_snapshots.load_catalog(tmp_path))
    assert _reasons(result)["drifted"] == {"api/thing.py::alpha"}
    assert result.units[0].evidence  # the two digests, so a reader can check the claim


def test_a_citation_with_no_stored_digest_is_not_called_drifted(tmp_path: Path) -> None:
    # A watermark says "this changed". Its absence never says "this did not" — and it must
    # never say "this did", which is how a pre-watermark book would light up entirely.
    graph = _repo(tmp_path, "api/thing.py::alpha")
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "alpha")])
    result = _plan(graph, inv, catalog=None)
    assert _reasons(result)["drifted"] == set()


# -- the two cases a set difference cannot express -----------------------------------------

def test_a_symbol_that_moved_unchanged_is_regrounding_work(tmp_path: Path) -> None:
    graph = _repo(tmp_path, "api/thing.py::alpha")
    source_snapshots.write_catalog(graph, ())
    write(tmp_path / "api/thing.py", "def beta(value):\n    return value * 2\n")
    write(tmp_path / "api/moved.py", "def alpha(value):\n    return value + 1\n")
    inv = _inventory(tmp_path, [_symbol("api/moved.py", "alpha"),
                                _symbol("api/thing.py", "beta")])
    result = _plan(graph, inv, catalog=source_snapshots.load_catalog(tmp_path))
    reasons = _reasons(result)
    assert reasons["moved"] == {"api/thing.py::alpha"}
    assert result.units[0].target == "api/moved.py::alpha"
    # Neither of the two rows a lesser instrument would emit for this one edit: doctor's
    # dangling citation, and the coverage join's undocumented destination.
    assert reasons["dangling"] == set()
    assert "api/moved.py::alpha" not in reasons["uncovered"]


def test_a_symbol_renamed_in_place_is_a_dead_citation_and_new_code(tmp_path: Path) -> None:
    # Deliberately *two* rows, unlike the move: the old name documents nothing and the new
    # name is documented by nobody. Collapsing them would lose one of the two edits.
    graph = _repo(tmp_path, "api/thing.py::alpha")
    source_snapshots.write_catalog(graph, ())
    write(tmp_path / "api/thing.py", SOURCE.replace("def alpha", "def gamma"))
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "gamma"),
                                _symbol("api/thing.py", "beta")])
    result = _plan(graph, inv, catalog=source_snapshots.load_catalog(tmp_path))
    reasons = _reasons(result)
    assert reasons["dangling"] == {"api/thing.py::alpha"}
    assert reasons["uncovered"] == {"api/thing.py::gamma", "api/thing.py::beta"}
    assert reasons["moved"] == set()


# -- narrowing ------------------------------------------------------------------------------

def test_a_scope_narrows_the_plan_without_widening_it(tmp_path: Path) -> None:
    graph = _repo(tmp_path)
    write(tmp_path / "web/other.py", "def delta():\n    return 0\n")
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "alpha"),
                                _symbol("web/other.py", "delta")])
    result = _plan(graph, inv, catalog=None, scope=("api",))
    assert _reasons(result)["uncovered"] == {"api/thing.py::alpha"}


def test_an_empty_changed_set_is_an_answer_and_an_absent_one_is_not(tmp_path: Path) -> None:
    # `--since` on a branch with no changes must produce an empty plan; git failing to answer
    # at all must produce the whole one. Conflating them is how a scoped run silently does
    # nothing and reports success.
    graph = _repo(tmp_path)
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "alpha")])
    assert _plan(graph, inv, catalog=None, changed=set()).units == ()
    assert _plan(graph, inv, catalog=None, changed=None).units != ()


# -- the gate --------------------------------------------------------------------------------

def test_check_exits_non_zero_on_a_stale_book(tmp_path: Path, capsys) -> None:
    # The inversion the whole change exists for: `ostler coverage` calls this book complete.
    graph = _repo(tmp_path, "api/thing.py::alpha", "api/thing.py::beta")
    source_snapshots.write_catalog(graph, ())
    inv = _inventory(tmp_path, [_symbol("api/thing.py", "alpha"),
                                _symbol("api/thing.py", "beta")])
    assert coverage.run(graph, surface="api", inventory=inv)["missing"] == []
    write(tmp_path / "api/thing.py", SOURCE.replace("value + 1", "value + 99"))
    argv = ["-C", str(tmp_path), "backfill", "plan", "--surface", "api",
            "--inventory", str(inv), "--check"]
    assert main(argv) == 1
    assert "drifted" in capsys.readouterr().out


def test_the_gate_passes_when_the_book_matches(tmp_path: Path) -> None:
    graph = _repo(tmp_path, "api/thing.py::alpha", "api/thing.py::beta")
    source_snapshots.write_catalog(graph, ())
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
    assert _reasons(_plan(graph, inv, catalog=None))["dangling"] == set()
