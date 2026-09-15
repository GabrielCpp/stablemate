"""The worklist builder: one composable answer to "what does the book owe the code?".

Both okf-builder and the coder docs lane call into the same function. The shape they
care about is the same — every row the drain should pick up — and the only difference
between the two is the path filter: ``None`` for the whole tree, the story's changed
paths for the coder lane. The tests pin both shapes against a real repo so the
joins are exercised end-to-end rather than as mocked units.

The cases that drove the design:

* ``uncovered`` — the inventory's first-fill case. A book that has never documented
  this code owes every unit it does not cite; the builder surfaces the join's
  ``missing`` list verbatim and the recheck agent adjudicates.

* ``drifted`` — a cited symbol whose bytes disagree with its own stamp. One
  ``fix:stale-citation`` row per citing node.

* ``moved`` — a cited symbol that is gone from the path the citation names and
  present unchanged elsewhere. Re-grounding work, distinct from a missing symbol:
  the bullet has to follow the move, not be rewritten from scratch.

* ``dangling`` — doctor codes the join cannot see. The checkpoint's channel.

* ``trim`` — an own-repository path the book cites that the tree does not carry. The
  file is gone, the bullets point at nothing in a way doctor misses (doctor reads
  the current tree), and the builder emits ``trim-bullet`` rows to retire them and
  ``trim-review`` rows for the nodes that linked to something now gone.

* ``unreachable`` — orphan nodes ``graph --orphans`` already computes. Authored
  removal, queued the same way the rest of the work is.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pytest

from workhorse_workflows.kit import build_worklist


SERVICE = "acme"

SOURCE = '''"""The billing service."""


def charge(amount):
    """Charge an amount."""
    return amount


def refund(amount):
    """Refund an amount."""
    return -amount
'''

CHARGE_CONCEPT = """---
type: concept
slug: charge
title: Charge
---
# Charge

- code: `acme/service.py::charge`

The charge entry point.
"""


@pytest.fixture
def fresh_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real git repo with a one-function source and an empty features tree."""
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setenv("OSTLER_INDEX_DIR", str(tmp_path / "ostler-index"))
    (root / "acme").mkdir()
    (root / "acme/service.py").write_text(SOURCE, encoding="utf-8")
    (root / "docs/features").mkdir(parents=True)
    return root


@pytest.fixture
def booked_repo(fresh_repo: Path) -> Path:
    """A repo whose one-function source is exactly covered by its one-doc book."""
    (fresh_repo / "docs/features/acme/concepts").mkdir(parents=True, exist_ok=True)
    (fresh_repo / "docs/features/acme/concepts/charge.md").write_text(
        CHARGE_CONCEPT, encoding="utf-8"
    )
    return fresh_repo


def _feature_text(citations: list[str]) -> str:
    bullets = "\n".join(f"- code: `{citation}`" for citation in citations)
    return (
        "---\ntype: concept\nslug: charge\ntitle: Charge\n---\n"
        "# Charge\n\n"
        f"{bullets}\n\nThe charge entry point.\n"
    )


# --- the whole-tree, no-book case ------------------------------------------------


def test_an_unbooked_repo_owes_every_unit_in_missing(
    fresh_repo: Path, write: Callable[[Path, str], Path]
) -> None:
    """The first-fill case: no book, no citations, every unit is work.

    The builder surfaces the inventory's ``missing`` list verbatim. The recheck agent
    adjudicates; the builder does not pretend to know which are real.
    """
    features = fresh_repo / "docs/features/acme"
    features.mkdir(parents=True)
    inv = features / ".source-inventory.json"
    inv.parent.mkdir(parents=True, exist_ok=True)

    from workhorse_workflows.okf_builder.main.nodes.coverage import inventory_source
    import logging
    inventory_source(
        logging.getLogger("test"), str(fresh_repo / "acme"), str(inv), "", str(fresh_repo),
    )

    result = build_worklist(fresh_repo, features, SERVICE)
    units = {miss["code"] for miss in result.missing}
    assert "acme/service.py::charge" in units
    assert "acme/service.py::refund" in units
    assert result.rows == ()


