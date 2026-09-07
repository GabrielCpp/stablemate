"""The program dossier: what a program-level review is judged on, computed with zero
model calls.

The failure this module exists for is a loop that can see one gate at a time. Every
gate-level state here is sound — the measurement runs outside the turn, the fault locus
is decided from the traceback, the repair budgets are capped — and a program can still
spend two months on KILLED → revive → REOPENED → apparatus rework with its frozen metric
unmoved, because nothing in the loop ever *counted*. The lead reviewing a kill is shown
one gate doc, by path. It is not shown that this is the fourth kill, that the metric
last moved seven weeks ago, or that the effect the target demands is smaller than the
seed noise of the eval it is measured on.

So this module counts. It reads the program folder — the README's frozen target, the
progress file's status tables and dated entries, `jobs/*/result.json`, the ledger, the
history sidecar — and produces one `Dossier`: a metric series with dates, the per-seed
spread against the required effect, kill/revive/apparatus counts, code churn per gate,
results still pending, and a list of *circling triggers* evaluated in code. The prompt
that reads it judges; it does not recompute.

Two rules:

* **Every parser is best-effort.** Progress files are prose. A row that does not parse,
  a section with no date, a job with no `result.json` — each lands in `unparsed` and
  the review is told, rather than raising and taking the run with it.
* **The thresholds live here**, as module constants the workflow imports, so a test
  patches one place and a reader finds the numbers beside the rule that uses them.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean, pstdev

if __name__ == "__main__":  # pragma: no cover
    # `python -m …dossier` would execute this file a second time under `__main__` and
    # register `build_dossier` twice on the blueprint; run the imported copy instead.
    import sys

    from workhorse_workflows.research.nodes.dossier import _main as _imported_main

    _imported_main()
    sys.exit(0)

from workhorse_workflows.research.nodes._blueprint import blueprint
from workhorse_workflows.research.nodes.history import (
    bootstrap_history,
    history_path,
    read_history,
)
from workhorse_workflows.research.schemas import (
    Dossier,
    FrozenTarget,
    GateRow,
    HistoryEvent,
    JobSummary,
    MetricPoint,
    Resolvability,
)

# ── the numbers behind the triggers ─────────────────────────────────────────

#: Required effect must be at least this many pooled standard errors to be told from
#: seed noise. Two is the conventional floor; below it a program can produce nulls
#: forever without any of them being a finding.
K_RESOLVABLE = 2.0
#: Days without the frozen metric improving before the program counts as stale.
STALE_DAYS = 21
#: Concluded gates (pass or kill) without the metric improving — the same thing,
#: counted in work rather than in time.
STALE_CYCLES = 4
#: Kill → revive laps on the program before that is itself the finding.
APPARATUS_CYCLES = 2
#: Days to the frozen deadline under which a stale program is under pressure.
DEADLINE_DAYS = 45
#: Lead reviews spent at which the loop is looping on a question its ladder cannot
#: settle. Mirrors `workflow.MAX_LEAD_REVIEWS`; kept here so the trigger has no import
#: back into the workflow.
LEAD_REVIEWS_EXHAUSTED = 4

_DATE = r"\d{4}-\d{2}-\d{2}"
_FRACTION = re.compile(r"~?\s*(\d+)\s*/\s*(\d+)")
_GATE_ID = re.compile(r"\b([A-Z]{1,2}\d+[a-z]?(?:-[a-z]+)?)\b")
_SEEDS = re.compile(r"\{\s*(\d+(?:\s*,\s*\d+)*)\s*\}")
_DATED_HEADING = re.compile(rf"^#{{2,3}}\s+(.*?)({_DATE})(.*)$")
_TABLE_SEP = re.compile(r"^\|?\s*:?-{2,}")
_SEED_FAMILY = re.compile(r"^(.*?)_seed(\d+)$")
_FLAG_NAME = re.compile(r"(_blocked|_flag|_tension|^leak|_leak)", re.IGNORECASE)
_PENDING = re.compile(r"\bPENDING\b|unexploited|[Nn]ot yet run|\b(IN PROGRESS|in progress)\b")
_SUPERSEDED_HEADING = re.compile(r"previous|superseded|retained historical", re.IGNORECASE)
#: A fraction that names the target rather than reporting a measurement: `>= 93/147`,
#: "the PASS level of 96/147", "criterion C < 93/147".
_TARGET_CONTEXT = re.compile(r"(>=|≥|<=|≤|<|>|level of|criterion|threshold|target|bar of)\s*`?\s*$")


# ── small helpers ───────────────────────────────────────────────────────────


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _strip_md(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    return text.replace("**", "").replace("`", "").strip()


def _parse_date(text: str) -> date | None:
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _fraction(text: str, n: int = 0) -> tuple[int, int]:
    """The first `N/D` in `text`, restricted to denominator `n` when given."""
    for m in _FRACTION.finditer(text):
        count, denom = int(m.group(1)), int(m.group(2))
        if denom and (not n or denom == n):
            return count, denom
    return 0, 0


def _sections(text: str, heading: str) -> str:
    """The body under the first heading whose text contains `heading` (any level)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#") and heading.lower() in line.lower():
            level = len(line) - len(line.lstrip("#"))
            body: list[str] = []
            for nxt in lines[i + 1 :]:
                if nxt.startswith("#") and (len(nxt) - len(nxt.lstrip("#"))) <= level:
                    break
                body.append(nxt)
            return "\n".join(body)
    return ""


