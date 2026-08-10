#!/usr/bin/env python3
"""Replay one story's docs or QA flow against a frozen app, and measure whether it converges.

`groom loops` put a number on the coder's review loops across every run on this machine:
1231 excess turns and $769, concentrated in four nodes that all judge *prose* rather than
code — `plan-qa` (18% exit rate), `document-story` (22%), `review-qa-plan` (28%),
`review-story-documentation` (28%). Every node that produces or changes code converges.

Fixing that means changing prompts and flow structure, and a change to a review loop can
only be believed if it is measured. `bench.py coder` is the wrong instrument: it costs
hours, builds the whole app, and moves every variable at once, so it cannot attribute a
difference to the one prompt you edited.

This can. A finished benchmark app is frozen into a git bundle; a trial clones it, rewinds
**one flow's outputs for one story**, and re-runs that flow standalone — `workhorse-coder
run qa` / `run docs`, which are first-class entry points taking a story slug. Everything
else about the tree is byte-identical between trials, so the exit rate that comes back is
a property of the code under test.

    replay.py capture                                   refresh the bundle from `source:`
    replay.py run --flow qa --story expense-list -n 3   three trials, one story
    replay.py run --flow qa --all -n 1                  one trial of every story
    replay.py report --label before                     the loop table for a saved label

`--label` names the configuration being measured, and is what makes a before/after
comparison possible: run the same command on either side of a change with different
labels, and `report` prints each one's exit rate per node. Measurement itself is not
reimplemented — the trials are recorded in groom's telemetry like any other run, and
`report` reads `groom.store.loop_convergence`, the same function behind `groom loops`.

What a trial deliberately does NOT do is judge the app. Whether the produced QA plan is
any *good* is `bench.py score`'s question, and it stays a floor rather than a gradient: a
change that halves the laps and guts the plan has not improved anything.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

import yaml

HERE = Path(__file__).resolve().parent
STABLEMATE = HERE.parent
FIXTURES = HERE / "fixtures"
# Off `/tmp`, which is where the source app happens to live and which does not survive a
# reboot. A fixture that evaporates is not a fixture.
BUNDLE_DIR = Path.home() / ".local" / "share" / "stablemate" / "fixtures"
WORK_DIR = HERE / ".replay"

# What each flow *writes*, and therefore what a trial must remove before re-running it.
#
# The QA flow's own `clear_qa_evidence` already deletes `qa/` and `qa-evidence.json` at
# entry, so listing them here is belt-and-braces rather than load-bearing; the plan files
# are the ones that matter, because a plan left on disk is a plan the flow would repair
# instead of author, which is a different loop from the one being measured.
QA_OUTPUTS = (
    "qa-plan.yml", "qa-plan.md", "qa.md", "qa-evidence.json",
    "qa-okf-verification-index.json", "qa",
)

# The nodes this harness exists to move. Others still print — a change that fixes one loop
# by pushing the work into another has not fixed anything — but these are the headline.
WATCHED = ("plan-qa", "review-qa-plan", "document-story", "review-story-documentation")

BOLD, RED, DIM, RESET = "\033[1m", "\033[31m", "\033[2m", "\033[0m"


def say(msg: str) -> None:
    print(f"\n{BOLD}== {msg}{RESET}", flush=True)


def die(msg: str) -> NoReturn:
    print(f"{RED}error: {msg}{RESET}", file=sys.stderr)
    raise SystemExit(1)


def git(*args: str, cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        die(f"git {' '.join(args)} failed in {cwd}:\n{proc.stderr.strip()}")
    return proc.stdout.strip()


@dataclass(frozen=True)
class Fixture:
    """A frozen app plus the commit each story is replayed against."""

    name: str
    source: Path
    stories: list[dict[str, str]]

    @property
    def bundle(self) -> Path:
        return BUNDLE_DIR / f"{self.name}.bundle"

    @property
    def repo_dirname(self) -> str:
        """What a trial's clone must be *called*, which is not a cosmetic choice.

        farrier derives the names of the files it generates from the repo directory's
        basename — `.claude/skills/<basename>-go-service/`, and so on for two dozen more.
        Clone the fixture into a directory named anything else and farrier writes a fresh
        set under the new prefix while the tracked set, which the book and the agents
        context both point at, is left dangling. The flow then runs against a repo that no
        longer resolves its own skills, and the resulting lap count measures that instead
        of the change under test.
        """
        return self.source.name

    def commit(self, story: str, flow: str) -> str:
        for entry in self.stories:
            if entry["story"] == story:
                if not entry.get(flow):
                    die(f"fixture {self.name!r} has no {flow} commit for story {story!r}")
                return str(entry[flow])
        known = ", ".join(entry["story"] for entry in self.stories)
        die(f"no story {story!r} in fixture {self.name!r} (have: {known})")

    def slugs(self, flow: str) -> list[str]:
        return [entry["story"] for entry in self.stories if entry.get(flow)]


def load_fixture(name: str) -> Fixture:
    path = FIXTURES / f"{name}.yml"
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in FIXTURES.glob("*.yml"))) or "none"
        die(f"no fixture {name!r} at {path} (have: {available})")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Fixture(
        name=data.get("name") or name,
        source=Path(data.get("source", "")),
        stories=list(data.get("stories") or []),
    )


# ── capture ───────────────────────────────────────────────────────────────────────────


def cmd_capture(fixture: Fixture) -> None:
    """Freeze the source app into a bundle.

    A bundle rather than a copy of the working tree, because the fixture's whole value is
    its *history*: a story is replayed against the tree as it stood when that story was
    finished, and the later stories' commits are what make that reachable.
    """
    if not (fixture.source / ".git").is_dir():
        die(f"no git repo at {fixture.source} — nothing to capture")
    dirty = git("status", "--porcelain", cwd=fixture.source)
    if dirty:
        print(f"{DIM}  note: {fixture.source} has uncommitted changes; "
              f"they are NOT in the bundle{RESET}")
    fixture.bundle.parent.mkdir(parents=True, exist_ok=True)
    git("bundle", "create", str(fixture.bundle), "--all", cwd=fixture.source)
    size = fixture.bundle.stat().st_size / 1024
    say(f"captured {fixture.name} → {fixture.bundle} ({size:.0f} KiB)")


# ── run ───────────────────────────────────────────────────────────────────────────────


def checkout(fixture: Fixture, story: str, flow: str, dest: Path) -> Path:
    """Clone the bundle at this story's commit and rewind the flow's outputs.

    The rewind is per flow, because the two flows write to different places:

      * **qa** deletes the story's plan and evidence from its spec dir, leaving the story,
        the implementation plan and the code — exactly the state `run qa` is entered in.
      * **docs** restores `docs/features` to the commit's *parent*, so the book lags this
        story by precisely one story. That is the real historical input, and it matters
        for what is being measured: a book rewound further would be missing entries
        outside this story's obligations, which is the very thing the reviewer is being
        asked to stop refusing on.
    """
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    commit = fixture.commit(story, flow)
    subprocess.run(
        ["git", "clone", "--quiet", str(fixture.bundle), str(dest)],
        check=True, capture_output=True, text=True,
    )
    git("checkout", "--quiet", commit, cwd=dest)

    if flow == "qa":
        spec = dest / "docs" / "specs" / story
        if not spec.is_dir():
            die(f"no spec dir {spec} at {commit} — is the fixture's commit right?")
        for name in QA_OUTPUTS:
            target = spec / name
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
    elif flow == "docs":
        git("checkout", f"{commit}~", "--", "docs/features", cwd=dest)
    else:  # pragma: no cover - argparse constrains the choices
        die(f"unknown flow {flow!r}")

    # `.agents/agents-context.json` is generated and gitignored, so a fresh clone has none
    # and every prompt path would fail to resolve. farrier regenerates it from the tracked
    # `agents.yml`, which is what a real checkout of this repo would do too.
    proc = subprocess.run(
        ["uv", "run", "farrier", "install", "--repo", str(dest)],
        cwd=STABLEMATE, capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        die(f"farrier install failed for {dest}:\n{proc.stdout}\n{proc.stderr}")
    return dest


def trial_id(label: str, flow: str, story: str, n: int) -> str:
    return f"replay-{label}-{flow}-{story}-{n}"


def run_trial(
    fixture: Fixture, *, flow: str, story: str, label: str, n: int, budget_s: float
) -> tuple[str, int]:
    """One clone, one flow run. Returns the run id and the workflow's exit code."""
    run_id = trial_id(label, flow, story, n)
    work = WORK_DIR / label / run_id
    repo = checkout(fixture, story, flow, work / fixture.repo_dirname)
    artifacts = work / "artifacts"
    log = work / "run.log"

    env = {**os.environ, "AGENT_REPO_DIR": str(repo)}
    if budget_s > 0:
        # Enforced between states by workhorse itself, so an over-budget trial stops at a
        # node boundary with its telemetry intact and still reports a partial lap count.
        env["WORKHORSE_MAX_RUNTIME_S"] = str(budget_s)
    cmd = [
        "uv", "run", "workhorse-coder", "run", flow,
        "--runs-dir", str(artifacts), "--run-id", run_id,
        "--params", json.dumps({"story": story, "docs_path": str(repo)}),
    ]
    say(f"{run_id}")
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen(
            cmd, cwd=STABLEMATE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=env,
        )
        assert proc.stdout is not None  # noqa: S101 - stdout=PIPE guarantees it
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            fh.write(line)
        rc = proc.wait()
    if rc != 0:
        # Not fatal. A flow that exhausted its budgets and blocked is a *result* — it is
        # the loop failing to converge, which is the thing being measured — and its spans
        # are already in groom. Only a crash before the first turn would be uninformative,
        # and that shows up as a run with no laps at all.
        print(f"{RED}  {run_id} exited {rc} — see {log}{RESET}")
    return run_id, rc


