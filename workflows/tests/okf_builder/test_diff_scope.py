"""The squashed-diff scope: how a backfill narrows itself to what a branch changed.

Three seams, tested at each end. `_diff_scope` is the git read — a branch scopes to its
squashed diff against the base (working tree and untracked included), the base itself is
the whole tree, and an unknown rev is an error rather than a quiet widening. `prepare`
turns that answer into run state — a scope file under the build dir and two `Prepared`
fields — and blocks the run when the scope it was asked for cannot be computed. The
coverage side consumes it: a scoped `inventory_source` keeps only diff-touched units
(operational ones included), an unreadable scope file is an error and an empty
inventory, and a scoped `compute_coverage` refuses to overwrite the committed
whole-book `coverage.json` with a subset measurement.
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
from workhorse_workflows.okf_builder.main.nodes.prepare import _diff_scope, prepare
from workhorse_workflows.okf_builder.shared import paths

SERVICE = "acme"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, stdout=subprocess.DEVNULL)


# --- _diff_scope: the git read ---------------------------------------------


def test_scope_on_a_branch_is_the_squashed_diff_plus_the_working_tree(
    booked: Path, write: Callable[[Path, str], Path]
) -> None:
    _git(booked, "checkout", "-q", "-b", "feature")
    write(booked / "acme/refunds.py", "def refund(amount):\n    return -amount\n")
    _git(booked, "add", "acme/refunds.py")
    _git(booked, "commit", "-qm", "feat: refunds")
    write(booked / "acme/notes.py", "pass\n")  # untracked, uncommitted

    scope, error = _diff_scope(booked, "main")
    assert error == ""
    assert scope == ["acme/notes.py", "acme/refunds.py"]


def test_scope_on_the_base_itself_is_the_whole_tree(booked: Path) -> None:
    scope, error = _diff_scope(booked, "main")
    assert scope is None
    assert error == ""


def test_a_fresh_branch_at_the_base_tip_still_scopes_to_its_diff(booked: Path) -> None:
    """Judged by name, not commit equality: an empty scope, not a full scan."""
    _git(booked, "checkout", "-q", "-b", "feature")
    scope, error = _diff_scope(booked, "main")
    assert error == ""
    assert scope == []


def test_an_unknown_base_is_an_error_never_a_silent_full_scan(booked: Path) -> None:
    scope, error = _diff_scope(booked, "no-such-rev")
    assert scope is None
    assert "no-such-rev" in error


# --- prepare: the scope as run state ---------------------------------------


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

    result = prepare(logger, service=SERVICE, diff_base="main")
    assert result.ostler_ok
    assert result.diff_scope_count == 1
    scope_file = Path(result.diff_scope_path)
    assert scope_file == paths.diff_scope_path(booked, SERVICE)
    data = read_json(scope_file)
    assert data["base"] == "main"
    assert data["paths"] == ["acme/refunds.py"]


def test_prepare_on_the_base_runs_a_full_scan(booked: Path, logger: logging.Logger) -> None:
    result = prepare(logger, service=SERVICE, diff_base="main")
    assert result.ostler_ok
    assert result.diff_scope_path == ""
    assert result.diff_scope_count == 0


def test_prepare_blocks_on_a_scope_it_cannot_compute(
    booked: Path, logger: logging.Logger
) -> None:
    result = prepare(logger, service=SERVICE, diff_base="no-such-rev")
    assert not result.ostler_ok
    assert "no-such-rev" in result.prepare_error


# --- the scoped inventory ---------------------------------------------------


def _scope_file(repo: Path, paths_list: list[str]) -> Path:
    scope = paths.ensure_build_dir(repo) / "test.diff-scope.json"
    scope.write_text(
        json.dumps({"base": "main", "paths": paths_list}), encoding="utf-8"
    )
    return scope


def test_scoped_inventory_keeps_only_diff_touched_units(
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


def test_scoped_inventory_keeps_operational_units_the_diff_touched(
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