# ── the README ──────────────────────────────────────────────────────────────


def parse_frozen_target(readme: str, unparsed: list[str] | None = None) -> FrozenTarget:
    """The `Frozen target` table, as numbers.

    The baseline is looked for in a `Baseline` row first, then in the first `~N/D`
    with the target's denominator on a line that says "baseline" anywhere in the
    README — the scaffold does not stamp a baseline row, and every real program
    states one in prose.
    """
    unparsed = unparsed if unparsed is not None else []
    body = _sections(readme, "Frozen target")
    target = FrozenTarget()
    if not body:
        unparsed.append("README: no `Frozen target` section")
        return target
    rows: dict[str, str] = {}
    for line in body.splitlines():
        if not line.strip().startswith("|") or _TABLE_SEP.match(line):
            continue
        cells = _cells(line)
        if len(cells) < 2 or cells[0].lower() == "field":
            continue
        rows[cells[0].lower()] = cells[1]
    for key, value in rows.items():
        if key.startswith("metric"):
            target.metric = _strip_md(value)
        elif key.startswith("dataset"):
            target.dataset = _strip_md(value)
        elif key.startswith("threshold"):
            target.threshold = _strip_md(value)
        elif key.startswith("deadline"):
            target.deadline = _strip_md(value)
        elif key.startswith("seeds"):
            m = _SEEDS.search(value)
            if m:
                target.seeds = [int(s) for s in m.group(1).split(",")]
        elif key.startswith("baseline"):
            count, denom = _fraction(value)
            if denom:
                target.baseline_count, target.baseline_source = count, "table"
    if not target.threshold:
        unparsed.append("README: Frozen target table has no Threshold row")
        return target
    count, denom = _fraction(target.threshold)
    if denom:
        target.threshold_count, target.n = count, denom
        target.threshold_value = count / denom
    else:
        m = re.search(r"([0-9]*\.?[0-9]+)", target.threshold)
        if m:
            target.threshold_value = float(m.group(1))
        unparsed.append("README: Threshold names no `N/D` count; per-seed math disabled")
    if not target.seeds:
        m = _SEEDS.search(target.metric) or _SEEDS.search(target.dataset)
        if m:
            target.seeds = [int(s) for s in m.group(1).split(",")]
    if target.baseline_source != "table":
        for line in readme.splitlines():
            if "baseline" not in line.lower():
                continue
            count, denom = _fraction(line, target.n)
            if denom:
                target.baseline_count, target.baseline_source = count, "prose"
                break
    if target.n and target.baseline_count:
        target.baseline_value = target.baseline_count / target.n
    elif not target.baseline_count:
        unparsed.append("README: no baseline `N/D` found (table row or prose)")
    if not _parse_date(target.deadline):
        unparsed.append(f"README: Deadline {target.deadline!r} is not a date")
    return target


# ── the progress file ───────────────────────────────────────────────────────


