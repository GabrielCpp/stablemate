"""Run-dir forensics: what the machinery did, read back off what a round staged."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from _stablemate import TrialError



REPAIR_NODES = {
    "fix_genesis", "fix_story", "fix_ci", "fix_merge", "setup_fix", "fix_knowledge",
    "rework_story", "rework_epics", "apply_review", "apply_qa_fixes",
}
ESCALATION_NODES = {
    "resolve_coverage", "resolve_epics", "resolve_integrity", "resolve_reconcile",
    "resolve_split", "resolve_write_epic",
    "resolve_write_story", "await_operator", "qa_give_up",
}

PAUSE_RE = re.compile(r"\[([a-zA-Z0-9_.-]+)\]\s*⏸[^\n]*pausing\s*~?(\d+)\s*s")

WATCHED = ("plan-qa", "audit-qa", "document-story", "review-story-documentation")

DRIVING_NODE = "run_qa_plan"




def workflow_src(checkout: Path) -> Path:
    """The workflow source tree, located only to *date* the code a round was produced by."""
    source = checkout / "workflows" / "src" / "workhorse_workflows"
    if not source.is_dir():
        raise TrialError(f"no workflow source at {source} — the round is out of date with the tree")
    return source


def newest_source_mtime(checkout: Path) -> float:
    return max(
        (f.stat().st_mtime
         for pat in ("**/*.py", "**/*.md", "**/*.j2")
         for f in workflow_src(checkout).glob(pat)
         if "__pycache__" not in f.parts),
        default=0.0,
    )


def read_runs(runs_root: Path, checkout: Path) -> list[dict[str, Any]]:
    """One row per recorded run: nodes entered, repair loops, escalations, staleness."""
    newest = newest_source_mtime(checkout)
    rows: list[dict[str, Any]] = []
    for directory in sorted(p for p in runs_root.glob("*") if p.is_dir()):
        events = directory / "events.jsonl"
        if not events.is_file():
            continue
        entered: list[str] = []
        repairs: list[str] = []
        escalations: list[str] = []
        failed = False
        for node in entered_nodes(events):
            entered.append(node)
            repairs += [node] if node in REPAIR_NODES else []
            escalations += [node] if node in ESCALATION_NODES else []
            failed = failed or node.endswith("_failed")
        rows.append({
            "run": directory.name, "nodes": len(entered), "repairs": repairs,
            "escalations": escalations, "failed": failed,
            "stale": bool(newest) and events.stat().st_mtime < newest,
        })
    return rows


def entered_nodes(events: Path) -> list[str]:
    """The node ids one events file entered, in order."""
    out: list[str] = []
    for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("phase") == "enter" and event.get("node"):
            out.append(str(event["node"]))
    return out


def cycles(entered: list[str], max_period: int = 4, min_repeats: int = 3) -> list[dict[str, Any]]:
    """Node cycles that repeat back-to-back in one entry sequence — the churn signal."""
    found: dict[tuple[str, ...], int] = {}
    i, n = 0, len(entered)
    while i < n:
        best: tuple[int, int] | None = None
        for p in range(1, max_period + 1):
            window = entered[i:i + p]
            if len(window) < p:
                break
            reps = 1
            while entered[i + reps * p: i + (reps + 1) * p] == window:
                reps += 1
            if reps >= min_repeats and (best is None or reps * p > best[0] * best[1]):
                best = (p, reps)
        if best is None:
            i += 1
            continue
        p, reps = best
        key = tuple(entered[i:i + p])
        found[key] = max(found.get(key, 0), reps)
        i += p * reps
    return [{"cycle": list(k), "repeats": v}
            for k, v in sorted(found.items(), key=lambda kv: -kv[1])]


def churn_candidates(runs_root: Path) -> list[dict[str, Any]]:
    """Every repeating cycle across every events file, flows included."""
    out: list[dict[str, Any]] = []
    root = runs_root
    for path in sorted(root.glob("**/events.jsonl")):
        where = path.parent.relative_to(root)
        for cycle in cycles(entered_nodes(path)):
            out.append({"where": str(where), **cycle})
    return sorted(out, key=lambda r: -int(r["repeats"]))


def node_totals(artifacts: Path) -> tuple[dict[str, float], dict[str, int], dict[str, float]]:
    """(total_s, runs, longest_s) per node, summed across every events.jsonl."""
    total: dict[str, float] = defaultdict(float)
    runs: dict[str, int] = defaultdict(int)
    longest: dict[str, float] = defaultdict(float)
    for path in artifacts.glob("**/events.jsonl"):
        open_at: dict[str, datetime] = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            node, phase, ts = event.get("node"), event.get("phase"), event.get("ts")
            if not (node and ts):
                continue
            when = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if phase == "enter":
                open_at[node] = when
            elif phase == "done" and node in open_at:
                spent = (when - open_at.pop(node)).total_seconds()
                total[node] += spent
                runs[node] += 1
                longest[node] = max(longest[node], spent)
    return total, runs, longest


def flow_containers(artifacts: Path) -> set[str]:
    """Nodes that are flows, not leaf work."""
    return {p.parent.parent.name for p in artifacts.glob("**/_flow/events.jsonl")}


def cap_wait_by_node(logs: Path) -> dict[str, float]:
    """Seconds each node spent sleeping on a usage cap, summed from the staged logs."""
    cap: dict[str, float] = defaultdict(float)
    for path in logs.glob("**/*.log"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for node, secs in PAUSE_RE.findall(text):
            cap[node] += float(secs)
    return cap


def hang_candidates(
    runs_root: Path, artifacts: Path, threshold_s: float = 1800.0
) -> list[dict[str, Any]]:
    """Leaf nodes ranked by ACTIVE time per run, cap-wait subtracted."""
    total, runs, longest = node_totals(runs_root)
    cap = cap_wait_by_node(artifacts)
    containers = flow_containers(runs_root)
    out: list[dict[str, Any]] = []
    for node, spent in total.items():
        if node in containers:
            continue
        waited = min(cap.get(node, 0.0), spent)
        active = max(0.0, spent - waited)
        per_run = active / runs[node] if runs[node] else 0.0
        out.append({"node": node, "active_per_run": per_run, "cap_wait": waited,
                    "longest": longest[node], "runs": runs[node],
                    "hang": per_run >= threshold_s})
    return sorted(out, key=lambda r: -float(r["active_per_run"]))




def timing_of(run_id: str, wall_s: float, since_ts: float = 0.0) -> dict[str, Any]:
    """Per-trial wall clock, the run's own time partition, and per-node seconds."""
    from groom import store

    profile = store.run_profile(run_id) or {}
    nodes: dict[str, float] = {}
    for span in store.query_spans(run=run_id, limit=100000, since_ts=since_ts or None):
        if span.get("name") != span.get("node") or not span.get("node"):
            continue
        seconds = float(span.get("end_ts") or 0.0) - float(span.get("start_ts") or 0.0)
        if seconds > 0:
            nodes[str(span["node"])] = nodes.get(str(span["node"]), 0.0) + seconds
    return {
        "wall_s": round(wall_s, 1),
        "time_s": {
            key: round(value, 1)
            for key, value in (profile.get("time_s") or {}).items()
            if isinstance(value, (int, float))
        },
        "nodes_s": {node: round(seconds, 1) for node, seconds in sorted(nodes.items())},
        "driving_s": round(nodes.get(DRIVING_NODE, 0.0), 1),
    }


