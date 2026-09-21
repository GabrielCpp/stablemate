"""`--since`: retired with the digest-scope build (okf-digest-scoped-build §2)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from workhorse_workflows.okf_builder.main.nodes.prepare import prepare

SERVICE = "acme"


def test_a_retired_parameter_warns_and_the_run_goes_on(
    booked: Path, logger: logging.Logger, caplog: Any
) -> None:
    """The retirement contract: declared, unread, and loud — never a crash on reload."""
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