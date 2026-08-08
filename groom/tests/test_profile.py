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
                    node="plan-qa",
                    attrs={
                        "work_id": "story-1",
                        "backend": "claude",
                        "qa.plan_rework": "1",
                        "qa.plan_review_disposition": "approved",
                        "usage.output_tokens": 50,
                    },
                ),
                _span(
                    "turn-3",
                    "agent_turn",
                    20,
                    30,
                    node="plan-qa",
                    attrs={
                        "work_id": "story-2",
                        "backend": "opencode",
                        "qa.plan_rework": "1",
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
            "work_items": 2,
            "turns_per_work": 1.5,
            "agent_s": 30.0,
            "cost_usd": 2.0,
            "cost_turns": 2,
            "missing_cost_turns": 1,
            "cost_coverage": 2 / 3,
            "zero_cost_output_turns": 1,
            "output_tokens": 175,
            "backends": ["claude", "opencode"],
        }
        attempt_one = next(
            row for row in profile["attempt_groups"] if row["value"] == "1"
        )
        assert attempt_one["turns"] == 2 and attempt_one["work_items"] == 2
        revised = next(
            row for row in profile["verdict_groups"] if row["value"] == "revise"
        )
        assert revised["turns"] == 1 and revised["cost_usd"] == 2.0


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
