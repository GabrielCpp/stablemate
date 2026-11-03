from __future__ import annotations

from typing import Any

from groom import churn

TURN_SPAN = "agent_turn"


def gate_check_failed(span: dict[str, Any]) -> bool:
    attrs = span["attrs"]
    return "workhorse.out.gate" in attrs and attrs.get("workhorse.out.status") == "dirty"


def _failed_spans(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Spans that finished in error with no failing span beneath them, so one failure counts once, and dirty gate checks."""
    failing = [span for span in spans if span["status"] == "ERROR" and not span["name"].startswith("run:")]
    parents = {span["parent_id"] for span in failing if span["parent_id"]}
    broken = {span["span_id"] for span in failing if span["span_id"] not in parents}
    return [span for span in spans if span["span_id"] in broken or gate_check_failed(span)]


def _retry_turns(spans: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Each agent turn after the first of its visit, with the attempt it follows."""
    visits: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for span in spans:
        if span["name"] == TURN_SPAN:
            visits.setdefault((span["trace_id"], span["parent_id"] or span["span_id"]), []).append(span)
    found = []
    for attempts in visits.values():
        ordered = sorted(attempts, key=lambda span: (float(span["start_ts"]), span["span_id"]))
        found.extend((later, earlier) for earlier, later in zip(ordered, ordered[1:], strict=False))
    return found


def found(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every problem of a run, once each: failed steps, failed gate checks, backend retries and churn alerts. The attention tile counts these and the Activity timeline lists them."""
    items: list[dict[str, Any]] = []
    for span in _failed_spans(spans):
        items.append({"kind": "failed", "span": span, "check": gate_check_failed(span)})
    for later, earlier in _retry_turns(spans):
        items.append({"kind": "retry", "span": later, "after": earlier})
    for span, count in churn.alerts(spans):
        items.append({"kind": "churn", "span": span, "count": count})
    return items


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


def standing(spans: list[dict[str, Any]]) -> dict[str, Any]:
    """The attention tile: gates, time waiting, and the one problem count.

    Problems are failed steps, backend retries, failed gate checks and churn alerts. An answered gate is not one.
    """
    items = found(spans)
    checks = sum(1 for item in items if item["kind"] == "failed" and item["check"])
    failed = sum(1 for item in items if item["kind"] == "failed") - checks
    retries = sum(1 for item in items if item["kind"] == "retry")
    churned = sum(1 for item in items if item["kind"] == "churn")
    gates = operator_gates(spans)
    return {
        "gates": gates["count"],
        "gate_wait_s": gates["wait_s"],
        "failed_steps": failed,
        "retries": retries,
        "failed_gate_checks": checks,
        "churn_alerts": churned,
        "problems": len(items),
    }