def parse_status_table(
    progress: str, unparsed: list[str] | None = None
) -> tuple[list[GateRow], list[GateRow]]:
    """`(active_rows, superseded_rows)` from every `| Gate | ... | Status |` table.

    The first such table not under a `Previous`/`Superseded` heading is the active
    ladder; every other one is superseded evidence. A row with the wrong number of
    cells is reported, not guessed at.
    """
    unparsed = unparsed if unparsed is not None else []
    active: list[GateRow] = []
    superseded: list[GateRow] = []
    header: list[str] | None = None
    heading_superseded = False
    have_active = False
    table_is_active = False
    for lineno, line in enumerate(progress.splitlines(), 1):
        if line.startswith("#"):
            heading_superseded = bool(_SUPERSEDED_HEADING.search(line))
            header = None
            continue
        if not line.strip().startswith("|"):
            header = None
            continue
        if _TABLE_SEP.match(line):
            continue
        cells = _cells(line)
        if header is None:
            lowered = [c.lower() for c in cells]
            if any(c.startswith("gate") or c.startswith("track") for c in lowered) and any(
                "status" in c for c in lowered
            ):
                header = lowered
                table_is_active = not have_active and not heading_superseded
                if table_is_active:
                    have_active = True
            continue
        if len(cells) != len(header):
            unparsed.append(f"PROGRESS:{lineno}: row has {len(cells)} cells, header {len(header)}")
            continue
        row = GateRow()
        for name, value in zip(header, cells):
            if name.startswith("gate") or name.startswith("track"):
                m = _GATE_ID.search(_strip_md(value))
                row.gate_id = m.group(1) if m else _strip_md(value)
            elif name.startswith("document") or name.startswith("title"):
                row.document = _strip_md(value)
            elif name.startswith("depends"):
                row.depends_on = _strip_md(value)
            elif "status" in name:
                row.status = _strip_md(value)
            elif name.startswith("result") or name.startswith("preserved"):
                row.result = _strip_md(value)
            elif name.startswith("date"):
                row.date = _strip_md(value)
        (active if table_is_active else superseded).append(row)
    if not active:
        unparsed.append("PROGRESS: no active `| Gate | ... | Status |` table")
    return active, superseded


def classify_entry(title: str) -> str:
    """Which history event a dated heading records, by its title alone."""
    t = title.upper()
    if "REOPEN" in t or "WITHDR" in t:
        return "revive"
    if "MAX_REWORKS" in t or "MAX_BUILD" in t or "APPARATUS" in t or "HARNESS" in t:
        return "apparatus_kill"
    if "KILLED" in t or "KILL" in t:
        return "kill"
    if "GOAL_" in t or "PROGRAM VERDICT" in t:
        return "goal"
    if "RE-CHARTER" in t or "RECHARTER" in t:
        return "recharter"
    if "DIRECTION" in t or "STEERING" in t:
        return "new_direction"
    if "REVIEW" in t:
        return "lead_review"
    if "WEAK_PASS" in t or "PASS" in t:
        return "pass"
    if "FAIL" in t:
        return "fail"
    if "PRE-REGISTRATION" in t or "PREREG" in t:
        return "gate_selected"
    if "REWORK" in t:
        return "rework"
    return "note"


def parse_dated_entries(progress: str) -> list[HistoryEvent]:
    """Every `##`/`###` heading carrying a date, classified by keyword.

    Also the bootstrap source for `history.jsonl` on a program that predates it.
    Returned in file order; the caller sorts when it needs time order.
    """
    events: list[HistoryEvent] = []
    for line in progress.splitlines():
        m = _DATED_HEADING.match(line)
        if not m:
            continue
        title = _strip_md((m.group(1) + " " + m.group(3)).strip(" -—:–"))
        gate = _GATE_ID.search(title)
        events.append(
            HistoryEvent(
                date=m.group(2),
                event=classify_entry(title),
                gate_id=gate.group(1) if gate else "",
                note=title[:200],
                source="bootstrap",
            )
        )
    return events


def pending_results(progress: str, cap: int = 20) -> list[str]:
    """Lines that say a result is owed: PENDING, unexploited, not yet run, in progress."""
    seen: list[str] = []
    for line in progress.splitlines():
        if line.lstrip().startswith("|") or not _PENDING.search(line):
            continue
        text = _strip_md(line).strip("# ").strip()
        if not text or text in seen:
            continue
        seen.append(text[:200])
        if len(seen) >= cap:
            break
    return seen


# ── the jobs ────────────────────────────────────────────────────────────────


def _epoch_to_date(value: object) -> str:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return ""


