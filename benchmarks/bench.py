#!/usr/bin/env python3
"""The workflow benchmark harness: drive a greenfield run, then score what it produced.

Two different questions get asked about a workflow run, and conflating them is how a
benchmark lies to you:

  * **Did the machinery hold?** — repair loops, operator-gate escalations, hung nodes.
    A run can be perfect here and have built nothing.
  * **Is the output any good?** — does the produced repo actually satisfy the backlog it
    was given? A run can be full of repair loops and still land a working app.

Both are reported side by side by ``score``, because each one alone is misleading.

The scoring model is deliberately small. The benchmark's input is a backlog of
user-observable bullets (``- [kebab-id] A person can …``), and every bullet is scored
0–3 on one fixed rubric:

    0 absent    nothing in the repo claims this bullet
    1 planned   a story exists that would deliver it; no implementing code
    2 built     implementing code exists on every surface the bullet implies
    3 verified  built, AND executable evidence exercises it (a test, a QA artifact)

The headline number is the mean, as a percentage of 3. That is the whole score: one
rubric, one number, comparable across runs and across benchmark apps.

**Why a judge, and how it is kept honest.** Levels 2 and 3 are behavioral claims that no
static check can make — "a plausible-looking stub" and "a working sign-up flow" have the
same shape on disk. So an agent reads the repo and assigns the level. To stop it from
being creative, every level ≥2 must cite real repo paths as evidence, and this script
*verifies those paths exist* before accepting the level; a bullet whose citations don't
resolve is capped at 1 and flagged. That check is cheap, deterministic, and catches the
judge's most common failure mode.

Nothing here is specific to any one benchmark app. The app is described entirely by a
spec file (see ``todo-app/bench.yml``); point ``--spec`` at another one to benchmark the
same workflows against a different backlog and stack.

    bench.py --spec todo-app/bench.yml genesis   create the repo + service skeletons  (minutes)
    bench.py --spec todo-app/bench.yml author    backlog.md → epics/stories           (tens of minutes)
    bench.py --spec todo-app/bench.yml coder     implement every story                (hours)
    bench.py --spec todo-app/bench.yml all       the three above, in order
    bench.py --spec todo-app/bench.yml status    what exists so far
    bench.py --spec todo-app/bench.yml score     THE SCORECARD: quality + reliability
    bench.py --spec todo-app/bench.yml reset     delete the target and start clean

Phases are separately invocable because they have wildly different costs and failure
modes, and you almost never want to redo an earlier one to retry a later one. They are
idempotent by construction — genesis keys each skeleton step on that *service's* marker
file — so a failed run is resumed by re-running the same command, which is the property
that makes a benchmark worth having.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

# The judge runs on whatever agent CLI the rest of the workspace runs on — `AGENT_CLI`
# picks the backend, and workhorse's cap classification/sleep helpers are reused so a
# benchmark left overnight behaves like a workflow left overnight. Imported at module
# scope (not lazily): workhorse is a workspace member, so this is a hard dependency, and
# a benchmark that silently degrades when its scorer is missing is worse than one that
# refuses to start.
from workhorse.runner import caps as wh_caps
from workhorse.runner import extract as wh_extract
from workhorse.runner import failure as wh_failure
from workhorse.runner.backends.registry import get_backend

HERE = Path(__file__).resolve().parent
STABLEMATE = HERE.parent
WORKFLOWS = STABLEMATE / "base-library" / "workflows"

# ── The rubric. One definition, used by the prompt, the parser, and the report. ────────
LEVELS = {
    0: ("absent", "nothing in the repo claims this bullet"),
    1: ("planned", "a story exists that would deliver it; no implementing code"),
    2: ("built", "implementing code exists on every surface the bullet implies"),
    3: ("verified", "built, and executable evidence exercises it"),
}
MAX_LEVEL = 3

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

# `- [kebab-id] A person does something observable.` — the benchmark's unit of input.
BULLET_RE = re.compile(r"^- \[([a-z0-9][a-z0-9-]*)\]\s+(.*\S)\s*$", re.MULTILINE)

BOLD, RED, DIM, RESET = "\033[1m", "\033[31m", "\033[2m", "\033[0m"


def say(msg: str) -> None:
    print(f"\n{BOLD}== {msg}{RESET}", flush=True)


def die(msg: str) -> None:
    raise SystemExit(f"{RED}error: {msg}{RESET}")


# ── Spec ──────────────────────────────────────────────────────────────────────────────


@dataclass
class Spec:
    """A benchmark app, entirely as data. The only file to edit for a new benchmark."""

    path: Path
    target: Path
    backlog: str
    surfaces: list[dict]
    repo: dict = field(default_factory=dict)
    checks: list[dict] = field(default_factory=list)
    judge: dict = field(default_factory=dict)

    @property
    def logs(self) -> Path:
        return self.path.parent / ".runs"

    @property
    def artifacts(self) -> Path:
        # Run artifacts (events.jsonl, per-node output) are the benchmark's EVIDENCE, so
        # they must outlive the workflow source tree. Workhorse defaults them to
        # `<cwd>/.agents/runs` — inside the library dir, which is checked out, cleaned and
        # reinstalled. A whole run's evidence vanished that way mid-session, and the
        # reliability report then cheerfully answered "no runs recorded yet" rather than
        # noticing its own history had been erased.
        return self.logs / "artifacts"

    def surface(self, name: str) -> dict:
        for s in self.surfaces:
            if s["service"] == name:
                return s
        die(f"no surface {name!r} in {self.path}")

    def params(self, service: str) -> str:
        """The flow params for one `workhorse run coder genesis` invocation."""
        s = self.surface(service)
        joined = lambda *xs: ",".join(x for x in xs if x)  # noqa: E731
        return json.dumps({
            "target": str(self.target),
            "service": s["service"],
            "service_root": s["service_root"],
            # Process packs (repo-level) + this surface's stack pack. write_agents_yml
            # unions them into agents.yml, so every surface carries the workflow packs.
            "packs": joined(self.repo.get("packs", ""), s.get("packs", "")),
            # The docs scaffold rides along with the first surface so docs/epics/ exists
            # before anything reads the graph; farrier's scaffold step skips files that
            # are already present.
            "scaffolds": joined(self.repo.get("docs_scaffold", ""), s.get("scaffolds", "")),
            "init_cmd": s.get("init_cmd", ""),
            "marker": s.get("marker", ""),
            "markers": s.get("markers", ""),
            "workflows": "coder,author",
        })


def load_spec(path: Path) -> Spec:
    if not path.is_file():
        die(f"no spec at {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    target = Path(os.environ.get("TARGET") or raw.get("target") or die("spec has no `target`"))
    # Validate here rather than at first use: a spec is edited by hand, and YAML turns a
    # bare `cmd: true` into a bool. Catching that at load costs one loop and replaces a
    # traceback from inside subprocess with a line naming the field.
    for i, c in enumerate(raw.get("checks") or []):
        for key in ("name", "cmd"):
            if not isinstance(c.get(key), str):
                die(f"{path}: checks[{i}].{key} must be a string, got {c.get(key)!r} "
                    f"(quote it — YAML reads bare true/no/on as booleans)")
    return Spec(
        path=path.resolve(),
        target=target.expanduser(),
        backlog=raw.get("backlog", "docs/backlog.md"),
        surfaces=raw.get("surfaces") or die("spec has no `surfaces`"),
        repo=raw.get("repo") or {},
        checks=raw.get("checks") or [],
        judge=raw.get("judge") or {},
    )


# ── Phases ────────────────────────────────────────────────────────────────────────────


def preflight(spec: Spec, phase: str) -> None:
    """Refuse to start without the tools a phase needs.

    Author once died three nodes in with a raw ``FileNotFoundError: 'claude'`` from deep
    inside workhorse's subprocess layer — after the agent had already been billed for two
    script nodes, and with a traceback naming ``subprocess.Popen`` rather than the actual
    problem. A missing binary is knowable before the first node runs.

    The agent CLI is the one that actually bites: it usually lives under nvm, whose PATH
    entry comes from an interactive shell profile, so it is present when you test by hand
    and absent in a background or cron shell. Same command, same machine, different PATH.
    """
    agent_cli = os.environ.get("AGENT_CLI", "claude")
    missing = [
        f"{tool} ({why})"
        for tool, why in (("uv", "the workspace runner"), ("git", "version control"),
                          (agent_cli, "the agent CLI — often under ~/.nvm/versions/node/*/bin, "
                                      "a PATH entry that comes from an interactive shell "
                                      "profile and so goes missing in background/cron shells. "
                                      "Set AGENT_CLI to use a different backend."))
        if not shutil.which(tool)
    ]
    # Stack init tools are genesis-only: author and coder never shell out to them.
    if phase == "genesis":
        for s in spec.surfaces:
            tool = (s.get("init_cmd") or "").split(" ")[0]
            if tool and not shutil.which(tool):
                missing.append(f"{tool} (init_cmd for surface {s['service']!r})")

    if missing:
        print(f"{RED}error: cannot run {phase} — missing required tool(s):{RESET}", file=sys.stderr)
        for m in dict.fromkeys(missing):
            print(f"  - {m}", file=sys.stderr)
        print("\nNothing has been modified. Install or PATH-expose these, then re-run.",
              file=sys.stderr)
        raise SystemExit(1)


def run_logged(cmd: list[str], cwd: Path, log: Path, env: dict[str, str] | None = None) -> int:
    """Run a workflow, streaming its output to the console and to ``log`` at once.

    The console stream is not just for watching: ``cap_wait_by_node`` reads these logs for
    the cap-sleep durations that the events file does not record.
    """
    log.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, env={**os.environ, **(env or {})},
    )
    with log.open("w", encoding="utf-8") as fh:
        for line in proc.stdout:  # type: ignore[union-attr]
            sys.stdout.write(line)
            sys.stdout.flush()
            fh.write(line)
    return proc.wait()


def cmd_genesis(spec: Spec) -> None:
    preflight(spec, "genesis")
    say(f"genesis → {spec.target}")
    spec.artifacts.mkdir(parents=True, exist_ok=True)
    for s in spec.surfaces:
        svc = s["service"]
        say(f"genesis: {svc}")
        rc = run_logged(
            ["uv", "run", "workhorse", "run", "coder", "genesis",
             "--runs-dir", str(spec.artifacts), "--params", spec.params(svc)],
            cwd=WORKFLOWS / "coder", log=spec.logs / f"genesis-{svc}.log",
        )
        if rc != 0:
            die(f"genesis failed for surface {svc!r} (exit {rc}) — see {spec.logs}/genesis-{svc}.log")
    cmd_backlog(spec)
    say("genesis complete")


def cmd_backlog(spec: Spec) -> None:
    """Seed the benchmark's input.

    Copied rather than generated: the whole point is that every run starts from the same
    bullets, so the outcome is attributable to the workflows and not to a backlog that
    drifted between runs.
    """
    src = spec.path.parent / spec.backlog
    dst = spec.target / spec.backlog
    if not src.is_file():
        die(f"no backlog at {src}")
    if not dst.parent.is_dir():
        die(f"no {dst.parent} — run genesis first")
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    say(f"seeded {spec.backlog} ({len(parse_backlog(src))} bullets)")


def cmd_author(spec: Spec) -> None:
    preflight(spec, "author")
    if not (spec.target / spec.backlog).is_file():
        die(f"no backlog at {spec.target / spec.backlog} — run genesis first")
    say("author → epics + stories")
    run_logged(
        ["uv", "run", "workhorse", "run", "author", "--runs-dir", str(spec.artifacts),
         "--params", json.dumps({"backlog": spec.backlog})],
        cwd=WORKFLOWS / "author", log=spec.logs / "author.log",
        env={"AGENT_REPO_DIR": str(spec.target)},
    )


def cmd_coder(spec: Spec) -> None:
    preflight(spec, "coder")
    if not (spec.target / "docs" / "epics" / "index.md").is_file():
        die("no epic queue — run author first")
    say("coder → implementation")
    run_logged(
        ["uv", "run", "workhorse", "run", "coder", "--runs-dir", str(spec.artifacts),
         "--params", json.dumps({"docs_path": str(spec.target)})],
        cwd=WORKFLOWS / "coder", log=spec.logs / "coder.log",
        env={"AGENT_REPO_DIR": str(spec.target)},
    )


def cmd_reset(spec: Spec) -> None:
    say(f"reset {spec.target}")
    shutil.rmtree(spec.target, ignore_errors=True)
    print("  removed")


def cmd_status(spec: Spec) -> None:
    say(f"status of {spec.target}")
    if not spec.target.is_dir():
        print("  (does not exist)")
        return
    print(f"  git:      {git_commits(spec.target)} commit(s)")
    for s in spec.surfaces:
        marker = spec.target / s["service_root"] / s.get("marker", "")
        ok = "✓" if marker.is_file() else "✗ missing"
        print(f"  {s['service']:<8} {ok} {s['service_root']}/{s.get('marker', '')}")
    print(f"  backlog:  {len(parse_backlog(spec.target / spec.backlog))} bullet(s)")
    print(f"  epics:    {len(find_epics(spec.target))}")
    print(f"  stories:  {len(list(spec.target.glob('docs/epics/*/stories/*/story.md')))}")


def git_commits(target: Path) -> int:
    try:
        out = subprocess.run(["git", "-C", str(target), "log", "--oneline"],
                             capture_output=True, text=True, timeout=30)
        return len(out.stdout.splitlines()) if out.returncode == 0 else 0
    except (OSError, subprocess.SubprocessError):
        return 0


# ── Evidence: what the run actually produced ──────────────────────────────────────────


def parse_backlog(path: Path) -> list[dict]:
    """The `- [kebab-id] text` bullets, in file order. The benchmark's unit of input."""
    if not path.is_file():
        return []
    return [{"id": m.group(1), "text": m.group(2)}
            for m in BULLET_RE.finditer(path.read_text(encoding="utf-8"))]


