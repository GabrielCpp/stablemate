"""A run's agent turns as the Activity tab lists them and reads them."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from workhorse.turnkey import VisitKey

from groom import churn, flows, localfs, overview, problems, store, transcript_parse, turns
from groom.projection import TURN_SPAN, transcript_entry

LiveRows = dict[str, list[dict[str, Any]]]

WINDOW_SLACK_S = 5.0

RESULT_CHARS = 140

UNMATCHED_PREFIX = "unmatched-"

VISIT_MARK = "~"

READ_ROLES = ("assistant", "plan")


class TurnNotFound(LookupError):
    """The run has no turn under this slug."""


class TurnUnreadable(RuntimeError):
    """The turn exists, and its transcript could not be read."""


def _visit(slug: str) -> str:
    if slug.startswith(UNMATCHED_PREFIX):
        return ""
    return "-".join(slug.split("-", 2)[:2])


def _slug_of(row: dict[str, Any]) -> str:
    if row.get("generation") == turns.LEGACY_GENERATION:
        return f"{turns.LEGACY_PREFIX}-{int(row['seq']):05d}-{row['node']}"
    return VisitKey(int(row["generation"]), int(row["seq"]), str(row["node"])).slug


def _base(key: str) -> str:
    """The visit slug a row key stands for: the key itself for a first visit, the part before the mark for a later one."""
    return key.partition(VISIT_MARK)[0]


def _record_directory(archived: list[dict[str, Any]], row: dict[str, Any], strict: bool) -> Path | None:
    """The archived record directory of one row. A slug that several visits share only matches the record of this visit's session, or when it names no session the record stamped inside this visit's window."""
    base = _base(row["slug"])
    mine = [one for one in archived if _slug_of(one) == base and turns.record_path(one).is_dir()]
    session_id = row["session_id"]
    if strict:
        if session_id:
            mine = [one for one in mine if one["session_id"] == session_id]
        else:
            low, high = row["started_ts"] - WINDOW_SLACK_S, row["ended_ts"] + WINDOW_SLACK_S
            mine = [one for one in mine if low <= float(one["ts"]) <= high]
    ordered = sorted(mine, key=lambda one: (one["session_id"] == session_id, one["ts"]))
    return turns.record_path(ordered[-1]) if ordered else None


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:RESULT_CHARS]
    return ""


def _span_slug(span: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    """The visit slug a span belongs to: the one it names, else the one archived turn row that fits it, else none."""
    named = str(span["attrs"].get("workhorse.visit.slug") or "")
    if named:
        return named
    node = str(span["node"] or span["attrs"].get("workhorse.node") or "")
    session = str(span["attrs"].get("session.id") or "")
    low, high = float(span["start_ts"]) - WINDOW_SLACK_S, float(span["end_ts"]) + WINDOW_SLACK_S
    fits = {
        _slug_of(row)
        for row in candidates
        if row["node"] == node
        and (not session or row["session_id"] == session)
        and low <= float(row["ts"]) <= high
    }
    return fits.pop() if len(fits) == 1 else ""


def _attempts(spans: list[dict[str, Any]], archived: list[dict[str, Any]] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Each agent turn span grouped by visit. A span no archived row matches stands alone under ``unmatched-<span id>``. Spans of one slug that sit under one parent are retries of one visit. A slug a resumed pass repeats gives one visit per parent: the first keeps the slug as its key and each later one adds the mark and the millisecond its own turns began."""
    candidates = archived or []
    found: dict[str, dict[tuple[str, str], list[dict[str, Any]]]] = {}
    for span in spans:
        if span["name"] != TURN_SPAN:
            continue
        slug = _span_slug(span, candidates) or f"{UNMATCHED_PREFIX}{span['span_id']}"
        found.setdefault(slug, {}).setdefault((span["trace_id"], span["parent_id"] or span["span_id"]), []).append(span)
    visits: dict[str, list[dict[str, Any]]] = {}
    for slug, groups in found.items():
        ordered = sorted(groups.values(), key=lambda one: min(float(span["start_ts"]) for span in one))
        for number, group in enumerate(ordered):
            first = min(float(span["start_ts"]) for span in group)
            visits[slug if number == 0 else f"{slug}{VISIT_MARK}{round(first * 1000)}"] = group
    return visits