def read_jobs(jobs_dir: Path, unparsed: list[str] | None = None) -> list[JobSummary]:
    """One summary per `jobs/<gate>/`, dry-run directories skipped."""
    unparsed = unparsed if unparsed is not None else []
    jobs: list[JobSummary] = []
    if not jobs_dir.is_dir():
        return jobs
    for gate_dir in sorted(jobs_dir.iterdir()):
        if not gate_dir.is_dir() or gate_dir.name.endswith("-dry"):
            continue
        summary = JobSummary(gate_id=gate_dir.name)
        runner = _load_json(gate_dir / "runner.json", unparsed)
        result = _load_json(gate_dir / "result.json", unparsed)
        if runner:
            summary.finished_at = _epoch_to_date(runner.get("finished_at"))
            summary.exit_code = int(runner.get("exit_code") or 0)
            summary.wall_s = float(runner.get("wall_s") or 0.0)
            summary.kill_reason = str(runner.get("kill_reason") or "")
        if result:
            summary.n_completed = int(result.get("n_completed") or 0)
            summary.n_planned = int(result.get("n_planned") or 0)
            summary.seeds = [int(s) for s in result.get("seeds") or [] if str(s).lstrip("-").isdigit()]
            _read_metrics(summary, result.get("metrics") or {})
        if runner or result:
            jobs.append(summary)
    return jobs


def _load_json(path: Path, unparsed: list[str]) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except ValueError as exc:
        unparsed.append(f"{path.name} in {path.parent.name}: {exc}")
        return {}
    return data if isinstance(data, dict) else {}


def _read_metrics(summary: JobSummary, metrics: dict) -> None:
    families: dict[str, dict[int, float]] = {}
    for name, value in metrics.items():
        if isinstance(value, dict):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        m = _SEED_FAMILY.match(name)
        if m:
            families.setdefault(m.group(1), {})[int(m.group(2))] = number
            continue
        summary.scalars[name] = number
        if number and _FLAG_NAME.search(name):
            summary.flags.append(name)
    for base, by_seed in families.items():
        values = [by_seed[k] for k in sorted(by_seed)]
        summary.families[base] = values
        summary.family_mean[base] = mean(values)
        summary.family_sd[base] = pstdev(values) if len(values) > 1 else 0.0


# ── the metric series ───────────────────────────────────────────────────────


def _metric_words(frozen: FrozenTarget) -> list[str]:
    words = re.findall(r"[a-z]{5,}", frozen.metric.lower())
    return [w for w in words if w not in ("strict", "pipeline", "unchanged", "seeds", "instances")][:3]


def metric_series(
    frozen: FrozenTarget,
    rows: list[GateRow],
    superseded: list[GateRow],
    progress: str,
    jobs: list[JobSummary],
    entries: list[HistoryEvent],
) -> list[MetricPoint]:
    """Dated observations of the frozen metric, from every source that names one.

    Sources, in order of trust: the README baseline (dated at the earliest history
    entry), status-table `Result` cells with the target's denominator, dated progress
    sections whose lines mention the metric and carry `N/D`, and job scalars whose
    name reads as a resolved total. A fraction equal to the threshold itself is a
    mention of the target, not a measurement, and is skipped.
    """
    n = frozen.n
    if not n:
        return []
    points: list[MetricPoint] = []
    dates = sorted(e.date for e in entries if _parse_date(e.date))
    if frozen.baseline_count:
        points.append(
            MetricPoint(
                date=dates[0] if dates else "",
                value=frozen.baseline_value,
                count=frozen.baseline_count,
                n=n,
                source="readme:baseline",
            )
        )
    for row in rows + superseded:
        count, denom = _fraction(row.result, n)
        if denom and count != frozen.threshold_count:
            points.append(
                MetricPoint(
                    date=row.date, value=count / n, count=count, n=n,
                    gate_id=row.gate_id, source="progress:table",
                )
            )
    words = _metric_words(frozen) or ["resolve"]
    current_date, current_gate, best_in_section = "", "", -1
    for line in progress.splitlines() + ["## end"]:
        m = _DATED_HEADING.match(line)
        if m or line.startswith("## end"):
            if current_date and best_in_section >= 0:
                points.append(
                    MetricPoint(
                        date=current_date, value=best_in_section / n, count=best_in_section,
                        n=n, gate_id=current_gate, source="progress:section",
                    )
                )
            best_in_section = -1
            if m:
                current_date = m.group(2)
                gate = _GATE_ID.search(m.group(1) + m.group(3))
                current_gate = gate.group(1) if gate else ""
            continue
        lowered = line.lower()
        if not any(w in lowered for w in words):
            continue
        for fm in _FRACTION.finditer(line):
            count, denom = int(fm.group(1)), int(fm.group(2))
            if _TARGET_CONTEXT.search(line[: fm.start()]):
                continue
            if denom == n and count != frozen.threshold_count and count > best_in_section:
                best_in_section = count
    for jb in jobs:
        for name, value in jb.scalars.items():
            if "resolve" in name and name.endswith("_total") and 0 < value <= n:
                points.append(
                    MetricPoint(
                        date=jb.finished_at, value=value / n, count=int(value), n=n,
                        gate_id=jb.gate_id, source="job:" + name,
                    )
                )
    points.sort(key=lambda p: (p.date, p.count))
    return points


