from __future__ import annotations

from ostler.qa.attribution import Cause
from ostler.qa.verdict import Verdict
from workhorse.runner.usage import TurnUsage

from workhorse_workflows.okf_book.main.nodes.progress_ledger import LapCounts
from workhorse_workflows.okf_book.main.nodes.report import BookReport, book_costs, render_report
from workhorse_workflows.okf_book.shared.blockers import Phase
from workhorse_workflows.okf_book.shared.metrics import TurnMetric, turn_metric
from workhorse_workflows.okf_book.shared.scenarios import FailedCheck, RunSummary, ScenarioOutcome


def _report(dollars: float | None) -> BookReport:
    return BookReport(
        services=("tally",),
        orphans=(),
        minutes=12.0,
        dollars=dollars,
        costs=book_costs((TurnMetric(phase=Phase.WRITE, node="write-book", subjects=("tally",), minutes=12.0, dollars=dollars),)),
        blockers=(),
        run=None,
        reading=(),
    )


def test_a_turn_metric_counts_every_token_read_and_generated() -> None:
    usage = TurnUsage(
        input_tokens=10,
        cache_read_input_tokens=100,
        cache_creation_input_tokens=5,
        output_tokens=7,
        reasoning_output_tokens=3,
        total_cost_usd=0.4,
    )

    metric = turn_metric(Phase.WRITE, "write-book", ("tally",), 2.0, usage)

    assert (metric.tokens_read, metric.tokens_generated, metric.dollars) == (115, 10, 0.4)


def test_a_turn_with_no_usage_reports_no_dollars() -> None:
    metric = turn_metric(Phase.WRITE, "write-book", ("tally",), 2.0, TurnUsage())

    assert (metric.tokens_read, metric.tokens_generated, metric.dollars) == (0, 0, None)


def test_a_shared_turn_splits_its_tokens_and_dollars_evenly() -> None:
    shared = TurnMetric(
        phase=Phase.WRITE, node="write-book", subjects=("a", "b"), minutes=4.0, tokens_read=100, tokens_generated=10, dollars=1.0
    )
    own = TurnMetric(phase=Phase.WRITE, node="write-book", subjects=("a",), minutes=1.0, tokens_read=20, dollars=None)

    costs = {c.subject: c for c in book_costs((shared, own))}

    assert (costs["a"].tokens_read, costs["a"].tokens_generated, costs["a"].dollars, costs["a"].turns) == (70, 5, 0.5, 2)
    assert (costs["b"].tokens_read, costs["b"].dollars) == (50, 0.5)


def test_the_report_shows_the_dollars_or_says_none_were_reported() -> None:
    assert "12.0 minutes of writing, $2.73." in render_report(_report(2.73))
    assert "12.0 minutes of writing, dollars not reported." in render_report(_report(None))


def test_the_report_lists_each_gapped_claim_with_the_capability_it_waits_for() -> None:
    claim = "okf:docs/billing.md#charge:does:1"
    check = FailedCheck(label="a charge", covers=(claim,), cause=Cause.ENVIRONMENT, gap="payment provider")
    run = RunSummary(status="failed", verdicts={claim: Verdict.GAPPED},
                     scenarios={"charge": ScenarioOutcome(status="failed", failed_checks=(check,))})

    rendered = render_report(_report(None).model_copy(update={"run": run}))

    assert f"## Gapped claims\n\n- `{claim}`: gapped: payment provider absent\n" in rendered
    assert "## Gapped claims\n\nNone.\n" in render_report(_report(None))


def test_the_report_shows_the_book_s_failed_checks_lap_by_lap() -> None:
    laps = (LapCounts(service="tally", failures={Cause.BOOK: 40, Cause.APP: 2}),
            LapCounts(service="tally", failures={Cause.BOOK: 12, Cause.ARRANGEMENT: 3}, gapped=5))

    rendered = render_report(_report(None).model_copy(update={"laps": laps}))

    assert "- `tally`: the book's failed checks, lap by lap: 40 → 15\n" in rendered
    assert "  - lap 2: book 12, arrangement 3, environment 0, app 0, unattributed 0, gapped 5\n" in rendered
    assert "## Progress per lap\n\nNo lap ran.\n" in render_report(_report(None))
