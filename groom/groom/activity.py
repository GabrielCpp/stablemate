"""A run's agent turns as the Activity tab lists them and reads them."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from workhorse.turnkey import VisitKey

from groom import flows, localfs, store, transcript_parse, turns
from groom.projection import TURN_SPAN, transcript_entry

LiveRows = dict[str, list[dict[str, Any]]]

WINDOW_SLACK_S = 5.0

RESULT_CHARS = 140

UNMATCHED_PREFIX = "unmatched-"

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


def _directories(run_id: str, session_id: str = "") -> dict[str, Path]:
    """The archived record directory of each visit slug, the record of ``session_id`` first when several exist."""
    ordered = sorted(
        store.query_turns(run=run_id, limit=100_000),
        key=lambda row: (row["session_id"] == session_id, row["ts"]),
    )
    found: dict[str, Path] = {}
    for row in ordered:
        directory = turns.record_path(row)
        if directory.is_dir():
            found[_slug_of(row)] = directory
    return found


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
    """Each agent turn span grouped by visit slug. A span no archived row matches stands alone under ``unmatched-<span id>``."""
    candidates = archived or []
    found: dict[str, list[dict[str, Any]]] = {}
    for span in spans:
        if span["name"] != TURN_SPAN:
            continue
        slug = _span_slug(span, candidates) or f"{UNMATCHED_PREFIX}{span['span_id']}"
        found.setdefault(slug, []).append(span)
    return found


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
    passes: dict[str, tuple[str, int]],
    directory: Path | None = None,
) -> dict[str, Any]:
    ordered = sorted(attempts, key=lambda span: float(span["start_ts"]))
    last = max(ordered, key=lambda span: float(span["end_ts"]))
    attrs = last["attrs"]
    costs = [float(span["profile_cost_usd"]) for span in ordered if span["profile_cost_usd"] is not None]
    flow, number = passes.get(last["span_id"], ("", 0))
    return {
        "slug": slug,
        "node": str(last["node"] or attrs.get("workhorse.node") or ""),
        "visit": _visit(slug),
        "work_id": str(attrs.get("work_id") or attrs.get("wf.work_id") or ""),
        "flow": flow,
        "pass": number,
        "model": str(attrs.get("model") or ""),
        "started_ts": float(ordered[0]["start_ts"]),
        "ended_ts": float(last["end_ts"]),
        "duration_s": max(0.0, float(last["end_ts"]) - float(ordered[0]["start_ts"])),
        "cost_usd": sum(costs) if costs else None,
        "output_tokens": sum(int(span["profile_output_tokens"] or 0) for span in ordered),
        "cache_read_tokens": sum(int(span["profile_cache_read_tokens"] or 0) for span in ordered),
        "status": "failed" if last["status"] == "ERROR" else "done",
        "result": _recorded_result(directory) or _first_line(str(attrs.get("activity") or "")),
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


def timeline(run_id: str, live: LiveRows | None = None) -> dict[str, Any]:
    """The run's agent turns, oldest first: the finished ones from their spans, the running one from its live transcript."""
    spans = store.run_turn_spans(run_id)
    passes = flows.turn_passes(spans)
    archived = store.query_turns(run=run_id, limit=100_000)
    attempts = _attempts(spans, archived)
    directories = _directories(run_id)
    rows = [_finished_row(slug, found, passes, directories.get(slug)) for slug, found in attempts.items()]
    for slug, entries in (live or {}).items():
        if slug not in attempts and entries:
            rows.append(_running_row(slug, entries))
    rows.sort(key=lambda row: (row["started_ts"], row["slug"]))
    return {"run_id": run_id, "rows": rows, "as_of": time.time()}


def _record_files(run_id: str, slug: str, session_id: str) -> dict[str, Path] | None:
    directory = _directories(run_id, session_id).get(slug)
    if directory is not None:
        return {path.name: path for path in directory.iterdir() if path.is_file()}
    for known, run_dir, _ in turns.known_runs():
        if known == run_id and localfs.is_local_dir(str(run_dir)):
            found = turns.run_dir_files(run_dir, slug, session_id)
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
    """One turn: its head figures and what the agent said and did in it, from the stored record or the live transcript."""
    spans = store.run_turn_spans(run_id)
    attempts = _attempts(spans, store.query_turns(run=run_id, limit=100_000)).get(slug)
    held = (live or {}).get(slug) or []
    if attempts is None and not held:
        raise TurnNotFound(slug)
    cut = False
    if attempts is None:
        head = _running_row(slug, held)
        entries: list[dict[str, Any]] | None = transcript_parse.from_updates(row["update"] for row in held)
        cut = _cut(slug, held)
    elif slug.startswith(UNMATCHED_PREFIX):
        head = _finished_row(slug, attempts, flows.turn_passes(spans))
        return {"run_id": run_id, "head": head, "entries": [], "cut": False}
    else:
        head = _finished_row(slug, attempts, flows.turn_passes(spans))
        window = (head["started_ts"] - WINDOW_SLACK_S, head["ended_ts"] + WINDOW_SLACK_S)
        files = _record_files(run_id, slug, head["session_id"])
        entries = transcript_parse.read_files(files, window) if files else None
        if entries is None and held:
            entries = transcript_parse.from_updates(row["update"] for row in held)
            cut = _cut(slug, held)
    if entries is None:
        raise TurnUnreadable(slug)
    return {"run_id": run_id, "head": head, "entries": _kept(entries), "cut": cut}
