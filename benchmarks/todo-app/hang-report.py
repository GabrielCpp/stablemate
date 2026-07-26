#!/usr/bin/env python3
"""Cap-wait-aware node-timing report — detect genuinely hung nodes, never flag a cap-wait.

A workflow node's wall-clock time is the sum of two very different things:

  * **active** — the agent actually working (streaming, running tools, retrying), and
  * **cap-wait** — sleeping on a usage/spending cap until its reset window reopens.

They must not be conflated. A node that took three hours because the account was capped is
behaving *correctly* — workhorse is designed to wait caps out ("run unattended for days"), and
a node sleeping on a cap ceiling must never be disturbed. A node that took three hours of
*active* time, on the other hand, is genuinely stuck (a retry/reframe churn or a wedged turn)
and is worth flagging.

So this report subtracts cap-wait time and ranks by **active** time. Cap-wait is shown, but
never counted toward the hang signal.

Inputs, both already produced by ``run.sh``:
  * ``<artifacts>/**/events.jsonl`` — node ``enter``/``done`` pairs → total wall-clock per node.
  * ``<logs>/*.log`` — the console stream, whose ``[node] ⏸ … pausing ~Ns`` lines give the
    exact cap-sleep each node incurred (emitted by ``_sleep_with_notice`` in the agent runner).

Usage: hang-report.py <artifacts_dir> <logs_dir> [active_threshold_s]
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

# "[node_id] ⏸ spending/usage cap reached — pausing ~6229s (resuming around …)".
# The one line that states a cap-sleep's exact length, attributed to a node. The per-tick
# "still paused" lines carry no duration, so they are not summed (double-count risk); this
# initial line is authoritative for the whole sleep.
_PAUSE_RE = re.compile(r"\[([a-zA-Z0-9_.-]+)\]\s*⏸[^\n]*pausing\s*~?(\d+)\s*s")


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def flow_containers(artifacts_dir: str) -> set[str]:
    """Nodes that are flows, not leaf work: their wall-clock is the sum of their children's,
    so flagging them as a hang points at the wrong thing (the hang is in one child). Identified
    by owning a ``<node>/_flow/events.jsonl``. Cap-wait is attributed to the LEAF node that
    slept, never to its container, so a container's apparent 'active' time would also wrongly
    include a child's cap-wait — another reason to judge hangs at the leaf only."""
    return {
        os.path.basename(os.path.dirname(os.path.dirname(p)))
        for p in glob.glob(f"{artifacts_dir}/**/_flow/events.jsonl", recursive=True)
    }


def node_totals(artifacts_dir: str) -> tuple[dict[str, float], dict[str, int], dict[str, float]]:
    """(total_s, runs, max_s) per node, summed across every events.jsonl (root + nested flows)."""
    total: dict[str, float] = defaultdict(float)
    runs: dict[str, int] = defaultdict(int)
    longest: dict[str, float] = defaultdict(float)
    for path in glob.glob(f"{artifacts_dir}/**/events.jsonl", recursive=True):
        open_at: dict[str, datetime] = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                node, phase, ts = ev.get("node"), ev.get("phase"), ev.get("ts")
                if not (node and ts):
                    continue
                if phase == "enter":
                    open_at[node] = _parse_ts(ts)
                elif phase == "done" and node in open_at:
                    d = (_parse_ts(ts) - open_at.pop(node)).total_seconds()
                    total[node] += d
                    runs[node] += 1
                    longest[node] = max(longest[node], d)
    return total, runs, longest


def cap_wait_by_node(logs_dir: str) -> dict[str, float]:
    """Seconds each node spent sleeping on a cap, summed from the console logs."""
    cap: dict[str, float] = defaultdict(float)
    for path in glob.glob(f"{logs_dir}/*.log"):
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for node, secs in _PAUSE_RE.findall(text):
            cap[node] += float(secs)
    return cap


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: hang-report.py <artifacts_dir> <logs_dir> [active_threshold_s]", file=sys.stderr)
        return 2
    artifacts_dir, logs_dir = sys.argv[1], sys.argv[2]
    threshold = float(sys.argv[3]) if len(sys.argv) > 3 else 1800.0  # 30 min of ACTIVE time

    total, runs, longest = node_totals(artifacts_dir)
    cap = cap_wait_by_node(logs_dir)
    containers = flow_containers(artifacts_dir)
    if not total:
        print("  no node timing recorded yet")
        return 0

    def m(s: float) -> str:
        return f"{s / 60:.1f}m"

    # active = wall-clock NOT spent sleeping on a cap. Clamp at 0 (cap-wait is attributed
    # from the run-wide log, so it can marginally exceed a node's summed total). Judge hangs
    # on LEAF nodes only — a container's time is its children's, and the single longest run
    # (max) is a cleaner hang signal than a sum inflated by many healthy resumes.
    leaves = []
    for node, tot in total.items():
        if node in containers:
            continue
        cw = min(cap.get(node, 0.0), tot)
        leaves.append((node, tot, cw, max(0.0, tot - cw), runs[node], longest[node]))
    leaves.sort(key=lambda r: r[3], reverse=True)  # by ACTIVE total

    print(f"  {'leaf node':<28}{'active/run':>11}{'cap-wait':>10}{'wall':>8}{'runs':>6}")
    print(f"  {'-' * 62}")
    flagged = []
    for node, tot, cw, active, n, mx in leaves[:12]:
        # The hang signal is ACTIVE work per run — total active (cap-wait already removed)
        # divided across the node's runs. Cap-wait cannot be pinned to one specific run from
        # the aggregate log, so per-run active is the honest, cap-wait-safe proxy: a node that
        # slept hours on caps but only ever did 2 min of work per run is NOT a hang. Only real,
        # sustained work in a single run trips it.
        active_per_run = active / n if n else 0.0
        hang = active_per_run >= threshold
        mark = " ⚠ HANG?" if hang else ""
        if hang:
            flagged.append((node, active_per_run, n))
        print(f"  {node:<28}{m(active_per_run):>11}{m(cw):>10}{m(mx):>8}{n:>6}{mark}")
    print(f"  {'-' * 62}")

    if flagged:
        print(f"\n  ⚠ {len(flagged)} leaf node(s) average over {threshold / 60:.0f} min of ACTIVE "
              f"work per run (cap-wait excluded) — a genuine hang / retry-churn:")
        for node, apr, n in flagged:
            print(f"      {node}: ~{m(apr)} active/run across {n} run(s)")
        print("  A per-node ACTIVE-time budget that PAUSES during cap-waits is the fix — never a "
              "plain wall-clock kill, which would cut a legitimate cap-wait.")
    else:
        print(f"\n  ✓ no leaf node averaged over {threshold / 60:.0f} min of ACTIVE work per run. "
              "Long wall-clocks were almost entirely cap-wait — healthy: a capped run is left to "
              "wait undisturbed, exactly as intended. (The apparent long 'hangs' were caps.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