def find_epics(target: Path) -> list[Path]:
    return sorted(target.glob("docs/epics/*/epic.md"))


def frontmatter(md: Path) -> dict[str, str]:
    """The `---`-delimited YAML header, as flat strings. Missing/malformed → empty."""
    try:
        text = md.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    _, _, rest = text.partition("---")
    body, sep, _ = rest.partition("\n---")
    if not sep:
        return {}
    try:
        data = yaml.safe_load(body) or {}
    except yaml.YAMLError:
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def trace_bullets(spec: Spec) -> list[dict]:
    """Trace each backlog bullet to the epic that claims it and that epic's stories.

    Author records coverage as a `## Backlog bullets covered` list of `[kebab-id]`s in
    each ``epic.md``, so backlog→epic is deterministic. Stories carry no bullet id, so
    story→bullet is not — which is exactly why the judge exists. The stories are handed
    over as *context* for the judge, never as a coverage claim in themselves.
    """
    bullets = parse_backlog(spec.target / spec.backlog)
    if not bullets:
        bullets = parse_backlog(spec.path.parent / spec.backlog)

    claims: dict[str, list[dict]] = defaultdict(list)
    for epic_md in find_epics(spec.target):
        text = epic_md.read_text(encoding="utf-8")
        stories = [
            {"slug": s.parent.name, "status": frontmatter(s).get("status", "unknown")}
            for s in sorted(epic_md.parent.glob("stories/*/story.md"))
        ]
        info = {"epic": epic_md.parent.name, "stories": stories}
        for bid in {m.group(1) for m in re.finditer(r"\[([a-z0-9][a-z0-9-]*)\]", text)}:
            claims[bid].append(info)

    for b in bullets:
        owners = claims.get(b["id"], [])
        b["epics"] = [o["epic"] for o in owners]
        b["stories"] = [s for o in owners for s in o["stories"]]
        b["stories_done"] = [s for s in b["stories"] if is_done(s["status"])]
    return bullets


