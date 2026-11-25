from __future__ import annotations

import functools
import logging
from collections import Counter, defaultdict
from typing import Any

logger = logging.getLogger(__name__)


_VERDICT_SUFFIXES = ("_verdict", "_disposition", "_failure_class", "_refutation_class")


_WORKHORSE_READ = frozenset(
    {
        "workhorse.cut",
        "workhorse.depth",
        "workhorse.flow",
        "workhorse.gate_path",
        "workhorse.gate_question",
        "workhorse.node",
        "workhorse.out.gate",
        "workhorse.out.reason",
        "workhorse.out.status",
        "workhorse.span_kind",
        "workhorse.state",
        "workhorse.terminal",
        "workhorse.visit.slug",
        "workhorse.wait_kind",
        "workhorse.wait_outcome",
    }
)


@functools.lru_cache(maxsize=4096)
def _kept_attr(key: str) -> bool:
    """Whether a run span read keeps attribute ``key``."""
    return (
        not key.startswith("workhorse.")
        or key in _WORKHORSE_READ
        or key.endswith(_VERDICT_SUFFIXES)
    )


def _profile_turn_summary(turns: list[dict[str, Any]]) -> dict[str, Any]:
    work_items = {
        str(value)
        for turn in turns
        if (value := turn["attrs"].get("work_id") or turn["attrs"].get("wf.work_id"))
    }
    visits = len(
        {(turn["trace_id"], turn["parent_id"] or turn["span_id"]) for turn in turns}
    )
    costs = [
        float(turn["profile_cost_usd"])
        for turn in turns
        if turn["profile_cost_usd"] is not None
    ]
    zeroed = sum(
        turn["profile_cost_usd"] == 0 and (turn["profile_output_tokens"] or 0) > 0
        for turn in turns
    )
    seconds = sum(max(0.0, turn["end_ts"] - turn["start_ts"]) for turn in turns)
    return {
        "turns": len(turns),
        "visits": visits,
        "backend_retries": len(turns) - visits,
        "work_items": len(work_items),
        "turns_per_work": len(turns) / len(work_items) if work_items else None,
        "visits_per_work": visits / len(work_items) if work_items else None,
        "agent_s": seconds,
        "cost_usd": sum(costs) if costs else None,
        "cost_turns": len(costs),
        "missing_cost_turns": len(turns) - len(costs),
        "cost_coverage": len(costs) / len(turns) if turns else None,
        "zero_cost_output_turns": zeroed,
        "output_tokens": sum(turn["profile_output_tokens"] or 0 for turn in turns),
        "backends": sorted(
            {
                str(turn["attrs"].get("backend"))
                for turn in turns
                if turn["attrs"].get("backend")
            }
        ),
    }


