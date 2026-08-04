#!/usr/bin/env python3
"""Run the benchmark once per model set, and measure each result against a gold reference.

`bench.py` answers *is this workflow chain any good?* for one configuration. This answers
*which configuration should we buy?* — by driving that same harness N times, holding
everything constant except the models, and diffing what each one produced against a frozen
Claude Code run.

**A set is not a model, and that is the whole reason this file exists.** One `coder` run
makes 41 agent turns: 34 at `power="high"`, 12 at `medium`, 2 at `low`. A set may point
each tier at a different model on a different backend, so "the Qwen result" names nothing.
Results are keyed by the set's *label*; the tier→model mapping travels inside every
scorecard and manifest, which is what makes "does the score depend on the high tier or the
medium tier?" answerable after the runs rather than only before them.

**Three things are held constant or the numbers mean nothing:**

* **The judge.** Pinned in `sets.yml`, independent of the `cli` a set runs its workflows
  on. An unpinned judge follows `$AGENT_CLI` and so switches in step with the thing it is
  grading — see `bench.judge_backlog`.
* **The backlog.** Copied, never generated, by `bench.py backlog`. Already true.
* **The workflow source.** Stamped into every manifest as a git sha. A set run before a
  prompt edit and one run after are not comparable, and this is the only record that says
  so afterwards.

**Gold is frozen, not re-run.** Two Claude Code runs over one backlog do not produce the
same repo, so a reference that moves would mix model quality into every delta. Gold is
produced once per task, bundled, and stamped with the workflow sha it ran on; a matrix
against a different sha is refused rather than quietly compared.

    matrix.py sets                     what is defined, its tags, and what has been run
    matrix.py gold --task <name>       produce or refresh the frozen reference
    matrix.py run [--set L] [--task T] every set × every task, sequentially
    matrix.py run --tag quick          only the tasks tagged `quick` (repeat --tag to AND)
    matrix.py report [--task T]        per-bullet delta against gold
    matrix.py status                   which cells are done, running, missing

Sequential by construction. Wall-clock is one of the outputs, and two sets running at once
contend for the same GPU or the same rate limit, which makes both readings fiction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

import yaml

HERE = Path(__file__).resolve().parent
STABLEMATE = HERE.parent
WORKFLOW_SRC = STABLEMATE / "workflows" / "src" / "workhorse_workflows"
DATA = STABLEMATE / "data"
BENCH = HERE / "bench.py"

#: The phases a cell runs, in order. Short-circuited: `coder` against a half-written epic
#: queue does not score worse, it scores meaninglessly, and the failure to explain is the
#: earlier one either way. `score` still runs after a failed phase — a set that got
#: halfway is a result, and refusing to record it loses the run that cost the hour.
PHASES = ("genesis", "author", "coder")

BOLD, RED, GREEN, DIM, RESET = "\033[1m", "\033[31m", "\033[32m", "\033[2m", "\033[0m"


def say(msg: str) -> None:
    print(f"\n{BOLD}== {msg}{RESET}", flush=True)


def die(msg: str) -> NoReturn:
    raise SystemExit(f"{RED}error: {msg}{RESET}")


# ── The sets file ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ModelSet:
    """One configuration under test: a backend, and a model at each power tier."""

    label: str
    cli: str
    power: dict
    notes: str = ""

    def env(self) -> dict[str, str]:
        """What `bench.py` must see for this set's runs. Everything else is inherited."""
        return {"AGENT_CLI": self.cli,
                "BENCH_SET": self.label,
                "BENCH_POWER": json.dumps(self.power)}


@dataclass(frozen=True, slots=True)
class Task:
    """One benchmark spec, and the labels it can be selected by."""

    path: Path
    tags: frozenset[str]

    @property
    def name(self) -> str:
        return task_name(self.path)