def _repeated(attempts: dict[str, list[dict[str, Any]]]) -> set[str]:
    return {_base(key) for key in attempts if VISIT_MARK in key}


RESULT_KEYS = ("summary", "notes")


def _recorded_result(directory: Path | None) -> str:
    if directory is None:
        return ""
    try:
        loaded = json.loads((directory / "output.json").read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return ""
    if not isinstance(loaded, dict):
        return ""
    for key in RESULT_KEYS:
        value = loaded.get(key)
        if isinstance(value, str) and _first_line(value):
            return _first_line(value)
    return ""


def _finished_row(
    slug: str,
    attempts: list[dict[str, Any]],
    passes: dict[str, tuple[str, int, bool]],
) -> dict[str, Any]:
    ordered = sorted(attempts, key=lambda span: float(span["start_ts"]))
    last = max(ordered, key=lambda span: float(span["end_ts"]))
    attrs = last["attrs"]
    costs = [float(span["profile_cost_usd"]) for span in ordered if span["profile_cost_usd"] is not None]
    flow, number, _ = passes.get(ordered[0]["span_id"], ("", 0, False))
    return {
        "slug": slug,
        "node": str(last["node"] or attrs.get("workhorse.node") or ""),
        "visit": _visit(_base(slug)),
        "work_id": str(attrs.get("work_id") or attrs.get("wf.work_id") or ""),
        "flow": flow,
        "pass": number,
        "model": str(attrs.get("model") or ""),
        "started_ts": float(ordered[0]["start_ts"]),
        "ended_ts": float(last["end_ts"]),
        "duration_s": sum(flows.span_seconds(span) for span in ordered),
        "cost_usd": sum(costs) if costs else None,
        "output_tokens": sum(int(span["profile_output_tokens"] or 0) for span in ordered),
        "cache_read_tokens": sum(int(span["profile_cache_read_tokens"] or 0) for span in ordered),
        "status": "failed" if last["status"] == "ERROR" else "done",
        "result": _first_line(str(attrs.get("activity") or "")),
        "session_id": str(attrs.get("session.id") or ""),
        "matched": not slug.startswith(UNMATCHED_PREFIX),
    }


def _result_of(rows: list[dict[str, Any]]) -> str:
    for row in reversed(rows):
        update = row["update"]
        if update.get("sessionUpdate") == "agent_message_chunk":
            entry = transcript_entry(update)
            if _first_line(entry["text"]):
                return _first_line(entry["text"])
    return ""


def _running_row(slug: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: float(row["ts"]))
    return {
        "slug": slug,
        "node": str(ordered[0].get("node") or slug.split("-", 2)[-1]),
        "visit": _visit(slug),
        "work_id": "",
        "flow": "",
        "pass": 0,
        "model": "",
        "started_ts": float(ordered[0]["ts"]),
        "ended_ts": None,
        "duration_s": None,
        "cost_usd": None,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "status": "running",
        "result": _result_of(ordered),
        "session_id": "",
        "matched": True,
    }


def _name(span: dict[str, Any]) -> str:
    return str(span["node"] or span["attrs"].get("workhorse.node") or span["name"])


def _work_id(span: dict[str, Any]) -> str:
    return str(span["attrs"].get("work_id") or span["attrs"].get("wf.work_id") or "")


def _plain(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip().lstrip("#>- ").replace("*", "").replace("`", "").strip()
        if cleaned:
            return cleaned[:RESULT_CHARS]
    return ""


def _failure(span: dict[str, Any]) -> str:
    attrs = span["attrs"]
    for key in ("status_message", "workhorse.out.reason"):
        if _plain(str(attrs.get(key) or "")):
            return _plain(str(attrs[key]))
    return "failed"


def _seconds_of(span: dict[str, Any]) -> float:
    return max(0.0, float(span["end_ts"]) - float(span["start_ts"]))


def _span_entry(kind: str, span: dict[str, Any], result: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "key": f"{kind}:{span['span_id']}",
        "name": _name(span),
        "node": _name(span),
        "ts": float(span["start_ts"]),
        "duration_s": _seconds_of(span),
        "result": result,
    }


def _event_entries(span: dict[str, Any]) -> list[dict[str, Any]]:
    found = []
    for number, event in enumerate(span["attrs"].get("events") or []):
        if not isinstance(event, dict) or event.get("name") != "retry":
            continue
        given = event.get("attrs") or {}
        attempt, delay = str(given.get("attempt") or ""), str(given.get("delay_s") or "")
        node = str(given.get("node") or _name(span))
        result = f"{node} turn retried" + (f" after {delay}s" if delay else "") + (f", attempt {attempt}" if attempt else "")
        found.append({
            "kind": "retry", "key": f"retry:{span['span_id']}:{number}", "name": "backend retry", "node": node,
            "ts": float(event.get("ts") or span["start_ts"]), "duration_s": 0.0, "result": result,
        })
    return found


def _gate_entry(span: dict[str, Any]) -> dict[str, Any]:
    attrs = span["attrs"]
    asked = _plain(str(attrs.get("activity") or "")) or _plain(str(attrs.get("workhorse.gate_question") or ""))
    outcome = str(attrs.get("workhorse.wait_outcome") or "")
    state = "answered" if outcome == "completed" else outcome or "ended"
    entry = _span_entry("gate", span, (asked + " · " if asked else "") + state)
    entry["name"] = "operator gate"
    return entry


class _Group:
    def __init__(self, opened: bool) -> None:
        self.opened = opened
        self.seconds = 0.0
        self.costs: list[float] = []
        self.entries: list[dict[str, Any]] = []
        self.first_ts = float("inf")
        self.last_ts = 0.0

    def see(self, ts: float) -> None:
        self.first_ts = min(self.first_ts, ts)
        self.last_ts = max(self.last_ts, ts)


def _fold(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    folded: list[dict[str, Any]] = []
    for entry in sorted(entries, key=lambda one: (one["ts"], one["key"])):
        if entry["kind"] != "step":
            folded.append(entry)
        elif folded and folded[-1]["kind"] == "steps":
            folded[-1]["steps"].append(entry)
        else:
            folded.append({"kind": "steps", "key": "steps:" + entry["key"], "ts": entry["ts"], "steps": [entry]})
    for entry in folded:
        if entry["kind"] == "steps":
            entry["count"] = len(entry["steps"])
            entry["time_s"] = sum(step["duration_s"] for step in entry["steps"])
    return folded


def _groups(spans: list[dict[str, Any]], rows: list[dict[str, Any]], placed: dict[str, tuple[str, int, bool]]) -> dict[tuple[str, str, int], _Group]:
    groups: dict[tuple[str, str, int], _Group] = {}
    nowhere = ("", 0, False)

    def group(work_id: str, flow: str, number: int, opened: bool = False) -> _Group:
        found = groups.get((work_id, flow, number))
        if found is None:
            found = groups[(work_id, flow, number)] = _Group(opened)
        return found

    def near(work_id: str, ts: float) -> tuple[str, str, int]:
        mine = sorted((key for key in groups if key[0] == work_id), key=lambda key: groups[key].first_ts)
        before = [key for key in mine if groups[key].first_ts <= ts]
        if before:
            return before[-1]
        return mine[0] if mine else (work_id, "", 0)

    turn_spans = [span for span in spans if span["name"] == TURN_SPAN]
    bucketed = {(placed.get(span["span_id"], nowhere)[0], span["node"]) for span in turn_spans}
    for span in turn_spans:
        flow, number, opened = placed.get(span["span_id"], nowhere)
        one = group(_work_id(span), flow, number, opened)
        one.seconds += flows.span_seconds(span)
        if span["profile_cost_usd"] is not None:
            one.costs.append(float(span["profile_cost_usd"]))
    for row in rows:
        one = group(row["work_id"], row["flow"], row["pass"])
        one.entries.append({"kind": "running" if row["status"] == "running" else "turn", "key": row["slug"], "slug": row["slug"], "ts": row["started_ts"]})
        one.see(row["started_ts"])
    leaves = flows.leaf_steps(spans)
    for span in leaves:
        flow, number, opened = placed.get(span["span_id"], nowhere)
        one = group(_work_id(span), flow, number, opened)
        if (flow, span["node"]) not in bucketed:
            one.seconds += flows.span_seconds(span)
    parents = {span["parent_id"] for span in turn_spans}
    for span in leaves:
        if span["span_id"] in parents:
            continue
        flow, number, _ = placed.get(span["span_id"], nowhere)
        one = group(_work_id(span), flow, number)
        failed = span["status"] == "ERROR" or problems.gate_check_failed(span)
        one.entries.append(_span_entry("failed" if failed else "step", span, _failure(span) if failed else _plain(str(span["attrs"].get("workhorse.out.reason") or ""))))
        one.see(float(span["start_ts"]))
    for span in spans:
        if span["attrs"].get("workhorse.span_kind") == "wait" and span["attrs"].get("workhorse.wait_kind") == "operator":
            key = (_work_id(span), *placed.get(span["span_id"], nowhere)[:2]) if span["span_id"] in placed else near(_work_id(span), float(span["start_ts"]))
            one = group(*key)
            one.entries.append(_gate_entry(span))
            one.see(float(span["start_ts"]))
        for entry in _event_entries(span):
            key = (_work_id(span), *placed[span["span_id"]][:2]) if span["span_id"] in placed else near(_work_id(span), entry["ts"])
            one = group(*key)
            one.entries.append(entry)
            one.see(entry["ts"])
    for span, count in churn.alerts(spans):
        key = (_work_id(span), *placed[span["span_id"]][:2]) if span["span_id"] in placed else near(_work_id(span), float(span["end_ts"]))
        one = group(*key)
        one.entries.append({
            "kind": "churn", "key": f"churn:{span['span_id']}", "name": "churn alert", "node": _name(span),
            "ts": float(span["end_ts"]), "duration_s": 0.0,
            "result": f"{_name(span)} repeated {count} times with the same labels",
        })
        one.see(float(span["end_ts"]))
    return groups


def _items(run_id: str, groups: dict[tuple[str, str, int], _Group], statuses: dict[tuple[str, str, int], str]) -> list[dict[str, Any]]:
    work = {row["work_id"]: row for row in store.run_work_items(run_id)}
    progress = store.latest_progress(run_id)
    latest = max((key[0] for key, one in groups.items() if key[0]), key=lambda work_id: max(one.last_ts for key, one in groups.items() if key[0] == work_id), default="")
    items: list[dict[str, Any]] = []
    for work_id in sorted({key[0] for key in groups}, key=lambda name: (name != "", min(one.first_ts for key, one in groups.items() if key[0] == name), name)):
        mine = sorted(((key, one) for key, one in groups.items() if key[0] == work_id), key=lambda pair: (pair[1].first_ts, pair[0][1], pair[0][2]))
        passes: list[dict[str, Any]] = []
        for (_, flow, number), one in mine:
            if not one.entries:
                continue
            running = any(entry["kind"] == "running" for entry in one.entries)
            state = "running" if running else "open" if one.opened else "failed" if statuses.get((work_id, flow, number)) == "ERROR" else "passed" if flow else ""
            passes.append({
                "flow": flow, "pass": number, "state": state, "time_s": one.seconds,
                "cost_usd": sum(one.costs) if one.costs else None, "first_ts": one.first_ts,
                "entries": _fold(one.entries),
            })
        known = work.get(work_id)
        costs: list[float] = [pas["cost_usd"] for pas in passes if pas["cost_usd"] is not None]
        items.append({
            "work_id": work_id,
            "outcome": overview.outcome(known, progress) if known else "",
            "latest": work_id == latest and bool(work_id),
            "running": any(pas["state"] == "running" for pas in passes),
            "time_s": known["seconds"] if known else sum(pas["time_s"] for pas in passes),
            "cost_usd": known["cost_usd"] if known else (sum(costs) if costs else None),
            "passes": passes,
        })
    return items


def timeline(run_id: str, live: LiveRows | None = None) -> dict[str, Any]:
    """The run's agent turns oldest first, and the same turns grouped by work item and flow pass with the steps, gates, retries and churn alerts around them."""
    spans = store.run_turn_spans(run_id)
    placed = flows.span_passes(spans)
    archived = store.query_turns(run=run_id, limit=100_000)
    attempts = _attempts(spans, archived)
    repeated = _repeated(attempts)
    rows = []
    for key, found in attempts.items():
        row = _finished_row(key, found, placed)
        directory = None if key.startswith(UNMATCHED_PREFIX) else _record_directory(archived, row, _base(key) in repeated)
        row = row | {"result": _recorded_result(directory) or row["result"]}
        if directory is None and _base(key) in repeated and not _record_files(run_id, row, archived, True):
            row["matched"] = False
        rows.append(row)
    running = []
    for slug, entries in (live or {}).items():
        if slug not in attempts and entries:
            running.append(_running_row(slug, entries))
    rows.sort(key=lambda row: (row["started_ts"], row["slug"]))
    groups = _groups(spans, rows, placed)
    for row in sorted(running, key=lambda one: (one["started_ts"], one["slug"])):
        target = max(groups, key=lambda key: groups[key].last_ts, default=("", "", 0))
        rows.append(row)
        group = groups.setdefault(target, _Group(False))
        group.entries.append({"kind": "running", "key": row["slug"], "slug": row["slug"], "ts": row["started_ts"]})
        group.see(row["started_ts"])
    return {"run_id": run_id, "rows": rows, "items": _items(run_id, groups, flows.pass_status(spans)), "as_of": time.time()}


def _record_files(run_id: str, head: dict[str, Any], archived: list[dict[str, Any]], strict: bool) -> dict[str, Path] | None:
    directory = _record_directory(archived, head, strict)
    if directory is not None:
        return {path.name: path for path in directory.iterdir() if path.is_file()}
    if strict and not head["session_id"]:
        return None
    for known, run_dir, _ in turns.known_runs():
        if known == run_id and localfs.is_local_dir(str(run_dir)):
            found = turns.run_dir_files(run_dir, _base(head["slug"]), head["session_id"])
            if found:
                return found
    return None


def _kept(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for entry in entries:
        if entry["kind"] == "tool":
            kept.append({
                "kind": "tool", "name": entry["name"], "summary": entry["summary"],
                "failed": bool(entry.get("failed")),
            })
        elif entry["kind"] == "message" and entry["role"] in READ_ROLES and entry["text"].strip():
            kept.append({"kind": "message", "role": entry["role"], "text": entry["text"]})
    return kept


def _cut(slug: str, held: list[dict[str, Any]]) -> bool:
    """Whether the live history dropped the start of this turn's transcript."""
    return not any(row.get("key") == f"{slug}:0" for row in held)


def turn(run_id: str, slug: str, live: LiveRows | None = None) -> dict[str, Any]:
    """One turn: its head figures and what the agent said and did in it, from the stored record or the live transcript. A key that names one of several visits sharing a slug reads only that visit's records."""
    spans = store.run_turn_spans(run_id)
    archived = store.query_turns(run=run_id, limit=100_000)
    attempted = _attempts(spans, archived)
    attempts = attempted.get(slug)
    base = _base(slug)
    strict = base in _repeated(attempted)
    held = (live or {}).get(base) or []
    if attempts is None and (not held or slug != base):
        raise TurnNotFound(slug)
    cut = False
    if attempts is None:
        head = _running_row(slug, held)
        entries: list[dict[str, Any]] | None = transcript_parse.from_updates(row["update"] for row in held)
        cut = _cut(slug, held)
    elif slug.startswith(UNMATCHED_PREFIX):
        head = _finished_row(slug, attempts, flows.span_passes(spans))
        return {"run_id": run_id, "head": head, "entries": [], "cut": False}
    else:
        head = _finished_row(slug, attempts, flows.span_passes(spans))
        window = (head["started_ts"] - WINDOW_SLACK_S, head["ended_ts"] + WINDOW_SLACK_S)
        if strict:
            held = [row for row in held if window[0] <= float(row["ts"]) <= window[1]]
        files = _record_files(run_id, head, archived, strict)
        if strict and files is None and not held:
            return {"run_id": run_id, "head": head | {"matched": False}, "entries": [], "cut": False}
        entries = transcript_parse.read_files(files, window) if files else None
        if entries is None and held:
            entries = transcript_parse.from_updates(row["update"] for row in held)
            cut = _cut(base, held)
    if entries is None:
        raise TurnUnreadable(slug)
    return {"run_id": run_id, "head": head, "entries": _kept(entries), "cut": cut}