def last_move(points: list[MetricPoint]) -> str:
    """The date the running best last increased; the first point's date if never."""
    best, moved = -1, ""
    for p in points:
        if p.count > best:
            best, moved = p.count, p.date
    return moved


# ── resolvability ───────────────────────────────────────────────────────────


def resolvability(frozen: FrozenTarget, observed_seed_sd: float = 0.0) -> Resolvability:
    """Can the target's effect be told from binomial seed noise on its eval?

    Pure, so `recharter` can run it on a proposed target before it is written.
    """
    r = Resolvability(observed_seed_sd=observed_seed_sd)
    n = frozen.n
    if not n or not frozen.threshold_count:
        r.statement = "not computable: the frozen target names no `N/D` count"
        return r
    if not frozen.baseline_count:
        r.statement = "not computable: no baseline `N/D` to measure the required effect from"
        return r
    p = frozen.baseline_count / n
    r.required_effect = (frozen.threshold_count - frozen.baseline_count) / n
    r.pooled_se = math.sqrt(max(p * (1 - p), 1e-9) / n)
    r.ratio = r.required_effect / r.pooled_se if r.pooled_se else 0.0
    r.resolvable = r.ratio >= K_RESOLVABLE
    seeds = len(frozen.seeds)
    if seeds:
        per_seed_n = n / seeds
        r.per_seed_required = (frozen.threshold_count - frozen.baseline_count) / seeds
        r.per_seed_se = math.sqrt(max(p * (1 - p), 1e-9) * per_seed_n)
    verdict = "resolvable" if r.resolvable else "NOT resolvable"
    r.statement = (
        f"required effect {frozen.threshold_count - frozen.baseline_count}/{n} = "
        f"{r.required_effect:.3f}; binomial SE at p={p:.2f}, n={n} is "
        f"{r.pooled_se:.3f}; ratio {r.ratio:.1f} SE (floor {K_RESOLVABLE:.1f}) → {verdict}"
    )
    if seeds:
        r.statement += (
            f"; per seed {r.per_seed_required:.1f} tasks required vs "
            f"{r.per_seed_se:.1f} tasks SE"
        )
    if observed_seed_sd:
        r.statement += f"; observed per-seed sd {observed_seed_sd:.1f}"
    return r


# ── code churn ──────────────────────────────────────────────────────────────


#: Marks a commit subject in `git log --numstat` output. Not a control character:
#: `str.splitlines` treats the record separator as a line break.
_SUBJECT = "@@subject@@"


def code_churn(
    repo_dir: Path, code_root: str, program_dir: str, since: str
) -> dict[str, int]:
    """Lines changed per gate id (from commit subjects) since `since`; soft-fail."""
    paths = [p for p in (code_root, f"{program_dir}/exp") if p and (repo_dir / p).exists()]
    if not paths:
        return {}
    cmd = ["git", "-C", str(repo_dir), "log", "--numstat", "--format=" + _SUBJECT + "%s"]
    if since:
        cmd.append(f"--since={since}")
    cmd += ["--", *paths]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return {}
    if out.returncode != 0:
        return {}
    churn: dict[str, int] = {}
    bucket = "other"
    for line in out.stdout.split("\n"):
        if line.startswith(_SUBJECT):
            m = _GATE_ID.search(line[len(_SUBJECT) :])
            bucket = m.group(1) if m else "other"
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            try:
                churn[bucket] = churn.get(bucket, 0) + int(parts[0]) + int(parts[1])
            except ValueError:
                continue
    return churn