def test_a_booked_repo_with_no_drift_is_complete(
    booked_repo: Path, write: Callable[[Path, str], Path]
) -> None:
    """A repo whose book matches its code returns no rows for the cited unit.

    The whole point of the digest skip: a rebase that changes nothing does not pay for
    an agent turn, and the cited units' worklist comes back empty. The other unit
    (``refund``) is missing because nothing cites it, which is the inventory's job,
    not the builder's — the builder surfaces that as ``missing``, not as a worklist
    row.
    """
    features = booked_repo / "docs/features/acme"
    inv = features / ".source-inventory.json"
    inv.parent.mkdir(parents=True, exist_ok=True)

    from workhorse_workflows.okf_builder.main.nodes.coverage import (
        compute_coverage, inventory_source,
    )
    import logging
    logger = logging.getLogger("test")
    inventory_source(logger, str(booked_repo / "acme"), str(inv), "", str(booked_repo))
    compute_coverage(
        logger, str(booked_repo), str(features), SERVICE, str(inv),
    )

    result = build_worklist(booked_repo, features, SERVICE)
    assert all(r["kind"] != "fix:stale-citation" for r in result.rows)
    assert all(r["kind"] != "trim-bullet" for r in result.rows)


# --- dangling ----------------------------------------------------------------------


def test_a_missing_symbol_queues_a_dangling_row(
    booked_repo: Path, write: Callable[[Path, str], Path]
) -> None:
    """A cited symbol that no longer exists at all — `missing-code-symbol`.

    Doctor reports it; the builder translates the finding into a ``fix:`` row keyed on
    the doctor code, so the drain dispatches to the right repair prompt.
    """
    features = booked_repo / "docs/features/acme"
    inv = features / ".source-inventory.json"
    inv.parent.mkdir(parents=True, exist_ok=True)

    from workhorse_workflows.okf_builder.main.nodes.coverage import inventory_source
    import logging
    inventory_source(
        logging.getLogger("test"),
        str(booked_repo / "acme"), str(inv), "", str(booked_repo),
    )
    # Replace the function with an unrelated name.
    (booked_repo / "acme/service.py").write_text(
        "def invoice(value):\n    return value\n", encoding="utf-8",
    )

    result = build_worklist(booked_repo, features, SERVICE)
    fix_rows = [r for r in result.rows if r["kind"].startswith("fix:")]
    assert fix_rows, result.rows
    targets = {r["target"] for r in fix_rows}
    assert "docs/features/acme/concepts/charge.md" in targets


# --- the trim path ---------------------------------------------------------------


def test_a_deleted_path_emits_trim_bullet_and_review_rows(
    booked_repo: Path, write: Callable[[Path, str], Path]
) -> None:
    """An own-repository path the book cites but the tree no longer carries: bullets
    retired, neighbours reviewed.

    Deleted-path detection reads the book's own citations, not a catalog: two pages
    cite the same file, the file is deleted, and both citations retire — one
    ``trim-bullet`` row per citation, not one per file.
    """
    write(
        booked_repo / "docs/features/acme/concepts/refund.md",
        CHARGE_CONCEPT.replace("charge", "refund").replace("Charge", "Refund"),
    )

    features = booked_repo / "docs/features/acme"
    inv = features / ".source-inventory.json"
    inv.parent.mkdir(parents=True, exist_ok=True)

    from workhorse_workflows.okf_builder.main.nodes.coverage import inventory_source
    import logging
    inventory_source(
        logging.getLogger("test"), str(booked_repo / "acme"), str(inv), "", str(booked_repo),
    )

    # Delete the cited source file. The book still cites it; the tree no longer has it.
    (booked_repo / "acme/service.py").unlink()

    result = build_worklist(booked_repo, features, SERVICE)
    trim_rows = [r for r in result.rows if r["kind"] == "trim-bullet"]
    citations = {json.loads(r["context"])["citation"] for r in trim_rows}
    assert citations == {"acme/service.py::charge", "acme/service.py::refund"}
    assert len(trim_rows) == len(citations)


