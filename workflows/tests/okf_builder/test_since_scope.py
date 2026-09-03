"""`--since`: how a reconcile narrows itself to what changed after a revision.

Two seams, tested at each end. `prepare` turns a revision into run state — a scope file
under the build dir and two `Prepared` fields — and blocks the run when the narrowing it
was asked for cannot be computed. The coverage side consumes that file: a scoped
`inventory_source` keeps only the units the change touched (operational ones included),
an unreadable scope file is an error and an empty inventory, and a scoped
`compute_coverage` refuses to overwrite the committed whole-book `coverage.json` with a
subset measurement.

The git read itself is `ostler.source_snapshots.changed_since`, tested in ostler where it
lives. What matters here is that an empty answer stays empty: `since` on the tip of the
branch it names narrows to nothing, and nothing is what gets measured — the run does not
widen back into a full scan behind the operator's back.
"""
from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from workhorse_workflows.okf_builder.main.nodes.coverage import (
    compute_coverage,
    inventory_source,
)
from workhorse_workflows.okf_builder.main.nodes.prepare import prepare
from workhorse_workflows.okf_builder.shared import paths

SERVICE = "acme"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, stdout=subprocess.DEVNULL)


# --- prepare: the revision as run state -------------------------------------


def test_prepare_writes_the_scope_file_and_carries_it(
    booked: Path,
    write: Callable[[Path, str], Path],
    logger: logging.Logger,
    read_json: Callable[[Path], Any],
) -> None:
    _git(booked, "checkout", "-q", "-b", "feature")
    write(booked / "acme/refunds.py", "def refund(amount):\n    return -amount\n")
    _git(booked, "add", "acme/refunds.py")
    _git(booked, "commit", "-qm", "feat: refunds")

    result = prepare(logger, service=SERVICE, since="main")
    assert result.ostler_ok
    assert result.diff_scope_count == 1
    scope_file = Path(result.diff_scope_path)
    assert scope_file == paths.diff_scope_path(booked, SERVICE)
    data = read_json(scope_file)
    assert data["base"] == "main"
    assert data["paths"] == ["acme/refunds.py"]


def test_a_narrowing_that_finds_nothing_stays_empty(
    booked: Path, logger: logging.Logger, read_json: Callable[[Path], Any]
) -> None:
    """`--since` on the revision the tree is already at is a no-op run, not a full scan.

    The old `diff_base` read this case as "no branch, so measure everything", which is the
    one answer an operator who asked for a narrowing cannot check: a full scan and an empty
    scope produce the same clean verdict for different reasons. An empty scope measures a
    subset of nothing and — because a scoped coverage never writes the committed artifact —
    cannot mistake that for a fresh book.
    """
    result = prepare(logger, service=SERVICE, since="main")
    assert result.ostler_ok
    assert result.diff_scope_count == 0
    assert read_json(Path(result.diff_scope_path))["paths"] == []


def test_prepare_blocks_on_a_narrowing_it_cannot_compute(
    booked: Path, logger: logging.Logger
) -> None:
    result = prepare(logger, service=SERVICE, since="no-such-rev")
    assert not result.ostler_ok
    assert "no-such-rev" in result.prepare_error


def test_a_retired_parameter_warns_and_the_run_goes_on(
    booked: Path, logger: logging.Logger, caplog: Any
) -> None:
    """The retirement contract: declared, unread, and loud — never a crash on reload.

    Deleting the field instead would kill every in-flight run with a bare pydantic
    `extra_forbidden`, so the old story-mode inputs survive one release as parameters that
    do nothing and say so.
    """
    with caplog.at_level(logging.WARNING):
        result = prepare(logger, service=SERVICE, recheck_only=True, diff_base="main")

    assert result.ostler_ok
    assert result.diff_scope_path == ""
    warned = [r.getMessage() for r in caplog.records if "retired" in r.getMessage()]
    assert len(warned) == 2, warned


# --- the scoped inventory ---------------------------------------------------


def _scope_file(repo: Path, paths_list: list[str]) -> Path:
    scope = paths.ensure_build_dir(repo) / "test.diff-scope.json"
    scope.write_text(json.dumps({"base": "main", "paths": paths_list}), encoding="utf-8")
    return scope


def test_scoped_inventory_keeps_only_the_units_the_change_touched(
    booked: Path, write: Callable[[Path, str], Path], logger: logging.Logger
) -> None:
    write(booked / "acme/refunds.py", "def refund(amount):\n    return -amount\n")
    write(booked / "Makefile", "lint:\n\ttrue\n")
    scope = _scope_file(booked, ["acme/refunds.py"])

    out = booked / "inventory.json"
    result = inventory_source(
        logger, str(booked / "acme"), str(out), "", str(booked), str(scope)
    )
    units = json.loads(out.read_text(encoding="utf-8"))["units"]
    assert {u["path"] for u in units} == {"acme/refunds.py"}
    # The Makefile's targets are outside the scope, so the run surface is empty too.
    assert result.operational_unit_count == 0
    assert result.inventory_errors == ""


def test_scoped_inventory_keeps_operational_units_the_change_touched(
    booked: Path, write: Callable[[Path, str], Path], logger: logging.Logger
) -> None:
    write(booked / "Makefile", "lint:\n\ttrue\n")
    scope = _scope_file(booked, ["Makefile"])

    out = booked / "inventory.json"
    inventory_source(logger, str(booked / "acme"), str(out), "", str(booked), str(scope))
    operational = json.loads(out.read_text(encoding="utf-8"))["operational"]
    assert [u["evidence"] for u in operational] == ["Makefile:lint"]


def test_an_unreadable_scope_is_an_error_not_a_full_scan(
    booked: Path, logger: logging.Logger
) -> None:
    result = inventory_source(
        logger,
        str(booked / "acme"),
        str(booked / "inventory.json"),
        "",
        str(booked),
        str(booked / "no-such-scope.json"),
    )
    assert "unreadable diff scope" in result.inventory_errors
    assert result.source_unit_count == 0
    assert result.operational_unit_count == 0


# --- the scoped verdict -----------------------------------------------------


def test_a_scoped_coverage_does_not_overwrite_the_committed_book_artifact(
    booked: Path, logger: logging.Logger
) -> None:
    features = paths.features_root(booked, SERVICE)
    out = booked / "inventory.json"
    inventory_source(logger, str(booked / "acme"), str(out), "", str(booked))

    scoped = compute_coverage(
        logger, str(booked), str(features), SERVICE, str(out), scoped=True
    )
    assert scoped.coverage_complete
    assert scoped.coverage_path == ""
    assert not (features / "coverage.json").exists()

    full = compute_coverage(logger, str(booked), str(features), SERVICE, str(out))
    assert full.coverage_path
    assert (features / "coverage.json").exists()