def is_done(status: str) -> bool:
    """Story frontmatter uses prose statuses ('Not started', 'QA passed', 'Done')."""
    return status.strip().lower() in {"done", "qa passed", "complete", "completed", "merged"}


def run_checks(spec: Spec) -> list[dict]:
    """The target repo's own gates (`make lint`, `make test`). Exit codes, nothing more.

    These do not feed the score — a half-built greenfield repo failing its own tests is
    expected, not a scoring event. They are reported because they *contradict* a judge:
    a bullet scored `verified` while the suite that would prove it is red is a finding.
    """
    results = []
    for c in spec.checks:
        name, cmd = c["name"], c["cmd"]
        print(f"  running {name}: {cmd}", flush=True)
        try:
            p = subprocess.run(cmd, shell=True, cwd=spec.target, capture_output=True,
                               text=True, timeout=c.get("timeout", 900))
            rc, tail = p.returncode, (p.stdout + p.stderr).strip().splitlines()[-3:]
        except subprocess.TimeoutExpired:
            rc, tail = None, [f"timed out after {c.get('timeout', 900)}s"]
        except OSError as e:
            rc, tail = None, [str(e)]
        results.append({"name": name, "cmd": cmd, "exit": rc, "tail": tail})
    return results


# ── Reliability: did the machinery get there on its own? ──────────────────────────────


