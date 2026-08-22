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
spec file (see ``suites/todo-app/benchmark.yaml``); point ``--spec`` at another one to
benchmark the same workflows against a different backlog and stack.

    bench.py --spec suites/todo-app/benchmark.yaml genesis   create the repo + service skeletons  (minutes)
    bench.py --spec suites/todo-app/benchmark.yaml author    backlog.md → epics/stories           (tens of minutes)
    bench.py --spec suites/todo-app/benchmark.yaml coder     implement every story                (hours)
    bench.py --spec suites/todo-app/benchmark.yaml all       the three above, in order
    bench.py --spec suites/todo-app/benchmark.yaml status    what exists so far
    bench.py --spec suites/todo-app/benchmark.yaml watch     is the RUNNING run progressing?      (free)
    bench.py --spec suites/todo-app/benchmark.yaml score     THE SCORECARD: quality + reliability
    bench.py --spec suites/docs-app/benchmark.yaml design-score  did author DESIGN, or transcribe?
    bench.py --spec suites/todo-app/benchmark.yaml reset     delete the target and start clean

Phases are separately invocable because they have wildly different costs and failure
modes, and you almost never want to redo an earlier one to retry a later one. They are
idempotent by construction — genesis keys each skeleton step on that *service's* marker
file — so a failed run is resumed by re-running the same command, which is the property
that makes a benchmark worth having.

**Two sizes of benchmark, for two different jobs.** Every task lives in `suites/<name>/`,
and they are not all the same size. `todo-app` is the full one: four surfaces, seventeen
bullets, hours per run, and the only one whose score means "how good are these workflows".
It is far too slow to *debug* with — a defect in the coder's fifth node costs most of a
day to reach twice. So the `quick` and `hour` tasks exist alongside it: one or two
surfaces, a handful of bullets, a cheap model tier pinned in the spec and a wall-clock
budget, sized so a whole genesis→author→coder chain lands inside an hour. Their scores
are not comparable to todo-app's and are not meant to be; what they produce is *failures,
quickly*, which is the input a fix cycle actually runs on.

Which is which is `tags:` in the spec rather than a rule about directory layout, so
`matrix.py run --tag quick` picks the cheap ones without anyone having to remember their
names. See `suites/README.md` for the vocabulary.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import NoReturn

import tomli_w
import yaml

from ostler import markdown
from stablemate_core.config import load_config
# The judge runs on whatever agent CLI the rest of the workspace runs on — `AGENT_CLI`
# picks the backend, and workhorse's cap classification/sleep helpers are reused so a
# benchmark left overnight behaves like a workflow left overnight. Imported at module
# scope (not lazily): workhorse is a workspace member, so this is a hard dependency, and
# a benchmark that silently degrades when its scorer is missing is worse than one that
# refuses to start.
from workhorse.config_run import AgentResilience
from workhorse.runner import caps as wh_caps
from workhorse.runner import extract as wh_extract
from workhorse.runner import failure as wh_failure
from workhorse.runner.backends import AgentBackend
from workhorse.runner.backends.registry import get_backend
from workhorse.runner.clock import SYSTEM_CLOCK, Clock

HERE = Path(__file__).resolve().parent
STABLEMATE = HERE.parent
# A workflow is an installed distribution that ships its own console script
# (`workhorse-coder`), so there is no per-workflow directory to run from any more
# (`base-library/workflows/<name>` was deleted with the YAML engine) and no name to hand
# a generic runner. Runs are launched from the workspace root, which is all `uv run`
# needs; the source tree is still located, but only to date the code a run was produced
# by — see `read_runs`.
WORKFLOW_SRC = STABLEMATE / "workflows" / "src" / "workhorse_workflows"

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

# `- [kebab-id] A person does something observable.` — the benchmark's unit of input. The
# bullet itself is read off `ostler.markdown`; this only says whether the handle it carries
# is one of ours, which is an identifier validator rather than a format parser.
KEBAB_ID = re.compile(r"[a-z0-9][a-z0-9-]*\Z")

# The heading under which an epic records the backlog bullets it claims.
COVERED_HEADING = "Backlog bullets covered"

BOLD, RED, DIM, RESET = "\033[1m", "\033[31m", "\033[2m", "\033[0m"


def say(msg: str) -> None:
    print(f"\n{BOLD}== {msg}{RESET}", flush=True)


def die(msg: str) -> NoReturn:
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
    #: Wall-clock ceiling per phase, in seconds (`budget: {author: 1800, coder: 2400}`).
    #: Absent or 0 for a phase means unbounded, which is the old behavior.
    budget: dict = field(default_factory=dict)
    #: The held-out half of a design suite: a directory beside the spec holding
    #: `expectations.yaml` and `journeys.yaml`. Nothing in it is ever copied into
    #: `target` or named to a workflow — see `suites/docs-app/hidden/README.md` for why
    #: the whole metric collapses the moment it is. Empty means this task has no design
    #: score, which is every task but `docs-app`.
    hidden: str = ""
    #: The operator's standing answer to `author`'s grill gate, as a path beside this
    #: spec. Empty means the shared `benchmarks/grill-answers.md`, which is what every
    #: task uses — an override exists only because a future task might need a different
    #: *stakeholder*, never a more helpful one. See that file for why the answer settles
    #: nothing.
    grill: str = ""
    #: A `power.<level>.<backend>` overlay for the runs this spec drives — the tier the
    #: benchmark is *meant* to be run at, as spec data rather than machine state.
    power: dict = field(default_factory=dict)
    #: Why this task deliberately budgets past the hour the task set otherwise promises
    #: (`over_hour: "a full five-story run, so the loop failures are reachable"`). Prose,
    #: because the only thing worth recording is the reason. Empty means the task claims
    #: the hour and is held to it.
    over_hour: str = ""
    #: Free-form labels this task is selected by — `matrix.py run --tag quick`. Inert for a
    #: single `bench.py --spec` invocation, which already named the one spec it runs; they
    #: exist so a *set* of tasks can be picked by shape ("the cheap ones", "the ones with a
    #: web surface") without the caller having to remember which names those are.
    tags: list[str] = field(default_factory=list)
    #: The model set this run belongs to, and where its evidence goes. Both are empty on a
    #: bare `bench.py` invocation, which keeps `.runs/` beside the spec exactly as before.
    #: `matrix.py` fills them, because a set is the thing that varies while the spec stays
    #: fixed: N sets driving ONE spec would otherwise overwrite each other's artifacts,
    #: scorecard and `config.toml`, and the last one to finish would look like all of them.
    label: str = ""
    runs_dir: Path | None = None

    @property
    def logs(self) -> Path:
        return self.runs_dir or self.path.parent / ".runs"

    @property
    def artifacts(self) -> Path:
        # Run artifacts (events.jsonl, per-node output) are the benchmark's EVIDENCE, so
        # they must outlive the workflow source tree. Workhorse defaults them to
        # `<cwd>/.agents/runs` — inside the library dir, which is checked out, cleaned and
        # reinstalled. A whole run's evidence vanished that way mid-session, and the
        # reliability report then cheerfully answered "no runs recorded yet" rather than
        # noticing its own history had been erased.
        return self.logs / "artifacts"

    @property
    def hidden_dir(self) -> Path | None:
        return self.path.parent / self.hidden if self.hidden else None

    @property
    def grill_file(self) -> Path:
        return self.path.parent / self.grill if self.grill else HERE / "grill-answers.md"

    def surface(self, name: str) -> dict:
        for s in self.surfaces:
            if s["service"] == name:
                return s
        die(f"no surface {name!r} in {self.path}")

    def params(self, service: str) -> str:
        """The flow params for one `workhorse-coder run genesis` invocation."""
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


