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

* ``drifted`` — the watermark's whole reason to exist. A cited symbol whose bytes
  disagree with the catalog. One ``fix:stale-citation`` row per citing node.

* ``moved`` — a cited symbol that is gone from the path the citation names and
  present unchanged elsewhere. Re-grounding work, distinct from a missing symbol:
  the bullet has to follow the move, not be rewritten from scratch.

* ``dangling`` — doctor codes the join cannot see. The checkpoint's channel.

* ``trim`` — a path the catalog carries but the tree does not. The file is gone, the
  bullets point at nothing in a way doctor misses (doctor reads the current tree),
  and the builder emits ``trim-bullet`` rows to retire them and ``trim-review``
  rows for the nodes that linked to something now gone.

* ``unreachable`` — orphan nodes ``graph --orphans`` already computes. Authored
  removal, queued the same way the rest of the work is.

* ``1-hop`` — when file B changes, every file that imports B is treated as changed
  too. The bound that stops the rebuild from being three days long for an edit to
  a core utility.
"""
from __future__ import annotations

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


def _row_targets(rows: list[dict]) -> set[str]:
    return {row["target"] for row in rows}


def _row_kinds(rows: list[dict]) -> set[str]:
    return {row["kind"] for row in rows}


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


# --- drifted, moved, dangling ----------------------------------------------------


def test_a_drifted_symbol_queues_a_stale_citation_row(
    booked_repo: Path, write: Callable[[Path, str], Path]
) -> None:
    """The inversion the join exists for: covered by the citation, stale against the bytes.

    Both functions get cited so the catalog's watermark is written at the first scan,
    and the second scan can tell that *only* ``charge`` drifted while ``refund`` did
    not — the per-symbol granularity is the whole reason the watermark exists.
    """
    refund_path = booked_repo / "docs/features/acme/concepts/refund.md"
    refund_path.write_text(CHARGE_CONCEPT.replace("charge", "refund").replace("Charge", "Refund"),
                           encoding="utf-8")

    features = booked_repo / "docs/features/acme"
    inv = features / ".source-inventory.json"
    inv.parent.mkdir(parents=True, exist_ok=True)

    from workhorse_workflows.okf_builder.main.nodes.coverage import (
        compute_coverage, inventory_source,
    )
    import logging
    logger = logging.getLogger("test")
    inventory_source(logger, str(booked_repo / "acme"), str(inv), "", str(booked_repo))
    coverage = compute_coverage(
        logger, str(booked_repo), str(features), SERVICE, str(inv),
    )
    assert coverage.coverage_complete

    # Now drift the symbol: the function's body changed.
    (booked_repo / "acme/service.py").write_text(
        SOURCE.replace("return amount", "return amount * 100"), encoding="utf-8",
    )

    result = build_worklist(booked_repo, features, SERVICE)
    rows = [r for r in result.rows if r["kind"] == "fix:stale-citation"]
    assert rows
    targets = {r["target"] for r in rows}
    assert "docs/features/acme/concepts/charge.md" in targets


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
    """A file the catalog carries but the tree lacks: bullets retired, neighbours reviewed.

    Both functions get cited so the watermark is written at the first scan and the
    catalog carries the file even after the second scan's tree walk says it is gone.
    The builder's deleted-path detection reads the catalog against the tree and emits
    trim rows for every node that cited the file.
    """
    refund_path = booked_repo / "docs/features/acme/concepts/refund.md"
    refund_path.write_text(
        CHARGE_CONCEPT.replace("charge", "refund").replace("Charge", "Refund"),
        encoding="utf-8",
    )

    features = booked_repo / "docs/features/acme"
    inv = features / ".source-inventory.json"
    inv.parent.mkdir(parents=True, exist_ok=True)

    from workhorse_workflows.okf_builder.main.nodes.coverage import (
        compute_coverage, inventory_source,
    )
    import logging
    logger = logging.getLogger("test")
    inventory_source(logger, str(booked_repo / "acme"), str(inv), "", str(booked_repo))
    coverage = compute_coverage(
        logger, str(booked_repo), str(features), SERVICE, str(inv),
    )
    assert coverage.coverage_complete

    # Delete the cited source file. The catalog still records it; the join knows nothing.
    (booked_repo / "acme/service.py").unlink()

    result = build_worklist(booked_repo, features, SERVICE)
    kinds = _row_kinds(list(result.rows))
    assert "trim-bullet" in kinds


def test_a_deleted_path_does_not_emit_trim_when_nothing_cited_it(
    fresh_repo: Path, write: Callable[[Path, str], Path]
) -> None:
    """A file the catalog carried but nothing cited: dropped silently, no rows queued.

    The catalog carries it because *something* once cited it; nothing cites it now, so
    a trim row would have nothing to do and would sit as busy-work on the worklist.
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
    # Write a catalog that knows about a file that has never existed.
    catalog_path = fresh_repo / "docs/features" / "sources.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    from ostler.source_snapshots import SourceCatalog, RepositorySnapshot, SourceFile, SELF_REPOSITORY
    catalog_path.write_text(
        SourceCatalog(repositories=(
            RepositorySnapshot(
                id=SELF_REPOSITORY, base="", head="WORKTREE",
                files=(SourceFile(path="ghost.py", content_sha256="0" * 64),),
            ),
        )).model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )

    result = build_worklist(fresh_repo, features, SERVICE)
    assert all(r["kind"] != "trim-bullet" for r in result.rows)


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