def laps_of(run_id: str, since_ts: float = 0.0) -> list[dict[str, Any]]:
    """This trial's per-node lap rows, persisted so the round can be re-scored later."""
    from groom import store

    keep = ("node", "work_items", "turns", "max_laps", "cost_usd", "est_cost_usd")
    return [
        {key: row.get(key) for key in keep}
        for row in store.loop_convergence(
            run=run_id, min_work_items=1, since_ts=since_ts or None
        )
    ]


def money(rows: list[dict[str, Any]]) -> str:
    """`$0.94`, or `~$0.71` when the estimate is standing in, or `$?` when neither exists."""
    billed = sum(row.get("cost_usd") or 0.0 for row in rows)
    if billed:
        return f"${billed:.2f}"
    estimated = sum(row.get("est_cost_usd") or 0.0 for row in rows)
    return f"~${estimated:.2f}" if estimated else "$?"


def convergence(trials: list[dict[str, Any]]) -> str:
    """The cost half of the headline: `| plan-qa 2.1 laps ~$0.94`, pooled over the round."""
    rows = [
        row
        for trial in trials
        for row in (trial.get("laps") or [])
        if row.get("node") == "plan-qa"
    ]
    if not rows:
        return ""
    items = sum(row.get("work_items") or 0 for row in rows)
    turns = sum(row.get("turns") or 0 for row in rows)
    return f" | plan-qa {turns / items:.1f} laps {money(rows)}" if items else ""


def time_leverage(trials: list[dict[str, Any]]) -> str:
    """`time-leverage: 8% (12m driving / 148m)` — the product-facing share of the round."""
    wall = sum(float((trial.get("timing") or {}).get("wall_s") or 0.0) for trial in trials)
    driving = sum(float((trial.get("timing") or {}).get("driving_s") or 0.0) for trial in trials)
    if not wall:
        return ""
    return (
        f"time-leverage: {driving / wall:.0%} "
        f"({driving / 60:.0f}m driving / {wall / 60:.0f}m)"
    )


