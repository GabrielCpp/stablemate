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
    replay.py report before                             the loop table for a saved label
    replay.py --fixture seat-booking score              detection, against the answer key

`--label` names the configuration being measured, and is what makes a before/after
comparison possible: run the same command on either side of a change with different
labels, and `report` prints each one's exit rate per node. Measurement itself is not
reimplemented — the trials are recorded in groom's telemetry like any other run, and
`report` reads `groom.store.loop_convergence`, the same function behind `groom loops`.

Convergence alone is only half a measurement, and the wrong half to optimise on its own: a
flow that approves everything converges in one lap. `score` supplies the other half. It
needs a fixture whose defects are known in advance, which is what an `app:` fixture is —
a hand-written app under `benchmarks/apps/` shipping `defects.yml`, an answer key naming
the OKF obligation each seeded defect makes false. A scored round runs a clean control plus
one trial per defect and prints detection beside the laps:

    caught 6/8  missed 2  false 1 | plan-qa 2.1 laps ~$0.94
    leverage: entry 3/3  deep-links 1  roles 14/15  obligations 22/24  journeys 2/3

The second line is the leverage scorecard, and it is there because detection is gameable
in a direction nobody notices: a plan that opens every screen by its URL and asserts on
rendered strings catches a seeded defect exactly as well as one that enters each flow
where the book says it starts, clicks its way between screens, and addresses the UI by the
roles the book documents. The scorecard reads the artifacts the trial already produced and
says which of the two it was. A metric whose input is missing prints `–`, never `0`.

The money is `$0.94` when the harness billed it, `~$0.94` when nothing billed and the
figure comes from `groom.prices`' rate card applied to the recorded tokens, and `$?` when
neither exists. The default backend is `opencode`, which reports a literal `$0` over
millions of tokens, so the estimate is what keeps the column alive at all.

What a trial deliberately does NOT do is judge the app. Whether the produced QA plan is
any *good* is `bench.py score`'s question, and it stays a floor rather than a gradient: a
change that halves the laps and guts the plan has not improved anything.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlsplit

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
#
# `review-qa-plan` used to be here and is gone: the node was deleted and its job folded
# into `audit-qa`, so leaving it listed would keep bolding a row that can never appear
# again while the node that inherited the work printed unmarked.
WATCHED = ("plan-qa", "audit-qa", "document-story", "review-story-documentation")

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
    """A frozen app plus how a trial reaches one story's state.

    Two forms, and a fixture is exactly one of them:

    * **`source:`** — an external repo with real history, frozen into a bundle. A story is
      replayed against the commit that finished it, named in `stories:`.
    * **`app:`** — a tracked tree under `benchmarks/apps/` with no history at all. A story
      is *materialized*: the git state is built from the story's own pre-images. This is
      the form used for measuring detection, because the app and its answer key have to be
      readable — a bundle is a binary pack `check_public.py` can only scan by path.
    """

    name: str
    source: Path
    app: Path | None
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
        return (self.app or self.source).name

    def commit(self, story: str, flow: str) -> str:
        for entry in self.stories:
            if entry["story"] == story:
                if not entry.get(flow):
                    die(f"fixture {self.name!r} has no {flow} commit for story {story!r}")
                return str(entry[flow])
        known = ", ".join(entry["story"] for entry in self.stories)
        die(f"no story {story!r} in fixture {self.name!r} (have: {known})")

    def slugs(self, flow: str) -> list[str]:
        # An `app:` fixture has no per-flow commits: every story it lists is materializable
        # for every flow, because its git state is built rather than checked out.
        if self.app is not None:
            return [entry["story"] for entry in self.stories]
        return [entry["story"] for entry in self.stories if entry.get(flow)]


def load_fixture(name: str) -> Fixture:
    path = FIXTURES / f"{name}.yml"
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in FIXTURES.glob("*.yml"))) or "none"
        die(f"no fixture {name!r} at {path} (have: {available})")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    app = data.get("app")
    if bool(app) == bool(data.get("source")):
        die(f"fixture {path} must set exactly one of `app:` or `source:`")
    if app and Path(app).is_absolute():
        # Repo-relative on purpose: an absolute path bakes one machine's layout into a
        # tracked file, and the whole point of the `app:` form is that the fixture travels
        # with the repo.
        die(f"fixture {path}: `app:` must be relative to the repo root, got {app!r}")
    return Fixture(
        name=data.get("name") or name,
        source=Path(data.get("source", "")),
        app=(STABLEMATE / app) if app else None,
        stories=list(data.get("stories") or []),
    )


# ── capture ───────────────────────────────────────────────────────────────────────────


def cmd_capture(fixture: Fixture) -> None:
    """Freeze the source app into a bundle.

    A bundle rather than a copy of the working tree, because the fixture's whole value is
    its *history*: a story is replayed against the tree as it stood when that story was
    finished, and the later stories' commits are what make that reachable.
    """
    if fixture.app is not None:
        die(f"fixture {fixture.name!r} is an `app:` fixture — its tree is tracked in this "
            f"repo and materialized per story, so there is nothing to capture")
    if not (fixture.source / ".git").is_dir():
        die(f"no git repo at {fixture.source} — nothing to capture")
    dirty = git("status", "--porcelain", cwd=fixture.source)
    if dirty:
        print(f"{DIM}  note: {fixture.source} has uncommitted changes; "
              f"they are NOT in the bundle{RESET}")
    fixture.bundle.parent.mkdir(parents=True, exist_ok=True)
    draft = fixture.bundle.with_suffix(".bundle.new")
    git("bundle", "create", str(draft), "--all", cwd=fixture.source)
    missing = unbundled_commits(fixture, draft)
    if missing:
        draft.unlink(missing_ok=True)
        die(f"{fixture.source} no longer reaches "
            f"{', '.join(f'{commit} ({story}.{flow})' for story, flow, commit in missing)}"
            f" from any ref — `git bundle --all` packs refs, so the capture would ship a "
            f"bundle those stories cannot be replayed from. The existing bundle at "
            f"{fixture.bundle} is untouched. Restore the commit to a ref in the source "
            f"(`git update-ref refs/heads/fixture/<story> <sha>`) or re-pin the fixture.")
    draft.replace(fixture.bundle)
    size = fixture.bundle.stat().st_size / 1024
    say(f"captured {fixture.name} → {fixture.bundle} ({size:.0f} KiB)")