# ── triggers ────────────────────────────────────────────────────────────────


def count_events(events: list[HistoryEvent]) -> dict[str, int]:
    counts = {
        "kills": 0, "apparatus_kills": 0, "revives": 0, "new_directions": 0,
        "recharters": 0, "passes": 0, "fails": 0, "lead_reviews": 0,
        "program_reviews": 0, "apparatus_cycles": 0, "max_gate_apparatus_cycles": 0,
    }
    per_gate: dict[str, int] = {}
    for e in events:
        key = {
            "kill": "kills", "apparatus_kill": "apparatus_kills", "revive": "revives",
            "new_direction": "new_directions", "recharter": "recharters",
            "pass": "passes", "fail": "fails", "lead_review": "lead_reviews",
            "program_review": "program_reviews",
        }.get(e.event)
        if key:
            counts[key] += 1
        if e.event == "revive":
            per_gate[e.gate_id] = per_gate.get(e.gate_id, 0) + 1
    counts["apparatus_cycles"] = counts["revives"]
    counts["max_gate_apparatus_cycles"] = max(per_gate.values(), default=0)
    return counts


def triggers(
    d: Dossier, *, lead_reviews: int, gate_cycles: int
) -> list[str]:
    fired: list[str] = []
    if d.counts.get("apparatus_cycles", 0) >= APPARATUS_CYCLES:
        fired.append(f"apparatus_cycles>={APPARATUS_CYCLES}")
    stale = bool(d.series) and (d.days_since_moved >= STALE_DAYS or gate_cycles >= STALE_CYCLES)
    if stale:
        fired.append("metric_stale")
    if d.resolvability.required_effect > 0 and not d.resolvability.resolvable:
        fired.append("unresolvable_effect")
    ceiling = _ceiling(d)
    if ceiling and d.frozen.threshold_count and ceiling < d.frozen.threshold_count:
        fired.append("ceiling_below_target")
    if d.frozen.deadline and 0 <= d.days_to_deadline <= DEADLINE_DAYS and stale:
        fired.append("deadline_pressure")
    if d.frozen.deadline and d.days_to_deadline < 0:
        fired.append("deadline_passed")
    if lead_reviews >= LEAD_REVIEWS_EXHAUSTED:
        fired.append("reviews_exhausted")
    return fired


def _ceiling(d: Dossier) -> float:
    for jb in d.jobs:
        for name, value in jb.scalars.items():
            if name == "C" or "ceiling" in name.lower():
                return value
        for base, values in jb.families.items():
            if "coverage" in base.lower():
                return float(sum(values))
    return 0.0


def fingerprint(d: Dossier) -> str:
    last = d.series[-1] if d.series else MetricPoint()
    raw = json.dumps(
        [sorted(d.triggers), last.date, last.count, d.active_gate], sort_keys=True
    )
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


# ── the node ────────────────────────────────────────────────────────────────