def cmd_run(fixture: Fixture, args: argparse.Namespace) -> int:
    if not fixture.bundle.is_file():
        die(f"no bundle at {fixture.bundle} — run `replay.py capture` first")
    stories = fixture.slugs(args.flow) if args.all_stories else [args.story]
    if not args.all_stories and not args.story:
        die("give --story <slug>, or --all for every story in the fixture")

    trials: list[dict[str, Any]] = []
    worst = 0
    for story in stories:
        for n in range(1, args.trials + 1):
            run_id, rc = run_trial(
                fixture, flow=args.flow, story=story, label=args.label,
                n=n, budget_s=args.budget,
            )
            trials.append({"run_id": run_id, "flow": args.flow, "story": story, "rc": rc})
            worst = max(worst, abs(rc))

    ledger = WORK_DIR / args.label / "trials.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(ledger.read_text(encoding="utf-8")) if ledger.is_file() else []
    by_id = {entry["run_id"]: entry for entry in [*existing, *trials]}
    ledger.write_text(json.dumps(sorted(by_id.values(), key=lambda e: e["run_id"]), indent=2))

    report(args.label)
    return worst


# ── report ────────────────────────────────────────────────────────────────────────────


def read_ledger(label: str) -> list[dict[str, Any]]:
    ledger = WORK_DIR / label / "trials.json"
    if not ledger.is_file():
        die(f"no trials recorded under label {label!r} — expected {ledger}")
    return json.loads(ledger.read_text(encoding="utf-8"))