def _profile_groups(
    turns: list[dict[str, Any]], *, verdicts: bool
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for turn in turns:
        for dimension, raw in turn["attrs"].items():
            if not isinstance(raw, str) or not raw:
                continue
            is_verdict = dimension.endswith(_VERDICT_SUFFIXES)
            is_attempt = (
                "." in dimension
                and raw.isdigit()
                and str(int(raw)) == raw
                and not dimension.startswith("workhorse.")
            )
            if (verdicts and is_verdict) or (not verdicts and is_attempt):
                grouped[(dimension, raw, turn["node"])].append(turn)

    rows = []
    for (dimension, value, node), members in grouped.items():
        rows.append(
            {
                "dimension": dimension,
                "value": value,
                "node": node,
                **_profile_turn_summary(members),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["dimension"],
            int(row["value"]) if not verdicts else row["value"],
            row["node"],
        ),
    )


def _profile_verdict_decisions(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """How many times each gate actually reached each verdict, cost aside."""
    current: dict[tuple[str, str], str] = {}
    counts: Counter[tuple[str, str]] = Counter()
    for span in spans:
        trace = span["trace_id"]
        present = {
            dimension: raw
            for dimension, raw in span["attrs"].items()
            if isinstance(raw, str) and raw and dimension.endswith(_VERDICT_SUFFIXES)
        }
        for dimension, raw in present.items():
            if current.get((trace, dimension)) != raw:
                counts[(dimension, raw)] += 1
                current[(trace, dimension)] = raw
        for key in [
            key for key in current if key[0] == trace and key[1] not in present
        ]:
            del current[key]
    return [
        {"dimension": dimension, "value": value, "decisions": count}
        for (dimension, value), count in sorted(counts.items())
    ]


def _span_category(span: dict[str, Any], parent_keys: set[tuple[str, str]]) -> str:
    attrs = span["attrs"]
    kind = str(attrs.get("workhorse.span_kind") or "")
    if kind == "wait":
        return f"wait:{attrs.get('workhorse.wait_kind') or 'unknown'}"
    if span["name"] == "agent_turn":
        return "agent"
    if kind == "infra":
        return "infra"
    has_child = (span["trace_id"], span["span_id"]) in parent_keys
    if not has_child and not kind and not span["name"].startswith("run:"):
        return "deterministic"
    return ""


def _resume_intervals(spans: list[dict[str, Any]]) -> list[tuple[float, float]]:
    sessions: dict[str, dict[str, Any]] = {}
    for span in spans:
        trace = span["trace_id"]
        session = sessions.setdefault(
            trace,
            {"start": span["start_ts"], "end": span["end_ts"], "generation": None},
        )
        session["start"] = min(session["start"], span["start_ts"])
        session["end"] = max(session["end"], span["end_ts"])
        generation = span.get("resume_generation")
        if isinstance(generation, int) and generation > 0:
            session["generation"] = generation

    ordered = sorted(sessions.values(), key=lambda session: session["start"])
    gaps = []
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if (
            current["start"] > previous["end"]
            and previous["generation"] is not None
            and current["generation"] is not None
            and previous["generation"] != current["generation"]
        ):
            gaps.append((previous["end"], current["start"]))
    return gaps


def _profile_time_partition(
    spans: list[dict[str, Any]], start_ts: float, end_ts: float
) -> dict[str, Any]:
    events: dict[float, list[tuple[str, int]]] = defaultdict(list)
    parent_keys = {
        (span["trace_id"], span["parent_id"]) for span in spans if span["parent_id"]
    }
    for span in spans:
        category = _span_category(span, parent_keys)
        if category and span["end_ts"] > span["start_ts"]:
            events[span["start_ts"]].append((category, 1))
            events[span["end_ts"]].append((category, -1))
    for gap_start, gap_end in _resume_intervals(spans):
        events[gap_start].append(("resume_gap", 1))
        events[gap_end].append(("resume_gap", -1))

    points = sorted({start_ts, end_ts, *events})
    active: Counter[str] = Counter()
    totals: defaultdict[str, float] = defaultdict(float)
    waits: defaultdict[str, float] = defaultdict(float)
    for left, right in zip(points, points[1:], strict=False):
        for category, delta in events.get(left, []):
            active[category] += delta
        duration = max(0.0, right - left)
        wait_kinds = sorted(
            category.removeprefix("wait:")
            for category, count in active.items()
            if category.startswith("wait:") and count > 0
        )
        if active["resume_gap"] > 0:
            totals["resume_gap"] += duration
        elif wait_kinds:
            kind = wait_kinds[0] if len(wait_kinds) == 1 else "overlap"
            totals["wait"] += duration
            waits[kind] += duration
        elif active["agent"] > 0:
            totals["agent"] += duration
        elif active["infra"] > 0:
            totals["infra"] += duration
        elif active["deterministic"] > 0:
            totals["deterministic"] += duration
        else:
            totals["unclassified"] += duration

    wall = max(0.0, end_ts - start_ts)
    return {
        "wall": wall,
        "agent": totals["agent"],
        "deterministic": totals["deterministic"],
        "infra": totals["infra"],
        "wait": totals["wait"],
        "waits_by_kind": dict(sorted(waits.items())),
        "resume_gap": totals["resume_gap"],
        "unclassified": totals["unclassified"],
    }