@blueprint.node
def build_dossier(
    logger: logging.Logger,
    repo_dir: str,
    program_dir: str,
    progress_path: str = "",
    code_root: str = "",
    lead_reviews: int = 0,
    program_reviews: int = 0,
    gate_cycles: int = 0,
    review_every: int = 3,
    today: str = "",
) -> Dossier:
    """Read the program folder and compute the dossier. Zero model calls.

    Bootstraps `history.jsonl` from the progress file when the program has none —
    once, and marked as parsed rather than recorded.
    """
    repo = Path(repo_dir)
    program = repo / program_dir
    progress_file = repo / progress_path if progress_path else program / "PROGRESS.md"
    d = Dossier(today=today or date.today().isoformat(), program_dir=program_dir)
    readme = _read(program / "README.md", d.unparsed)
    progress = _read(progress_file, d.unparsed)

    d.frozen = parse_frozen_target(readme, d.unparsed)
    d.rows, d.superseded_rows = parse_status_table(progress, d.unparsed)
    entries = parse_dated_entries(progress)
    hist = history_path(repo_dir, program_dir)
    if bootstrap_history(hist, entries):
        logger.info("history bootstrapped from %s: %d entries", progress_file.name, len(entries))
    d.history = read_history(hist) or entries
    d.jobs = read_jobs(program / "jobs", d.unparsed)
    d.series = metric_series(d.frozen, d.rows, d.superseded_rows, progress, d.jobs, entries)
    d.moved_last_on = last_move(d.series)
    today_d = _parse_date(d.today) or date.today()
    moved = _parse_date(d.moved_last_on)
    d.days_since_moved = (today_d - moved).days if moved else 0
    deadline = _parse_date(d.frozen.deadline)
    d.days_to_deadline = (deadline - today_d).days if deadline else 0
    d.resolvability = resolvability(d.frozen, _seed_sd(d))
    d.counts = count_events(d.history)
    d.counts["lead_reviews"] = max(d.counts["lead_reviews"], lead_reviews)
    d.counts["program_reviews"] = max(d.counts["program_reviews"], program_reviews)
    d.churn = code_churn(repo, code_root, program_dir, d.moved_last_on)
    d.pending = pending_results(progress)
    d.active_gate = _active_gate(d.rows)
    d.triggers = triggers(d, lead_reviews=lead_reviews, gate_cycles=gate_cycles)
    d.circling = bool(d.triggers)
    d.fingerprint = fingerprint(d)
    last_review = next(
        (e for e in reversed(d.history) if e.event == "program_review"), None
    )
    # A changed fingerprint is new evidence — unless the change is the last review's own
    # doing. A re-charter rewrites the target and so the triggers; asking again before a
    # single gate has cycled would review the review. Same day and no gate since: wait.
    if last_review is None:
        new_evidence = True
    else:
        new_evidence = last_review.fingerprint != d.fingerprint and (
            gate_cycles >= 1 or last_review.date != d.today
        )
    d.review_due = (d.circling and new_evidence) or (
        review_every > 0 and gate_cycles >= review_every
    )
    logger.info(
        "dossier %s: triggers=%s review_due=%s fingerprint=%s unparsed=%d",
        program_dir, d.triggers, d.review_due, d.fingerprint, len(d.unparsed),
    )
    return d


def _read(path: Path, unparsed: list[str]) -> str:
    try:
        return path.read_text()
    except OSError:
        unparsed.append(f"missing: {path.name}")
        return ""


def _seed_sd(d: Dossier) -> float:
    """Observed per-seed sd of the most recent job family that reads as the metric."""
    words = _metric_words(d.frozen) or ["resolve"]
    for jb in reversed(d.jobs):
        for base, sd in jb.family_sd.items():
            if any(w in base.lower() for w in words) or "coverage" in base.lower():
                return sd
    return 0.0


def _active_gate(rows: list[GateRow]) -> str:
    for row in rows:
        s = row.status.upper()
        if any(k in s for k in ("REOPENED", "IN PROGRESS", "KILLED", "FAIL")) and "NOT" not in s:
            return row.gate_id
    for row in rows:
        if "NOT STARTED" in row.status.upper():
            return row.gate_id
    return rows[0].gate_id if rows else ""


# ── rendering ───────────────────────────────────────────────────────────────


