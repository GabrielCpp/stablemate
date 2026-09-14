"""Re-exports `workhorse_workflows.qa.support` for coder's existing call sites.

The functions here moved to the family-neutral `workhorse_workflows.qa.support` — a
live-audit lane reads the same NDJSON run log and wants the same routing-note
extraction, so the logic no longer belongs under `coder/shared/`. This module keeps
coder's imports (`from ...qa_support import X` and `from ... import qa_support` then
`qa_support.X(...)`) working unchanged.
"""
from __future__ import annotations

from workhorse_workflows.qa.support import (
    QA_PLAN_FILE,
    QA_RUN_LOG,
    assert_records,
    failed_assertions,
    notes_for,
    parse_source_roots,
    scored_run_log,
)

__all__ = [
    "QA_PLAN_FILE",
    "QA_RUN_LOG",
    "assert_records",
    "failed_assertions",
    "notes_for",
    "parse_source_roots",
    "scored_run_log",
]
