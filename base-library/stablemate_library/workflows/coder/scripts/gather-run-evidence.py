#!/usr/bin/env python3
"""Deterministically digest a coder run's PROCESS RECORD for the `dream` flow.

Reflection is only as good as its evidence. A story's final artifacts (review.md, qa.md)
do not show what LOOPED, STALLED, or RETRIED — that lives in the run directory:

  - events.jsonl               one line per node enter/done (seq, ts, next). Repeated
                               `enter`s for a node = a LOOP; a long enter→done gap =
                               a SLOW/stalled step. This is the authoritative record.
  - <node>/output.json         each node's structured result (final state; re-runs
                               overwrite, but events.jsonl preserves that it re-ran).
  - <node>/.session_id         the opencode session id — a pointer to the full
                               turn-by-turn transcript (tool calls, retries) in
                               opencode's own store, for optional deep-dive.

This turns events.jsonl (across the top-level run AND nested `_flow` sub-runs) into a
structured digest — loops, slowest steps, wall time, the node path, session pointers —
so the dream agent reflects on the REAL process, not a guess from output artifacts.

Args:
    argv[1]  run_dir     the coder run to reflect on; empty → newest non-dream run
                         under <docs_path>/.agents/runs.
    argv[2]  docs_path   repo root (empty → CWD).

Stdlib-only (system python3). Emits: {"run_digest": {...}, "run_dir": "<path>"}.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from workhorse.scriptutil import find_docs_root


def _auto_run_dir(docs_root: Path) -> Path | None:
    runs = docs_root / ".agents" / "runs"
    if not runs.is_dir():
        return None
    # The run to reflect ON is a build run (has events.jsonl), not a dream run.
    cands = [p.parent for p in runs.glob("*/events.jsonl") if "dream" not in p.parent.name]
    if not cands:
        return None
    return max(cands, key=lambda p: (p / "events.jsonl").stat().st_mtime)


def _resolve_run_dir(arg: str, docs_root: Path) -> Path | None:
    """Resolve the run dir robustly regardless of the script's CWD: an explicit arg is
    taken as-is if absolute, else relative to the repo root; if it has no events.jsonl
    (wrong path / not a run), fall back to the newest non-dream run under .agents/runs."""
    if arg:
        p = Path(arg)
        cand = p if p.is_absolute() else (docs_root / p)
        if (cand / "events.jsonl").is_file():
            return cand.resolve()
    return _auto_run_dir(docs_root)


def _parse_ts(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _load_events(run_dir: Path) -> list[dict]:
    """Aggregate events from the top-level log and every nested `_flow` sub-run."""
    events: list[dict] = []
    for ev_file in sorted(run_dir.rglob("events.jsonl")):
        scope = "" if ev_file.parent == run_dir else str(ev_file.parent.relative_to(run_dir))
        for line in ev_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            e["_scope"] = scope
            events.append(e)
    return events


def main() -> None:
    run_dir_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    docs_path = sys.argv[2] if len(sys.argv) > 2 else ""

    docs_root = find_docs_root(docs_path)
    run_dir = _resolve_run_dir(run_dir_arg, docs_root)
    if run_dir is None or not (run_dir / "events.jsonl").is_file():
        print(json.dumps({
            "run_digest": {"error": "no run with events.jsonl found", "run_dir": str(run_dir or "")},
            "run_dir": str(run_dir or ""),
        }))
        return

    events = _load_events(run_dir)

    enters: dict[str, int] = {}
    order: list[str] = []
    open_enter: dict[str, datetime] = {}
    durations: list[tuple[str, float]] = []
    all_ts: list[datetime] = []
    for e in events:
        node = e.get("node")
        scope = e.get("_scope", "")
        key = f"{scope}/{node}" if scope else node
        ts = _parse_ts(e.get("ts", ""))
        if ts:
            all_ts.append(ts)
        if e.get("phase") == "enter":
            enters[key] = enters.get(key, 0) + 1
            order.append(key)
            open_enter[key] = ts
        elif e.get("phase") == "done":
            st = open_enter.get(key)
            if st and ts:
                durations.append((key, (ts - st).total_seconds()))

    loops = sorted(
        [{"node": n, "entered": c} for n, c in enters.items() if c > 1],
        key=lambda x: -x["entered"],
    )
    slow_nodes = [
        {"node": n, "seconds": round(s)}
        for n, s in sorted(durations, key=lambda x: -x[1])[:10]
    ]
    wall = round((max(all_ts) - min(all_ts)).total_seconds()) if len(all_ts) >= 2 else 0

    sessions: dict[str, str] = {}
    for sid_file in run_dir.rglob(".session_id"):
        try:
            rel = str(sid_file.parent.relative_to(run_dir))
            sessions[rel] = sid_file.read_text(encoding="utf-8").strip()
        except OSError:
            continue

    digest = {
        "run_dir": str(run_dir),
        "run_id": run_dir.name,
        "total_node_visits": len(order),
        "wall_time_seconds": wall,
        # The core signals reflection needs but final artifacts hide:
        "loops": loops,            # node entered >1 → a loop (which pair spun, how many times)
        "slow_nodes": slow_nodes,  # longest enter→done → stalls / cost hot-spots
        "path_tail": order[-30:],  # the recent node sequence (how it actually flowed)
        "sessions": sessions,      # scope → opencode session id (deep-dive into transcripts)
        "hint": ("Read events.jsonl and the per-node prompt.md/output.json under run_dir "
                 "for detail; .session_id points at the full opencode transcript in its store."),
    }
    print(json.dumps({"run_digest": digest, "run_dir": str(run_dir)}))


if __name__ == "__main__":
    main()