@dataclass(slots=True)
class Matrix:
    """`sets.yml`, validated."""

    path: Path
    judge: dict
    gold: str
    sets: list[ModelSet]
    tasks: list[Task] = field(default_factory=list)

    def set(self, label: str) -> ModelSet:
        for s in self.sets:
            if s.label == label:
                return s
        die(f"no set {label!r} in {self.path} (have: {', '.join(s.label for s in self.sets)})")

    def task(self, name: str) -> Task:
        for t in self.tasks:
            if t.name == name:
                return t
        die(f"no task {name!r} in {self.path} "
            f"(have: {', '.join(t.name for t in self.tasks)})")

    def tags(self) -> list[str]:
        return sorted({tag for t in self.tasks for tag in t.tags})

    def select(self, name: str = "", tags: Sequence[str] = ()) -> list[Task]:
        """The tasks a `--task`/`--tag` pair names, narrowing left to right.

        Repeated `--tag` is AND, not OR: `--tag quick --tag web` means the tasks that are
        both, which is what a filter reads as. OR is spelled by running twice.

        An unknown tag is fatal rather than an empty selection. The two look identical at
        the shell — a matrix that finishes in a second having run nothing — and one of
        them is a typo that would otherwise be read as "nothing needs running".
        """
        known = self.tags()
        for tag in tags:
            if tag not in known:
                die(f"no task tagged {tag!r} (have: {', '.join(known) or '—'})")
        chosen = [self.task(name)] if name else list(self.tasks)
        for tag in tags:
            chosen = [t for t in chosen if tag in t.tags]
        if not chosen:
            die(f"no task matches {' + '.join(filter(None, [name, *tags]))}")
        return chosen


def task_name(spec: Path) -> str:
    """A task is named by the directory holding its spec — `suites/bookmarks/benchmark.yaml`
    is `bookmarks`. Nothing inside the spec names it, and giving it a second name here
    would let the two disagree the way the repo `name:` key once did."""
    return spec.parent.name


def task_tags(spec: Path) -> frozenset[str]:
    """A spec's `tags:`, normalised the way `bench.load_spec` normalises them.

    Read here rather than imported from `bench` because the matrix only needs this one
    key, and `load_spec` reads `$TARGET`/`$BENCH_POWER` and dies on a spec missing
    `surfaces:` — a selection flag must not depend on the ambient environment or on the
    spec being runnable this minute.
    """
    raw = (yaml.safe_load(spec.read_text(encoding="utf-8")) or {}).get("tags") or []
    if isinstance(raw, str):
        raw = [raw]
    return frozenset(str(t) for t in raw)