def render_dossier(d: Dossier) -> str:
    """Markdown for `{{ dossier }}`: every number the review may cite, nothing else."""
    f, r = d.frozen, d.resolvability
    out = [f"# Program dossier — `{d.program_dir}` (as of {d.today})", ""]
    out += ["## Frozen target", ""]
    out.append(f"- Metric: {f.metric or '(unparsed)'}")
    out.append(f"- Dataset: {f.dataset or '(unparsed)'}")
    thr = f"{f.threshold_count}/{f.n}" if f.n else f.threshold or "(unparsed)"
    base = (
        f"{f.baseline_count}/{f.n} ({f.baseline_source})" if f.baseline_count else "(none found)"
    )
    out.append(f"- Threshold: {thr}; baseline: {base}; seeds: {f.seeds or '(unknown)'}")
    out.append(f"- Deadline: {f.deadline or '(none)'} ({d.days_to_deadline} days away)")
    out += ["", "## Resolvability (computed)", "", f"**{r.statement}**", ""]
    out += ["## Metric series", ""]
    if d.series:
        out.append("| date | value | count | gate | source |")
        out.append("|---|---|---|---|---|")
        for p in d.series:
            out.append(f"| {p.date or '?'} | {p.value:.4f} | {p.count}/{p.n} | {p.gate_id} | {p.source} |")
        out.append("")
        out.append(
            f"Best last improved on **{d.moved_last_on or '?'}** "
            f"({d.days_since_moved} days ago)."
        )
    else:
        out.append("(no dated observations of the frozen metric were found)")
    out += ["", "## Counts", ""]
    out.append(", ".join(f"{k}={v}" for k, v in d.counts.items()))
    out += ["", "## Active ladder", ""]
    for row in d.rows:
        out.append(f"- {row.gate_id}: **{row.status}** — {row.result[:160]} ({row.date})")
    if d.superseded_rows:
        out += ["", f"Superseded rows: {len(d.superseded_rows)} (prior directions/tracks)."]
    out += ["", "## Jobs (per seed)", ""]
    for jb in d.jobs:
        fams = "; ".join(
            f"{k}={[int(v) if float(v).is_integer() else round(v, 3) for v in vals]} "
            f"(mean {jb.family_mean[k]:.2f}, sd {jb.family_sd[k]:.2f})"
            for k, vals in jb.families.items()
        )
        out.append(
            f"- {jb.gate_id} [{jb.finished_at or '?'}] exit={jb.exit_code} "
            f"{jb.n_completed}/{jb.n_planned} units; {fams or 'no seed families'}; "
            f"flags={jb.flags or 'none'}"
        )
    out += ["", "## Code churn since the metric last moved (lines, by gate in commit subject)", ""]
    out.append(", ".join(f"{k}={v}" for k, v in sorted(d.churn.items())) or "(none / not a git repo)")
    out += ["", "## Results still pending", ""]
    out += [f"- {p}" for p in d.pending] or ["(none)"]
    out += ["", "## Circling triggers (evaluated in code)", ""]
    out.append(", ".join(d.triggers) if d.triggers else "none fired")
    out.append(f"\nActive gate: {d.active_gate or '?'}; fingerprint {d.fingerprint}")
    if d.unparsed:
        out += ["", "## Could not parse", ""] + [f"- {u}" for u in d.unparsed]
    return "\n".join(out) + "\n"


def summarize(d: Dossier) -> str:
    """Five lines for the gate-selection turn."""
    last = d.series[-1] if d.series else None
    lines = [
        f"Target {d.frozen.threshold_count}/{d.frozen.n}; latest "
        + (f"{last.count}/{last.n} on {last.date}" if last else "no observation")
        + f"; best last moved {d.moved_last_on or '?'} ({d.days_since_moved} days ago).",
        f"Resolvability: {d.resolvability.statement}",
        "Counts: " + ", ".join(f"{k}={v}" for k, v in d.counts.items() if v),
        f"Triggers: {', '.join(d.triggers) or 'none'}; active gate {d.active_gate or '?'}.",
        f"Pending: {'; '.join(d.pending[:3]) or 'none'}.",
    ]
    return "\n".join(lines)


def _main() -> None:  # pragma: no cover - operator entry point
    import argparse

    ap = argparse.ArgumentParser(description="Print a program's dossier.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--program", required=True)
    ap.add_argument("--code-root", default="")
    ap.add_argument("--today", default="")
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    from workhorse_workflows.research.nodes.program import ledger_path, read_ledger

    ledger = read_ledger(ledger_path(Path(ns.repo), ns.program))
    d = build_dossier(
        logging.getLogger("dossier"),
        ns.repo,
        ns.program,
        "",
        ns.code_root,
        lead_reviews=ledger.lead_reviews,
        program_reviews=ledger.program_reviews,
        today=ns.today,
    )
    print(json.dumps(d.model_dump(mode="json"), indent=2) if ns.json else render_dossier(d))




__all__ = [
    "APPARATUS_CYCLES",
    "DEADLINE_DAYS",
    "K_RESOLVABLE",
    "LEAD_REVIEWS_EXHAUSTED",
    "STALE_CYCLES",
    "STALE_DAYS",
    "build_dossier",
    "classify_entry",
    "code_churn",
    "count_events",
    "fingerprint",
    "last_move",
    "metric_series",
    "parse_dated_entries",
    "parse_frozen_target",
    "parse_status_table",
    "pending_results",
    "read_jobs",
    "render_dossier",
    "resolvability",
    "summarize",
    "triggers",
]