def report(label: str) -> None:
    """Aggregate every trial under one label into a per-node convergence table.

    Laps are summed across trials rather than averaged, which is the right aggregation for
    this statistic: the exit rate is a per-lap acceptance probability, and pooling the laps
    is its maximum-likelihood estimate over the whole sample. Averaging per-trial rates
    would weight a one-lap story the same as a thirteen-lap one.
    """
    from groom import store  # noqa: PLC0415 - a heavy import only `report` needs

    trials = read_ledger(label)
    # node -> [laps per (run, work item)], pooled over every trial under this label.
    pooled: dict[str, list[dict[str, Any]]] = {}
    for trial in trials:
        # min_work_items=1: a trial is ONE story, so every node has exactly one work item.
        # `groom loops`' default of 3 exists to keep one-off nodes out of a whole-machine
        # report and would silence this one entirely.
        for row in store.loop_convergence(run=trial["run_id"], min_work_items=1):
            pooled.setdefault(row["node"], []).append(row)

    if not pooled:
        print(f"{DIM}  no laps recorded for label {label!r} — did the runs reach an "
              f"agent turn? (check .replay/{label}/*/run.log){RESET}")
        return

    say(f"label {label!r}: {len(trials)} trial(s)")
    print(f"  {'node':<30} {'items':>5} {'turns':>5} {'exit':>6} {'mean':>5} {'max':>4} "
          f"{'cost$':>8}")
    order = sorted(
        pooled.items(), key=lambda kv: (kv[0] not in WATCHED, -sum(r["turns"] for r in kv[1]))
    )
    for node, rows in order:
        items = sum(row["work_items"] for row in rows)
        turns = sum(row["turns"] for row in rows)
        cost = sum(row["cost_usd"] or 0.0 for row in rows)
        mark = BOLD if node in WATCHED else ""
        print(f"  {mark}{node:<30}{RESET if mark else ''} {items:>5} {turns:>5} "
              f"{items / turns:>5.0%} {turns / items:>5.2f} "
              f"{max(row['max_laps'] for row in rows):>4} {cost:>8.2f}")
    total = sum(row["turns"] - row["work_items"] for rows in pooled.values() for row in rows)
    spend = sum(row["cost_usd"] or 0.0 for rows in pooled.values() for row in rows)
    print(f"  {DIM}{'—' * 68}{RESET}")
    print(f"  {'TOTAL':<30} {'':>5} {'':>5} {'':>6} {'':>5} {'':>4} {spend:>8.2f}"
          f"   ({total} excess turns)")


def cmd_report(args: argparse.Namespace) -> int:
    for label in args.labels:
        report(label)
    return 0


# ── cli ───────────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--fixture", default="expense-split", help="fixture name under fixtures/")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("capture", help="freeze the fixture's source app into a bundle")

    run_p = sub.add_parser("run", help="replay one flow for one story, N times")
    run_p.add_argument("--flow", choices=("qa", "docs"), required=True)
    run_p.add_argument("--story", default="", help="story slug; omit with --all")
    run_p.add_argument("--all", dest="all_stories", action="store_true",
                       help="every story the fixture has a commit for on this flow")
    run_p.add_argument("-n", "--trials", type=int, default=1,
                       help="trials per story (default 1). A review loop is stochastic; "
                            "one trial is an anecdote")
    run_p.add_argument("--label", default="local",
                       help="names the configuration under test — the unit `report` compares")
    run_p.add_argument("--budget", type=float, default=0.0,
                       help="wall-clock ceiling per trial, in seconds (0 = unbounded)")

    report_p = sub.add_parser("report", help="the loop table for saved labels")
    report_p.add_argument("labels", nargs="+")

    args = parser.parse_args(argv)
    if args.command == "report":
        return cmd_report(args)
    fixture = load_fixture(args.fixture)
    if args.command == "capture":
        cmd_capture(fixture)
        return 0
    return cmd_run(fixture, args)


if __name__ == "__main__":
    raise SystemExit(main())