def read_runs(spec: Spec) -> list[dict]:
    """One row per recorded run: nodes entered, repair loops, escalations, staleness.

    The benchmark's reliability question is not "did a valid repo appear" but "did the
    machinery get there without hand-holding". Those come apart: a run that needed an
    agent to diagnose and repair a deterministic gap still ends with a valid repo, and
    reading only the end state scores that as success.
    """
    # A report that can describe a run older than the code under test is the same vacuous
    # success it exists to detect, one level up: a run once aborted with exit 127 before
    # doing anything, the previous run's artifacts were still on disk, and the report
    # scored them without complaint. Newest workflow-source mtime vs each run's own.
    newest_src = max(
        (f.stat().st_mtime
         for pat in ("workflow.yaml", "scripts/*.py", "prompts/*.md")
         for f in WORKFLOWS.glob(f"*/{pat}")),
        default=0.0,
    )

    rows = []
    for run in sorted(p for p in spec.artifacts.glob("*") if p.is_dir()):
        events = run / "events.jsonl"
        if not events.is_file():
            continue
        entered, repairs, escalations, failed = [], [], [], False
        for line in events.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("phase") != "enter":
                continue
            node = ev.get("node", "")
            entered.append(node)
            repairs += [node] if node in REPAIR_NODES else []
            escalations += [node] if node in ESCALATION_NODES else []
            failed = failed or node.endswith("_failed")
        rows.append({
            "run": run.name, "nodes": len(entered), "repairs": repairs,
            "escalations": escalations, "failed": failed,
            "stale": bool(newest_src) and events.stat().st_mtime < newest_src,
        })
    return rows