def test_a_deleted_path_does_not_emit_trim_when_nothing_cited_it(
    booked_repo: Path, write: Callable[[Path, str], Path]
) -> None:
    """A file the tree loses that nothing in the book ever cited: no trim, no busy-work.

    Trim fires only for a path the book's own citations name. A file nothing cites
    disappearing is invisible to the join, exactly as it should be.
    """
    write(booked_repo / "acme/legacy.py", "def helper():\n    return 1\n")

    features = booked_repo / "docs/features/acme"
    inv = features / ".source-inventory.json"
    inv.parent.mkdir(parents=True, exist_ok=True)

    from workhorse_workflows.okf_builder.main.nodes.coverage import inventory_source
    import logging
    inventory_source(
        logging.getLogger("test"),
        str(booked_repo / "acme"), str(inv), "", str(booked_repo),
    )

    (booked_repo / "acme/legacy.py").unlink()

    result = build_worklist(booked_repo, features, SERVICE)
    assert all(r["kind"] != "trim-bullet" for r in result.rows)


# --- relocation: a moved symbol is not a deletion ---------------------------------


def test_a_relocated_symbol_keeps_the_dangling_row_instead_of_trim(
    booked_repo: Path, write: Callable[[Path, str], Path]
) -> None:
    """A citation whose symbol moved to another file: the ``dangling`` row survives so
    the citation can be re-pointed, instead of trim deleting the node outright.
    """
    features = booked_repo / "docs/features/acme"
    inv = features / ".source-inventory.json"
    inv.parent.mkdir(parents=True, exist_ok=True)

    # The cited file is gone; `charge` now lives, uniquely, at a new path.
    (booked_repo / "acme/service.py").unlink()
    write(booked_repo / "acme/moved.py", "def charge(amount):\n    return amount\n")

    from workhorse_workflows.okf_builder.main.nodes.coverage import inventory_source
    import logging
    inventory_source(
        logging.getLogger("test"), str(booked_repo / "acme"), str(inv), "", str(booked_repo),
    )

    result = build_worklist(booked_repo, features, SERVICE)
    dangling = [r for r in result.rows if r["kind"] == "fix:dangling"]
    assert dangling, result.rows
    contexts = [json.loads(r["context"]) for r in dangling]
    assert any(
        c["citation"] == "acme/service.py::charge"
        and c.get("relocated_to") == "acme/moved.py::charge"
        for c in contexts
    )
    trim_rows = [r for r in result.rows if r["kind"] == "trim-bullet"]
    assert all(
        json.loads(r["context"])["citation"] != "acme/service.py::charge"
        for r in trim_rows
    )


def test_a_repeated_symbol_name_elsewhere_still_trims(
    booked_repo: Path, write: Callable[[Path, str], Path]
) -> None:
    """The symbol name recurs at more than one other path: not provably a move, so
    trim still fires and the duplicated uncovered units are not suppressed.
    """
    features = booked_repo / "docs/features/acme"
    inv = features / ".source-inventory.json"
    inv.parent.mkdir(parents=True, exist_ok=True)

    (booked_repo / "acme/service.py").unlink()
    write(booked_repo / "acme/moved.py", "def charge(amount):\n    return amount\n")
    write(booked_repo / "acme/other.py", "def charge(amount):\n    return amount * 2\n")

    from workhorse_workflows.okf_builder.main.nodes.coverage import inventory_source
    import logging
    inventory_source(
        logging.getLogger("test"), str(booked_repo / "acme"), str(inv), "", str(booked_repo),
    )

    result = build_worklist(booked_repo, features, SERVICE)
    trim_rows = [r for r in result.rows if r["kind"] == "trim-bullet"]
    assert any(
        json.loads(r["context"])["citation"] == "acme/service.py::charge"
        for r in trim_rows
    )
    dangling = [r for r in result.rows if r["kind"] == "fix:dangling"]
    assert all(not json.loads(r["context"]).get("relocated_to") for r in dangling)
    missing_units = {miss["code"] for miss in result.missing}
    assert "acme/moved.py::charge" in missing_units
    assert "acme/other.py::charge" in missing_units