def load_matrix(path: Path) -> Matrix:
    if not path.is_file():
        die(f"no sets file at {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    sets: list[ModelSet] = []
    for i, s in enumerate(raw.get("sets") or die(f"{path}: no `sets`")):
        label = s.get("label") or die(f"{path}: sets[{i}] has no `label`")
        if not s.get("power"):
            die(f"{path}: set {label!r} has no `power` — a set with no tier mapping runs "
                f"on the operator's ambient config, which is the one thing it must not do")
        sets.append(ModelSet(label=label, cli=s.get("cli") or "claude",
                             power=s["power"], notes=s.get("notes") or ""))

    # A duplicate label is not a warning: cells are keyed by label, so the second set
    # would write its repo, artifacts and scorecard over the first one's and the matrix
    # would report N results having produced N-1.
    seen = [s.label for s in sets]
    if len(set(seen)) != len(seen):
        dupes = sorted({x for x in seen if seen.count(x) > 1})
        die(f"{path}: duplicate set label(s): {', '.join(dupes)}")

    paths = [(path.parent / t).resolve() for t in (raw.get("tasks") or [])]
    for p in paths:
        if not p.is_file():
            die(f"{path}: task spec not found: {p}")
    tasks = [Task(path=p, tags=task_tags(p)) for p in paths]

    gold = raw.get("gold") or "gold"
    matrix = Matrix(path=path, judge=raw.get("judge") or {}, gold=gold, sets=sets, tasks=tasks)
    matrix.set(gold)  # dies here, naming the file, rather than at report time
    if not matrix.judge.get("cli"):
        die(f"{path}: `judge.cli` is required — an unpinned judge follows $AGENT_CLI and "
            f"so changes with every set, which makes each set's score incomparable")
    return matrix


# ── Provenance ────────────────────────────────────────────────────────────────────────


def git_out(*args: str, cwd: Path = STABLEMATE) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    return p.stdout.strip() if p.returncode == 0 else ""


def workflow_sha() -> str:
    """The commit the workflow source is at. A set run before a prompt edit and one run
    after measure different software, and this is the only thing that says so later."""
    return git_out("log", "-1", "--format=%H", "--", str(WORKFLOW_SRC)) or "unknown"


def workflow_dirty() -> bool:
    """Uncommitted workflow edits. Recorded rather than refused — iterating on a prompt
    and benchmarking it is the normal case — but a gold frozen against a dirty tree is
    pinned to a state no sha can recover, so `report` says so."""
    return bool(git_out("status", "--porcelain", "--", str(WORKFLOW_SRC)))


def spec_sha(spec: Path) -> str:
    """The spec and its backlog, hashed together. The backlog is the benchmark's input;
    editing a bullet changes what every score means, and the spec file alone would not
    notice."""
    h = hashlib.sha256()
    for p in (spec, spec.parent / "docs" / "backlog.md"):
        h.update(p.read_bytes() if p.is_file() else b"")
    return h.hexdigest()[:12]


# ── One cell ──────────────────────────────────────────────────────────────────────────


def cell_dir(label: str, task: str) -> Path:
    return DATA / label / task


def manifest_path(label: str, task: str) -> Path:
    return cell_dir(label, task) / "manifest.json"


def read_manifest(label: str, task: str) -> dict | None:
    p = manifest_path(label, task)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def is_complete(m: dict | None) -> bool:
    """A cell is done when it reached `score` and wrote a satisfaction number. A cell whose
    `coder` failed still counts: a partial build is a result, and re-running it would throw
    away the hour it cost to learn that."""
    return bool(m and m.get("finished_at") and m.get("satisfaction_pct") is not None)


def guard_data_dir() -> None:
    """Refuse to write unless `data/` is genuinely untracked.

    Every cell holds a repo with its own `.git`. A nested working tree the outer repo can
    see is how a benchmark ends up staged into the harness that produced it — and this
    repo ships publicly, so a produced app landing in a commit is not merely untidy.
    Checked at runtime because a `.gitignore` entry is one careless edit from gone.
    """
    DATA.mkdir(parents=True, exist_ok=True)
    probe = DATA / ".gitignore-probe"
    probe.write_text("", encoding="utf-8")
    try:
        ignored = subprocess.run(["git", "check-ignore", "-q", str(probe)],
                                 cwd=STABLEMATE, check=False).returncode == 0
    finally:
        probe.unlink(missing_ok=True)
    if not ignored:
        die(f"{DATA} is not gitignored — add `/data/` to .gitignore before running a "
            f"matrix. Every cell contains a git repo of its own, and this tree is public.")


def run_phase(spec: Path, phase: str, env: dict[str, str], log: Path,
              extra: list[str] | None = None) -> tuple[int, float]:
    """One `bench.py` phase, logged. Returns its exit code and wall-clock seconds.

    Driven as a subprocess rather than imported, so the command in the manifest is one a
    person can retype and get the same run. That property is worth more than the
    milliseconds an in-process call would save on a phase measured in hours.
    """
    cmd = [sys.executable, str(BENCH), "--spec", str(spec), phase, *(extra or [])]
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"\n$ {' '.join(cmd)}\n")
        fh.flush()
        rc = subprocess.run(cmd, cwd=STABLEMATE, env={**os.environ, **env},
                            stdout=fh, stderr=subprocess.STDOUT, check=False).returncode
    return rc, time.monotonic() - started


def bundle_repo(repo: Path, out: Path) -> bool:
    """Archive the produced code as a git bundle: full history, one file, no working tree.

    The live `repo/` stays too — it is what `report` and any later re-judging read. The
    bundle is what survives being moved to another machine or another year, and it carries
    the commit history, which is itself evidence: how many commits a set needed, and which
    stories they claim, is a reliability signal the scorecard does not hold.
    """
    if not (repo / ".git").is_dir() or not git_out("log", "-1", "--format=%H", cwd=repo):
        return False
    out.unlink(missing_ok=True)
    return subprocess.run(["git", "-C", str(repo), "bundle", "create", str(out), "--all"],
                          capture_output=True, check=False).returncode == 0


