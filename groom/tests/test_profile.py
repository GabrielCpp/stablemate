"""Fast, synthetic coverage for groom's retained-run profiler.

No OTel SDK, server, subprocess or clock is involved: each case inserts a handful
of decoded spans into a throwaway SQLite store and checks the resulting partition.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from groom import cli, store


class _DB:
    def __enter__(self) -> _DB:
        self._tmp = tempfile.TemporaryDirectory()
        self._previous = os.environ.get("GROOM_DB")
        os.environ["GROOM_DB"] = str(Path(self._tmp.name) / "groom.db")
        store.reset()
        return self

    def __exit__(self, *exc: object) -> None:
        store.reset()
        if self._previous is None:
            os.environ.pop("GROOM_DB", None)
        else:
            os.environ["GROOM_DB"] = self._previous
        self._tmp.cleanup()


def _span(
    span_id: str,
    name: str,
    start: float,
    end: float,
    *,
    trace: str = "trace-1",
    parent: str = "",
    node: str = "",
    attrs: dict | None = None,
    generation: int | None = 1,
) -> dict:
    return {
        "span_id": span_id,
        "trace_id": trace,
        "parent_id": parent,
        "run_id": "run-1",
        "workflow": "coder",
        "node": node,
        "name": name,
        "start_ts": start,
        "end_ts": end,
        "attrs": attrs or {},
        "resume_generation": generation,
    }


def test_profile_partitions_nested_spans_without_double_counting() -> None:
    """Nested wrappers must not make the profile larger than the wall clock."""
    with _DB():
        store.insert_spans(
            [
                _span("root", "run:coder", 0, 100),
                _span("det", "resolve", 0, 10, parent="root", node="resolve"),
                _span("wrapper", "plan", 10, 40, parent="root", node="plan"),
                _span("turn", "agent_turn", 10, 40, parent="wrapper", node="plan"),
                _span(
                    "infra",
                    "ensure_stack",
                    40,
                    60,
                    parent="root",
                    node="ensure_stack",
                    attrs={"workhorse.span_kind": "infra"},
                ),
                _span(
                    "cap",
                    "wait:cap",
                    45,
                    55,
                    parent="infra",
                    node="ensure_stack",
                    attrs={
                        "workhorse.span_kind": "wait",
                        "workhorse.wait_kind": "cap",
                    },
                ),
                _span(
                    "operator",
                    "wait:operator",
                    60,
                    70,
                    parent="root",
                    node="review",
                    attrs={
                        "workhorse.span_kind": "wait",
                        "workhorse.wait_kind": "operator",
                    },
                ),
            ]
        )

        profile = store.run_profile("run-1")
        assert profile is not None
        assert profile["time_s"] == {
            "wall": 100.0,
            "agent": 30.0,
            "deterministic": 10.0,
            "infra": 10.0,
            "wait": 20.0,
            "waits_by_kind": {"cap": 10.0, "operator": 10.0},
            "resume_gap": 0,
            "unclassified": 30.0,
        }
        time_s = profile["time_s"]
        assert time_s["wall"] == sum(
            time_s[key]
            for key in (
                "agent",
                "deterministic",
                "infra",
                "wait",
                "resume_gap",
                "unclassified",
            )
        )


def test_profile_marks_only_cross_generation_gaps_as_resume_time() -> None:
    with _DB():
        store.insert_spans(
            [
                _span("root-1", "run:coder", 0, 10, trace="trace-1", generation=1),
                _span("root-2", "run:coder", 20, 30, trace="trace-2", generation=2),
            ]
        )
        profile = store.run_profile("run-1")
        assert profile is not None
        assert profile["time_s"]["resume_gap"] == 10.0
        assert profile["time_s"]["unclassified"] == 20.0


def test_profile_counts_turns_cost_attempts_and_verdicts() -> None:
    with _DB():
        store.insert_spans(
            [
                _span(
                    "turn-1",
                    "agent_turn",
                    0,
                    10,
                    parent="visit-1",
                    node="plan-qa",
                    attrs={
                        "work_id": "story-1",
                        "backend": "claude",
                        "qa.plan_rework": "0",
                        "qa.plan_review_disposition": "revise",
                        "total_cost_usd": 2.0,
                        "usage.output_tokens": 100,
                    },
                ),
                _span(
                    "turn-2",
                    "agent_turn",
                    10,
                    20,
                    parent="visit-1",
                    node="plan-qa",
                    attrs={
                        "work_id": "story-1",
                        "backend": "claude",
                        "qa.plan_rework": "0",
                        "qa.plan_review_disposition": "revise",
                        "usage.output_tokens": 50,
                    },
                ),
                _span(
                    "turn-3",
                    "agent_turn",
                    20,
                    30,
                    parent="visit-2",
                    node="plan-qa",
                    attrs={
                        "work_id": "story-2",
                        "backend": "opencode",
                        "qa.plan_rework": "1",
                        "qa.plan_review_disposition": "approved",
                        "total_cost_usd": 0.0,
                        "usage.output_tokens": 25,
                    },
                ),
            ]
        )

        profile = store.run_profile("run-1")
        assert profile is not None
        assert profile["work"] == {
            "turns": 3,
            "visits": 2,
            "backend_retries": 1,
            "work_items": 2,
            "turns_per_work": 1.5,
            "visits_per_work": 1.0,
            "agent_s": 30.0,
            "cost_usd": 2.0,
            "cost_turns": 2,
            "missing_cost_turns": 1,
            "cost_coverage": 2 / 3,
            "zero_cost_output_turns": 1,
            "output_tokens": 175,
            "backends": ["claude", "opencode"],
        }
        attempt_zero = next(
            row for row in profile["attempt_groups"] if row["value"] == "0"
        )
        assert attempt_zero["turns"] == 2
        assert attempt_zero["visits"] == 1
        assert attempt_zero["backend_retries"] == 1
        revised = next(
            row for row in profile["verdict_groups"] if row["value"] == "revise"
        )
        assert revised["turns"] == 2 and revised["visits"] == 1
        assert revised["cost_usd"] == 2.0

        rendered = cli._format_profile(profile)
        assert "visits=2  backend_retries=1  turns=3" in rendered
        assert "visits/work=1.0" in rendered


def test_a_verdict_that_buys_no_agent_turn_is_still_counted_as_a_decision() -> None:
    """The bias the decisions section exists to remove, staged at its smallest.

    Both gates ran twice. `stands` routed to deterministic work and `refuted` routed to
    another agent turn, so the priced groups see one and not the other — read alone they
    say the auditor refutes everything. Counting transitions over every span restores the
    denominator: two of each. This is not hypothetical rounding; on the retained runs
    `qa.audit_verdict=stands` sat on 99 spans and zero turns.
    """
    with _DB():
        store.insert_spans(
            [
                _span("run-1", "workflow_run", 0, 100, attrs={"run_id": "run-1"}),
                # stands -> the backlog drain, which is a `self.call`, so no turn is priced.
                _span("v1", "backlog", 0, 10, parent="run-1", node="file_backlog_items",
                      attrs={"qa.audit_verdict": "stands"}),
                # Cleared between work items, which is what makes the next `stands` a
                # second decision rather than a continuation of the first.
                _span("v2", "plan", 10, 20, parent="run-1", node="plan-qa"),
                _span("v3", "backlog", 20, 30, parent="run-1", node="file_backlog_items",
                      attrs={"qa.audit_verdict": "stands"}),
                _span("v4", "plan", 30, 40, parent="run-1", node="plan-qa"),
                # refuted -> a replan, so it does buy a turn and does get priced.
                _span("v5", "plan", 40, 50, parent="run-1", node="plan-qa",
                      attrs={"qa.audit_verdict": "refuted"}),
                _span("turn-1", "agent_turn", 40, 50, parent="v5", node="plan-qa",
                      attrs={"work_id": "s1", "qa.audit_verdict": "refuted",
                             "total_cost_usd": 2.0}),
                _span("v6", "plan", 50, 60, parent="run-1", node="plan-qa"),
                _span("v7", "plan", 60, 70, parent="run-1", node="plan-qa",
                      attrs={"qa.audit_verdict": "refuted"}),
                _span("turn-2", "agent_turn", 60, 70, parent="v7", node="plan-qa",
                      attrs={"work_id": "s2", "qa.audit_verdict": "refuted",
                             "total_cost_usd": 2.0}),
            ]
        )

        profile = store.run_profile("run-1")
        assert profile is not None
        priced = {row["value"] for row in profile["verdict_groups"]}
        assert priced == {"refuted"}, priced

        decisions = {
            row["value"]: row["decisions"]
            for row in profile["verdict_decisions"]
            if row["dimension"] == "qa.audit_verdict"
        }
        assert decisions == {"stands": 2, "refuted": 2}, decisions

        rendered = cli._format_profile(profile)
        assert "qa.audit_verdict=stands  decisions=2  (50%)" in rendered


def test_a_verdict_held_across_several_spans_is_one_decision_not_several() -> None:
    """A label rides every span opened after the state that set it — those are not votes."""
    with _DB():
        store.insert_spans(
            [
                _span("run-1", "workflow_run", 0, 40, attrs={"run_id": "run-1"}),
                *[
                    _span(f"s{i}", "stack", i, i + 1, parent="run-1", node="ensure_stack",
                          attrs={"qa.plan_review_disposition": "approved"})
                    for i in range(6)
                ],
            ]
        )

        profile = store.run_profile("run-1")
        assert profile is not None
        assert profile["verdict_decisions"] == [
            {"dimension": "qa.plan_review_disposition", "value": "approved", "decisions": 1}
        ], profile["verdict_decisions"]


def test_the_docs_loop_labels_land_in_the_buckets_they_were_named_for() -> None:
    """The docs subflow's progress labels need no groom change — this is the proof.

    `workhorse_workflows` picked those names to match the two classifiers here: a
    `_verdict` suffix for the productivity verdict, a canonical non-negative integer for
    the outstanding count. Nothing on either side imports the other, so if
    `_VERDICT_SUFFIXES` is ever narrowed or the attempt predicate tightened, this is where
    it surfaces rather than as a silently empty section of a report.
    """
    with _DB():
        store.insert_spans(
            [
                _span("run-1", "workflow_run", 0, 40, attrs={"run_id": "run-1"}),
                _span("visit-1", "workflow_state", 0, 20, parent="run-1", node="document"),
                _span(
                    "turn-1",
                    "agent_turn",
                    0,
                    60,
                    parent="visit-1",
                    node="document",
                    attrs={
                        "work_id": "story-1",
                        "docs.gate_progress_verdict": "stalled",
                        "docs.review_findings": "2",
                        "total_cost_usd": 3.5,
                    },
                ),
            ]
        )

        profile = store.run_profile("run-1")
        assert profile is not None
        verdict = next(
            row
            for row in profile["verdict_groups"]
            if row["dimension"] == "docs.gate_progress_verdict"
        )
        assert verdict["value"] == "stalled" and verdict["turns"] == 1
        outstanding = next(
            row
            for row in profile["attempt_groups"]
            if row["dimension"] == "docs.review_findings"
        )
        assert outstanding["value"] == "2" and outstanding["turns"] == 1

        rendered = cli._format_profile(profile)
        assert "docs.gate_progress_verdict=stalled  document" in rendered
        assert "docs.review_findings=2  document" in rendered
        assert "agent=1.0m  cost=$3.50" in rendered


def test_profile_does_not_collapse_unparented_legacy_turns_into_one_visit() -> None:
    with _DB():
        store.insert_spans(
            [
                _span("legacy-turn-1", "agent_turn", 0, 1, node="plan"),
                _span("legacy-turn-2", "agent_turn", 1, 2, node="plan"),
            ]
        )

        profile = store.run_profile("run-1")
        assert profile is not None
        assert profile["work"]["visits"] == 2
        assert profile["work"]["backend_retries"] == 0


def test_profile_cli_emits_the_complete_json_object(capsys) -> None:
    with _DB():
        store.insert_spans([_span("root", "run:coder", 0, 1)])
        cli.profile("run-1", as_json=True)
        payload = json.loads(capsys.readouterr().out)
        assert payload["run_id"] == "run-1"
        assert payload["time_s"]["wall"] == 1.0


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