# --- the path filter --------------------------------------------------------------


def test_a_path_filter_narrows_missing_to_those_paths(
    fresh_repo: Path, write: Callable[[Path, str], Path]
) -> None:
    """A coder lane passes the story's changed paths; the builder narrows accordingly.

    The same join runs in both cases — only the denominator differs — so a story that
    touched only ``acme/service.py`` does not pay for the join to inspect every other
    unit in the tree.
    """
    features = fresh_repo / "docs/features/acme"
    features.mkdir(parents=True)
    (features / ".source-inventory.json").parent.mkdir(parents=True, exist_ok=True)

    # Add a second file with a function, to widen the inventory.
    (fresh_repo / "acme/notifier.py").write_text(
        "def notify(event):\n    return event\n", encoding="utf-8",
    )
    inv = features / ".source-inventory.json"

    from workhorse_workflows.okf_builder.main.nodes.coverage import inventory_source
    import logging
    inventory_source(
        logging.getLogger("test"),
        str(fresh_repo / "acme"), str(inv), "", str(fresh_repo),
    )

    # Whole tree: both files are missing.
    whole = build_worklist(fresh_repo, features, SERVICE, paths=None)
    whole_paths = {miss["path"] for miss in whole.missing}
    assert "acme/service.py" in whole_paths
    assert "acme/notifier.py" in whole_paths

    # Just the notifier: only its units are missing.
    narrow = build_worklist(
        fresh_repo, features, SERVICE, paths=["acme/notifier.py"],
    )
    narrow_paths = {miss["path"] for miss in narrow.missing}
    assert narrow_paths == {"acme/notifier.py"}


def test_an_empty_filter_is_a_real_filter_not_whole_tree(
    fresh_repo: Path, write: Callable[[Path, str], Path]
) -> None:
    """``[]`` is "filter to nothing", not "no filter".

    A story that touched no source files is a legitimate answer — its worklist is
    empty, not the wider whole-tree view. The two are not the same shape; conflating
    them is how a scoped build silently widened to everything.
    """
    features = fresh_repo / "docs/features/acme"
    features.mkdir(parents=True)
    inv = features / ".source-inventory.json"
    inv.parent.mkdir(parents=True, exist_ok=True)

    from workhorse_workflows.okf_builder.main.nodes.coverage import inventory_source
    import logging
    inventory_source(
        logging.getLogger("test"),
        str(fresh_repo / "acme"), str(inv), "", str(fresh_repo),
    )

    empty = build_worklist(fresh_repo, features, SERVICE, paths=[])
    whole = build_worklist(fresh_repo, features, SERVICE, paths=None)
    assert empty.missing == ()
    assert empty.rows == ()
    assert len(whole.missing) > 0


# --- the orphans -----------------------------------------------------------------


def test_orphan_concepts_queue_unreachable_rows(
    fresh_repo: Path, write: Callable[[Path, str], Path]
) -> None:
    """A concept the book never links to queues an authored-removal row.

    ``graph --orphans`` finds the node; the builder translates it into a worklist row
    that the drain dispatches to the authored-removal handler. The check already lives
    in ostler — the builder does not reimplement it, only translates its output.
    """
    (fresh_repo / "docs/features/concepts").mkdir(parents=True, exist_ok=True)
    (fresh_repo / "docs/features/concepts/orphan.md").write_text(
        "---\ntype: concept\nslug: orphan\ntitle: Orphan\n---\n# Orphan\n\nNothing links here.\n",
        encoding="utf-8",
    )

    features = fresh_repo / "docs/features"
    inv = features / ".source-inventory.json"
    inv.parent.mkdir(parents=True, exist_ok=True)

    from workhorse_workflows.okf_builder.main.nodes.coverage import inventory_source
    import logging
    inventory_source(
        logging.getLogger("test"),
        str(fresh_repo / "acme"), str(inv), "", str(fresh_repo),
    )

    result = build_worklist(fresh_repo, features, "")
    unreachable = [r for r in result.rows if r["kind"] == "unreachable"]
    assert unreachable, result.rows
    assert any("orphan" in r["target"] for r in unreachable)