def unbundled_commits(fixture: Fixture, bundle: Path) -> list[tuple[str, str, str]]:
    """Every `(story, flow, commit)` the fixture pins that *bundle* cannot check out.

    A story's commit stops being reachable the moment the source repo's branches move off
    it — an abandoned lane, a reset, a rebase — and it then survives only in the reflog,
    where `--all` cannot see it. Nothing about the capture fails: it writes a smaller
    bundle over the working one, and the loss surfaces later as a replay dying on
    `pathspec ... did not match`, with the artifact that had the commit already gone.
    """
    listed = {
        line.split()[0]
        for line in git("bundle", "list-heads", str(bundle), cwd=fixture.source).splitlines()
        if line.strip()
    }
    missing: list[tuple[str, str, str]] = []
    for entry in fixture.stories:
        for flow in ("qa", "docs"):
            commit = str(entry.get(flow) or "")
            if not commit:
                continue
            reachable = any(_is_ancestor(fixture.source, commit, head) for head in listed)
            if not reachable:
                missing.append((str(entry["story"]), flow, commit))
    return missing


def _is_ancestor(source: Path, commit: str, head: str) -> bool:
    """Whether *commit* is *head* or one of its ancestors.

    Not `git()`, because a pin that has been garbage-collected outright is exactly the
    case this is asking about, and `merge-base` exits non-zero rather than answering —
    which is the answer.
    """
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, head],
        cwd=source, capture_output=True, text=True, check=False,
    )
    return proc.returncode == 0


# ── run ───────────────────────────────────────────────────────────────────────────────


#: What an app tree carries that is *not* the app: the materialization inputs and the
#: answer key. A trial that copied these would hand the run under measurement the list of
#: seeded defects, which is the one thing it must not have.
NOT_THE_APP = ("stories", "defects", "defects.yml")


def story_diff(app: Path, story: str) -> dict[str, list[str]]:
    """The `changed:`/`added:` manifest for one story, validated against the tree."""
    manifest = app / "stories" / story / "diff.yml"
    if not manifest.is_file():
        known = ", ".join(sorted(p.name for p in (app / "stories").glob("*"))) or "none"
        die(f"no diff manifest at {manifest} (stories: {known})")
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    return {
        "changed": list(data.get("changed") or []),
        "added": list(data.get("added") or []),
    }


def story_image(app: Path, story: str, rel: str, *, phase: str) -> Path:
    """Where the `pre`/`post` content of one path for one story lives.

    `post/` is optional and the fallback is the app tree, because the app tree IS the last
    story's post-image — that is what keeps it the single thing a reader checks the book
    against. `pre/` has no fallback: a `changed:` path with no pre-image would be committed
    at its final content, and the story's diff would silently come out empty.
    """
    image = app / "stories" / story / phase / rel
    if image.is_file():
        return image
    if phase == "pre":
        die(f"story {story!r} lists {rel} as changed but has no pre/ image at {image}")
    return app / rel


def materialize(app: Path, story: str, dest: Path) -> Path:
    """Build, at `dest`, the git state a QA run for `story` is supposed to face.

    The coder's QA lane mints its obligations from *uncommitted* changes
    (`build_okf_context(..., base="HEAD", head="WORKTREE", ...)`), so a plain copy of a
    finished app obligates nothing at all and the run has nothing to prove. Hence:

      1. copy the app tree, minus the answer key;
      2. commit a *before* tree — each `changed:` path replaced by its `pre/` image, each
         `added:` path deleted;
      3. restore this story's files into the worktree, uncommitted, from `post/` where that
         exists and from the app tree otherwise.

    `HEAD..WORKTREE` is then exactly this story's implementation diff, while the book, the
    specs and every other story's code sit at their authored state.
    """
    diff = story_diff(app, story)
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    def ignore(directory: str, names: list[str]) -> set[str]:
        # `NOT_THE_APP` is matched at the app root only. `shutil.ignore_patterns` matches a
        # basename at any depth, and `stories` is also what an epic calls its story folders
        # — which silently removed every story.md from the trial and left the run with
        # nothing authored to plan against.
        top = NOT_THE_APP if Path(directory) == app else ()
        return {name for name in names if name in top or name in ("__pycache__", ".git")}

    shutil.copytree(app, dest, ignore=ignore)

    # The finished content this story is responsible for, held aside while the before tree
    # is committed.
    after = {
        rel: story_image(app, story, rel, phase="post").read_bytes()
        for rel in [*diff["changed"], *diff["added"]]
    }
    for rel in diff["added"]:
        (dest / rel).unlink(missing_ok=True)
    for rel in diff["changed"]:
        (dest / rel).write_bytes(story_image(app, story, rel, phase="pre").read_bytes())

    git("init", "--quiet", "--initial-branch", "main", cwd=dest)
    # Identity on the repo rather than the machine: a trial must not depend on whether the
    # host has a global git config, and must not write to it either.
    git("config", "user.email", "benchmark@example.com", cwd=dest)
    git("config", "user.name", "seat-booking benchmark", cwd=dest)
    git("add", "--all", cwd=dest)
    git("commit", "--quiet", "-m", f"before {story}", cwd=dest)

    for rel, body in after.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    return dest