def env_json(name: str) -> dict:
    """A dict handed in through the environment, or ``{}`` — with a parse error named.

    `matrix.py` drives `bench.py` as a subprocess rather than importing it, so that every
    set's run is a command a person can retype and get the same result; the per-set
    overrides therefore travel as environment, the same way ``TARGET`` and ``AGENT_CLI``
    already do. (The no-environment rule in the root CLAUDE.md is about
    ``workhorse_workflows``, whose reads land in no checkpoint. This is the process
    boundary, which is exactly where the environment belongs.)

    A malformed value is fatal rather than silently empty. A set that ran on the
    operator's ambient config instead of its own still produces a scorecard, and that
    scorecard is indistinguishable from a real one while measuring something else.
    """
    raw = os.environ.get(name)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        die(f"${name} is not valid JSON: {exc}")
    if not isinstance(parsed, dict):
        die(f"${name} must be a JSON object, got {type(parsed).__name__}")
    return parsed


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
    # `tags: quick` is a string, and a string is iterable — left alone it would silently
    # become the five tags q/u/i/c/k and match nothing anyone typed. Sequence-or-scalar is
    # exactly the shape a hand-edited list gets wrong, so it is normalised, not trusted.
    raw_tags = raw.get("tags") or []
    tags = [raw_tags] if isinstance(raw_tags, str) else list(raw_tags)
    for t in tags:
        if not isinstance(t, str) or not t.strip():
            die(f"{path}: tags must be non-empty strings, got {t!r}")
    # The per-set layer. A spec says what the benchmark IS — backlog, surfaces, gates —
    # and is the thing held constant; a set says which models were pointed at it. One
    # spec is run by many sets, so the models cannot live in the spec file, and the two
    # keys a set moves are the only two it is allowed to move.
    power = {level: dict(backends) for level, backends in (raw.get("power") or {}).items()}
    for level, backends in env_json("BENCH_POWER").items():
        power[level] = {**power.get(level, {}), **backends}
    runs = os.environ.get("BENCH_RUNS")
    return Spec(
        path=path.resolve(),
        target=target.expanduser(),
        backlog=raw.get("backlog", "docs/backlog.md"),
        surfaces=raw.get("surfaces") or die("spec has no `surfaces`"),
        repo=raw.get("repo") or {},
        checks=raw.get("checks") or [],
        judge={**(raw.get("judge") or {}), **env_json("BENCH_JUDGE")},
        budget=raw.get("budget") or {},
        power=power,
        hidden=raw.get("hidden") or "",
        grill=raw.get("grill") or "",
        over_hour=raw.get("over_hour") or "",
        tags=tags,
        label=os.environ.get("BENCH_SET", ""),
        runs_dir=Path(runs).expanduser().resolve() if runs else None,
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


def effective_config(spec: Spec) -> Path:
    """Write the config this spec's runs see: the operator's, with `spec.power` overlaid.

    A node asks for an abstract tier (``power="high"``), and the operator's
    ``~/.config/stablemate/config.toml`` decides what that costs. That is right for real
    work and wrong for a benchmark: which model ran is the single biggest term in both
    the score and the wall-clock, so leaving it to whatever the machine happens to be
    configured with makes two runs incomparable and makes "finishes in an hour" a
    property of the laptop rather than of the spec.

    So the tier is spec data. It is *overlaid* rather than replacing the file, because
    the rest of that config is machine truth this process cannot invent — ``library_dir``,
    ``stablemate_dir``, ``[harness.*]`` credentials-adjacent knobs — and ``load_config``
    deliberately does not merge: an explicit ``$STABLEMATE_CONFIG`` means *this file and
    no other*. Overlaying and writing a whole file is what makes that isolation usable
    without also mutating the operator's own config, which a benchmark must never do.
    """
    data = load_config()
    merged = {**data.get("power", {})}
    for level, backends in spec.power.items():
        merged[level] = {**merged.get(level, {}), **backends}
    out = spec.logs / "config.toml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(tomli_w.dumps({**data, "power": merged}), encoding="utf-8")
    return out


def phase_env(spec: Spec, phase: str, budget_s: float | None = None) -> dict[str, str]:
    """The environment one phase's workflow run is launched with.

    Three things, and each is a benchmark property rather than an operator preference:
    which repo the agent works in, which model tier it runs at, and how long it is
    allowed to take. The budget is enforced by workhorse itself
    (``WORKHORSE_MAX_RUNTIME_S``), which checks it *between* states — so an over-budget
    run stops at a node boundary with its checkpoint and artifacts intact, and can be
    scored and resumed. That is the difference between a time limit and a `kill`.

    ``budget_s`` overrides the spec's figure for one invocation, and exists because of
    how the ceiling is anchored: workhorse counts it from the *original* ``started_at``
    (`records.RunRecord`), so a run that already spent its budget meets an expired
    deadline on the resume's first transition check and stops without doing any work.
    Resuming an over-budget run therefore means passing a *larger total*, not the same
    one again — see ``--budget``.
    """
    env = {"AGENT_REPO_DIR": str(spec.target)}
    if spec.power:
        env["STABLEMATE_CONFIG"] = str(effective_config(spec))
    budget = float(spec.budget.get(phase) or 0) if budget_s is None else budget_s
    if budget > 0:
        env["WORKHORSE_MAX_RUNTIME_S"] = str(budget)
    return env


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
    if proc.stdout is None:  # pragma: no cover - `stdout=PIPE` above guarantees the pipe
        raise RuntimeError("the workflow subprocess was started without a stdout pipe")
    with log.open("w", encoding="utf-8") as fh:
        for line in proc.stdout:
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
            ["uv", "run", "workhorse-coder", "run", "genesis",
             "--runs-dir", str(spec.artifacts), "--params", spec.params(svc)],
            cwd=STABLEMATE, log=spec.logs / f"genesis-{svc}.log",
            env=phase_env(spec, "genesis"),
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


def resume_flags(spec: Spec, phase: str, resume: bool) -> list[str]:
    """``--resume-run`` pointed at the newest run of this phase that has a checkpoint.

    The two workflow phases are *not* idempotent the way genesis is. Genesis keys each
    skeleton step on that service's marker file, so re-running it re-derives where it got
    to; author and coder instead carry their position in a checkpoint, and a bare re-run
    opens a **new** run directory and starts from the first node. Repeating the command
    after a crash therefore redoes the work rather than continuing it — which is why this
    is an explicit flag and not a default.

    Deliberately **not** ``--resume-latest``, which resolves through
    ``rundir.find_latest_resumable`` and skips any run carrying a ``terminal``. That is the
    right default for an operator — a run that reached an end state is over — but it is the
    wrong one here, because this harness exists to debug workflows and its central move is
    *fix the bug the run failed on, then continue that run*. A failed run has a checkpoint
    and hours of work in it; refusing to resume it would mean re-running the whole story to
    reach the state under test. Naming the dir is how the operator says the verdict is stale.

    Guarded on there being a checkpoint at all, because a benchmark whose resume switch is
    fatal on a clean target is one you cannot put in a script.
    """
    if not resume:
        return []
    checkpoints = sorted(
        spec.artifacts.glob(f"{phase}-*/checkpoint.json"), key=lambda p: p.stat().st_mtime
    )
    if not checkpoints:
        die(f"--resume: no {phase} run with a checkpoint under {spec.artifacts} to resume")
    return ["--resume-run", str(checkpoints[-1].parent)]


def phase_rc(phase: str, rc: int, log: Path) -> int:
    """Report a workflow phase's exit code, and hand it back for the caller to propagate.

    Not `die`: a workflow that failed left a run dir with a checkpoint in it, and the next
    move is to read the log and resume rather than to treat the phase as an abort. But it
    must not be *silent* either — a benchmark harness that exits 0 on a failed run is the
    one bug that discredits every number it prints, and it also lets `all` start `coder`
    against epics `author` never finished writing.
    """
    if rc != 0:
        print(f"{RED}  {phase} failed (exit {rc}) — see {log}{RESET}")
    return rc


#: The one operator gate `author` opens for every run, and the file it parks on.
AUTHOR_CONTEXT = "docs/epics/_author-context.md"
AWAITING = "STATUS: AWAITING_OPERATOR"
#: What the grill's own notes say, and nothing else's do. The watcher answers *only* this
#: gate: every other block reached an operator because the resolver could not ground it in
#: something already written, and a canned answer to one of those is a give-up wearing an
#: answer's clothes. Those park, the phase runs out its budget, and the escalation shows up
#: in the reliability half of the scorecard where it belongs.
GRILL_MARK = "grill this backlog"
GATE_POLL_S = 15.0


def grill_answer(spec: Spec) -> str:
    """The standing operator answer: everything below the answers file's first rule.

    The prose above the rule is for the person reading the file and would only confuse a
    workflow reading the gate, so the split is load-bearing rather than cosmetic.
    """
    if not spec.grill_file.is_file():
        die(f"no grill answers at {spec.grill_file}")
    _, rule, answer = spec.grill_file.read_text(encoding="utf-8").partition("\n---\n")
    if not rule or not answer.strip():
        die(f"{spec.grill_file}: expected the standing answer below a `---` rule")
    return answer.strip()


def answer_grill(path: Path, answer: str) -> bool:
    """Stamp one parked grill gate answered, or report that it was not the grill.

    Only the *first* `STATUS:` line is read by the workflow — an answer appended anywhere
    else is silently inert — so the stamp is a replacement of that line, not an addition.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:  # being rewritten under us; the next poll gets it
        return False
    if not text.lstrip().startswith(AWAITING) or GRILL_MARK not in text:
        return False
    path.write_text(
        text.replace(AWAITING, "STATUS: ANSWERED", 1).rstrip() + f"\n\n## Answer\n\n{answer}\n",
        encoding="utf-8",
    )
    return True


def watch_for_grill(spec: Spec, stop: threading.Event) -> threading.Thread:
    """Answer the grill gate while `author` waits on it, in a thread beside the run.

    `grill_backlog` is an `Await` that `operator_mode` does not gate — the whole premise
    is that those decisions are a person's. A benchmark has no person, so without this the
    `author` phase of every suite blocks until its budget expires and no task can be scored
    at all. The answer it writes is deliberately scope-neutral; `grill-answers.md` says why.
    """
    answer = grill_answer(spec)
    path = spec.target / AUTHOR_CONTEXT

    def poll() -> None:
        while not stop.wait(GATE_POLL_S):
            if path.is_file() and answer_grill(path, answer):
                print(f"  grill gate answered from {spec.grill_file.name}")

    thread = threading.Thread(target=poll, daemon=True)
    thread.start()
    return thread


def cmd_author(spec: Spec, *, resume: bool = False, budget_s: float | None = None) -> int:
    preflight(spec, "author")
    if not (spec.target / spec.backlog).is_file():
        die(f"no backlog at {spec.target / spec.backlog} — run genesis first")
    say("author → epics + stories" + (" (resuming)" if resume else ""))
    log = spec.logs / "author.log"
    stop = threading.Event()
    watch_for_grill(spec, stop)
    try:
        rc = run_logged(
            ["uv", "run", "workhorse-author", "run", "--runs-dir", str(spec.artifacts),
             *resume_flags(spec, "author", resume),
             "--params", json.dumps({"backlog": spec.backlog})],
            cwd=STABLEMATE, log=log,
            env=phase_env(spec, "author", budget_s),
        )
    finally:
        stop.set()
    return phase_rc("author", rc, log)


def cmd_coder(spec: Spec, *, resume: bool = False, budget_s: float | None = None) -> int:
    preflight(spec, "coder")
    if not find_epics(spec.target):
        die("no epic queue — run author first")
    say("coder → implementation" + (" (resuming)" if resume else ""))
    log = spec.logs / "coder.log"
    return phase_rc("coder", run_logged(
        ["uv", "run", "workhorse-coder", "run", "--runs-dir", str(spec.artifacts),
         *resume_flags(spec, "coder", resume),
         "--params", json.dumps({"docs_path": str(spec.target)})],
        cwd=STABLEMATE, log=log,
        env=phase_env(spec, "coder", budget_s),
    ), log)


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


def last_activity(spec: Spec) -> tuple[float, str] | None:
    """(seconds since the run last wrote anything, and what it wrote); None if nothing has.

    The liveness signal a babysitter actually needs. A workflow that is working writes
    node output and appends to events.jsonl continuously, so silence is the one symptom
    common to every way a run can stop making progress — a wedged subprocess, an agent
    turn that will never return, a state loop with no side effects — none of which show
    up as a non-zero exit, because the process is still there.
    """
    newest, what = 0.0, ""
    for path in spec.logs.glob("**/*"):
        if not path.is_file():
            continue
        mtime = path.stat().st_mtime
        if mtime > newest:
            newest, what = mtime, str(path.relative_to(spec.logs))
    # "no run has written anything" and "the run went quiet" are opposite verdicts —
    # the first is nothing started, the second is something stopped — so they must not
    # arrive at the caller as the same zero.
    return (max(0.0, time.time() - newest), what) if newest else None


def waiting_on_cap(spec: Spec) -> str | None:
    """The cap-pause line a log ends on, if it does — silence that is *not* a stall.

    Workhorse sleeps out a usage cap by design and a node on a cap ceiling must never be
    disturbed, so cap-wait looks exactly like a hang from the outside and has to be ruled
    out before anything is called stuck. It is ruled out by reading, not inferred from
    duration: the pause line names the node and the length.
    """
    logs = [p for p in spec.logs.glob("*.log") if p.is_file()]
    if not logs:
        return None
    newest = max(logs, key=lambda p: p.stat().st_mtime)
    tail = newest.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
    for line in reversed(tail):
        if "⏸" in line:
            return line.strip()
        if line.strip():
            # Something was said after the last pause line, so the pause is over.
            return None
    return None


def cmd_watch(spec: Spec, *, silence_s: float, live_only: bool = False) -> int:
    """One glance at a live run: is it progressing, churning, stalled, or on stale code.

    Separate from `score` because the questions are asked at different times and cost
    different amounts. `score` is the verdict on a finished run and spends agent turns to
    reach it. This is the babysitter's poll — structural, free, safe to run every minute
    against a run in flight — and its exit code is the whole point: non-zero means
    something needs a human, so it composes with a wait loop instead of being read.

    `live_only` is what makes that composition work, and all it does is demote the
    staleness row. A run that predates the current workflow source is worth saying out
    loud — it is why its score cannot be trusted — but it is not a thing that needs a
    human *now*, and it never stops being true: editing the workflow to fix today's
    defect is itself what makes every earlier run stale. A loop that treats it as a
    problem returns on its first poll, every time, after every fix. Nor is there a live
    run hiding in that row to rescue it: a run still writing keeps its events file newer
    than the source no matter when it started, and a run wedged on genuinely old code is
    already the silence check's to report. The other three rows are all about the run in
    flight, so the loop waits on those and prints this one as context.
    """
    say(f"watch {spec.path.parent.name}")
    problems: list[str] = []

    stories = list(spec.target.glob("docs/epics/*/stories/*/story.md"))
    done = [s for s in stories if is_done(frontmatter(s).get("status", ""))]
    print(f"  progress: {len(find_epics(spec.target))} epic(s), {len(done)}/{len(stories)} "
          f"story(ies) done, {git_commits(spec.target)} commit(s)")

    activity = last_activity(spec)
    cap = waiting_on_cap(spec)
    if activity is None:
        print(f"  liveness: — no run has written to {spec.logs} yet")
    elif cap:
        print(f"  liveness: quiet {activity[0] / 60:.0f}m — on a usage cap, which is healthy:\n"
              f"            {cap}")
    elif activity[0] >= silence_s:
        quiet, what = activity
        problems.append(f"nothing written for {quiet / 60:.0f}m (last: {what})")
        print(f"  liveness: ✗ SILENT for {quiet / 60:.0f}m — last write was {what}")
    else:
        print(f"  liveness: ✓ wrote {activity[1]} {activity[0] / 60:.0f}m ago")

    churn = churn_candidates(spec)
    if churn:
        problems.append(f"{len(churn)} repeating node cycle(s)")
        print("  churn:    ✗ repeating cycles")
        for c in churn[:5]:
            print(f"              {' → '.join(c['cycle'])}  x{c['repeats']}  in {c['where']}")
    else:
        print("  churn:    ✓ no node cycle repeats back-to-back")

    hangs = [n for n in hang_candidates(spec) if n["hang"]]
    if hangs:
        problems.append(f"{len(hangs)} node(s) over the active-time threshold")
        for n in hangs[:5]:
            print(f"  stall:    ✗ {n['node']} averages {n['active_per_run'] / 60:.0f}m ACTIVE per run")
    else:
        print("  stall:    ✓ no leaf node is over the active-time threshold")

    runs = read_runs(spec)
    stale = [r["run"] for r in runs if r["stale"]]
    if stale:
        if not live_only:
            problems.append(f"{len(stale)} run(s) predate the workflow source")
        print(f"  code:     {'·' if live_only else '✗'} {', '.join(stale)} predate the "
              f"current workflow source{' (context, not a fault)' if live_only else ''}")
    elif runs:
        print(f"  code:     ✓ all {len(runs)} run(s) postdate the workflow source")
    else:
        print("  code:     — no runs recorded")

    if problems:
        print(f"\n{RED}  needs attention: {'; '.join(problems)}{RESET}")
        return 1
    print("\n  ✓ healthy")
    return 0


def run_outcome(run_dir: Path) -> tuple[str, str]:
    """How a run ended, as `(verdict, detail)`, or `("", "")` while it is still open.

    Two fields on `run.json` say "over", and they mean different things. `terminal` is a
    *verdict*: the workflow reached an end state and `writer.finish` stamped which one.
    `interrupted_at` (with `terminal` still null) is a *stop*: the process ended between
    states without deciding anything — Ctrl-C, or the `WORKHORSE_MAX_RUNTIME_S` budget
    tripping as `RunBudgetExceeded`. Reading only the first is what made a budget stop
    invisible here: the run is finished, the process is gone, and `babysit` would have
    polled on to its ceiling waiting for a `terminal` that is deliberately never coming.

    A stop is not sticky: `writer.resume` rewrites `run.json` without the stamp, so a run
    that has been picked back up reads as open again rather than settling forever.
    """
    try:
        data = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "", ""
    if terminal := str(data.get("terminal") or ""):
        return terminal, ""
    if data.get("interrupted_at"):
        return "stopped", str(data.get("error") or "no reason recorded")
    return "", ""


def settled_run(spec: Spec) -> tuple[str, str, str] | None:
    """`(run name, verdict, detail)` of the newest run that has ended; None while one is open.

    Workhorse writes the outcome into a run's `run.json` as the process exits, so a run
    that is over says so on disk. That is what a wait loop needs and what a log tail is a
    bad substitute for: the log's last line is whatever was printed, which is also what it
    looks like the instant before the next line is printed.
    """
    newest, record = 0.0, None
    for run in spec.artifacts.glob("*/run.json"):
        mtime = run.stat().st_mtime
        if mtime > newest:
            newest, record = mtime, (run.parent.name, *run_outcome(run.parent))
    return record if record and record[1] else None


def cmd_babysit(spec: Spec, *, silence_s: float, every_s: float, ceiling_s: float) -> int:
    """Poll `watch` until the run needs a human, finishes, or outlives its ceiling.

    `watch` answers "is it healthy *now*" and composes by exit code; this is the loop that
    was meant to close over it. The point is not automation for its own sake — it is that
    a babysitter who polls by hand pays a turn per poll and still misses the failure by
    however long the last interval was, while a loop that blocks costs one turn total and
    returns the moment the picture changes.

    Three exits, deliberately distinct, because they call for different next moves:
    0 the run ended on its own terms (read `score`), 1 something needs a human (read the
    report the loop just printed), 2 the ceiling ran out with the run still open (nothing
    is known to be wrong — decide whether to keep waiting).

    A finished run must be *seen twice* before the loop believes it. `all` runs three
    phases back to back, so an ended newest run is equally consistent with "the chain is
    over" and "genesis just ended and author is a second from starting" — and one poll
    apart is enough to tell those apart, while one poll is not.
    """
    say(f"babysit {spec.path.parent.name} — polling every {every_s / 60:.0f}m")
    deadline = time.time() + ceiling_s
    seen: str | None = None
    while True:
        if cmd_watch(spec, silence_s=silence_s, live_only=True):
            print(f"\n{RED}  babysit: stopping — the run needs a human{RESET}")
            return 1

        settled = settled_run(spec)
        if settled and settled[0] == seen:
            run, verdict, detail = settled
            if verdict == "fail":
                print(f"\n{RED}  babysit: {run} ended on the fail terminal{RESET}")
                return 1
            if verdict == "stopped":
                # Exit 1, not 0: the run decided nothing, so there is no result to score
                # — but its checkpoint is good, which is the whole reason the stop does
                # not stamp a terminal. This is the exit that means read, fix, resume.
                print(f"\n{RED}  babysit: {run} stopped without a verdict — {detail}{RESET}")
                phase = run.split("-")[0]
                # genesis is marker-keyed and re-runs rather than resuming, so pointing at
                # `--resume` there would name a flag that refuses the phase.
                print(f"  continue it with: bench.py --spec {spec.path} {phase}" + (
                    " --resume --budget <more than the run already spent>"
                    if phase in ("author", "coder") else ""))
                return 1
            print(f"\n  babysit: {run} ended ({verdict}) and nothing followed it — done")
            return 0
        seen = settled[0] if settled else None

        if time.time() >= deadline:
            print(f"\n  babysit: {ceiling_s / 60:.0f}m ceiling reached with the run still "
                  f"open — healthy at the last poll, so this is a choice, not a fault")
            return 2
        time.sleep(every_s)


def git_commits(target: Path) -> int:
    try:
        out = subprocess.run(["git", "-C", str(target), "log", "--oneline"],
                             capture_output=True, text=True, timeout=30)
        return len(out.stdout.splitlines()) if out.returncode == 0 else 0
    except (OSError, subprocess.SubprocessError):
        return 0


# ── Evidence: what the run actually produced ──────────────────────────────────────────


def parse_backlog(path: Path) -> list[dict]:
    """The `- [kebab-id] text` bullets, in file order. The benchmark's unit of input.

    Parsed rather than matched line by line: a backlog that shows its own grammar in a
    fenced example must not have that example scored as work the run was asked to do.
    """
    if not path.is_file():
        return []
    out = []
    for bullet in markdown.split(path.read_text(encoding="utf-8")).walk_bullets():
        bid, text = bullet.bracketed
        if KEBAB_ID.fullmatch(bid) and text.strip():
            out.append({"id": bid, "text": " ".join(text.split())})
    return out


def find_epics(target: Path) -> list[Path]:
    return sorted(target.glob("docs/epics/*/epic.md"))


def frontmatter(md: Path) -> dict[str, str]:
    """The `---`-delimited YAML header, as flat strings. Missing/malformed → empty.

    The fence is located by the same parser the doc graph uses, so a `---` inside a block
    scalar closes nothing and this reads the header the tooling wrote.
    """
    try:
        text = md.read_text(encoding="utf-8")
    except OSError:
        return {}
    data = markdown.split(text).frontmatter
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
        doc = markdown.split(epic_md.read_text(encoding="utf-8"))
        stories = [
            {"slug": s.parent.name, "status": frontmatter(s).get("status", "unknown")}
            for s in sorted(epic_md.parent.glob("stories/*/story.md"))
        ]
        info = {"epic": epic_md.parent.name, "stories": stories}
        # The claim is the `## Backlog bullets covered` list, read as a list. An epic that
        # never wrote the section falls back to every IDed bullet in the file, which is
        # what the old whole-text scan approximated — minus the prose and fenced mentions
        # it also counted, which is the point of parsing.
        section = doc.find_section(COVERED_HEADING)
        claimed = (
            [b for top in section.bullets for b in top.walk()]
            if section is not None
            else doc.walk_bullets()
        )
        for bid in {b.bracketed[0] for b in claimed}:
            if KEBAB_ID.fullmatch(bid):
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
    #
    # The globs used to be `workflow.yaml` / `scripts/*.py` / `prompts/*.md` under
    # `base-library/workflows/*` — the YAML engine's layout, deleted with it. They matched
    # nothing, `newest_src` fell to its 0.0 default, and `bool(newest_src)` turned every
    # staleness verdict to False: the check that exists to stop a benchmark reporting on
    # code that no longer exists had itself gone stale, silently and in exactly the way it
    # was written to catch. Which is why it is now measured off a directory whose absence
    # is loud rather than a glob whose emptiness is not.
    if not WORKFLOW_SRC.is_dir():
        die(f"no workflow source at {WORKFLOW_SRC} — bench.py is out of date with the tree")
    newest_src = max(
        (f.stat().st_mtime
         for pat in ("**/*.py", "**/*.md", "**/*.j2")
         for f in WORKFLOW_SRC.glob(pat)
         if "__pycache__" not in f.parts),
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


def entered_nodes(events: Path) -> list[str]:
    """The node ids one events file entered, in order."""
    out = []
    for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("phase") == "enter" and ev.get("node"):
            out.append(ev["node"])
    return out


def cycles(entered: list[str], max_period: int = 4, min_repeats: int = 3) -> list[dict]:
    """Node cycles that repeat back-to-back in one entry sequence — the churn signal.

    Churn is *not* "a node ran many times": a loop over a queue re-enters `implement`
    once per story, and that is the workflow working. Churn is the same short cycle
    repeating with nothing else between — `plan → implement → plan → implement → …`, or
    a single node re-entered three times running. That distinguishes a run advancing
    through a queue from one orbiting a state it cannot leave, and it needs to know
    nothing about any particular workflow's node names to say so.

    Reported per cycle rather than per node because the two failure modes it separates
    need different fixes: a period-1 cycle is a node retrying itself, a period-2+ cycle
    is a transition condition that never becomes false.
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


def churn_candidates(spec: Spec) -> list[dict]:
    """Every repeating cycle across every events file, flows included.

    Flow files are walked too, unlike `read_runs`: a subflow spinning is the case worth
    catching, and it is invisible from the parent, which sees one long-running container
    node and no repetition at all.
    """
    out = []
    for path in sorted(spec.artifacts.glob("**/events.jsonl")):
        where = path.parent.relative_to(spec.artifacts)
        for c in cycles(entered_nodes(path)):
            out.append({"where": str(where), **c})
    return sorted(out, key=lambda r: -r["repeats"])


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


@dataclass(frozen=True, slots=True)
class Judge:
    """The agent CLI plus the two dependencies its recovery ladder needs.

    `run_turn`, `cap_delay_seconds` and `sleep_with_notice` each take the resilience
    settings and the clock, so the three travel together through every judging call —
    context, not per-call inputs. Built once at the edge (`judge_backlog`) so the
    environment is read once and every judged bullet shares one policy.
    """
    backend: AgentBackend
    resilience: AgentResilience
    clock: Clock


def judge_one(spec: Spec, bullet: dict, rubric: str, judge: Judge) -> dict:
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
    text = call_agent(judge, prompt, node_id=f"judge_{bullet['id']}", spec=spec)
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


def call_agent(judge: Judge, prompt: str, *, node_id: str, spec: Spec,
               attempts: int = 4) -> str:
    """One agent turn, waiting out usage caps the same way workhorse itself does.

    Reuses workhorse's cap classification and sleep helpers rather than reimplementing
    them, so a benchmark run left overnight behaves like a workflow run left overnight
    instead of failing at the first cap. A node sleeping on a cap ceiling is healthy and
    must never be disturbed — the same rule the timing report is built around.
    """
    last = ""
    for attempt in range(attempts):
        try:
            return judge.backend.run_turn(
                prompt, node_id, None,
                model=spec.judge.get("model"),
                timeout=judge.resilience.result_timeout_s,
                resilience=judge.resilience,
                cwd=str(spec.target),
                effort=spec.judge.get("effort"),
            )
        except wh_failure.BackendInvocationError as exc:
            last = str(exc)
            if wh_failure.is_cap(last):
                delay, when = wh_caps.cap_delay_seconds(
                    exc, resilience=judge.resilience, clock=judge.clock)
                print(f"[{node_id}] ⏸ usage cap reached — pausing ~{int(delay)}s ({when})",
                      flush=True)
                wh_caps.sleep_with_notice(
                    delay, node_id, when, resilience=judge.resilience, clock=judge.clock)
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
    # `judge.cli` outranks $AGENT_CLI, and that precedence is the whole point rather than
    # a convenience. Comparing model sets means each set runs the workflows on its OWN
    # backend — `opencode` for a local model, `claude` for the reference — and
    # `get_backend()` falls back to $AGENT_CLI, so an unpinned judge would switch backends
    # in step with the thing it is grading. Every set would then be scored by a different
    # grader, and a delta between two sets would carry no information about either: the
    # benchmark would be measuring its own instrument. Pinning costs one argument.
    judge = Judge(get_backend(spec.judge.get("cli")), AgentResilience.from_env(), SYSTEM_CLOCK)
    pinned = " (pinned by spec/set)" if spec.judge.get("cli") else ""
    print(f"  judging {len(bullets)} bullet(s) with {judge.backend.name}"
          f"{'/' + spec.judge['model'] if spec.judge.get('model') else ''}{pinned}, "
          f"{jobs} at a time…", flush=True)
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        return list(pool.map(lambda b: judge_one(spec, b, rubric, judge), bullets))


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
        # Which set produced this, recorded IN the result rather than only in the path
        # that holds it. A scorecard gets copied, attached to an issue and read months
        # later; one that cannot say which model was at `high` — or which judge graded
        # it — is a number with no claim attached.
        "set": {
            "label": spec.label,
            "cli": os.environ.get("AGENT_CLI", "claude"),
            "power": spec.power,
            "judge": spec.judge,
        },
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


# ── Design completeness: what the brief implied, and author never wrote ────────────────
#
# `score` measures backlog satisfaction, and is blind to this failure by construction: the
# things a real docs-app run left out — no sign-out, no way to delete a page, screens
# reachable only by typing a URL — were never bullets, so satisfying every bullet said
# nothing about them. Authoring an app from a brief is a *design* act; this is the
# instrument that says whether the workflow performed one.
#
# The invariant the whole metric rests on: **a design-completeness score is judged against
# expectations the workflow under test was never shown.** They live under `hidden/` beside
# the spec, no phase of the run reads them, and the suite's `backlog.md` is deliberately
# underspecified. See `suites/docs-app/hidden/README.md`.

DESIGN_LEVELS = {
    0: ("absent", "no epic or story acknowledges this expectation"),
    1: ("mentioned", "prose refers to it; no story's acceptance criteria would deliver it"),
    2: ("covered", "a story's acceptance criteria, taken literally, deliver it"),
}
DESIGN_MAX = 2
# Only reachable on the anchor run (`--live`), which scores the same expectations against
# the app the coder actually built. Its job is calibration, not scoring: if the cheap
# author-phase number stops predicting the live one, the instrument is wrong and gets
# fixed before any more author work trusts it.
OPERABLE = (3, "operable", "the built app does it — executable evidence exercises it live")

PAPER_NOTE = """The epics and stories are the **only** thing you may score from. Do not
open implementation code, and do not let its presence or absence move the level: this
metric grades what the planning step wrote down, and a story the coder happened to build
well is still a story, while a feature built without a story is not this workflow's doing.
Level 2 is the ceiling here."""

LIVE_NOTE = """This is the anchor run, so the built application is in scope **in addition
to** the planning documents. Score levels 0-2 exactly as you would on the documents alone;
award level 3 only when the running app's behavior is exercised by executable evidence you
can point at — a test, an end-to-end script, a recorded QA artifact — that would fail if
the rendering stopped holding. Implementing code that merely looks correct is level 2."""

# The citation rule differs by mode, and it has to: a level-3 finding is *by construction*
# not a planning document, so the paper rule ("cite an epic.md or a story.md") would make
# `operable` uncitable and silently unreachable — the anchor run would then agree with the
# paper run for a reason that has nothing to do with the app.
PAPER_EVIDENCE = """each entry must be a **real, repo-relative path to a planning document
you opened** — an `epic.md` or a `story.md` — optionally with a heading or criterion after
a colon, e.g. `docs/epics/pages/stories/delete-page/story.md:acceptance criteria`."""

LIVE_EVIDENCE = """each entry must be a **real, repo-relative path to a file you opened**,
optionally with a heading, symbol or criterion after a colon. Levels 1 and 2 are still
decided by the planning documents, so cite an `epic.md` or a `story.md` for those. Level 3
is decided by executable evidence, so cite the test or script itself — e.g.
`web/app/routes/page.spec.ts:deletes a page` — and cite the story beside it."""


def design_levels(live: bool) -> dict[int, tuple[str, str]]:
    levels = dict(DESIGN_LEVELS)
    if live:
        levels[OPERABLE[0]] = (OPERABLE[1], OPERABLE[2])
    return levels


def load_pack(spec: Spec, name: str, required: tuple[str, ...]) -> list[dict]:
    """One held-out YAML file, validated at load.

    Hand-edited data whose fields are only ever read inside a rendered prompt: a typo'd
    key would otherwise reach the judge as the literal string `None`, and the judge would
    grade whatever it made of that rather than refusing.
    """
    if spec.hidden_dir is None:
        die(f"{spec.path.parent.name}: no `hidden:` in the spec — this task has no design score")
    path = spec.hidden_dir / name
    if not path.is_file():
        die(f"no {name} at {path}")
    items = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(items, list) or not items:
        die(f"{path}: expected a non-empty list")
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            die(f"{path}[{i}]: expected a mapping, got {type(item).__name__}")
        for key in required:
            value = item.get(key)
            if not isinstance(value, str) or not value.strip():
                die(f"{path}[{i}]: `{key}` must be a non-empty string, got {value!r}")
    return [dict(item) for item in items]


def load_expectations(spec: Spec) -> list[dict]:
    """The held-out pack: an invariant plus its rendering for this app.

    The invariant is the type-independent symmetry ("every entered state is exitable"),
    which is what lets the pack format outlive this suite; the rendering is what that
    means for an app of this shape, and the rendering is what the judge scores.
    """
    return load_pack(spec, "expectations.yaml", ("id", "invariant", "rendering"))


def load_journeys(spec: Spec) -> list[dict]:
    journeys = load_pack(spec, "journeys.yaml", ("id", "persona"))
    for j in journeys:
        steps = j.get("steps") or []
        if not isinstance(steps, list) or not all(isinstance(s, str) and s.strip() for s in steps):
            die(f"journey {j['id']!r}: `steps` must be a non-empty list of strings")
        j["steps"] = [" ".join(s.split()) for s in steps]
    return journeys


def authored_docs(spec: Spec) -> list[str]:
    """Every epic and story author wrote, repo-relative — the judge's whole corpus."""
    out = []
    for epic_md in find_epics(spec.target):
        out.append(str(epic_md.relative_to(spec.target)))
        out += [str(s.relative_to(spec.target))
                for s in sorted(epic_md.parent.glob("stories/*/story.md"))]
    return out


def bad_citations(spec: Spec, evidence: list[str], *, docs_only: bool) -> list[str]:
    """The citations that do not resolve — the judge's commonest failure, checked for free.

    `docs_only` is what keeps the paper score a *paper* score: a citation of
    `web/app/routes/page.tsx` proves the coder built something and proves nothing about
    what author wrote, so on the author-phase run it counts as no citation at all.
    """
    bad = []
    for e in evidence:
        rel = e.split(":", 1)[0].strip()
        if not (spec.target / rel).exists() or (docs_only and not rel.startswith("docs/")):
            bad.append(e)
    return bad


def judge_expectation(spec: Spec, exp: dict, rubric: str, judge: Judge, docs: list[str],
                      *, live: bool) -> dict:
    levels = design_levels(live)
    prompt = render(
        rubric,
        expectation_id=exp["id"],
        invariant=exp["invariant"],
        rendering=" ".join(exp["rendering"].split()),
        target=str(spec.target),
        documents="\n".join(f"  - {d}" for d in docs) or "  (none — author wrote nothing)",
        mode_note=LIVE_NOTE if live else PAPER_NOTE,
        evidence_note=LIVE_EVIDENCE if live else PAPER_EVIDENCE,
        levels="\n".join(f"  {n} {name} — {desc}" for n, (name, desc) in sorted(levels.items())),
    )
    text = call_agent(judge, prompt, node_id=f"design_{exp['id']}", spec=spec)
    parsed = wh_extract.parse_json_from_text(text, ["level", "evidence", "reason"]) or {}
    try:
        level = max(0, min(max(levels), int(parsed.get("level", 0))))
    except (TypeError, ValueError):
        level = 0
    evidence = [str(e) for e in (parsed.get("evidence") or []) if str(e).strip()]
    reason = str(parsed.get("reason") or "").strip() or "(judge returned no reason)"

    # Stricter than `score`'s, and deliberately: there the unproven claim falls back to a
    # structural fact (`planned`) that the epic graph independently establishes. Here
    # there is no such fallback — the citation IS the finding — so an unverifiable claim
    # scores `absent` rather than being discounted to `mentioned`.
    bad = bad_citations(spec, evidence, docs_only=not live)
    unverified = bool(bad) or (level >= 1 and not evidence)
    if unverified and level >= 1:
        level = 0
    return {**exp, "level": level, "evidence": evidence, "reason": reason,
            "unverified_citations": bad, "capped": unverified}


def judge_journey(spec: Spec, journey: dict, rubric: str, judge: Judge,
                  docs: list[str]) -> dict:
    """Walk one persona journey on paper and count the steps no story delivers.

    A checklist catches what someone thought to list; this catches what no enumeration
    holds — a control that exists on a screen the journey never reaches, a step that falls
    between two stories that each assumed the other had it.
    """
    prompt = render(
        rubric,
        journey_id=journey["id"],
        persona=journey["persona"],
        steps="\n".join(f"  {i + 1}. {s}" for i, s in enumerate(journey["steps"])),
        target=str(spec.target),
        documents="\n".join(f"  - {d}" for d in docs) or "  (none — author wrote nothing)",
    )
    text = call_agent(judge, prompt, node_id=f"journey_{journey['id']}", spec=spec)
    parsed = wh_extract.parse_json_from_text(text, ["steps"]) or {}
    answers = parsed.get("steps")
    answers = answers if isinstance(answers, list) else []

    steps = []
    for i, script in enumerate(journey["steps"]):
        # Aligned by position, never by the judge's echo of the step text: a judge that
        # paraphrases (or returns nine answers for ten steps) must not silently drop a
        # step from the denominator. An unanswered step is a dead end, not an absence.
        answer = answers[i] if i < len(answers) and isinstance(answers[i], dict) else {}
        evidence = [str(e) for e in (answer.get("evidence") or []) if str(e).strip()]
        bad = bad_citations(spec, evidence, docs_only=True)
        delivered = bool(answer.get("delivered")) and bool(evidence) and not bad
        why = str(answer.get("why") or "").strip()
        if not answer:
            why = "the judge returned no verdict for this step"
        elif answer.get("delivered") and not delivered:
            why = f"cited nothing that resolves ({', '.join(bad) or 'no citation'})"
        steps.append({"step": script, "delivered": delivered, "evidence": evidence,
                      "why": why or "(no reason given)", "unverified_citations": bad})
    return {**journey, "steps": steps,
            "dead_ends": [s["step"] for s in steps if not s["delivered"]]}


# ── The deterministic sub-check: which entities the stories forgot half of ─────────────
#
# Free, runs first, and reported *alongside* the judged score rather than merged into it —
# the same way reliability already is. It is a second lens with its own failure mode (it
# reads verbs, so a story that delivers deletion without ever saying "delete" is a false
# gap), and averaging a heuristic into a judged number would hide both.

OPERATIONS = {
    "create": ("create", "creates", "creating", "add", "adds", "adding", "start", "starts"),
    "read": ("see", "sees", "view", "views", "read", "reads", "list", "lists", "browse",
             "browses", "open", "opens", "find", "finds"),
    "update": ("edit", "edits", "editing", "update", "updates", "rename", "renames",
               "change", "changes", "move", "moves", "save", "saves"),
    "delete": ("delete", "deletes", "deleting", "remove", "removes", "archive", "archives"),
}
VERB_OP = {verb: op for op, verbs in OPERATIONS.items() for verb in verbs}
# Words that stand between a verb and the thing it acts on. Not a parser — a determiner
# list, which is the whole extent of the grammar this needs.
DETERMINERS = {"a", "an", "the", "their", "its", "his", "her", "our", "any", "all", "each",
               "that", "this", "these", "those", "new", "existing", "another", "other",
               "same", "first", "second", "own", "one", "more", "up", "it", "them", "to",
               "into", "from", "of", "on", "in", "at", "by", "for", "with", "and", "or"}
WORD = re.compile(r"[a-z][a-z'-]*")


def singular(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("sses"):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def entity_operations(text: str) -> dict[str, set[str]]:
    """`verb → the noun it acts on`, over one document. Deterministic, and only that."""
    words = WORD.findall(text.lower())
    found: dict[str, set[str]] = defaultdict(set)
    for i, word in enumerate(words):
        op = VERB_OP.get(word)
        if not op:
            continue
        for candidate in words[i + 1:i + 5]:
            if candidate in DETERMINERS:
                continue
            found[singular(candidate)].add(op)
            break
    return found


def crud_matrix(spec: Spec) -> list[dict]:
    """Every entity the stories create, crossed with read/update/delete.

    `create` is the anchor because it is the operation a brief always names — nobody
    writes an app that never makes anything — while the other three are exactly what a
    stakeholder assumes and a transcribing planner drops. An entity a story creates and no
    story deletes is the `page-delete` miss, found without an agent turn.
    """
    combined: dict[str, set[str]] = defaultdict(set)
    for epic_md in find_epics(spec.target):
        for story in sorted(epic_md.parent.glob("stories/*/story.md")):
            try:
                text = story.read_text(encoding="utf-8")
            except OSError:
                continue
            for entity, ops in entity_operations(text).items():
                combined[entity] |= ops
    return sorted(
        ({"entity": entity, "operations": sorted(ops),
          "missing": sorted({"read", "update", "delete"} - ops)}
         for entity, ops in combined.items() if "create" in ops),
        key=lambda row: (-len(row["missing"]), row["entity"]))


def report_crud_matrix(spec: Spec) -> list[dict]:
    say("entity × operation (deterministic — a second lens, not part of the score)")
    rows = crud_matrix(spec)
    if not rows:
        print("  no story text names anything being created — nothing to cross")
        return rows
    ops = ("create", "read", "update", "delete")
    print(f"  {'entity':<24}" + "".join(f"{o:<9}" for o in ops))
    print(f"  {'-' * 60}")
    for row in rows:
        marks = "".join(f"{'✓' if o in row['operations'] else '·':<9}" for o in ops)
        print(f"  {row['entity'][:23]:<24}{marks}")
    print(f"  {'-' * 60}")
    print(f"  {DIM}read from the stories' verbs, so a story that delivers an operation "
          f"without naming it{RESET}")
    print(f"  {DIM}reads as a gap. Gaps are questions to ask the plan, never a score.{RESET}")
    return rows


def cmd_design_score(spec: Spec, *, judge: bool, jobs: int, only: list[str],
                     live: bool, journeys: bool) -> int:
    """Score what author designed against expectations it was never shown."""
    if not spec.target.is_dir():
        die(f"no target at {spec.target} — nothing to score")
    expectations = load_expectations(spec)
    if only:
        expectations = [e for e in expectations if e["id"] in set(only)]
        if not expectations:
            die(f"no expectation matches {', '.join(only)}")
    docs = authored_docs(spec)
    if not docs:
        die(f"no epics or stories under {spec.target}/docs/epics — run author first")

    say(f"design completeness ({spec.target} — {len(docs)} authored document(s))")
    rows = report_crud_matrix(spec)

    if not judge:
        # There is no structural stand-in for "would these acceptance criteria deliver
        # this". `score --no-judge` can still say `planned` because the epic graph records
        # coverage; nothing records this, so the honest structural answer is to print the
        # deterministic lens and decline to name a number.
        print("\n  --no-judge: the entity × operation matrix above is the whole output.")
        print("  Design satisfaction is a judgement about acceptance criteria and has no")
        print("  structural stand-in — a score without the judge would be an invention.")
        out = write_design_scorecard(spec, [], [], rows, live=live, judged=False)
        print(f"\n  scorecard written to {out}")
        return 0

    rubric_path = HERE / "design-rubric.md"
    journey_rubric_path = HERE / "journey-rubric.md"
    for path in (rubric_path, journey_rubric_path):
        if not path.is_file():
            die(f"no rubric at {path}")
    rubric = rubric_path.read_text(encoding="utf-8")
    grader = Judge(get_backend(spec.judge.get("cli")), AgentResilience.from_env(), SYSTEM_CLOCK)
    mode = "live (built app in scope)" if live else "paper (epics + stories only)"
    print(f"\n  judging {len(expectations)} expectation(s) with {grader.backend.name}, "
          f"{jobs} at a time — {mode}", flush=True)
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        scored = list(pool.map(
            lambda e: judge_expectation(spec, e, rubric, grader, docs, live=live), expectations))

    levels = design_levels(live)
    say("design satisfaction")
    print(f"  {'expectation':<24}{'level':<14}invariant / why")
    print(f"  {'-' * 92}")
    for e in sorted(scored, key=lambda x: -x["level"]):
        flag = " ⚠" if e.get("capped") else ""
        print(f"  {e['id']:<24}{e['level']} {levels[e['level']][0]:<12}{e['invariant'][:36]:<38}"
              f"{e['reason'][:28]}{flag}")
    print(f"  {'-' * 92}")

    total = sum(e["level"] for e in scored)
    pct = 100.0 * total / (DESIGN_MAX * len(scored))
    tally: dict[int, int] = defaultdict(int)
    for e in scored:
        tally[e["level"]] += 1
    # Always a percentage of 2, live run included. The anchor exists to be *compared* with
    # the paper run, and a denominator that moved between them would make the comparison
    # measure the denominator; level 3 is reported as its own count instead.
    print(f"\n  {BOLD}design satisfaction: {pct:.0f}%{RESET}  "
          f"({total}/{DESIGN_MAX * len(scored)} across {len(scored)} expectations, "
          f"as a percentage of {DESIGN_MAX})")
    print("  " + "   ".join(f"{levels[n][0]}: {tally[n]}" for n in sorted(levels, reverse=True)))

    capped = [e for e in scored if e.get("capped")]
    if capped:
        print(f"\n  ⚠ {len(capped)} expectation(s) scored `absent`: the judge claimed coverage")
        print("    but cited planning documents that do not resolve. Unproven, not near-misses:")
        for e in capped:
            print(f"      - {e['id']}: {', '.join(e['unverified_citations']) or '(no citation)'}")

    walked = []
    if journeys:
        scripts = load_journeys(spec)
        journey_rubric = journey_rubric_path.read_text(encoding="utf-8")
        print(f"\n  walking {len(scripts)} journey(s)…", flush=True)
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
            walked = list(pool.map(
                lambda j: judge_journey(spec, j, journey_rubric, grader, docs), scripts))
        report_journeys(walked)

    out = write_design_scorecard(spec, scored, walked, rows, live=live, judged=True, pct=pct)
    print(f"\n  scorecard written to {out}")
    if live:
        compare_paper_and_live(spec, scored)
    return 0


def report_journeys(walked: list[dict]) -> None:
    say("journey walkthrough — dead ends per journey")
    dead = 0
    for j in walked:
        n = len(j["dead_ends"])
        dead += n
        mark = "✓" if not n else "✗"
        print(f"\n  {mark} {j['id']:<24}{n} dead end(s) of {len(j['steps'])} step(s)"
              f"  {DIM}{j['persona'][:40]}{RESET}")
        for step in j["steps"]:
            bullet = " " if step["delivered"] else "✗"
            print(f"      {bullet} {step['step'][:56]:<58}{DIM}{step['why'][:30]}{RESET}")
    if walked:
        print(f"\n  {BOLD}dead ends per journey: {dead / len(walked):.1f}{RESET}  "
              f"({dead} across {len(walked)} journeys)")
        print(f"  {DIM}A checklist catches what someone thought to list. This catches the "
              f"steps that fall{RESET}")
        print(f"  {DIM}between two stories that each assumed the other had them.{RESET}")


def compare_paper_and_live(spec: Spec, scored: list[dict]) -> None:
    """The anchor's only job: does the cheap paper score predict the live one?

    Not a second score. If the two diverge, the *instrument* is what is wrong, and it gets
    fixed before any more author work is judged by it — a paper number nobody has
    calibrated is a number about documents, not about an app anyone can use.
    """
    paper_path = spec.logs / "design-scorecard.json"
    if not paper_path.is_file():
        print(f"\n  {DIM}no paper scorecard at {paper_path} — nothing to calibrate against{RESET}")
        return
    paper = json.loads(paper_path.read_text(encoding="utf-8"))
    before = {e["id"]: e["level"] for e in paper.get("expectations", [])}
    say("calibration — paper (author only) vs live (built app)")
    print(f"  {'expectation':<24}{'paper':<10}{'live':<10}")
    print(f"  {'-' * 48}")
    diverged = []
    for e in sorted(scored, key=lambda x: x["id"]):
        was = before.get(e["id"])
        if was is None:
            continue
        # A live level of 3 is the paper 2 confirmed, not a disagreement.
        if abs(min(e["level"], DESIGN_MAX) - was) >= 1:
            diverged.append(e["id"])
        print(f"  {e['id']:<24}{was:<10}{e['level']:<10}"
              f"{'← diverges' if e['id'] in diverged else ''}")
    print(f"  {'-' * 48}")
    if diverged:
        print(f"\n  ⚠ {len(diverged)} expectation(s) diverge: {', '.join(diverged)}.")
        print("    The paper score is not predicting what a user experiences. Fix the")
        print("    instrument before trusting another author-phase number.")
    else:
        print("\n  ✓ paper and live agree — the cheap score is predicting the expensive one.")


def write_design_scorecard(spec: Spec, expectations: list[dict], journeys: list[dict],
                           crud: list[dict], *, live: bool, judged: bool,
                           pct: float | None = None) -> Path:
    # A separate file from `scorecard.json`, and separately named for the live run: the
    # anchor's whole purpose is to be compared with the paper run it would otherwise
    # overwrite.
    out = spec.logs / ("design-scorecard-live.json" if live else "design-scorecard.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    levels = design_levels(live)
    dead = sum(len(j["dead_ends"]) for j in journeys)
    out.write_text(json.dumps({
        "spec": str(spec.path),
        "target": str(spec.target),
        "mode": "live" if live else "paper",
        "judged": judged,
        "set": {"label": spec.label, "cli": os.environ.get("AGENT_CLI", "claude"),
                "power": spec.power, "judge": spec.judge},
        "design_satisfaction_pct": round(pct, 1) if pct is not None else None,
        "max_level": DESIGN_MAX,
        "levels": {n: name for n, (name, _) in levels.items()},
        "expectations": [{k: e[k] for k in
                          ("id", "invariant", "rendering", "level", "reason", "evidence",
                           "capped", "unverified_citations")} for e in expectations],
        "journeys": [{"id": j["id"], "persona": j["persona"],
                      "steps": j["steps"], "dead_ends": j["dead_ends"]} for j in journeys],
        "dead_ends_per_journey": round(dead / len(journeys), 2) if journeys else None,
        "entity_operations": crud,
        "authored_documents": authored_docs(spec),
        "runs": read_runs(spec),
    }, indent=2), encoding="utf-8")
    return out


# ── CLI ───────────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="bench.py", description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["genesis", "backlog", "author", "coder", "all",
                                       "status", "watch", "babysit", "score", "design-score",
                                       "reset"])
    p.add_argument("--spec", default=str(HERE / "suites" / "todo-app" / "benchmark.yaml"),
                   help="the benchmark app's spec file (default: the todo-app benchmark)")
    p.add_argument("--no-judge", action="store_true",
                   help="score structurally only — no agent turns, no behavioral claim")
    p.add_argument("--jobs", type=int, default=4, help="judge turns to run at once")
    p.add_argument("--bullet", action="append", default=[],
                   help="score only this bullet id (repeatable)")
    p.add_argument("--expectation", action="append", default=[],
                   help="design-score: score only this expectation id (repeatable)")
    p.add_argument("--live", action="store_true",
                   help="design-score: the anchor run — score the same expectations "
                        "against the BUILT app and calibrate the paper score against it")
    p.add_argument("--no-journeys", action="store_true",
                   help="design-score: skip the journey walkthrough (expectations only)")
    p.add_argument("--silence", type=float, default=900.0,
                   help="watch: seconds of no artifact write before a run is called stalled")
    p.add_argument("--every", type=float, default=180.0,
                   help="babysit: seconds between polls")
    p.add_argument("--for", dest="ceiling", type=float, default=7200.0,
                   help="babysit: seconds to keep waiting before giving up (exit 2)")
    p.add_argument("--resume", action="store_true",
                   help="author/coder: continue the newest unfinished run from its "
                        "checkpoint instead of starting a new one")
    p.add_argument("--budget", type=float, default=None,
                   help="author/coder: override the spec's WORKHORSE_MAX_RUNTIME_S. "
                        "Counted from the ORIGINAL start, so a --resume needs a larger "
                        "total than the run already spent, not a fresh allowance")
    args = p.parse_args(argv)

    # Refused rather than ignored: both flags change how long a run takes and where it
    # starts, so a command that silently drops one would hand back a run that looks like
    # the one asked for and is not. `all` is excluded too — "resume" has no single
    # meaning across three phases.
    for flag, given in (("--resume", args.resume), ("--budget", args.budget is not None)):
        if given and args.command not in ("author", "coder"):
            die(f"{flag} applies to `author` and `coder`, not `{args.command}`")
    for flag, given in (("--expectation", bool(args.expectation)), ("--live", args.live),
                        ("--no-journeys", args.no_journeys)):
        if given and args.command != "design-score":
            die(f"{flag} applies to `design-score`, not `{args.command}`")

    spec = load_spec(Path(args.spec).resolve())
    if args.command == "genesis":
        cmd_genesis(spec)
    elif args.command == "backlog":
        cmd_backlog(spec)
    elif args.command == "author":
        return cmd_author(spec, resume=args.resume, budget_s=args.budget)
    elif args.command == "coder":
        return cmd_coder(spec, resume=args.resume, budget_s=args.budget)
    elif args.command == "all":
        # Short-circuited, because each phase consumes the last one's output: `coder`
        # against a half-written epic queue does not produce a worse score, it produces a
        # meaningless one, and the failure to explain is the earlier one either way.
        cmd_genesis(spec)
        return cmd_author(spec) or cmd_coder(spec)
    elif args.command == "status":
        cmd_status(spec)
    elif args.command == "watch":
        return cmd_watch(spec, silence_s=args.silence)
    elif args.command == "babysit":
        return cmd_babysit(spec, silence_s=args.silence, every_s=args.every,
                           ceiling_s=args.ceiling)
    elif args.command == "reset":
        cmd_reset(spec)
    elif args.command == "score":
        return cmd_score(spec, judge=not args.no_judge, jobs=args.jobs, only=args.bullet)
    elif args.command == "design-score":
        return cmd_design_score(spec, judge=not args.no_judge, jobs=args.jobs,
                                only=args.expectation, live=args.live,
                                journeys=not args.no_journeys)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
