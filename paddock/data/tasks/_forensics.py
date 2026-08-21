"""Run-dir forensics: what the machinery did, read back off what a round staged.

Three task families ask the same questions of a `runs/` tree — did the run get there on
its own, how many laps did each node take, where did the wall clock go — and the answers
are the same computation in all three. The greenfield round asks it of a whole build, the
frozen-app round of a single-story QA trial, and the replay round of a story bouncing
around a review loop. None of it knows which app it is reading, and none of it needs the
answer key, which is why it is one module rather than three copies drifting apart.

Everything here is **read-only** over a staged result: paths in, numbers out. A score
function may call all of it (paddock decision 14) and a sealed zip can be re-scored later
without re-running anything.

The leading underscore keeps `paddock.loader` from treating this as a task module.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from _stablemate import TrialError


# ── the vocabulary ────────────────────────────────────────────────────────────────────

# Nodes that only ever run because something upstream failed. Reaching one is not an
# error — the bounded loops exist so a run can recover — but it means the deterministic
# path did not hold, which is what the reliability half of this report is about.
REPAIR_NODES = {
    "fix_genesis", "fix_story", "fix_ci", "fix_merge", "setup_fix", "fix_knowledge",
    "rework_story", "rework_epics", "apply_review", "apply_qa_fixes",
}
# Worse than a rework: the auto-resolver agents that stand in for a human at an operator
# gate. Reaching one means the run exhausted its bounded retries and, with
# `operator_mode: human`, would have HALTED for a person. Counting them as ordinary
# reworks would hide that — an unattended benchmark can otherwise sail straight through
# every point where it should have stopped and asked.
ESCALATION_NODES = {
    "resolve_coverage", "resolve_epics", "resolve_integrity", "resolve_reconcile",
    "resolve_split", "resolve_write_epic",
    "resolve_write_story", "await_operator", "qa_give_up",
}

# "[node_id] ⏸ spending/usage cap reached — pausing ~6229s (resuming around …)". The one
# line that states a cap-sleep's exact length, attributed to a node. The per-tick "still
# paused" lines carry no duration, so they are not summed (double-count risk); this
# initial line is authoritative for the whole sleep.
PAUSE_RE = re.compile(r"\[([a-zA-Z0-9_.-]+)\]\s*⏸[^\n]*pausing\s*~?(\d+)\s*s")

#: The nodes the round exists to move. Others still print — a change that fixes one loop
#: by pushing the work into another has not fixed anything — but these are the headline.
WATCHED = ("plan-qa", "audit-qa", "document-story", "review-story-documentation")

#: The deterministic node that drives the product: the QA plan actually executing against
#: a running app. Its share of the trial's wall clock is the time-leverage numerator —
#: everything else is the loop talking to itself about what it is going to do.
DRIVING_NODE = "run_qa_plan"


# ── reliability: did the machinery get there on its own? ──────────────────────────────


def workflow_src(checkout: Path) -> Path:
    """The workflow source tree, located only to *date* the code a round was produced by.

    A report that can describe a round older than the code under test is the same vacuous
    success it exists to detect, one level up. Measured off a directory whose absence is
    loud rather than a glob whose emptiness is not — the previous spelling was a glob for
    the deleted YAML layout, it matched nothing, and every staleness verdict silently
    became False in exactly the way the check was written to catch.
    """
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
    """One row per recorded run: nodes entered, repair loops, escalations, staleness.

    The reliability question is not "did a valid repo appear" but "did the machinery get
    there without hand-holding". Those come apart: a run that needed an agent to diagnose
    and repair a deterministic gap still ends with a valid repo, and reading only the end
    state scores that as success.
    """
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
    """Node cycles that repeat back-to-back in one entry sequence — the churn signal.

    Churn is *not* "a node ran many times": a loop over a queue re-enters `implement` once
    per story, and that is the workflow working. Churn is the same short cycle repeating
    with nothing else between — `plan → implement → plan → implement → …`, or a single node
    re-entered three times running. That distinguishes a run advancing through a queue from
    one orbiting a state it cannot leave, and it needs to know nothing about any particular
    workflow's node names to say so.

    Reported per cycle rather than per node because the two failure modes it separates need
    different fixes: a period-1 cycle is a node retrying itself, a period-2+ cycle is a
    transition condition that never becomes false.
    """
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
            # Longest span wins, so `a b a b a b` is reported as one 3× period-2 cycle
            # rather than as the period-1 non-cycle it also technically is not.
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
    """Every repeating cycle across every events file, flows included.

    Flow files are walked too, unlike `read_runs`: a subflow spinning is the case worth
    catching, and it is invisible from the parent, which sees one long-running container
    node and no repetition at all.
    """
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
    """Nodes that are flows, not leaf work.

    Their wall-clock is the sum of their children's, so flagging one as a hang points at
    the wrong thing (the hang is in one child). Cap-wait is attributed to the LEAF that
    slept, never to its container, so a container's "active" time would also wrongly
    include a child's cap-wait.
    """
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
    """Leaf nodes ranked by ACTIVE time per run, cap-wait subtracted.

    A node's wall-clock is two very different things: **active** (the agent working) and
    **cap-wait** (sleeping on a usage cap until its window reopens). A node that took three
    hours because the account was capped is behaving *correctly* — workhorse waits caps out
    by design, and a node on a cap ceiling must never be disturbed. A node that took three
    hours of *active* time is genuinely stuck. So cap-wait is shown but never counted
    toward the hang signal.

    Cap-wait cannot be pinned to one specific run from the aggregate log, so active *per
    run* is the honest, cap-wait-safe proxy: a node that slept for hours on caps but only
    ever did two minutes of work per run is not a hang.
    """
    total, runs, longest = node_totals(runs_root)
    cap = cap_wait_by_node(artifacts)
    containers = flow_containers(runs_root)
    out: list[dict[str, Any]] = []
    for node, spent in total.items():
        if node in containers:
            continue
        # Clamp: cap-wait is attributed from the run-wide log, so it can marginally exceed
        # a node's summed total.
        waited = min(cap.get(node, 0.0), spent)
        active = max(0.0, spent - waited)
        per_run = active / runs[node] if runs[node] else 0.0
        out.append({"node": node, "active_per_run": per_run, "cap_wait": waited,
                    "longest": longest[node], "runs": runs[node],
                    "hang": per_run >= threshold_s})
    return sorted(out, key=lambda r: -float(r["active_per_run"]))


# ── convergence: how many laps, at what cost, against how much wall clock ─────────────


def timing_of(run_id: str, wall_s: float) -> dict[str, Any]:
    """Per-trial wall clock, the run's own time partition, and per-node seconds.

    Two clocks on purpose. `wall_s` is measured around the subprocess and includes
    everything the harness paid for — materialization, compose bring-up, the run, the
    teardown. groom's partition is what happened *inside* the run, and it is the only one
    that can separate the agent thinking from the product being driven.

    Per-node seconds come from the spans directly rather than from `node_costs`, which
    counts `agent_turn` spans only: the node this instrument is about, `run_qa_plan`, is
    deterministic and has no turn under it. A node span is named after its node, so
    selecting `name == node` sums each node once instead of once per nested turn.
    """
    from groom import store

    profile = store.run_profile(run_id) or {}
    nodes: dict[str, float] = {}
    for span in store.query_spans(run=run_id, limit=100000):
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


def laps_of(run_id: str) -> list[dict[str, Any]]:
    """This trial's per-node lap rows, persisted so the round can be re-scored later.

    `min_work_items=1` because a trial is ONE story, so every node has exactly one work
    item; `groom loops`' default of 3 exists to keep one-off nodes out of a whole-machine
    report and would silence this one entirely.
    """
    from groom import store

    keep = ("node", "work_items", "turns", "max_laps", "cost_usd", "est_cost_usd")
    return [
        {key: row.get(key) for key in keep}
        for row in store.loop_convergence(run=run_id, min_work_items=1)
    ]


def money(rows: list[dict[str, Any]]) -> str:
    """`$0.94`, or `~$0.71` when the estimate is standing in, or `$?` when neither exists.

    `?` rather than `$0.00`: a backend that reports nothing and a model the rate card does
    not name leave the round genuinely unpriced, and a zero there is a claim. A backend
    under subscription auth reports a literal `$0` over millions of tokens, which is not a
    cheap round, it is an unpriced one.
    """
    billed = sum(row.get("cost_usd") or 0.0 for row in rows)
    if billed:
        return f"${billed:.2f}"
    estimated = sum(row.get("est_cost_usd") or 0.0 for row in rows)
    return f"~${estimated:.2f}" if estimated else "$?"


def convergence(trials: list[dict[str, Any]]) -> str:
    """The cost half of the headline: `| plan-qa 2.1 laps ~$0.94`, pooled over the round.

    Detection and convergence belong on one line because either alone is gameable in the
    direction of the other — a flow that refutes everything catches every defect and never
    terminates, and one that approves everything converges in a single lap.
    """
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
    """`time-leverage: 8% (12m driving / 148m)` — the product-facing share of the round.

    The question the number answers is what a QA lane spends its hour on. `run_qa_plan` is
    the only node that touches the running application; everything else is the loop
    authoring, reviewing and repairing its intention to do so. A round that catches every
    defect at 3% time-leverage and one that catches them at 30% are the same scorecard and
    very different products, which is the same reason the leverage line sits under the
    detection line rather than replacing it.

    Wall clock is summed across trials rather than measured end to end: the round is
    sequential today, and a sum stays honest if it ever stops being.
    """
    wall = sum(float((trial.get("timing") or {}).get("wall_s") or 0.0) for trial in trials)
    driving = sum(float((trial.get("timing") or {}).get("driving_s") or 0.0) for trial in trials)
    if not wall:
        return ""
    return (
        f"time-leverage: {driving / wall:.0%} "
        f"({driving / 60:.0f}m driving / {wall / 60:.0f}m)"
    )


def node_table(trials: list[dict[str, Any]]) -> list[str]:
    """The per-node convergence table, pooled over every trial in the round.

    Laps are summed rather than averaged, which is the right aggregation for this
    statistic: the exit rate is a per-lap acceptance probability, and pooling the laps is
    its maximum-likelihood estimate over the whole sample. Averaging per-trial rates would
    weight a one-lap story the same as a thirteen-lap one.
    """
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


# ── the lines these numbers become ───────────────────────────────────────────────────


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
