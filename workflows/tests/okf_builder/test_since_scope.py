"""`--since`: retired with the digest-scope build (okf-digest-scoped-build §2).

The scope file, the narrowed inventory, and the `scoped=` flag on `compute_coverage` were
all part of one mechanism: a run told which files had changed since a revision, and the
coverage join measured only those. The digest skip in `sources.json` carries a rebase
for free, and a teammate who never runs stablemate cannot narrow against a diff that does
not exist for them. The diff-scope machinery is retired, and the four things this file
used to assert are reduced to one — that a retired input is still declared and unread.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from workhorse_workflows.okf_builder.main.nodes.prepare import prepare

SERVICE = "acme"


def test_a_retired_parameter_warns_and_the_run_goes_on(
    booked: Path, logger: logging.Logger, caplog: Any
) -> None:
    """The retirement contract: declared, unread, and loud — never a crash on reload.

    Deleting the field instead would kill every in-flight run with a bare pydantic
    `extra_forbidden`, so the old story-mode inputs survive one release as parameters that
    do nothing and say so.
    """
    with caplog.at_level(logging.WARNING):
        result = prepare(
            logger, service=SERVICE,
            since="main", recheck_only=True, diff_base="main",
        )

    assert result.ostler_ok
    assert result.diff_scope_path == ""
    assert result.diff_scope_count == 0
    warned = [r.getMessage() for r in caplog.records if "retired" in r.getMessage()]
    assert len(warned) == 3, warned