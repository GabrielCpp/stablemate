"""The watermark and the regrounding queue (`main/nodes/coverage.py`).

Two behaviours, one loop. The **watermark** is the record of what the book was written
against, and it is claimed at exactly one moment: the verdict that says every unit is
covered *and* nothing has drifted under it, on a full scan. Anywhere earlier — the clean
checkpoint, which runs before this join — would stamp symbols nobody re-read as current
and erase, in the same pass, the drift the join exists to report.

**Regrounding** is the other half: when a cited symbol's bytes change under a node, the
join queues that node as `fix:stale-citation` rather than calling the book complete. The
row retires only when `advance_watermark` re-reads the file the turn documented against —
without that, the very next join reports the same drift and the drain laps forever.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from workhorse_workflows.okf_builder.shared import paths
from ostler.source_snapshots import catalog_path

from workhorse_workflows.okf_builder.main.nodes.coverage import (
    advance_watermark,
    compute_coverage,
    inventory_source,
)

SERVICE = "acme"
SOURCE_FILE = "acme/service.py"
CITATION = f"{SOURCE_FILE}::charge"

#: `charge`'s body, rewritten. The file's other declarations are untouched, so a run that
#: requeued every node citing the *file* rather than the *symbol* would be visible here.
DRIFTED_SOURCE = '''"""The billing service."""


def charge(amount):
    """Charge an amount, in cents."""
    return amount * 100
'''


def _verdict(book: Path, logger: logging.Logger, *, scoped: bool = False):
    out = book / "inventory.json"
    inventory_source(logger, str(book / SERVICE), str(out), "", str(book))
    return compute_coverage(
        logger,
        str(book),
        str(paths.features_root(book, SERVICE)),
        SERVICE,
        str(out),
        scoped=scoped,
    )


def _catalog(book: Path) -> dict:
    return json.loads(catalog_path(book).read_text())


# --- the watermark ----------------------------------------------------------


def test_a_complete_verdict_leaves_a_watermark_the_next_run_can_read(
    booked: Path, logger: logging.Logger
) -> None:
    """`ostler backfill plan` can only call a citation drifted against a stored digest.

    Nothing but a converged, full scan is entitled to say "this node was written against
    these bytes", so the verdict is where the catalog is written and the digest is
    per-declaration — the granularity the whole plan turns on.
    """
    result = _verdict(booked, logger)
    assert result.coverage_complete
    assert not result.regrounding

    (repo,) = _catalog(booked)["repositories"]
    (file,) = repo["files"]
    assert file["path"] == SOURCE_FILE
    assert [s["name"] for s in file["declarations"]] == ["charge"]
    assert file["declarations"][0]["content_sha256"]


def test_a_scoped_verdict_claims_no_watermark(booked: Path, logger: logging.Logger) -> None:
    """A scoped run read a subset of the source, so its "complete" is about that subset.

    Stamping the whole catalog off it would mark every unvisited symbol current — the same
    reason a scoped run does not overwrite `coverage.json`.
    """
    assert _verdict(booked, logger, scoped=True).coverage_complete
    assert not catalog_path(booked).exists()


def test_an_incomplete_verdict_claims_no_watermark(
    booked: Path, logger: logging.Logger
) -> None:
    """A symbol nothing documents leaves the join short, and a short join earns no stamp.

    Writing the catalog anyway would mark every *other* symbol current on the strength of a
    round that documented none of them, and the next run would see a clean stale set over a
    book nobody finished. (A dangling citation is the checkpoint's channel, not this one —
    the join only reaches a verdict on a doctor-green book.)
    """
    (booked / SOURCE_FILE).write_text(
        DRIFTED_SOURCE + "\n\ndef refund(amount):\n    return -amount\n", encoding="utf-8"
    )
    result = _verdict(booked, logger)

    assert not result.coverage_complete
    assert result.missing_count
    assert not catalog_path(booked).exists()


# --- regrounding ------------------------------------------------------------


def test_a_symbol_that_changed_under_its_citation_is_queued_not_converged(
    booked: Path, logger: logging.Logger
) -> None:
    """The inversion the plan exists for: covered by the join, stale against the watermark.

    Coverage arithmetic alone still says every unit is cited — that is exactly how four
    books stayed green two hundred commits behind their source. The verdict has to refuse.
    """
    assert _verdict(booked, logger).coverage_complete
    (booked / SOURCE_FILE).write_text(DRIFTED_SOURCE, encoding="utf-8")

    result = _verdict(booked, logger)
    assert not result.coverage_complete
    (item,) = result.regrounding
    assert item["kind"] == "fix:stale-citation"
    assert item["requeue"] is True
    context = json.loads(item["context"])
    assert context["reason"] == "drifted"
    assert context["citation"] == CITATION
    assert context["grounded"] is True


def test_a_closed_regrounding_row_retires_its_own_watermark(
    booked: Path, logger: logging.Logger
) -> None:
    """Without this the drain laps: the join reports the same drift on the next round.

    The advance is per-path and mid-run, which is also what makes an interrupted run
    resumable — the next plan's stale set is the remainder, not the original set.
    """
    _verdict(booked, logger)
    before = _catalog(booked)["repositories"][0]["files"][0]["declarations"][0]
    (booked / SOURCE_FILE).write_text(DRIFTED_SOURCE, encoding="utf-8")
    (item,) = _verdict(booked, logger).regrounding

    result = advance_watermark(
        logger, str(booked), item["kind"], item["context"], "complete"
    )
    assert result.advanced == [SOURCE_FILE]
    assert not result.watermark_error

    after = _catalog(booked)["repositories"][0]["files"][0]["declarations"][0]
    assert after["name"] == before["name"] == "charge"
    assert after["content_sha256"] != before["content_sha256"]


def test_a_partial_turn_advances_nothing(booked: Path, logger: logging.Logger) -> None:
    """A citation the turn did not finish reconciling still describes bytes nobody read.

    Stamping it current would hide the gap under the next clean verdict, which is the one
    failure mode a watermark must never introduce.
    """
    _verdict(booked, logger)
    (booked / SOURCE_FILE).write_text(DRIFTED_SOURCE, encoding="utf-8")
    (item,) = _verdict(booked, logger).regrounding

    result = advance_watermark(
        logger, str(booked), item["kind"], item["context"], "partial"
    )
    assert result.advanced == []
    assert _verdict(booked, logger).regrounding
