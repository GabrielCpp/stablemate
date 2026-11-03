from __future__ import annotations

from typing import Any

from groom import churn, projection, store
from groom.activity import _name

PAGE = 200
ALERT, SPAN, EVENT, LOG, METRIC = 5, 4, 3, 2, 1
KINDS = {ALERT: "ALERT", SPAN: "SPAN", EVENT: "EVENT", METRIC: "METRIC"}
LOG_LEVELS = {"WARNING": "WARN"}


class BadCursor(ValueError):
    pass


def parse(cursor: str) -> tuple[float, int, int] | None:
    if not cursor:
        return None
    try:
        when, rank, ident = cursor.split("|")
        return float(when), int(rank), int(ident)
    except ValueError as exc:
        raise BadCursor(cursor) from exc


def _cursor(record: dict[str, Any]) -> str:
    return f"{record['ts']!r}|{record['rank']}|{record['id']}"


def _record(rank: int, ident: int, ts: float, kind: str, node: str, text: str, tone: str = "") -> dict[str, Any]:
    return {"rank": rank, "id": ident, "ts": ts, "time": projection.fmt_ts(ts), "kind": kind, "node": node, "text": text, "tone": tone}


def _span_text(span: dict[str, Any]) -> tuple[str, str]:
    took = projection.fmt_duration(float(span["end_ts"]) - float(span["start_ts"]))
    named = "" if span["name"] == _name(span) else f"{span['name']} "
    if str(span["status"]).upper() == "ERROR":
        return f"{named}failed, {took}", "bad"
    cost = span.get("profile_cost_usd")
    return f"{named}ended, {took}" + (f", ${float(cost):.2f}" if cost is not None else ""), ""


def _event_text(event: dict[str, Any]) -> str:
    given = event.get("attrs") or {}
    return ", ".join([str(event.get("name") or "event"), *(f"{key} {value}" for key, value in given.items())])


def _derived(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for span in spans:
        text, tone = _span_text(span)
        found.append(_record(SPAN, span["row_id"], float(span["end_ts"]), "SPAN", _name(span), text, tone))
        for number, event in enumerate(span["attrs"].get("events") or []):
            if isinstance(event, dict) and event.get("ts"):
                found.append(_record(EVENT, span["row_id"] * 1000 + number, float(event["ts"]), "EVENT", _name(span), _event_text(event)))
    for span, count in churn.alerts(spans):
        found.append(_record(ALERT, span["row_id"], float(span["end_ts"]), "ALERT", _name(span), f"CHURN: repeated {count} times with the same labels", "bad"))
    return found


def _log_record(row: dict[str, Any]) -> dict[str, Any]:
    severity = str(row["severity"])
    tone = "bad" if severity in ("ERROR", "FATAL") else "warn" if severity == "WARNING" else ""
    return _record(LOG, row["id"], float(row["ts"]), LOG_LEVELS.get(severity, severity), str(row["node"]), str(row["body"]), tone)


def page(run_id: str, before: str = "", limit: int = PAGE, metrics: bool = False) -> dict[str, Any]:
    """One page of a run's stored records newest first: spans by end time, logs, span events and churn alerts, and metric samples when asked."""
    cursor = parse(before)
    limit = max(1, min(int(limit), PAGE))
    spans = store.run_turn_spans(run_id)
    derived = _derived(spans)
    mine = [one for one in derived if cursor is None or (one["ts"], one["rank"], one["id"]) < cursor]
    pool = mine + [_log_record(row) for row in store.run_log_rows(run_id, limit + 1, cursor, LOG, True)]
    if metrics:
        for row in store.detail_metrics(run_id, limit + 1, cursor, METRIC):
            node = str((row.get("attrs") or {}).get("node") or "")
            pool.append(_record(METRIC, row["id"], float(row["ts"]), "METRIC", node, projection.metric_text(row)))
    pool.sort(key=lambda one: (one["ts"], one["rank"], one["id"]), reverse=True)
    shown = pool[:limit]
    more = len(pool) > limit
    samples = store.count_metrics(run_id)
    total = len(derived) + store.count_logs(run_id, True) + (samples if metrics else 0)
    return {
        "run_id": run_id,
        "records": [{key: value for key, value in one.items() if key not in ("rank",)} | {"key": f"{one['kind']}:{one['id']}"} for one in shown],
        "total": total,
        "metric_samples": samples,
        "metrics": metrics,
        "next": _cursor(shown[-1]) if more and shown else "",
    }
