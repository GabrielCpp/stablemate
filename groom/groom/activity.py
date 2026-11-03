"""A run's agent turns as the Activity tab lists them and reads them."""

from __future__ import annotations

import bisect
import json
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from workhorse import gates as gate_file
from workhorse.turnkey import VisitKey

from groom import churn, flows, gates, localfs, overview, problems, store, transcript_parse, turns
from groom.projection import TURN_SPAN, transcript_entry

LiveRows = dict[str, list[dict[str, Any]]]

WINDOW_SLACK_S = 5.0

RESULT_CHARS = 140

UNMATCHED_PREFIX = "unmatched-"

VISIT_MARK = "~"

RUNNING_STEP = "step:running:"

LOG_LINES = 500

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
        **({"problem": True} if kind == "failed" else {}),
    }


def _retry_note(span: dict[str, Any], earlier: dict[str, Any], spans: list[dict[str, Any]]) -> dict[str, str]:
    """The backend's own account of a retry: the last retry event stamped between the failed attempt's end and this attempt's start."""
    low, high = float(earlier["end_ts"]) - WINDOW_SLACK_S, float(span["start_ts"]) + WINDOW_SLACK_S
    noted: list[tuple[float, dict[str, Any]]] = []
    for one in spans:
        for event in one["attrs"].get("events") or []:
            if isinstance(event, dict) and event.get("name") == "retry" and low <= float(event.get("ts") or 0) <= high:
                noted.append((float(event["ts"]), event.get("attrs") or {}))
    if not noted:
        return {}
    given = max(noted, key=lambda pair: pair[0])[1]
    return {"attempt": str(given.get("attempt") or ""), "delay": str(given.get("delay_s") or "")}


def _retry_entry(span: dict[str, Any], earlier: dict[str, Any], spans: list[dict[str, Any]], visit: str) -> dict[str, Any]:
    note = _retry_note(span, earlier, spans)
    node = _name(span)
    result = f"{node} turn started again" + (f" after {note['delay']}s" if note.get("delay") else "") + (f", attempt {note['attempt']}" if note.get("attempt") else "")
    return {
        "kind": "retry", "key": f"retry:{span['span_id']}", "name": "backend retry", "node": node,
        "ts": float(span["start_ts"]), "duration_s": 0.0, "result": result, "problem": True, "turn": visit,
    }


def _gate_key(node: str, ordinal: int) -> str:
    return f"gate:{node}#{ordinal}"


def _gate_entry(span: dict[str, Any], ordinal: int) -> dict[str, Any]:
    attrs = span["attrs"]
    asked = _plain(str(attrs.get("activity") or "")) or _plain(str(attrs.get("workhorse.gate_question") or ""))
    outcome = str(attrs.get("workhorse.wait_outcome") or "")
    state = "answered" if outcome == "completed" else outcome or "ended"
    entry = _span_entry("gate", span, (asked + " · " if asked else "") + state)
    entry["name"] = "operator gate"
    entry["key"] = _gate_key(entry["node"], ordinal)
    return entry


def _open_gate_entry(standing: dict[str, Any], ordinal: int) -> dict[str, Any]:
    asked = _plain(str(standing.get("question") or ""))
    node = str(standing["node"])
    return {
        "kind": "gate", "key": _gate_key(node, ordinal), "name": "operator gate", "node": node,
        "ts": float(standing["since_ts"]), "duration_s": None, "open": True, "result": (asked + " " if asked else "") + "Waiting",
    }


def _doing_entry(standing: dict[str, Any]) -> dict[str, Any]:
    node = str(standing["node"])
    return {
        "kind": "doing", "key": f"{RUNNING_STEP}{node}", "name": node, "node": node,
        "ts": float(standing["since_ts"]), "duration_s": None, "open": True, "result": "",
    }


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


