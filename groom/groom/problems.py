from __future__ import annotations

from typing import Any

from groom import churn


def _gate_check_failed(span: dict[str, Any]) -> bool:
    attrs = span["attrs"]
    return "workhorse.out.gate" in attrs and attrs.get("workhorse.out.status") == "dirty"


def failed_steps(spans: list[dict[str, Any]]) -> int:
    """Ended spans that finished in error with no failing span beneath them, so one failure counts once."""
    failing = [span for span in spans if span["status"] == "ERROR" and not span["name"].startswith("run:")]
    parents = {span["parent_id"] for span in failing if span["parent_id"]}
    return sum(1 for span in failing if span["span_id"] not in parents)


def operator_gates(spans: list[dict[str, Any]]) -> dict[str, Any]:
    """The operator gates a run opened and answered, and the time they held it."""
    waits = [
        span
        for span in spans
        if span["attrs"].get("workhorse.span_kind") == "wait"
        and span["attrs"].get("workhorse.wait_kind") == "operator"
    ]
    return {
        "count": len(waits),
        "wait_s": sum(max(0.0, span["end_ts"] - span["start_ts"]) for span in waits),
    }


def sessions(spans: list[dict[str, Any]]) -> int:
    """How many times the run was started or resumed: its distinct resume generations, and one when it never reported any."""
    generations = {span["resume_generation"] for span in spans if isinstance(span.get("resume_generation"), int)}
    return len(generations) if generations else (1 if spans else 0)


def standing(spans: list[dict[str, Any]], retries: int) -> dict[str, Any]:
    """The attention tile: gates, time waiting, and the one problem count.

    Problems are failed steps, backend retries, failed gate checks and churn alerts. An answered gate is not one.
    """
    failed = failed_steps(spans)
    checks = sum(1 for span in spans if _gate_check_failed(span))
    churned = churn.count_alerts(spans)
    gates = operator_gates(spans)
    return {
        "gates": gates["count"],
        "gate_wait_s": gates["wait_s"],
        "failed_steps": failed,
        "retries": retries,
        "failed_gate_checks": checks,
        "churn_alerts": churned,
        "problems": failed + retries + checks + churned,
    }