def reset_stack_state(dest: Path) -> None:
    """Drop the trial's compose volumes, once, before the run starts.

    The app's `qa-stack.yml` deliberately does not do this in its `launch` line: a bring-up
    happens at the head of every plan lane, so a `down -v` there can land in the middle of a
    story that is proving a booking survives a restart, and empty the ledger under it. Here
    there is no run in flight yet, which makes this the one safe moment to reset.

    Every trial shares one compose project name (farrier ties the trial directory's basename
    to its generated skills, so the directory cannot be named after the defect), which is
    exactly why the previous trial's volume is still there to drop.
    """
    compose = dest / "compose.yml"
    if not compose.is_file():
        return
    subprocess.run(
        ["docker", "compose", "-f", "compose.yml", "down", "-v", "--remove-orphans"],
        cwd=dest, capture_output=True, text=True, check=False,
    )


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

    An `app:` fixture has no history to check out, so the tree is materialized from the
    story's pre-images instead; the rewind below then applies unchanged.
    """
    if fixture.app is not None:
        if flow != "qa":
            die(f"fixture {fixture.name!r} is an `app:` fixture and only replays the qa "
                f"flow — a docs replay needs the book at the previous story, which a "
                f"materialized tree does not have")
        commit = f"materialized {story}"
        materialize(fixture.app, story, dest)
        reset_stack_state(dest)
    else:
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


#: `rc` for a trial whose agents committed into this checkout instead of their sandbox.
#: Distinct from any exit code workhorse produces, so the ledger says which failure it was.
LEAK_RC = 90


def head_of(repo: Path) -> str:
    """`repo`'s HEAD, or `""` when git cannot answer.

    Tolerant where `git()` is fatal: this is only ever compared against itself, and a
    reading that failed must not take a measurement run down with it.
    """
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def leaked_commits(before: str) -> list[str]:
    """Commits this checkout gained while a trial ran — always a bug, never a result.

    A trial agent is given a sandbox clone and every path it is asked to touch is inside
    it. It has nonetheless twice reached for the *enclosing* stablemate worktree instead —
    absolute paths in its prompt point here, `benchmarks/.replay/` is ignored here, and the
    agent read that ignore as an obstacle to force past rather than as the sign it was in
    the wrong repository. The result is a commit on the branch the harness is being
    developed on, which is invisible until someone reads `git log`, and public as soon as
    anyone pushes.

    So it is checked rather than hoped for: HEAD is read either side of every trial and a
    difference fails that trial loudly. Prevention is `cwd=repo` on the trial process
    (below); this is what says the prevention still holds.
    """
    after = head_of(STABLEMATE)
    if not before or not after or before == after:
        return []
    return git("log", "--oneline", f"{before}..{after}", cwd=STABLEMATE).splitlines()


def trial_id(label: str, flow: str, story: str, n: int, variant: str = "") -> str:
    return f"replay-{label}-{flow}-{story}{f'-{variant}' if variant else ''}-{n}"


def run_trial(
    fixture: Fixture,
    *,
    flow: str,
    story: str,
    label: str,
    n: int,
    budget_s: float,
    cli: str,
    variant: str = "",
    mutate: Callable[[Path], None] | None = None,
) -> tuple[str, int]:
    """One clone, one flow run. Returns the run id and the workflow's exit code.

    `mutate` runs against the checked-out tree just before the flow starts, and is how a
    scored trial seeds its defect: the checkout is the same for every trial under a label,
    so whatever `mutate` changes is the only variable between them.
    """
    run_id = trial_id(label, flow, story, n, variant)
    work = WORK_DIR / label / run_id
    repo = checkout(fixture, story, flow, work / fixture.repo_dirname)
    if mutate is not None:
        mutate(repo)
    artifacts = work / "artifacts"
    log = work / "run.log"

    env = {**os.environ, "AGENT_REPO_DIR": str(repo)}
    # `cwd=` below is not enough on its own. A child inherits `$PWD` from whoever launched
    # it — `Popen(cwd=...)` changes the directory and leaves the variable — and an agent CLI
    # that resolves its project root from `$PWD` rather than `getcwd()` then works on the
    # repo the *harness* was started in. That is the mechanism behind the strays this
    # function checks for below, and it is the same alignment `workhorse.runner.process`
    # does for a node that declares a `cwd`; the QA nodes declare none, so the harness has
    # to do it at its own boundary.
    env["PWD"] = str(repo)
    env.pop("OLDPWD", "")
    if budget_s > 0:
        # Enforced between states by workhorse itself, so an over-budget trial stops at a
        # node boundary with its telemetry intact and still reports a partial lap count.
        env["WORKHORSE_MAX_RUNTIME_S"] = str(budget_s)
    cmd = [
        # `--project` rather than an inherited cwd: the trial process runs *in the sandbox*
        # (see `cwd=repo` below), so uv is told where the workspace is instead of finding it
        # underfoot.
        "uv", "run", "--project", str(STABLEMATE), "workhorse-coder", "run", flow,
        "--runs-dir", str(artifacts), "--run-id", run_id,
        # Passed explicitly rather than left to $AGENT_CLI, and for the same reason
        # `bench.py` pins its judge: the backend is the largest single term in both the
        # laps and the detection rate, so a label whose trials inherited whatever the shell
        # happened to export is not a configuration anyone can compare against.
        "--cli", cli,
        "--params", json.dumps({"story": story, "docs_path": str(repo)}),
    ]
    say(f"{run_id}")
    log.parent.mkdir(parents=True, exist_ok=True)
    outer_head = head_of(STABLEMATE)
    with log.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen(
            # The sandbox, not this checkout. A node that names no `cwd` gets the runner
            # process's, and every agent turn under it then holds a git context pointing at
            # the repo the harness itself lives in — which is how two trials came to commit
            # their QA audit onto the development branch. The tree the trial is about is the
            # only one it should be standing in.
            cmd, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=env,
        )
        assert proc.stdout is not None  # noqa: S101 - stdout=PIPE guarantees it
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            fh.write(line)
        rc = proc.wait()
    leaked = leaked_commits(outer_head)
    if leaked:
        print(
            f"{RED}  {run_id} committed into {STABLEMATE} instead of its sandbox:{RESET}\n"
            + "\n".join(f"    {line}" for line in leaked)
            + f"\n{RED}  the trial is void — drop those commits "
              f"(`git reset --hard {outer_head}` if nothing else has landed since, a "
              f"`git revert` once they are pushed) before believing any label they are "
              f"part of.{RESET}",
            file=sys.stderr,
        )
        rc = rc or LEAK_RC
    if rc != 0:
        # Not fatal. A flow that exhausted its budgets and blocked is a *result* — it is
        # the loop failing to converge, which is the thing being measured — and its spans
        # are already in groom. Only a crash before the first turn would be uninformative,
        # and that shows up as a run with no laps at all.
        print(f"{RED}  {run_id} exited {rc} — see {log}{RESET}")
    return run_id, rc


def cmd_run(fixture: Fixture, args: argparse.Namespace) -> int:
    if fixture.app is None and not fixture.bundle.is_file():
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
                n=n, budget_s=args.budget, cli=args.cli,
            )
            trials.append({"run_id": run_id, "flow": args.flow, "story": story,
                           "rc": rc, "cli": args.cli})
            worst = max(worst, abs(rc))

    ledger = WORK_DIR / args.label / "trials.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(ledger.read_text(encoding="utf-8")) if ledger.is_file() else []
    by_id = {entry["run_id"]: entry for entry in [*existing, *trials]}
    ledger.write_text(json.dumps(sorted(by_id.values(), key=lambda e: e["run_id"]), indent=2))

    report(args.label)
    return worst


# ── score ─────────────────────────────────────────────────────────────────────────────


CLEAN = "clean"


def load_defects(app: Path) -> list[dict[str, str]]:
    path = app / "defects.yml"
    if not path.is_file():
        die(f"no answer key at {path} — an `app:` fixture can be replayed but not scored")
    rows = list((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("defects") or [])
    if not rows:
        die(f"{path} lists no defects")
    return rows


def select_defects(app: Path, wanted: list[str]) -> list[dict[str, str]]:
    rows = load_defects(app)
    if not wanted:
        return rows
    by_id = {str(row["id"]): row for row in rows}
    unknown = [name for name in wanted if name not in by_id]
    if unknown:
        die(f"no such defect(s): {', '.join(unknown)} (have: {', '.join(sorted(by_id))})")
    return [by_id[name] for name in wanted]


def seed_defect(app: Path, row: dict[str, str]) -> Callable[[Path], None]:
    """Return the mutation that plants one defect in a checked-out tree.

    A whole-file overwrite: the variant either lands on a path that exists or raises here,
    where the trial has not yet cost anything. A patch would apply cleanly against a stale
    app and leave the trial measuring an app with no defect in it at all.
    """
    variant = app / "defects" / str(row["id"]) / str(row["path"])
    if not variant.is_file():
        die(f"defect {row['id']}: no variant at {variant}")

    def mutate(repo: Path) -> None:
        target = repo / str(row["path"])
        if not target.is_file():
            die(f"defect {row['id']}: {row['path']} is not in the materialized tree")
        shutil.copyfile(variant, target)

    return mutate


def defect_survived(app: Path, row: dict[str, str], repo: Path) -> bool:
    """Is the seeded file still byte-for-byte the defect variant at the end of the trial?

    This is the half of the score the terminal evidence map cannot see. The QA lane does not
    only observe — it triages a failing observation as `code` and repairs the product. When
    it does, the *last* evidence map is computed over a fixed app and reads `covered`, which
    is indistinguishable from a run that never noticed anything. Reading only that end state
    scores the loudest possible detection as a miss.

    So the seeded file itself is the witness. It was planted by an overwrite (`seed_defect`)
    and nothing but the flow can have touched it since; if it no longer matches the variant,
    the flow acted on the defect. Byte equality, not a semantic check, because the question
    is only whether the code under test is still the code that was seeded — a repair that
    differs from the canonical app is still a repair.
    """
    variant = app / "defects" / str(row["id"]) / str(row["path"])
    target = repo / str(row["path"])
    if not target.is_file():
        return False
    return target.read_bytes() == variant.read_bytes()


def evidence_statuses(repo: Path, story: str) -> dict[str, str] | None:
    """`{obligation id: status}` for the run's owed obligations, or None if unbuildable.

    None is not an empty map. `build_evidence_map` refuses when an input is missing, and a
    map computed over a missing run log reports every obligation `uncovered` — which is
    indistinguishable from a run that genuinely asserted nothing and would score a trial
    that never started as a wall of detections.
    """
    from ostler import qa as qa_mod  # noqa: PLC0415 - a heavy import only scoring needs

    try:
        data = qa_mod.build_evidence_map(repo / "docs" / "specs" / story)
    except qa_mod.EvidenceMapError:
        return None
    return {str(row["id"]): str(row["status"]) for row in data["obligations"]}


def audit_result(work: Path, run_id: str) -> dict[str, Any]:
    """The auditor's last verdict for a trial, or an empty dict if it never ran."""
    path = work / "artifacts" / f"coder-{run_id}" / "audit-qa" / "output.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def classify(
    row: dict[str, str] | None,
    statuses: dict[str, str] | None,
    audit: dict[str, Any],
    *,
    survived: bool = True,
) -> tuple[str, str]:
    """Score one trial against its row. Returns `(verdict, the status that decided it)`.

    Three routes count as a catch, because the flow has three places a defect can surface
    and which one fires is a property of the QA plan — the thing under measurement:

    * the **evidence map** puts the named obligation at the row's `expect`, which is a set
      operation over the run's own artifacts, or
    * the **auditor** refuted the pass and its findings name that obligation, or
    * the seeded code **did not survive** the run: QA observed the defect, triaged it as a
      code failure and repaired it. That path ends with the obligation `covered` — the map
      is right, the app really is fixed — so only the seeded file distinguishes it from a
      run that never noticed. It is checked last, since the first two say *where* the
      detection was recorded and this one only says that it happened.

    A miss is the specific, worse outcome: the run published a pass, claimed the obligation
    covered, *and* left the defect in place. Anything else — no map, an obligation out of
    scope, a run that blocked before it asserted anything — is `inconclusive` rather than a
    catch or a miss, since scoring an infrastructure failure either way is a number about
    this machine.
    """
    refuted = str(audit.get("verdict", "")) == "refuted"
    if row is None:  # the clean control: any contradiction at all is a false alarm
        if statuses is None:
            return "inconclusive", "no evidence map"
        contradicted = sorted(k for k, v in statuses.items() if v == "contradicted")
        if contradicted:
            return "false", contradicted[0]
        return ("false", "audit refuted") if refuted else ("clean", "no contradiction")

    obligation = str(row["obligation"])
    status = (statuses or {}).get(obligation, "")
    if status == str(row["expect"]):
        return "caught", status
    cited = obligation in json.dumps(audit)
    if refuted and cited:
        return "caught", "audit refutation"
    if not survived:
        return "caught", "defect repaired"
    if statuses is None:
        return "inconclusive", "no evidence map"
    if not status:
        return "inconclusive", "obligation not owed by this trial"
    if status == "covered":
        return "missed", status
    return "inconclusive", status