def node_table(trials: list[dict[str, Any]]) -> list[str]:
    """The per-node convergence table, pooled over every trial in the round."""
    pooled: dict[str, list[dict[str, Any]]] = {}
    seconds: dict[str, float] = {}
    for trial in trials:
        for row in trial.get("laps") or []:
            pooled.setdefault(str(row.get("node")), []).append(row)
        for node, value in ((trial.get("timing") or {}).get("nodes_s") or {}).items():
            seconds[node] = seconds.get(node, 0.0) + float(value)
    if not pooled:
        return ["no laps recorded — did the runs reach an agent turn?"]

    lines = [f"  {'node':<30} {'items':>5} {'turns':>5} {'exit':>6} {'mean':>5} "
             f"{'max':>4} {'cost$':>8} {'min':>6}"]
    order = sorted(
        pooled.items(),
        key=lambda kv: (kv[0] not in WATCHED, -sum(row.get("turns") or 0 for row in kv[1])),
    )
    for node, rows in order:
        items = sum(row.get("work_items") or 0 for row in rows)
        turns = sum(row.get("turns") or 0 for row in rows)
        if not items or not turns:
            continue
        mark = "*" if node in WATCHED else " "
        lines.append(
            f"{mark} {node:<30} {items:>5} {turns:>5} {items / turns:>5.0%} "
            f"{turns / items:>5.2f} {max(row.get('max_laps') or 0 for row in rows):>4} "
            f"{money(rows):>8} {seconds.get(node, 0.0) / 60:>6.1f}"
        )
    excess = sum(
        (row.get("turns") or 0) - (row.get("work_items") or 0)
        for rows in pooled.values()
        for row in rows
    )
    every = [row for rows in pooled.values() for row in rows]
    lines.append(f"  {'-' * 75}")
    lines.append(
        f"  {'TOTAL':<30} {'':>5} {'':>5} {'':>6} {'':>5} {'':>4} {money(every):>8} "
        f"{'':>6}   ({excess} excess turns)"
    )
    return lines




def minutes(seconds: float) -> str:
    return f"{seconds / 60:.1f}m"


def reliability_lines(rows: list[dict[str, Any]]) -> list[str]:
    lines = ["", "  machinery reliability"]
    if not rows:
        return [*lines, "  no runs recorded yet"]
    for r in rows:
        status = ("FAILED" if r["failed"] else "ESCALATED" if r["escalations"]
                  else "repaired" if r["repairs"] else "clean")
        mark = {"clean": "✓", "repaired": "⚠", "ESCALATED": "⚠", "FAILED": "✗"}[status]
        bits = []
        if r["repairs"]:
            bits.append(f"{', '.join(sorted(set(r['repairs'])))} x{len(r['repairs'])}")
        if r["escalations"]:
            bits.append(f"would-halt: {', '.join(sorted(set(r['escalations'])))} "
                        f"x{len(r['escalations'])}")
        note = f"  ({'; '.join(bits)})" if bits else ""
        lines.append(f"  {mark} {str(r['run']):<40} {r['nodes']:>3} nodes  {status}{note}")

    stale = [str(r["run"]) for r in rows if r["stale"]]
    if stale:
        lines.append(f"  ✗ {len(stale)} run(s) PREDATE the current workflow source and say")
        lines.append("    nothing about it. Re-run before trusting any score above:")
        lines.extend(f"      - {name}" for name in stale)

    clean = sum(1 for r in rows if not r["repairs"] and not r["escalations"] and not r["failed"])
    repairs = sum(len(r["repairs"]) for r in rows)
    escalations = sum(len(r["escalations"]) for r in rows)
    lines.append(f"  {clean}/{len(rows)} run(s) completed with no repair loop.")
    if repairs:
        lines.append(f"  {repairs} repair-loop entr(y/ies) — each one is a workflow defect, not")
        lines.append("  a successful recovery. A clean re-run is the only proof a fix landed.")
    if escalations:
        lines.append(f"  {escalations} operator-gate escalation(s) — with operator_mode=human")
        lines.append("  this run would have STOPPED and asked. Unattended, it resolved itself.")
    return lines


def timing_lines(nodes: list[dict[str, Any]]) -> list[str]:
    lines = ["", "  node timing (hangs vs cap-waits)"]
    if not nodes:
        return [*lines, "  no node timing recorded yet"]
    lines.append(f"  {'leaf node':<28}{'active/run':>11}{'cap-wait':>10}{'wall':>8}{'runs':>6}")
    lines.append(f"  {'-' * 63}")
    for n in nodes[:12]:
        lines.append(
            f"  {str(n['node']):<28}{minutes(float(n['active_per_run'])):>11}"
            f"{minutes(float(n['cap_wait'])):>10}{minutes(float(n['longest'])):>8}"
            f"{n['runs']:>6}{' ⚠ HANG?' if n['hang'] else ''}"
        )
    flagged = [n for n in nodes if n["hang"]]
    if flagged:
        lines.append(f"  ⚠ {len(flagged)} leaf node(s) average over 30 min of ACTIVE work per")
        lines.append("  run (cap-wait excluded) — a genuine hang / retry-churn. A per-node")
        lines.append("  ACTIVE-time budget that PAUSES during cap-waits is the fix — never a")
        lines.append("  wall-clock kill, which would cut a legitimate cap-wait.")
    else:
        lines.append("  ✓ no leaf node averaged over 30 min of ACTIVE work per run. Long")
        lines.append("  wall-clocks were cap-wait — healthy: a capped run waits undisturbed.")
    return lines