def node_totals(artifacts: Path) -> tuple[dict[str, float], dict[str, int], dict[str, float]]:
    """(total_s, runs, longest_s) per node, summed across every events.jsonl."""
    total: dict[str, float] = defaultdict(float)
    runs: dict[str, int] = defaultdict(int)
    longest: dict[str, float] = defaultdict(float)
    for path in artifacts.glob("**/events.jsonl"):
        open_at: dict[str, datetime] = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            node, phase, ts = ev.get("node"), ev.get("phase"), ev.get("ts")
            if not (node and ts):
                continue
            when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if phase == "enter":
                open_at[node] = when
            elif phase == "done" and node in open_at:
                d = (when - open_at.pop(node)).total_seconds()
                total[node] += d
                runs[node] += 1
                longest[node] = max(longest[node], d)
    return total, runs, longest


def flow_containers(artifacts: Path) -> set[str]:
    """Nodes that are flows, not leaf work: their wall-clock is the sum of their
    children's, so flagging one as a hang points at the wrong thing (the hang is in one
    child). Cap-wait is attributed to the LEAF that slept, never to its container, so a
    container's 'active' time would also wrongly include a child's cap-wait."""
    return {p.parent.parent.name for p in artifacts.glob("**/_flow/events.jsonl")}


def cap_wait_by_node(logs: Path) -> dict[str, float]:
    """Seconds each node spent sleeping on a usage cap, summed from the console logs."""
    cap: dict[str, float] = defaultdict(float)
    for path in logs.glob("*.log"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for node, secs in PAUSE_RE.findall(text):
            cap[node] += float(secs)
    return cap


def hang_candidates(spec: Spec, threshold_s: float = 1800.0) -> list[dict]:
    """Leaf nodes ranked by ACTIVE time per run, cap-wait subtracted.

    A node's wall-clock is two very different things: **active** (the agent working) and
    **cap-wait** (sleeping on a usage cap until its window reopens). A node that took
    three hours because the account was capped is behaving *correctly* — workhorse waits
    caps out by design, and a node on a cap ceiling must never be disturbed. A node that
    took three hours of *active* time is genuinely stuck. So cap-wait is shown but never
    counted toward the hang signal.

    Cap-wait cannot be pinned to one specific run from the aggregate log, so active *per
    run* is the honest, cap-wait-safe proxy: a node that slept for hours on caps but only
    ever did two minutes of work per run is not a hang.
    """
    total, runs, longest = node_totals(spec.artifacts)
    cap = cap_wait_by_node(spec.logs)
    containers = flow_containers(spec.artifacts)
    out = []
    for node, tot in total.items():
        if node in containers:
            continue
        # Clamp: cap-wait is attributed from the run-wide log, so it can marginally
        # exceed a node's summed total.
        cw = min(cap.get(node, 0.0), tot)
        active = max(0.0, tot - cw)
        per_run = active / runs[node] if runs[node] else 0.0
        out.append({"node": node, "active_per_run": per_run, "cap_wait": cw,
                    "longest": longest[node], "runs": runs[node],
                    "hang": per_run >= threshold_s})
    return sorted(out, key=lambda r: r["active_per_run"], reverse=True)


# ── The judge ─────────────────────────────────────────────────────────────────────────


def render(template: str, **fields: str) -> str:
    """Fill ``{{name}}`` placeholders in the rubric.

    Deliberately not ``str.format``: the rubric shows the judge a JSON response shape, and
    every brace in that example would have to be doubled to survive ``format`` — an
    editing hazard in the one file whose whole purpose is to be edited and tuned.
    """
    for key, value in fields.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def judge_one(spec: Spec, bullet: dict, rubric: str, backend) -> dict:
    """Score one backlog bullet by having an agent read the produced repo.

    One turn per bullet, not one turn for the whole backlog: a focused turn over a
    four-surface repo gives a far more reliable answer than one turn asked to hold
    eighteen judgements at once, and a failure is isolated to the bullet it belongs to.
    """
    prompt = render(
        rubric,
        bullet_id=bullet["id"],
        bullet_text=bullet["text"],
        target=str(spec.target),
        epics=", ".join(bullet["epics"]) or "(none — no epic claims this bullet)",
        stories="\n".join(f"  - {s['slug']} — {s['status']}" for s in bullet["stories"])
                or "  (none)",
        levels="\n".join(f"  {n} {name} — {desc}" for n, (name, desc) in LEVELS.items()),
    )
    text = call_agent(backend, prompt, node_id=f"judge_{bullet['id']}", spec=spec)
    # Reuse workhorse's own response parser — the tested one that already handles fenced
    # blocks, bare objects, and the tolerant repair pass — rather than a second parser
    # that would drift from it.
    parsed = wh_extract.parse_json_from_text(text, ["level", "evidence", "reason"]) or {}

    try:
        level = max(0, min(MAX_LEVEL, int(parsed.get("level", 0))))
    except (TypeError, ValueError):
        level = 0
    evidence = [str(e) for e in (parsed.get("evidence") or []) if str(e).strip()]
    reason = str(parsed.get("reason") or "").strip() or "(judge returned no reason)"

    # The anti-hallucination check. A behavioral claim is only as good as the code it
    # points at, and the judge's most common failure is citing a file that does not
    # exist. Verifying the cited paths is deterministic and cheap, so a level ≥2 whose
    # citations do not resolve is capped at `planned` and flagged rather than believed.
    bad = [e for e in evidence if not (spec.target / e.split(":", 1)[0].strip()).exists()]
    unverified = bool(bad) or (level >= 2 and not evidence)
    if unverified and level >= 2:
        level = 1
    return {**bullet, "level": level, "evidence": evidence, "reason": reason,
            "unverified_citations": bad, "capped": unverified}


def call_agent(backend, prompt: str, *, node_id: str, spec: Spec, attempts: int = 4) -> str:
    """One agent turn, waiting out usage caps the same way workhorse itself does.

    Reuses workhorse's cap classification and sleep helpers rather than reimplementing
    them, so a benchmark run left overnight behaves like a workflow run left overnight
    instead of failing at the first cap. A node sleeping on a cap ceiling is healthy and
    must never be disturbed — the same rule the timing report is built around.
    """
    last = ""
    for attempt in range(attempts):
        try:
            return backend.run_turn(
                prompt, node_id, None,
                model=spec.judge.get("model"),
                cwd=str(spec.target),
                effort=spec.judge.get("effort"),
            )
        except wh_failure.BackendInvocationError as exc:
            last = str(exc)
            if wh_failure.is_cap(last):
                delay, when = wh_caps.cap_delay_seconds(exc)
                print(f"[{node_id}] ⏸ usage cap reached — pausing ~{int(delay)}s ({when})",
                      flush=True)
                wh_caps.sleep_with_notice(delay, node_id, when)
            elif attempt < attempts - 1:
                time.sleep(5 * (attempt + 1))
            else:
                break
        except Exception as exc:  # a judge failing must not lose the other 17 scores
            last = str(exc)
            break
    print(f"[{node_id}] {RED}judge failed: {last[:200]}{RESET}", file=sys.stderr)
    return ""


def judge_backlog(spec: Spec, bullets: list[dict], jobs: int) -> list[dict]:
    rubric_path = HERE / "rubric.md"
    if not rubric_path.is_file():
        die(f"no rubric at {rubric_path}")
    rubric = rubric_path.read_text(encoding="utf-8")
    backend = get_backend()
    print(f"  judging {len(bullets)} bullet(s) with {backend.name}, {jobs} at a time…",
          flush=True)
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        return list(pool.map(lambda b: judge_one(spec, b, rubric, backend), bullets))


# ── The scorecard ─────────────────────────────────────────────────────────────────────


def cmd_score(spec: Spec, *, judge: bool, jobs: int, only: list[str]) -> int:
    if not spec.target.is_dir():
        die(f"no target at {spec.target} — nothing to score")

    bullets = trace_bullets(spec)
    if only:
        bullets = [b for b in bullets if b["id"] in set(only)]
    if not bullets:
        die(f"no backlog bullets found (looked in {spec.target / spec.backlog})")

    say(f"deterministic gates ({spec.target})")
    checks = run_checks(spec) if spec.checks else []
    for c in checks:
        mark = "✓" if c["exit"] == 0 else "✗"
        print(f"  {mark} {c['name']:<10} exit={c['exit']}")
        if c["exit"] != 0:
            for line in c["tail"]:
                print(f"      {DIM}{line}{RESET}")

    say("backlog satisfaction")
    if judge:
        bullets = judge_backlog(spec, bullets, jobs)
    else:
        # Without a judge there is no behavioral evidence, so the only defensible claim
        # is the deterministic one: an epic claims it (planned) or nothing does (absent).
        # Never `built` — that is precisely the claim static structure cannot make.
        print("  --no-judge: structural trace only. `planned` here means an epic claims the")
        print("  bullet — it is NOT a claim that anything was built.")
        for b in bullets:
            b.update(level=1 if b["epics"] else 0, evidence=[], capped=False,
                     unverified_citations=[], reason="claimed by an epic" if b["epics"]
                     else "no epic claims it")

    print(f"\n  {'bullet':<28}{'level':<12}{'epic ✓/n':>9}  why")
    print(f"  {'-' * 86}")
    for b in sorted(bullets, key=lambda x: -x["level"]):
        name = LEVELS[b["level"]][0]
        flag = " ⚠" if b.get("capped") else ""
        done = f"{len(b['stories_done'])}/{len(b['stories'])}"
        print(f"  {b['id']:<28}{b['level']} {name:<10}{done:>9}  {b['reason'][:44]}{flag}")
    print(f"  {'-' * 86}")
    # Stories are counted per *epic*, not per bullet — author records coverage on the epic,
    # so every bullet in one epic shares its story tally. It is context for reading the
    # level, never an input to it.
    print(f"  {DIM}epic ✓/n = done stories / all stories in the epic(s) claiming the bullet{RESET}")

    total = sum(b["level"] for b in bullets)
    pct = 100.0 * total / (MAX_LEVEL * len(bullets))
    tally = defaultdict(int)
    for b in bullets:
        tally[b["level"]] += 1
    print(f"\n  {BOLD}backlog satisfaction: {pct:.0f}%{RESET}  "
          f"({total}/{MAX_LEVEL * len(bullets)} across {len(bullets)} bullets)")
    print("  " + "   ".join(f"{LEVELS[n][0]}: {tally[n]}" for n in sorted(LEVELS, reverse=True)))

    capped = [b for b in bullets if b.get("capped")]
    if capped:
        print(f"\n  ⚠ {len(capped)} bullet(s) capped at `planned`: the judge claimed built/verified")
        print("    but cited repo paths that do not exist. Treat these as unproven, not as near-misses:")
        for b in capped:
            missing = ", ".join(b["unverified_citations"]) or "(no citation at all)"
            print(f"      - {b['id']}: {missing}")

    red = [c for c in checks if c["exit"] != 0]
    verified = [b for b in bullets if b["level"] == MAX_LEVEL]
    if red and verified:
        print(f"\n  ⚠ {len(verified)} bullet(s) scored `verified` while {len(red)} repo gate(s) "
              f"are red ({', '.join(c['name'] for c in red)}).")
        print("    Executable evidence that does not execute is not evidence — audit those bullets.")

    report_reliability(spec)
    out = write_scorecard(spec, bullets, checks, pct)
    print(f"\n  scorecard written to {out}")
    return 0


def report_reliability(spec: Spec) -> None:
    say("machinery reliability")
    rows = read_runs(spec)
    if not rows:
        print("  no runs recorded yet")
    else:
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
            detail = f"  ({'; '.join(bits)})" if bits else ""
            print(f"  {mark} {r['run']:<26} {r['nodes']:>3} nodes  {status}{detail}")

        stale = [r["run"] for r in rows if r["stale"]]
        if stale:
            print(f"\n  ✗ {len(stale)} run(s) PREDATE the current workflow source and say nothing")
            print("    about it. Reset and re-run before trusting any score above:")
            for name in stale:
                print(f"      - {name}")

        clean = sum(1 for r in rows if not r["repairs"] and not r["escalations"]
                    and not r["failed"])
        repairs = sum(len(r["repairs"]) for r in rows)
        escalations = sum(len(r["escalations"]) for r in rows)
        print(f"\n  {clean}/{len(rows)} run(s) completed with no repair loop.")
        if repairs:
            print(f"  {repairs} repair-loop entr(y/ies) — each one is a workflow defect, not a")
            print("  successful recovery. A clean re-run is the only proof a fix landed.")
        if escalations:
            print(f"  {escalations} operator-gate escalation(s) — with operator_mode=human this")
            print("  run would have STOPPED and asked. Unattended, it resolved itself.")

    say("node timing (hangs vs cap-waits)")
    nodes = hang_candidates(spec)
    if not nodes:
        print("  no node timing recorded yet")
        return
    m = lambda s: f"{s / 60:.1f}m"  # noqa: E731
    print(f"  {'leaf node':<28}{'active/run':>11}{'cap-wait':>10}{'wall':>8}{'runs':>6}")
    print(f"  {'-' * 63}")
    for n in nodes[:12]:
        print(f"  {n['node']:<28}{m(n['active_per_run']):>11}{m(n['cap_wait']):>10}"
              f"{m(n['longest']):>8}{n['runs']:>6}{' ⚠ HANG?' if n['hang'] else ''}")
    flagged = [n for n in nodes if n["hang"]]
    if flagged:
        print(f"\n  ⚠ {len(flagged)} leaf node(s) average over 30 min of ACTIVE work per run "
              "(cap-wait excluded) — a genuine hang / retry-churn. A per-node ACTIVE-time")
        print("  budget that PAUSES during cap-waits is the fix — never a wall-clock kill,")
        print("  which would cut a legitimate cap-wait.")
    else:
        print("\n  ✓ no leaf node averaged over 30 min of ACTIVE work per run. Long wall-clocks")
        print("  were cap-wait — healthy: a capped run is left to wait undisturbed.")


def write_scorecard(spec: Spec, bullets: list[dict], checks: list[dict], pct: float) -> Path:
    out = spec.logs / "scorecard.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "spec": str(spec.path),
        "target": str(spec.target),
        "satisfaction_pct": round(pct, 1),
        "max_level": MAX_LEVEL,
        "levels": {n: name for n, (name, _) in LEVELS.items()},
        "bullets": [{k: b[k] for k in
                     ("id", "text", "level", "reason", "evidence", "epics",
                      "capped", "unverified_citations")} for b in bullets],
        "checks": checks,
        "runs": read_runs(spec),
        "commits": git_commits(spec.target),
    }, indent=2), encoding="utf-8")
    return out