def run_cell(mx: Matrix, ms: ModelSet, spec: Path, *, jobs: int, redo: bool) -> dict:
    """Drive one (set, task) end to end and return its manifest."""
    task = task_name(spec)
    cell = cell_dir(ms.label, task)
    existing = read_manifest(ms.label, task)
    if existing and is_complete(existing) and not redo:
        print(f"  {DIM}skip {ms.label}/{task} — already complete "
              f"({existing['satisfaction_pct']}%){RESET}")
        return existing

    say(f"{ms.label} × {task}")
    repo, runs, log = cell / "repo", cell / ".runs", cell / "matrix.log"
    if redo:
        shutil.rmtree(cell, ignore_errors=True)
    cell.mkdir(parents=True, exist_ok=True)

    env = {**ms.env(),
           "TARGET": str(repo),
           "BENCH_RUNS": str(runs),
           "BENCH_JUDGE": json.dumps(mx.judge)}

    manifest: dict = {
        "set": ms.label, "task": task, "notes": ms.notes,
        "cli": ms.cli, "power": ms.power, "judge": mx.judge,
        "spec": str(spec), "spec_sha": spec_sha(spec),
        "workflow_sha": workflow_sha(), "workflow_dirty": workflow_dirty(),
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "command": " ".join(f"{k}={v!r}" for k, v in sorted(env.items()))
                   + f" python benchmarks/bench.py --spec {spec} all",
        "phases": [], "finished_at": None, "satisfaction_pct": None,
    }
    write_manifest(ms.label, task, manifest)

    for phase in PHASES:
        rc, secs = run_phase(spec, phase, env, log)
        manifest["phases"].append({"name": phase, "rc": rc, "seconds": round(secs, 1)})
        write_manifest(ms.label, task, manifest)
        mark = f"{GREEN}ok{RESET}" if rc == 0 else f"{RED}rc={rc}{RESET}"
        print(f"  {phase:<9} {mark}  {secs / 60:.1f} min")
        if rc != 0:
            print(f"  {DIM}stopping the chain — later phases consume this one's output; "
                  f"scoring what exists{RESET}")
            break

    # Scored regardless. A chain that stopped at `coder` still built something, and the
    # partial score is the measurement that hour bought.
    rc, secs = run_phase(spec, "score", env, log, ["--jobs", str(jobs)])
    manifest["phases"].append({"name": "score", "rc": rc, "seconds": round(secs, 1)})
    manifest["satisfaction_pct"] = read_satisfaction(runs)
    manifest["bundled"] = bundle_repo(repo, cell / "repo.bundle")
    manifest["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    write_manifest(ms.label, task, manifest)
    pct = manifest["satisfaction_pct"]
    print(f"  {BOLD}satisfaction: {pct if pct is not None else '—'}%{RESET}"
          f"  {DIM}({cell}){RESET}")
    return manifest


def write_manifest(label: str, task: str, manifest: dict) -> None:
    """Written after every phase, not once at the end: a matrix that dies in hour six must
    leave behind what the first five hours learned."""
    p = manifest_path(label, task)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def read_scorecard(label: str, task: str) -> dict | None:
    p = cell_dir(label, task) / ".runs" / "scorecard.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def read_satisfaction(runs: Path) -> float | None:
    p = runs / "scorecard.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("satisfaction_pct")
    except json.JSONDecodeError:
        return None


# ── Gold ──────────────────────────────────────────────────────────────────────────────


def gold_staleness(mx: Matrix, task: str) -> str:
    """Why the frozen reference cannot be compared against, or "" if it can.

    Refused rather than warned, per the design: a delta computed against a gold that ran
    on different workflow source, or a different backlog, is a number with no meaning that
    nonetheless prints and gets quoted.
    """
    m = read_manifest(mx.gold, task)
    if not m or not is_complete(m):
        return f"no frozen gold for {task!r} — run: matrix.py gold --task {task}"
    if m.get("workflow_sha") != workflow_sha():
        return (f"gold for {task!r} ran on workflow {m.get('workflow_sha', '?')[:7]}, "
                f"HEAD is {workflow_sha()[:7]} — re-run: matrix.py gold --task {task}")
    if m.get("spec_sha") != spec_sha(mx.task(task).path):
        return (f"gold for {task!r} ran on a different spec/backlog — "
                f"re-run: matrix.py gold --task {task}")
    if m.get("judge") != mx.judge:
        return (f"gold for {task!r} was graded by a different judge "
                f"({m.get('judge')}) than sets.yml now pins ({mx.judge})")
    return ""


# ── Commands ──────────────────────────────────────────────────────────────────────────


def tier_model(ms: ModelSet, tier: str) -> str:
    """The model a set puts at one power tier, for display.

    A tier maps backend→settings (`{high: {opencode: {model: …}}}`) because that is the
    shape `bench.effective_config` overlays onto the operator's config. A set names one
    backend, so the first value is the one that will be used.
    """
    return next(iter((ms.power.get(tier) or {}).values()), {}).get("model", "—")


def cmd_sets(mx: Matrix) -> int:
    print(f"\n{BOLD}judge{RESET}  {mx.judge.get('cli')}/{mx.judge.get('model', '(default)')}"
          f"  {DIM}— pinned for every set, including gold{RESET}")
    print(f"{BOLD}gold{RESET}   {mx.gold}\n")
    # Width from the content, not a guess: an OpenRouter id like
    # `openrouter/deepseek/deepseek-v4-flash` overruns any fixed column, and a table whose
    # cells run together is one nobody reads twice.
    w = max((len(tier_model(s, n)) for s in mx.sets for n in ("high", "medium")), default=8) + 2
    print(f"  {'set':<20}{'cli':<10}{'high':<{w}}{'medium':<{w}}low")
    for s in mx.sets:
        print(f"  {s.label:<20}{s.cli:<10}{tier_model(s, 'high'):<{w}}"
              f"{tier_model(s, 'medium'):<{w}}{tier_model(s, 'low')}")
    # Tags are printed beside the task rather than summarised, because the point of the
    # listing is to answer "what can I pass to --tag?" without opening four spec files.
    tw = max((len(t.name) for t in mx.tasks), default=8) + 2
    print(f"\n  {BOLD}tasks{RESET}")
    for t in mx.tasks:
        print(f"  {t.name:<{tw}}{DIM}{' '.join(sorted(t.tags)) or '(untagged)'}{RESET}")
    print(f"\n  {DIM}{len(mx.sets)} set(s) × {len(mx.tasks)} task(s) = "
          f"{len(mx.sets) * len(mx.tasks)} cell(s) — narrow with --set/--task/--tag{RESET}")
    return 0


def cmd_status(mx: Matrix) -> int:
    print(f"\n  {'set':<20}" + "".join(f"{t.name:<20}" for t in mx.tasks))
    for s in mx.sets:
        row = f"  {s.label:<20}"
        for t in mx.tasks:
            m = read_manifest(s.label, t.name)
            if m and is_complete(m):
                text, colour = f"{m['satisfaction_pct']}%", ""
            elif m:
                text, colour = "partial", DIM
            else:
                text, colour = "—", DIM
            # Padded on the plain text, coloured afterwards. An f-string width counts the
            # escape sequence as visible characters, so colouring first silently shortens
            # every coloured column by the length of its escapes.
            row += f"{colour}{text:<20}{RESET}" if colour else f"{text:<20}"
        print(row)
    print()
    for t in mx.tasks:
        if stale := gold_staleness(mx, t.name):
            print(f"  {RED}gold: {stale}{RESET}")
    return 0


def cmd_run(mx: Matrix, *, only_set: str, only_task: str, only_tags: Sequence[str],
            jobs: int, redo: bool, gold_only: bool) -> int:
    guard_data_dir()
    sets = [mx.set(only_set)] if only_set else ([mx.set(mx.gold)] if gold_only else mx.sets)
    tasks = mx.select(only_task, only_tags)
    if not gold_only and not only_set:
        # Gold first, always: every other set is measured against it, and running the
        # cheap sets first only to find the reference missing wastes the whole batch.
        sets = sorted(sets, key=lambda s: s.label != mx.gold)

    print(f"\n{BOLD}{len(sets)} set(s) × {len(tasks)} task(s), sequentially{RESET}")
    print(f"{DIM}workflow {workflow_sha()[:7]}"
          f"{' (DIRTY — uncommitted workflow edits)' if workflow_dirty() else ''}{RESET}")
    for ms in sets:
        for t in tasks:
            run_cell(mx, ms, t.path, jobs=jobs, redo=redo)
    say("matrix complete")
    return cmd_status(mx)


def cmd_report(mx: Matrix, *, only_task: str, only_tags: Sequence[str], write: bool) -> int:
    rc = 0
    for t in mx.select(only_task, only_tags):
        task = t.name
        if stale := gold_staleness(mx, task):
            print(f"\n{RED}error: {stale}{RESET}", file=sys.stderr)
            rc = 1
            continue
        text = render_report(mx, task)
        print(text)
        if write:
            out = DATA / "reports" / f"{task}.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            print(f"  {DIM}written to {out}{RESET}")
    return rc


def render_report(mx: Matrix, task: str) -> str:
    """Per-bullet levels, every set beside gold.

    The headline percentage is reported but is not the interesting column. Two sets can
    tie at 55% having failed on disjoint bullets, and which bullets a configuration drops
    is what tells you whether the weakness is reasoning, tool use, or breadth — a mean
    cannot say that, and averaging it away is how a benchmark stops being diagnostic.
    """
    gold = read_scorecard(mx.gold, task)
    gm = read_manifest(mx.gold, task)
    if not gold or not gm:
        # `gold_staleness` vouches for both before this is reached, so arriving here means
        # the cell was deleted between the two reads. Say that, rather than tracebacking.
        return f"# {task}\n\ngold scorecard or manifest is missing — re-run `matrix.py gold`.\n"
    gold_levels = {b["id"]: b["level"] for b in gold["bullets"]}

    others = [(s, read_scorecard(s.label, task)) for s in mx.sets if s.label != mx.gold]
    scored = [(s, c) for s, c in others if c]

    lines = [
        f"# {task}",
        "",
        f"Gold: `{mx.gold}` at {gold['satisfaction_pct']}% — "
        f"workflow `{gm['workflow_sha'][:7]}`, spec `{gm['spec_sha']}`, "
        f"judge `{mx.judge.get('cli')}/{mx.judge.get('model', 'default')}`.",
        "",
        "## Headline",
        "",
        "| set | satisfaction | vs gold | wall-clock | phases ok |",
        "| --- | ---: | ---: | ---: | --- |",
        f"| **{mx.gold}** (gold) | {gold['satisfaction_pct']}% | — | "
        f"{total_minutes(gm):.0f} min | {phases_ok(gm)} |",
    ]
    for s, card in scored:
        m = read_manifest(s.label, task) or {}
        delta = card["satisfaction_pct"] - gold["satisfaction_pct"]
        lines.append(f"| {s.label} | {card['satisfaction_pct']}% | {delta:+.1f} | "
                     f"{total_minutes(m):.0f} min | {phases_ok(m)} |")
    for s, card in others:
        if not card:
            lines.append(f"| {s.label} | *not run* | | | |")

    lines += ["", "## Per bullet", "",
              "Level 0 absent · 1 planned · 2 built · 3 verified. "
              "A cell below gold is where that set lost the point.", "",
              "| bullet | gold | " + " | ".join(s.label for s, _ in scored) + " |",
              "| --- | ---: | " + " | ".join("---:" for _ in scored) + " |"]
    for b in gold["bullets"]:
        cells = []
        for _, card in scored:
            lvl = next((x["level"] for x in card["bullets"] if x["id"] == b["id"]), None)
            if lvl is None:
                cells.append("·")
            else:
                d = lvl - gold_levels[b["id"]]
                cells.append(f"{lvl}" if d == 0 else f"{lvl} ({d:+d})")
        lines.append(f"| `{b['id']}` | {b['level']} | " + " | ".join(cells) + " |")

    lines += ["", "## Sets", "",
              "| set | cli | high | medium | low | notes |",
              "| --- | --- | --- | --- | --- | --- |"]
    for s in mx.sets:
        lines.append(f"| {s.label} | {s.cli} | {tier_model(s, 'high')} | "
                     f"{tier_model(s, 'medium')} | {tier_model(s, 'low')} | {s.notes} |")
    return "\n".join(lines) + "\n"


def total_minutes(manifest: dict) -> float:
    return sum(float(p.get("seconds") or 0) for p in manifest.get("phases", [])) / 60


def phases_ok(manifest: dict) -> str:
    phases = manifest.get("phases", [])
    bad = [p["name"] for p in phases if p.get("rc")]
    return "all" if not bad else "failed: " + ", ".join(bad)


# ── CLI ───────────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="matrix.py", description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["sets", "run", "gold", "report", "status"])
    p.add_argument("--sets", default=str(HERE / "sets.yml"), help="the sets file")
    p.add_argument("--set", dest="only_set", default="", help="run only this set")
    p.add_argument("--task", dest="only_task", default="", help="run/report only this task")
    p.add_argument("--tag", dest="only_tags", action="append", default=[], metavar="TAG",
                   help="run/report only tasks carrying this tag; repeat to narrow "
                        "further (AND). `matrix.py sets` lists them")
    p.add_argument("--jobs", type=int, default=4, help="judge turns to run at once")
    p.add_argument("--redo", action="store_true",
                   help="re-run cells that are already complete, discarding what is there")
    p.add_argument("--write", action="store_true",
                   help="report: also write data/reports/<task>.md")
    args = p.parse_args(argv)

    mx = load_matrix(Path(args.sets).resolve())
    if args.command == "sets":
        return cmd_sets(mx)
    if args.command == "status":
        return cmd_status(mx)
    if args.command == "report":
        return cmd_report(mx, only_task=args.only_task, only_tags=args.only_tags,
                          write=args.write)
    return cmd_run(mx, only_set=args.only_set, only_task=args.only_task,
                   only_tags=args.only_tags, jobs=args.jobs, redo=args.redo,
                   gold_only=args.command == "gold")


if __name__ == "__main__":
    raise SystemExit(main())
