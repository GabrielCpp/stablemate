"""The evidence gate's obligation check — `_obligation_problems`.

An OKF packet holds more than the story built. The graph closure walks from a changed file
out to whatever the book links it to, and lands on endpoints nobody has written yet and
screens with no `code:` behind them. The context builder marks those `"required": false`,
and the plan validator refuses a plan that writes scenarios for them.

This gate read the flag the other way round: it demanded a passing verdict for every member
of the packet. The two rules together are unsatisfiable — the planner is told to leave the
context-only ids out of `covers`, then the evidence gate fails the pass for the verdicts
that omission did not produce, and the flow routes back to planning to do it again. What is
pinned here is that the two gates read the same flag, and that a packet without the flag is
still held to the strict reading.
"""
from __future__ import annotations

from workhorse_workflows.coder.qa.nodes import evidence

#: A verdict shaped the way a runner writes one for an obligation it actually proved.
PROVED = {"verdict": "pass", "log_refs": ["qa/qa-run.ndjson#3"]}


def _context(*obligations: dict) -> dict:
    return {"obligations": list(obligations)}


def test_a_context_only_obligation_is_owed_no_verdict() -> None:
    context = _context(
        {"id": "okf:docs/features/docs-api/http/docs-api.md#get-pages:does:1", "required": False},
        {"id": "okf:docs/features/docs-api/http/docs-api.md#publish:does:1", "required": True},
    )
    data = {"obligations": [{"id": "okf:docs/features/docs-api/http/docs-api.md#publish:does:1", **PROVED}]}

    assert evidence._obligation_problems(context, data) == []


def test_a_required_obligation_still_needs_a_verdict() -> None:
    context = _context({"id": "okf:docs/features/docs-api/http/docs-api.md#publish:does:1"})

    problems = evidence._obligation_problems(context, {"obligations": []})

    assert problems == [
        "okf:docs/features/docs-api/http/docs-api.md#publish:does:1: "
        "required OKF obligation has no evidence verdict."
    ]


def test_an_unflagged_obligation_is_required() -> None:
    """A packet written before the flag existed says nothing about which members are real."""
    context = _context({"id": "okf:docs/features/docs-api/manifest.md:contract"})

    problems = evidence._obligation_problems(context, {"obligations": []})

    assert len(problems) == 1


def test_a_required_obligation_needs_executed_logs_behind_its_pass() -> None:
    context = _context({"id": "okf:docs/features/docs-api/manifest.md:contract", "required": True})
    data = {"obligations": [{"id": "okf:docs/features/docs-api/manifest.md:contract", "verdict": "pass"}]}

    problems = evidence._obligation_problems(context, data)

    assert problems == [
        "okf:docs/features/docs-api/manifest.md:contract: "
        "required OKF obligation has no executed log_refs."
    ]


def test_a_context_only_obligation_that_failed_is_not_a_problem() -> None:
    """Evidence for a context-only id is welcome; it is simply not held against the pass."""
    context = _context({"id": "okf:docs/features/docs-app/gui/screens/app-shell.md:contract", "required": False})
    data = {
        "obligations": [
            {"id": "okf:docs/features/docs-app/gui/screens/app-shell.md:contract", "verdict": "fail"}
        ]
    }

    assert evidence._obligation_problems(context, data) == []