# ── CLI ───────────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="bench.py", description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["genesis", "backlog", "author", "coder", "all",
                                       "status", "score", "reset"])
    p.add_argument("--spec", default=str(HERE / "todo-app" / "bench.yml"),
                   help="the benchmark app's spec file (default: the todo-app benchmark)")
    p.add_argument("--no-judge", action="store_true",
                   help="score structurally only — no agent turns, no behavioral claim")
    p.add_argument("--jobs", type=int, default=4, help="judge turns to run at once")
    p.add_argument("--bullet", action="append", default=[],
                   help="score only this bullet id (repeatable)")
    args = p.parse_args(argv)

    spec = load_spec(Path(args.spec).resolve())
    if args.command == "genesis":
        cmd_genesis(spec)
    elif args.command == "backlog":
        cmd_backlog(spec)
    elif args.command == "author":
        cmd_author(spec)
    elif args.command == "coder":
        cmd_coder(spec)
    elif args.command == "all":
        cmd_genesis(spec)
        cmd_author(spec)
        cmd_coder(spec)
    elif args.command == "status":
        cmd_status(spec)
    elif args.command == "reset":
        cmd_reset(spec)
    elif args.command == "score":
        return cmd_score(spec, judge=not args.no_judge, jobs=args.jobs, only=args.bullet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