# ── leverage ──────────────────────────────────────────────────────────────────────────


#: Printed in place of a metric whose inputs are not there, and never `0`. A trial that
#: blocked before writing a plan navigated through no links and addressed no roles; a
#: `roles 0/0` there is a claim about the QA it produced rather than a report that there
#: was none — the same lie `classify` refuses when it scores a missing evidence map
#: `inconclusive` instead of a miss.
BLANK = "–"

#: The scorecard, in print order. Detection says whether the QA flow noticed a defect;
#: these say whether the plan it wrote used the book it was handed — entered each flow
#: where the book says the flow starts, moved between screens by clicking rather than by
#: re-navigating, addressed the UI by the roles the book documents, and closed the
#: obligations and the journeys it owed. A plan can catch a seeded defect while doing none
#: of that, and it is the difference between QA and a regression suite of URL fetches.
LEVERAGE_KEYS = ("entry", "deep_links", "roles", "obligations", "journeys")

LEVERAGE_LABELS = {
    "entry": "entry",
    "deep_links": "deep-links",
    "roles": "roles",
    "obligations": "obligations",
    "journeys": "journeys",
}

#: The one evidence-map status that is a discharged obligation. The other three
#: (`uncovered`, `claimed-but-unasserted`, `contradicted`) are each a different way of not
#: having proved it, and none of them counts here.
PASSING_STATUS = "covered"


