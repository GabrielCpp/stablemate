"""The regrounding queue (`main/nodes/coverage.py`).

When a cited file's bytes change under a citation that carries a digest, doctor reports
`stale-citation` and the join queues one row per changed file, naming every node that
cites it — rather than calling the book complete.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from workhorse_workflows.okf_builder.shared import paths
from ostler import stamp as stamp_mod

from okf_builder.conftest import CONCEPT
from workhorse_workflows.okf_builder.main.nodes.coverage import (
    compute_coverage,
    inventory_source,
)

SERVICE = "acme"
SOURCE_FILE = "acme/service.py"
CITATION = f"{SOURCE_FILE}::charge"
CHARGE_PAGE = f"docs/features/{SERVICE}/concepts/charge.md"

#: `charge`'s body, rewritten. The file's other declarations are untouched, so a run that
#: requeued every node citing the *file* rather than the *symbol* would be visible here.
DRIFTED_SOURCE = '''"""The billing service."""


def charge(amount):
    """Charge an amount, in cents."""
    return amount * 100
'''


def _verdict(book: Path, logger: logging.Logger):
    out = book / "inventory.json"
    inventory_source(logger, str(book / SERVICE), str(out), "", str(book))
    return compute_coverage(
        logger,
        str(book),
        str(paths.features_root(book, SERVICE)),
        SERVICE,
        str(out),
    )


def _stamp(book: Path, page: str = CHARGE_PAGE) -> None:
    """Stamp a page's citation with the digest of the file it currently cites.

    The shared `booked`/`CONCEPT` fixture writes a bare `` `path::symbol` `` bullet with no
    `@digest` — deliberately, since most tests have nothing to do with staleness. A bullet
    with no digest can only ever be `unstamped-citation`; it is never `stale-citation`, no
    matter how far the cited file drifts. Any test that means to exercise drift has to stamp
    its own citation first, the same way a real turn's finalize step would.
    """
    result = stamp_mod.stamp_page(book, paths.features_root(book, SERVICE), page)
    assert not result.unresolved, result.unresolved


# --- regrounding ------------------------------------------------------------


def test_a_symbol_that_changed_under_its_citation_is_queued_not_converged(
    booked: Path, logger: logging.Logger
) -> None:
    """The inversion the plan exists for: covered by the join, stale against its own stamp.

    Coverage arithmetic alone still says every unit is cited — that is exactly how four
    books stayed green two hundred commits behind their source. The verdict has to refuse.
    """
    _stamp(booked)
    assert _verdict(booked, logger).coverage_complete
    (booked / SOURCE_FILE).write_text(DRIFTED_SOURCE, encoding="utf-8")

    result = _verdict(booked, logger)
    assert not result.coverage_complete
    (item,) = result.regrounding
    assert item["kind"] == "fix:stale-citation"
    assert item["requeue"] is True
    context = json.loads(item["context"])
    assert context["code"] == "stale-citation"
    assert context["grounded"] is True
    assert context["file"] == SOURCE_FILE
    (node,) = context["nodes"]
    assert context["citations"][node].startswith(CITATION)


def test_a_changed_file_is_batched_five_citing_nodes_per_row(
    booked: Path, logger: logging.Logger
) -> None:
    """One changed file, many citing nodes: rows chunk at five, not one row for the lot.

    A single repair turn that had to re-read twelve nodes against one file would run out of
    context long before it finished; capping a row at five citing nodes is what keeps each
    turn's `stale-citation` prompt a size a model can actually act on.
    """
    total_citing = 12
    for i in range(total_citing - 1):
        (booked / f"docs/features/{SERVICE}/concepts/charge_{i}.md").write_text(
            CONCEPT.format(
                slug=f"charge-{i}", title=f"Charge {i}", symbol="charge",
                prose=f"Also charging, node {i}.",
            ),
            encoding="utf-8",
        )
    subprocess.run(["git", "add", "-A"], cwd=booked, check=True)
    subprocess.run(["git", "commit", "-qm", "more citations of the same symbol"], cwd=booked,
                    check=True)

    pages = [CHARGE_PAGE] + [
        f"docs/features/{SERVICE}/concepts/charge_{i}.md" for i in range(total_citing - 1)
    ]
    for page in pages:
        _stamp(booked, page)
    assert _verdict(booked, logger).coverage_complete

    (booked / SOURCE_FILE).write_text(DRIFTED_SOURCE, encoding="utf-8")
    result = _verdict(booked, logger)
    assert not result.coverage_complete

    assert len(result.regrounding) == 3  # ceil(12 / 5)
    sizes = sorted(len(json.loads(item["context"])["nodes"]) for item in result.regrounding)
    assert sizes == [2, 5, 5]
    all_nodes = {
        node
        for item in result.regrounding
        for node in json.loads(item["context"])["nodes"]
    }
    assert len(all_nodes) == total_citing
    for item in result.regrounding:
        assert item["kind"] == "fix:stale-citation"
        assert json.loads(item["context"])["file"] == SOURCE_FILE
