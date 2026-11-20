"""The non-agent work only the `qa` flow calls, grouped by subject."""
from __future__ import annotations

from workhorse_workflows.coder.qa.nodes.evidence import verify_qa_evidence
from workhorse_workflows.coder.qa.nodes.hygiene import check_sentinel_ids, flush_root_screenshots
from workhorse_workflows.coder.qa.nodes.qa import (
    QA_SCRATCH_DIRNAME,
    clear_qa_evidence,
    ensure_stack,
    hold_copy,
    lint_qa_plan,
    release_copy,
    run_qa_plan,
    stack_target,
    teardown_stack,
)
from workhorse_workflows.coder.qa.nodes.regression import (
    detect_regression_suites,
    run_regression_suite,
)

__all__ = [
    "QA_SCRATCH_DIRNAME",
    "check_sentinel_ids",
    "clear_qa_evidence",
    "detect_regression_suites",
    "ensure_stack",
    "hold_copy",
    "flush_root_screenshots",
    "lint_qa_plan",
    "release_copy",
    "run_qa_plan",
    "run_regression_suite",
    "stack_target",
    "teardown_stack",
    "verify_qa_evidence",
]