def route_matches(route: str, url: str) -> bool:
    """Whether a planned `goto` lands on a route the book documents.

    Ostler's own `_route_matches` when it imports: it is the rule `qa validate` already
    applied to this plan, and a second implementation here would score plans against a
    gate that never ran. The fallback below is a transcription of that function, for a
    benchmarks environment without ostler on the path.
    """
    try:
        from ostler.qa.plan import _route_matches  # noqa: PLC0415 - the authority when present
    except ImportError:
        planned = [part for part in urlsplit(url).path.strip("/").split("/") if part]
        documented = [part for part in urlsplit(route).path.strip("/").split("/") if part]
        if len(planned) != len(documented):
            return False
        return all(
            part.startswith((":", "{")) or other.startswith((":", "{")) or part == other
            for part, other in zip(planned, documented, strict=True)
        )
    return _route_matches(route, url)


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    return [str(item) for item in (value if isinstance(value, list) else [value])]


def _route_of(node: dict[str, Any]) -> str:
    """The route a screen node documents, or `""`.

    First whitespace token of the `route:` bullet with its backticks stripped, because the
    bullet is prose-shaped — ``- route: `/policies/:id` (the detail screen)`` — and only the
    path is a route.
    """
    for value in _values(node.get("bullets", {}).get("route")):
        token = value.strip().split()[0].strip("`") if value.strip() else ""
        if token.startswith("/"):
            return token
    return ""


