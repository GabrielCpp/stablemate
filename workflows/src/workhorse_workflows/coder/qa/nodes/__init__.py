"""The non-agent work only the `qa` flow calls, grouped by subject.

* `qa` — clear the evidence, bring the stack up, validate the plan, run it
* `evidence` — the gate that fails closed: is the claimed pass backed by checkable proof
* `regression` — which committed journey suites this story touched, and how they ran
* `hygiene` — the two pre-commit gates: stray screenshots, and sentinel IDs

Four modules rather than one `nodes.py`, for the reason `workflows/README.md` gives: one
subject per module, and `evidence` alone is over five hundred lines.

Every node here registers on the same `blueprint` as the rest of the distribution — being
reached by exactly one flow is what puts it beside that flow rather than in
[`shared/`](../../shared). The QA graph's shared middle — the story spine, the review
context, the OKF obligation packet — is in that package instead, and `qa_support`, the
run-log parse two of these modules read, is there for the same reason: the dry-run gate
and the evidence gate both read it.
"""
from __future__ import annotations

from workhorse_workflows.coder.qa.nodes.evidence import verify_qa_evidence
from workhorse_workflows.coder.qa.nodes.hygiene import check_sentinel_ids, flush_root_screenshots
from workhorse_workflows.coder.qa.nodes.qa import (
    QA_SCRATCH_DIRNAME,
    clear_qa_evidence,
    ensure_stack,
    lint_qa_plan,
    qa_tools_catalog,
    run_qa_plan,
    teardown_stack,
    validate_qa_plan,
    verify_qa_dry_run,
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
    "flush_root_screenshots",
    "lint_qa_plan",
    "qa_tools_catalog",
    "run_qa_plan",
    "run_regression_suite",
    "teardown_stack",
    "validate_qa_plan",
    "verify_qa_dry_run",
    "verify_qa_evidence",
]