def _groups(spans: list[dict[str, Any]], rows: list[dict[str, Any]], placed: dict[str, tuple[str, int, bool]], visits: dict[str, str]) -> dict[tuple[str, str, int], _Group]:
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
    states = flows.state_steps(spans)
    for span in leaves + states:
        flow, number, opened = placed.get(span["span_id"], nowhere)
        one = group(_work_id(span), flow, number, opened)
        if (flow, span["node"]) not in bucketed:
            one.seconds += flows.span_seconds(span)
    found = problems.found(spans)
    broken = {item["span"]["span_id"] for item in found if item["kind"] == "failed"}
    parents = {span["parent_id"] for span in turn_spans}
    for span in leaves + [one for one in states if one["status"] != "ERROR"]:
        if span["span_id"] in parents or span["span_id"] in broken:
            continue
        flow, number, _ = placed.get(span["span_id"], nowhere)
        one = group(_work_id(span), flow, number)
        one.entries.append(_span_entry("step", span, _plain(str(span["attrs"].get("workhorse.out.reason") or ""))))
        one.see(float(span["start_ts"]))

    def home(span: dict[str, Any], ts: float) -> _Group:
        if span["span_id"] in placed:
            return group(_work_id(span), *placed[span["span_id"]][:2])
        return group(*near(_work_id(span), ts))

    for item in found:
        span = item["span"]
        if item["kind"] == "failed":
            entry = _span_entry("failed", span, _failure(span))
            if span["name"] == TURN_SPAN:
                entry["turn"] = visits.get(span["span_id"], "")
        elif item["kind"] == "retry":
            entry = _retry_entry(span, item["after"], spans, visits.get(span["span_id"], ""))
        else:
            continue
        one = home(span, entry["ts"])
        one.entries.append(entry)
        one.see(entry["ts"])
    asked_at: dict[str, int] = {}
    for span in spans:
        if span["attrs"].get("workhorse.span_kind") == "wait" and span["attrs"].get("workhorse.wait_kind") == "operator":
            ordinal = asked_at[_name(span)] = asked_at.get(_name(span), 0) + 1
            key = (_work_id(span), *placed.get(span["span_id"], nowhere)[:2]) if span["span_id"] in placed else near(_work_id(span), float(span["start_ts"]))
            one = group(*key)
            one.entries.append(_gate_entry(span, ordinal))
            one.see(float(span["start_ts"]))
    for span, count in churn.alerts(spans):
        key = (_work_id(span), *placed[span["span_id"]][:2]) if span["span_id"] in placed else near(_work_id(span), float(span["end_ts"]))
        one = group(*key)
        one.entries.append({
            "kind": "churn", "key": f"churn:{span['span_id']}", "name": "CHURN", "node": _name(span),
            "ts": float(span["end_ts"]), "duration_s": 0.0,
            "result": f"{_name(span)} repeated {count} times with the same labels", "problem": True,
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


def _waits(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [span for span in spans if span["attrs"].get("workhorse.span_kind") == "wait" and span["attrs"].get("workhorse.wait_kind") == "operator"]


def _standing_entry(spans: list[dict[str, Any]], standing: dict[str, Any], held: bool) -> dict[str, Any] | None:
    node = str(standing.get("node") or "")
    if not node:
        return None
    if standing.get("wait_kind") == "operator":
        return _open_gate_entry(standing, sum(1 for span in _waits(spans) if _name(span) == node) + 1)
    if standing.get("wait_kind") or standing.get("turn_active") is True or held:
        return None
    return _doing_entry(standing)


def _log_entry(row: dict[str, Any]) -> dict[str, Any]:
    level = str(row["severity"])
    node = str(row["node"])
    return {
        "kind": "log", "key": f"log:{row['id']}", "name": f"{level} {node}".strip(), "node": node, "level": level,
        "ts": float(row["ts"]), "duration_s": 0.0, "result": str(row["body"]),
    }


def _with_logs(items: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    """Put each log into the pass that was open at its time, after the folds are made so no log splits a fold."""
    passes = sorted(((pas["first_ts"], pas) for item in items for pas in item["passes"]), key=lambda pair: pair[0])
    if not passes:
        return
    starts = [first for first, _ in passes]
    for row in sorted(rows, key=lambda one: (one["ts"], one["id"])):
        entry = _log_entry(row)
        at = max(0, bisect.bisect_right(starts, entry["ts"]) - 1)
        entries = passes[at][1]["entries"]
        entries.insert(bisect.bisect_right([one["ts"] for one in entries], entry["ts"]), entry)


def timeline(run_id: str, live: LiveRows | None = None, standing: dict[str, Any] | None = None, logs: bool = False) -> dict[str, Any]:
    """The run's agent turns oldest first, and the same turns grouped by work item and flow pass with the steps, gates, retries and churn alerts around them. `standing` is where the run is now: the step it is in, or the operator gate it waits at, which no stored span shows yet."""
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
    visits = {span["span_id"]: key for key, found in attempts.items() for span in found}
    groups = _groups(spans, rows, placed, visits)
    for row in sorted(running, key=lambda one: (one["started_ts"], one["slug"])):
        target = max(groups, key=lambda key: groups[key].last_ts, default=("", "", 0))
        rows.append(row)
        group = groups.setdefault(target, _Group(False))
        group.entries.append({"kind": "running", "key": row["slug"], "slug": row["slug"], "ts": row["started_ts"]})
        group.see(row["started_ts"])
    here = _standing_entry(spans, standing, bool(running)) if standing else None
    if here is not None:
        target = max(groups, key=lambda key: groups[key].last_ts, default=("", "", 0))
        group = groups.setdefault(target, _Group(False))
        here["place"] = list(target)
        group.entries.append(here)
        group.see(here["ts"])
    items = _items(run_id, groups, flows.pass_status(spans))
    if logs:
        _with_logs(items, store.run_log_rows(run_id, 1_000_000))
    return {"run_id": run_id, "rows": rows, "items": items, "problems": len(problems.found(spans)), "log_count": store.count_logs(run_id), "as_of": time.time()}


def _record_files(run_id: str, head: dict[str, Any], archived: list[dict[str, Any]], strict: bool) -> dict[str, Path] | None:
    directory = _record_directory(archived, head, strict)
    if directory is not None:
        return {path.name: path for path in directory.iterdir() if path.is_file()}
    if strict and not head["session_id"]:
        return None
    for _, run_dir, _ in turns.known_runs(run_id):
        if localfs.is_local_dir(str(run_dir)):
            found = turns.run_dir_files(run_dir, _base(head["slug"]), head["session_id"])
            if found:
                return found
    return None


def _recorded_prompt(files: dict[str, Path] | None) -> str:
    path = (files or {}).get("prompt.md")
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _joined(entries: list[dict[str, Any]], role: str) -> str:
    return "\n\n".join(entry["text"].strip() for entry in entries if entry["kind"] == "message" and entry["role"] == role and entry["text"].strip())


def _kept(entries: list[dict[str, Any]], finished: bool = False) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for entry in entries:
        if entry["kind"] == "tool":
            failed = bool(entry.get("failed"))
            kept.append({
                "kind": "tool", "name": entry["name"], "summary": entry["summary"], "failed": failed,
                "duration_s": entry.get("duration_s"), "result": entry.get("result", "") if failed else "",
            })
        elif entry["kind"] == "message" and entry["role"] in READ_ROLES and entry["text"].strip():
            kept.append({"kind": "message", "role": entry["role"], "text": entry["text"], "final": False})
    if finished:
        said = [entry for entry in kept if entry["kind"] == "message" and entry["role"] == "assistant"]
        if said:
            said[-1]["final"] = True
    return kept


def _blank(run_id: str, head: dict[str, Any]) -> dict[str, Any]:
    return {"run_id": run_id, "head": head, "entries": [], "cut": False, "prompt": None, "thinking": None}


def _stamped(held: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**row["update"], "_ts": float(row["ts"])} for row in held]


def _cut(slug: str, held: list[dict[str, Any]]) -> bool:
    """Whether the live history dropped the start of this turn's transcript."""
    return not any(row.get("key") == f"{slug}:0" for row in held)


def turn(run_id: str, slug: str, live: LiveRows | None = None, pending: bool = False) -> dict[str, Any]:
    """One turn: its head figures and what the agent said and did in it, from the stored record or the live transcript. A key that names one of several visits sharing a slug reads only that visit's records. A finished turn with no transcript in any record reads as unmatched, unless `pending` says its records may still be pulled from a container."""
    spans = store.run_turn_spans(run_id)
    archived = store.query_turns(run=run_id, limit=100_000)
    return _read_turn(run_id, slug, live, pending, spans, archived, _attempts(spans, archived), flows.span_passes(spans))


def _read_turn(
    run_id: str,
    slug: str,
    live: LiveRows | None,
    pending: bool,
    spans: list[dict[str, Any]],
    archived: list[dict[str, Any]],
    attempted: dict[str, list[dict[str, Any]]],
    placed: dict[str, tuple[str, int, bool]],
) -> dict[str, Any]:
    attempts = attempted.get(slug)
    base = _base(slug)
    strict = base in _repeated(attempted)
    held = (live or {}).get(base) or []
    if attempts is None and (not held or slug != base):
        raise TurnNotFound(slug)
    cut = False
    recorded = ""
    if attempts is None:
        head = _running_row(slug, held)
        entries: list[dict[str, Any]] | None = transcript_parse.from_updates(_stamped(held))
        cut = _cut(slug, held)
    elif slug.startswith(UNMATCHED_PREFIX):
        head = _finished_row(slug, attempts, placed)
        return _blank(run_id, head)
    else:
        head = _finished_row(slug, attempts, placed)
        window = (head["started_ts"] - WINDOW_SLACK_S, head["ended_ts"] + WINDOW_SLACK_S)
        if strict:
            held = [row for row in held if window[0] <= float(row["ts"]) <= window[1]]
        files = _record_files(run_id, head, archived, strict)
        entries = transcript_parse.read_files(files, window) if files else None
        recorded = _recorded_prompt(files) if entries is not None else ""
        if entries is None and held:
            entries = transcript_parse.from_updates(_stamped(held))
            cut = _cut(base, held)
    if entries is None:
        if attempts is not None and not pending:
            return _blank(run_id, head | {"matched": False})
        raise TurnUnreadable(slug)
    return {
        "run_id": run_id, "head": head, "entries": _kept(entries, attempts is not None), "cut": cut,
        "prompt": (recorded if recorded.strip() else _joined(entries, "user")) or None,
        "thinking": _joined(entries, "thought") or None,
    }


class EntryNotFound(LookupError):
    """The run has no timeline row under this key."""


def _flat(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for item in items:
        for one in item["passes"]:
            for entry in one["entries"]:
                found.extend(entry["steps"] if entry["kind"] == "steps" else [entry])
    return sorted(found, key=lambda entry: (entry["ts"], entry["key"]))


NOUNS = {"turn": "turn", "running": "turn", "gate": "gate", "step": "step", "failed": "step", "doing": "step"}


def _next(key: str, flat: list[dict[str, Any]], names: dict[str, str], going: bool) -> dict[str, Any]:
    keys = [entry["key"] for entry in flat]
    after = flat[keys.index(key) + 1] if key in keys and keys.index(key) + 1 < len(keys) else None
    if after is None:
        return {"key": "", "noun": "", "text": "Nothing yet. This is still running." if going else "Nothing came after this."}
    name = after.get("name") or names.get(after["key"], after["key"])
    kind = after["kind"]
    text = {
        "turn": f"{name} ran next, an agent turn.",
        "running": f"{name} is running next, an agent turn.",
        "gate": f"The run stopped at {name} next.",
        "step": f"{name} ran next and passed.",
        "failed": f"{name} ran next and failed.",
        "doing": f"{name} is running next.",
        "retry": f"{name} followed.",
        "churn": f"{name} followed.",
    }.get(kind, f"{name} followed.")
    return {"key": after["key"], "noun": NOUNS.get(kind, "row"), "text": text}


def _lines(run_id: str, node: str, start: float, end: float | None) -> tuple[list[dict[str, Any]], bool]:
    found = store.query_logs(run=run_id, node=node, limit=LOG_LINES + 1, since_ts=start - 0.001, before_ts=None if end is None else end + 0.001)
    return (
        [{"ts": float(row["ts"]), "level": str(row["severity"] or ""), "node": str(row["node"] or node), "body": str(row["body"] or "")} for row in reversed(found[:LOG_LINES])],
        len(found) > LOG_LINES,
    )


def _placed(key: str, context: dict[str, Any]) -> tuple[str, str, int]:
    for one in context["flat"]:
        if one["key"] == key and one.get("place"):
            work_id, flow, number = one["place"]
            return str(work_id), str(flow), int(number)
    return "", "", 0


def _step_reading(run_id: str, key: str, span: dict[str, Any] | None, standing: dict[str, Any] | None, context: dict[str, Any]) -> dict[str, Any]:
    if span is None:
        assert standing is not None
        node, started, ended = str(standing["node"]), float(standing["since_ts"]), None
        work_id, flow, number = _placed(key, context)
        head = {"name": node, "work_id": work_id, "flow": flow, "pass": number, "state": "running", "started_ts": started, "duration_s": None, "error_class": ""}
        error = None
    else:
        attrs = span["attrs"]
        node, started, ended = _name(span), float(span["start_ts"]), float(span["end_ts"])
        failed = key.startswith("failed:")
        flow, number, _ = context["placed"].get(span["span_id"], ("", 0, False))
        head = {
            "name": node, "work_id": _work_id(span), "flow": flow, "pass": number, "state": "failed" if failed else "passed",
            "started_ts": started, "duration_s": _seconds_of(span), "error_class": str(attrs.get("error.class") or ""),
        }
        error = (str(attrs.get("status_message") or attrs.get("workhorse.out.reason") or "").strip() or "failed") if failed else None
    logs, cut = _lines(run_id, node, started, ended)
    turn = str(next((one for one in context["flat"] if one["key"] == key), {}).get("turn") or "")
    return {
        "run_id": run_id, "kind": "step", "key": key, "head": head, "error": error, "logs": logs, "cut": cut,
        "next": {"key": turn, "noun": "turn", "text": f"{node} is an agent turn."} if turn else _next(key, context["flat"], context["names"], ended is None),
    }


def _problem_head(span: dict[str, Any], context: dict[str, Any], ts: float) -> dict[str, Any]:
    flow, number, _ = context["placed"].get(span["span_id"], ("", 0, False))
    return {"name": _name(span), "work_id": _work_id(span), "flow": flow, "pass": number, "started_ts": ts}


def _problem_reading(run_id: str, key: str, item: dict[str, Any], spans: list[dict[str, Any]], context: dict[str, Any]) -> dict[str, Any]:
    span = item["span"]
    entry = next((one for one in context["flat"] if one["key"] == key), None)
    if item["kind"] == "churn":
        node, work_id = _name(span), _work_id(span)
        happened = f"{node} has run {item['count']} times in a row" + (f" on {work_id}" if work_id else "") + " with the same labels. This alert means the run may be going round in circles."
        head = _problem_head(span, context, float(span["end_ts"])) | {"state": "churn"}
        return {"run_id": run_id, "kind": "churn", "key": key, "head": head, "happened": happened, "next": _next(key, context["flat"], context["names"], False)}
    earlier = item["after"]
    note = _retry_note(span, earlier, spans)
    node = _name(span)
    reason = _failure(earlier) if earlier["status"] == "ERROR" else ""
    failure = (" That attempt failed" + (f": {reason}" if reason != "failed" else "") + ".") if earlier["status"] == "ERROR" else ""
    happened = f"The backend started the {node} turn again after the attempt before it ended." + failure + (f" It waited {note['delay']}s first." if note.get("delay") else "")
    later = sorted(
        (one for one in spans if one["name"] == span["name"] and one["trace_id"] == span["trace_id"] and (one["parent_id"] or one["span_id"]) == (span["parent_id"] or span["span_id"]) and float(one["start_ts"]) > float(span["start_ts"])),
        key=lambda one: float(one["start_ts"]),
    )
    if span["status"] == "ERROR":
        came = "The retry failed as well." if not later else "The retry failed, and the backend tried again."
    else:
        came = "This attempt finished and the turn went on." if not later else "The backend started it again after this attempt."
    visit = str((entry or {}).get("turn") or "")
    head = _problem_head(span, context, float(span["start_ts"])) | {"state": "retry", "attempt": note.get("attempt", "")}
    return {
        "run_id": run_id, "kind": "retry", "key": key, "head": head, "happened": happened,
        "next": {"key": visit, "noun": "turn" if visit else "", "text": came},
    }


def _answer_after(text: str, asked: str, which: int = -1) -> str:
    want = asked.strip()
    if not want:
        return ""
    spots = [found.start() for found in re.finditer(re.escape(want), text)]
    if not spots or which >= len(spots):
        return ""
    at = spots[which]
    end = spots[which + 1] if which != -1 and which + 1 < len(spots) else len(text)
    rest = text[at + len(want):end]
    cut = _NEXT_QUESTION.search(rest)
    return (rest[: cut.start()] if cut else rest).strip()


def _asked_of(span: dict[str, Any]) -> str:
    attrs = span["attrs"]
    return gates.extract_question(str(attrs.get("workhorse.gate_question") or "")) or str(attrs.get("activity") or "").strip()


def _asking(text: str, asked: str, path: str, waits: list[dict[str, Any]], mine: dict[str, Any] | None) -> int | None:
    same = [
        one for one in waits
        if str(one["attrs"].get("workhorse.gate_path") or "") == path and _asked_of(one) == asked
        and one["attrs"].get("workhorse.wait_outcome") == "completed"
    ]
    if mine is not None and mine not in same:
        return None
    total = len(re.findall(re.escape(asked.strip()), text)) if asked.strip() else 0
    askings = len(same) + (1 if mine is None else 0)
    position = len(same) if mine is None else same.index(mine)
    index = position - (askings - total)
    return index if 0 <= index < total else None


_NEXT_QUESTION = re.compile(r"^#{1,2}\s+questions?\s+from\s+the\s+agent\s*$", re.IGNORECASE | re.MULTILINE)


def _gate_reading(
    run_id: str, key: str, span: dict[str, Any] | None, standing: dict[str, Any] | None, context: dict[str, Any], read: Callable[[str], str | None],
) -> dict[str, Any]:
    if span is None:
        assert standing is not None
        path, asked = str(standing.get("path") or ""), str(standing.get("question") or "")
        work_id, flow, number = _placed(key, context)
        head = {"work_id": work_id, "flow": flow, "pass": number, "state": "open", "started_ts": float(standing["since_ts"]), "ended_ts": None, "waited_s": None, "path": path}
    else:
        attrs = span["attrs"]
        path = str(attrs.get("workhorse.gate_path") or "")
        asked = gates.extract_question(str(attrs.get("workhorse.gate_question") or "")) or str(attrs.get("activity") or "").strip()
        flow, number, _ = context["placed"].get(span["span_id"], ("", 0, False))
        outcome = str(attrs.get("workhorse.wait_outcome") or "")
        head = {
            "work_id": _work_id(span), "flow": flow, "pass": number, "state": "answered" if outcome == "completed" else "ended",
            "started_ts": float(span["start_ts"]), "ended_ts": float(span["end_ts"]), "waited_s": _seconds_of(span), "path": path,
        }
    text = read(path) if path else None
    if not asked and text:
        asked = gate_file.latest_question(text)
    answer = ""
    if text and asked:
        which = _asking(text, asked, path, context["waits"], span)
        answer = "" if which is None else _answer_after(text, asked, which)
    taken = head["state"] != "open"
    if head["state"] == "open" and answer and gate_file.status_of(text or "") in ("ANSWERED", "CONSUMED"):
        head["state"] = "answered"
    elif head["state"] == "open":
        answer = ""
    return {
        "run_id": run_id, "kind": "gate", "key": key, "head": head, "question": asked, "answer": answer, "taken": taken,
        "readable": text is not None, "next": _next(key, context["flat"], context["names"], head["ended_ts"] is None),
    }


def entry(
    run_id: str,
    key: str,
    live: LiveRows | None = None,
    standing: dict[str, Any] | None = None,
    read: Callable[[str], str | None] = lambda _path: None,
) -> dict[str, Any]:
    """A step or an operator gate read in full: for a step its error, its logs and what came next, for a gate its question, its answer and how long it waited."""
    spans = store.run_turn_spans(run_id)
    overview_ = timeline(run_id, live, standing)
    flat = _flat(overview_["items"])
    context = {
        "placed": flows.span_passes(spans), "flat": flat,
        "waits": sorted(_waits(spans), key=lambda span: float(span["start_ts"])),
        "names": {row["slug"]: row["node"] for row in overview_["rows"]},
    }
    by_id = {span["span_id"]: span for span in spans}
    kind, _, rest = key.partition(":")
    if kind in ("step", "failed") and not key.startswith(RUNNING_STEP):
        span = by_id.get(rest)
        if span is None:
            raise EntryNotFound(key)
        return _step_reading(run_id, key, span, None, context)
    if key.startswith(RUNNING_STEP):
        node = key[len(RUNNING_STEP):]
        if standing and standing.get("node") == node and not standing.get("wait_kind"):
            return _step_reading(run_id, key, None, standing, context)
        done = [span for span in flows.leaf_steps(spans) + flows.state_steps(spans) if _name(span) == node]
        if not done:
            raise EntryNotFound(key)
        last = max(done, key=lambda span: float(span["end_ts"]))
        failed = last["status"] == "ERROR" or problems.gate_check_failed(last)
        return _step_reading(run_id, f"{'failed' if failed else 'step'}:{last['span_id']}", last, None, context)
    if kind == "gate":
        node, _, number = rest.rpartition("#")
        waits = [span for span in _waits(spans) if _name(span) == node]
        if not number.isdigit() or not node or int(number) < 1:
            raise EntryNotFound(key)
        if int(number) <= len(waits):
            return _gate_reading(run_id, key, waits[int(number) - 1], None, context, read)
        if standing and standing.get("wait_kind") == "operator" and standing.get("node") == node and int(number) == len(waits) + 1:
            return _gate_reading(run_id, key, None, standing, context, read)
    if kind in ("retry", "churn"):
        for item in problems.found(spans):
            if item["kind"] == kind and f"{kind}:{item['span']['span_id']}" == key:
                return _problem_reading(run_id, key, item, spans, context)
    raise EntryNotFound(key)


class SearchFailed(RuntimeError):
    pass


SEARCH_QUERY_CHARS = 200
SEARCH_LINE_CHARS = 160


def _hit_line(text: str, needle: str) -> str:
    lowered = text.lower()
    at = lowered.find(needle)
    if at < 0:
        return ""
    start = max(0, at - SEARCH_LINE_CHARS // 4)
    return " ".join(text[start : start + SEARCH_LINE_CHARS].split())


def _entry_lines(entries: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for one in entries:
        if one["kind"] == "message":
            lines.extend(one["text"].splitlines())
        else:
            lines.append(one.get("summary") or "")
            lines.extend((one.get("result") or "").splitlines())
    return lines


def search(run_id: str, query: str, live: LiveRows | None = None, pending: bool = False) -> dict[str, Any]:
    """The turns of this run, and only this run, whose transcript says `query`, each with the first matching line. A turn that cannot be read fails the whole search."""
    needle = " ".join(query.split())[:SEARCH_QUERY_CHARS].lower()
    if not needle:
        return {"run_id": run_id, "query": "", "matches": []}
    matches: list[dict[str, str]] = []
    spans = store.run_turn_spans(run_id)
    archived = store.query_turns(run=run_id, limit=100_000)
    attempted = _attempts(spans, archived)
    placed = flows.span_passes(spans)
    slugs = list(attempted) + [slug for slug, held in (live or {}).items() if slug not in attempted and held]
    for slug in slugs:
        try:
            read = _read_turn(run_id, slug, live, pending, spans, archived, attempted, placed)
        except TurnNotFound:
            continue
        except TurnUnreadable as exc:
            raise SearchFailed(slug) from exc
        for line in _entry_lines(read["entries"]):
            found = _hit_line(line, needle)
            if found:
                matches.append({"key": slug, "line": found})
                break
    return {"run_id": run_id, "query": needle, "matches": matches}