def _literal(node: ast.expr | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def plan_scenarios(source: str) -> dict[str, dict[str, Any]]:
    """`{scenario id: {"covers": [...], "actions": [...]}}`, read statically from a `qa_plan.py`.

    From the plan rather than the run log because a `goto` URL never reaches
    `qa-run.ndjson`: the ledger records steps and assertions, not the browser calls inside
    them. The plan is also the artifact `ostler qa validate` judges, so scoring it scores
    the thing the flow was gated on.

    The action list comes from ostler's own `extract_locators` — the parser
    `_validate_book_locators` reads — so a locator counted here is the locator that gate
    saw, computed roles (`"*"`) and all. Only the `@scenario(...)` header is parsed
    locally, and only for the two fields the harness's static half does not return: the
    id, which is what the run log calls a scenario, and `covers`, which is what ties a
    scenario to the book.
    """
    from ostler.qa.harness_host import load_harness_module  # noqa: PLC0415 - only scoring needs it

    actions = load_harness_module("ostler_qa").extract_locators(source)
    found: dict[str, dict[str, Any]] = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or _called(decorator) != "scenario":
                continue
            keywords = {kw.arg: kw.value for kw in decorator.keywords if kw.arg}
            given = _literal(keywords.get("id"))
            covers = _literal(keywords.get("covers"))
            found[given if isinstance(given, str) else node.name.replace("_", "-")] = {
                "covers": [str(item) for item in covers] if isinstance(covers, list) else [],
                "actions": actions.get(node.name, []),
            }
    return found


def _called(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


def _gotos(scenario: dict[str, Any]) -> list[str]:
    return [
        str(action["url"])
        for action in scenario["actions"]
        if isinstance(action, dict) and action.get("do") == "goto" and action.get("url")
    ]


def _locators(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        action["locator"]
        for action in scenario["actions"]
        if isinstance(action, dict) and isinstance(action.get("locator"), dict)
    ]


def required_flows(packet: dict[str, Any]) -> list[str]:
    """The flow nodes this story owes live evidence for.

    Off the obligations rather than the packet's `journeys:` list, because that list is
    every flow the graph closure reached and most of them are context: a story touching one
    endpoint pulls in every journey that endpoint appears in, and scoring a plan for not
    walking all of them would report a correct plan as a third of one.
    """
    return sorted({
        str(obligation["node"])
        for obligation in packet.get("obligations", []) or []
        if isinstance(obligation, dict)
        and obligation.get("kind") == "journey"
        and obligation.get("required", True)
        and obligation.get("node")
    })


def flow_starts(book: dict[str, Any]) -> dict[str, str]:
    """`{flow node id: the route its `start:` screen documents}`.

    Two hops, because neither end carries both halves: the flow names its start screen as a
    link, and the route lives on the screen. `via` is the bullet key the link was written
    under, which is what keeps a `start:` edge apart from a `steps:` one pointing at the
    same screen.
    """
    routes = {str(node["id"]): _route_of(node) for node in book.get("nodes", []) or []}
    starts: dict[str, str] = {}
    for edge in book.get("edges", []) or []:
        if edge.get("via") == "start" and routes.get(str(edge.get("to"))):
            starts.setdefault(str(edge["from"]), routes[str(edge["to"])])
    return starts


def entry_routes(book: dict[str, Any]) -> set[str]:
    """Every route a user may legitimately arrive at from outside in-app navigation.

    A flow's start plus any screen carrying an `entry:` bullet — the book's own word for
    "reached by an app root, an emailed link or an OAuth callback". Navigating straight to
    one of these mid-scenario is arriving, not deep-linking.
    """
    routes = {
        _route_of(node)
        for node in book.get("nodes", []) or []
        if node.get("bullets", {}).get("entry") and _route_of(node)
    }
    return routes | set(flow_starts(book).values())


def documented_routes(book: dict[str, Any]) -> set[str]:
    return {route for node in book.get("nodes", []) or [] if (route := _route_of(node))}


def leverage_from(
    book: dict[str, Any] | None,
    packet: dict[str, Any] | None,
    plan_source: str | None,
    run_log: list[dict[str, Any]] | None,
    statuses: dict[str, str] | None,
) -> dict[str, Any]:
    """The five leverage metrics, each a `[n, of]` pair, an int, or None when incomputable.

    None rather than a zero everywhere an input is missing. Every one of these is a
    fraction whose denominator is a property of the *book* — flows documented, obligations
    owed, locators written — so an absent artifact makes the question unaskable rather than
    the answer bad, and `leverage_line` prints `–` for it.
    """
    scenarios = plan_scenarios(plan_source) if plan_source else {}
    if run_log is not None:
        # Only what the run actually started. A scenario the plan declares and the driver
        # never reached entered nothing and clicked nothing, and crediting it for the entry
        # its source says it would have made scores an intention.
        started = {
            str(record.get("scenario", ""))
            for record in run_log
            if record.get("kind") == "scenario_start"
        }
        scenarios = {name: data for name, data in scenarios.items() if name in started}

    flows = required_flows(packet) if packet else []
    starts = flow_starts(book) if book else {}
    covering: dict[str, list[dict[str, Any]]] = {flow: [] for flow in flows}
    for data in scenarios.values():
        for flow in flows:
            if any(cover.startswith(f"okf:{flow}:") for cover in data["covers"]):
                covering[flow].append(data)

    entry: list[int] | None = None
    if flows and any(starts.get(flow) for flow in flows):
        entry = [
            sum(
                1
                for flow in flows
                if (route := starts.get(flow))
                and any(
                    (gotos := _gotos(data)) and route_matches(route, gotos[0])
                    for data in covering[flow]
                )
            ),
            len(flows),
        ]

    deep_links: int | None = None
    if book and scenarios:
        elsewhere = documented_routes(book)
        arrivals = entry_routes(book)
        deep_links = sum(
            1
            for data in scenarios.values()
            for url in _gotos(data)[1:]
            if any(route_matches(route, url) for route in elsewhere)
            and not any(route_matches(route, url) for route in arrivals)
        )

    roles: list[int] | None = None
    uses = [locator for data in scenarios.values() for locator in _locators(data)]
    if uses:
        # `role` and `css` are the two strategies the book can vouch for — a `role:` bullet
        # and a `selector:` one. `text` and `label` address a rendered string, which is what
        # the next copy edit changes; `test_id` addresses a hook the book never mentions.
        roles = [sum(1 for locator in uses if "role" in locator or "css" in locator), len(uses)]

    obligations = (
        [sum(1 for status in statuses.values() if status == PASSING_STATUS), len(statuses)]
        if statuses
        else None
    )

    journeys = (
        [
            sum(1 for flow in flows if statuses.get(f"okf:{flow}:end-state") == PASSING_STATUS),
            len(flows),
        ]
        if statuses and flows
        else None
    )

    return {
        "entry": entry,
        "deep_links": deep_links,
        "roles": roles,
        "obligations": obligations,
        "journeys": journeys,
    }


def read_ndjson(path: Path) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def load_book(repo: Path) -> dict[str, Any] | None:
    """The feature graph as `{"nodes": [...], "edges": [...]}`, or None if it will not load.

    The same `graph.build` behind `ostler graph`, in this process. A trial's book is the
    frozen app's book plus whatever the flow wrote, and it is the only artifact carrying a
    flow's start screen — the packet lifts `route:` onto an obligation but never `start:`.
    """
    try:
        from ostler import graph as graph_mod  # noqa: PLC0415 - a heavy import only scoring needs
        from ostler import model
    except ImportError:
        return None
    try:
        return graph_mod.build(model.load(repo))
    except Exception:  # noqa: BLE001 - a book that will not load scores `–`, not a crash
        return None


def leverage(repo: Path, story: str, statuses: dict[str, str] | None) -> dict[str, Any]:
    """Score one trial's artifacts. Every input is optional; a missing one prints `–`."""
    spec = repo / "docs" / "specs" / story
    plan_file = spec / "qa_plan.py"
    return leverage_from(
        load_book(repo),
        read_json(spec / "qa-okf-context.json"),
        plan_file.read_text(encoding="utf-8") if plan_file.is_file() else None,
        read_ndjson(spec / "qa" / "qa-run.ndjson"),
        statuses,
    )


def pool_leverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum the metrics across trials, keeping a metric None when no trial could compute it.

    Summed rather than averaged, for the reason `report` pools laps: these are counts over
    a denominator that varies per story, and averaging per-trial fractions would weight a
    one-flow story the same as a five-flow one.
    """
    pooled: dict[str, Any] = dict.fromkeys(LEVERAGE_KEYS)
    for row in rows:
        metrics = row.get("leverage") or {}
        for key in LEVERAGE_KEYS:
            value = metrics.get(key)
            if value is None:
                continue
            current = pooled[key]
            if isinstance(value, list):
                pair = [int(value[0]), int(value[1])]
                pooled[key] = pair if current is None else [current[0] + pair[0], current[1] + pair[1]]
            else:
                pooled[key] = int(value) + (current or 0)
    return pooled


def leverage_line(metrics: dict[str, Any]) -> str:
    parts = []
    for key in LEVERAGE_KEYS:
        value = metrics.get(key)
        if value is None:
            shown = BLANK
        elif isinstance(value, list):
            shown = f"{value[0]}/{value[1]}"
        else:
            shown = str(value)
        parts.append(f"{LEVERAGE_LABELS[key]} {shown}")
    return "  leverage: " + "  ".join(parts)


def cmd_score(fixture: Fixture, args: argparse.Namespace) -> int:
    """Run a clean control plus one trial per defect, then print detection beside cost.

    The control is what makes the detection number readable. A harness that refutes
    everything scores every defect as caught, and only a trial with nothing wrong in it
    tells the two apart — so a control that refutes is reported as a false alarm and is a
    fixture bug, not a finding about QA.
    """
    if fixture.app is None:
        die(f"fixture {fixture.name!r} has no `app:` — only an app fixture ships an answer "
            f"key, and detection cannot be scored without one")
    rows = select_defects(fixture.app, args.defects)
    stories = sorted({str(row["story"]) for row in rows})

    trials: list[dict[str, Any]] = []
    worst = 0
    # One control per story, not one per run: the obligations a trial owes come from the
    # story's diff, so a control for story A says nothing about false alarms in story B.
    plan: list[tuple[str, dict[str, str] | None]] = [
        *([] if args.no_control else [(story, None) for story in stories]),
        *[(str(row["story"]), row) for row in rows],
    ]
    for story, row in plan:
        variant = str(row["id"]) if row else CLEAN
        run_id, rc = run_trial(
            fixture, flow="qa", story=story, label=args.label, n=1, variant=variant,
            budget_s=args.budget, cli=args.cli,
            mutate=seed_defect(fixture.app, row) if row else None,
        )
        work = WORK_DIR / args.label / run_id
        repo = work / fixture.repo_dirname
        statuses = evidence_statuses(repo, story)
        verdict, because = classify(
            row,
            statuses,
            audit_result(work, run_id),
            survived=defect_survived(fixture.app, row, repo) if row else True,
        )
        trials.append({
            "run_id": run_id, "flow": "qa", "story": story, "rc": rc, "cli": args.cli,
            "defect": variant, "obligation": str(row["obligation"]) if row else "",
            "verdict": verdict, "because": because,
            # In the same row the verdict lands in, because the two are read together: a
            # round that caught everything by fetching URLs and one that caught everything
            # by walking the product are the same headline and different products.
            "leverage": leverage(repo, story, statuses),
        })
        worst = max(worst, abs(rc))

    ledger = WORK_DIR / args.label / "trials.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(ledger.read_text(encoding="utf-8")) if ledger.is_file() else []
    by_id = {entry["run_id"]: entry for entry in [*existing, *trials]}
    ledger.write_text(json.dumps(sorted(by_id.values(), key=lambda e: e["run_id"]), indent=2))

    score(args.label, trials)
    report(args.label)
    return worst


def convergence(trials: list[dict[str, Any]]) -> str:
    """The cost half of the headline: `| plan-qa 2.1 laps ~$0.94`, pooled over these trials.

    Detection and convergence belong on one line because either alone is gameable in the
    direction of the other — a flow that refutes everything catches every defect and never
    terminates, and one that approves everything converges in a single lap.

    The money is the harness's own when it reports any, and `groom.prices`' rate card —
    marked `~` — when it does not. A backend under subscription auth reports a literal
    `$0` over millions of tokens, which is not a cheap round, it is an unpriced one; a
    headline printing `$0.00` there says the flow was free and makes the whole column
    dead on that backend. `est_cost_usd` is the same tokens at published rates, and it is
    only ever quoted in place of a report that has nothing in it — never summed with one.
    """
    from groom import store  # noqa: PLC0415 - a heavy import only the headline needs

    rows = [
        row
        for trial in trials
        for row in store.loop_convergence(run=trial["run_id"], min_work_items=1)
        if row["node"] == "plan-qa"
    ]
    if not rows:
        return ""
    items = sum(row["work_items"] for row in rows)
    turns = sum(row["turns"] for row in rows)
    return f" | plan-qa {turns / items:.1f} laps {money(rows)}" if items else ""


def money(rows: list[dict[str, Any]]) -> str:
    """`$0.94`, or `~$0.71` when the estimate is standing in, or `$?` when neither exists.

    `?` rather than `$0.00`: a backend that reports nothing and a model the rate card
    does not name leave the round genuinely unpriced, and a zero there is a claim.
    """
    billed = sum(row["cost_usd"] or 0.0 for row in rows)
    if billed:
        return f"${billed:.2f}"
    estimated = sum(row["est_cost_usd"] or 0.0 for row in rows)
    return f"~${estimated:.2f}" if estimated else "$?"


def score(label: str, trials: list[dict[str, Any]]) -> None:
    say(f"label {label!r}: detection")
    for trial in trials:
        colour = {"caught": "", "clean": "", "missed": RED, "false": RED}.get(trial["verdict"], DIM)
        print(f"  {colour}{trial['defect']:<6} {trial['verdict']:<13}{RESET if colour else ''}"
              f" {DIM}{trial['because']}{RESET}"
              f"\n    {DIM}{trial['obligation'] or '(control)'}{RESET}")
    seeded = [trial for trial in trials if trial["defect"] != CLEAN]
    caught = sum(1 for trial in seeded if trial["verdict"] == "caught")
    missed = sum(1 for trial in seeded if trial["verdict"] == "missed")
    false = sum(1 for trial in trials if trial["verdict"] == "false")
    unknown = sum(1 for trial in trials if trial["verdict"] == "inconclusive")
    line = f"  caught {caught}/{len(seeded)}  missed {missed}  false {false}{convergence(trials)}"
    if unknown:
        # Loudly, and never folded into a miss: an inconclusive trial is the harness
        # failing, and averaging it into the detection rate hides the outage as a result.
        line += f"  {RED}inconclusive {unknown}{RESET}"
    print(f"\n{BOLD}{line}{RESET}")
    print(f"{DIM}{leverage_line(pool_leverage(trials))}{RESET}")


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
        mark = BOLD if node in WATCHED else ""
        print(f"  {mark}{node:<30}{RESET if mark else ''} {items:>5} {turns:>5} "
              f"{items / turns:>5.0%} {turns / items:>5.2f} "
              f"{max(row['max_laps'] for row in rows):>4} {money(rows):>8}")
    total = sum(row["turns"] - row["work_items"] for rows in pooled.values() for row in rows)
    every = [row for rows in pooled.values() for row in rows]
    print(f"  {DIM}{'—' * 68}{RESET}")
    print(f"  {'TOTAL':<30} {'':>5} {'':>5} {'':>6} {'':>5} {'':>4} {money(every):>8}"
          f"   ({total} excess turns)")
    print(leverage_line(pool_leverage(trials)))


def cmd_report(args: argparse.Namespace) -> int:
    for label in args.labels:
        report(label)
    return 0


# ── cli ───────────────────────────────────────────────────────────────────────────────


#: The backend a trial drives unless told otherwise. `opencode` rather than the workflow
#: default of `claude`: a full scored round is a clean control per story plus one run per
#: seeded defect, which is a dozen QA flows for one number, and a benchmark nobody can
#: afford to re-run is a benchmark that stops being run.
DEFAULT_CLI = "opencode"


def add_cli_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cli", default=DEFAULT_CLI, metavar="NAME",
                        help=f"agent CLI backend driving each trial (default {DEFAULT_CLI}); "
                             f"recorded per trial, since the backend moves both halves of "
                             f"the headline")


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
    add_cli_flag(run_p)

    score_p = sub.add_parser(
        "score", help="score detection: a clean control plus one trial per seeded defect"
    )
    score_p.add_argument("--defect", dest="defects", action="append", default=[],
                         metavar="ID", help="repeatable; default is every defect in the key")
    score_p.add_argument("--label", default="score",
                         help="names the configuration under test — the unit `report` compares")
    score_p.add_argument("--budget", type=float, default=0.0,
                         help="wall-clock ceiling per trial, in seconds (0 = unbounded)")
    score_p.add_argument("--no-control", action="store_true",
                         help="skip the clean control — cheaper, and the false-alarm count "
                              "then means nothing")
    add_cli_flag(score_p)

    # `main` has always dispatched this and no parser ever accepted it, so the pooled
    # table could only be read by re-running the trials that produced it.
    report_p = sub.add_parser("report", help="pooled lap-and-cost table for saved labels")
    report_p.add_argument("labels", nargs="+", metavar="LABEL")

    args = parser.parse_args(argv)
    if args.command == "report":
        return cmd_report(args)
    fixture = load_fixture(args.fixture)
    if args.command == "capture":
        cmd_capture(fixture)
        return 0
    if args.command == "score":
        return cmd_score(fixture, args)
    return cmd_run(fixture, args)


if __name__ == "__main__":
    raise SystemExit(main())
