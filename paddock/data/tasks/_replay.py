"""Replay one lane of the coder workflow, cold, on a tree that already ran it once.

A replay answers a question no end-to-end round can: **what does this one lane cost, on
this exact input, after I changed its prompts?** Re-running the whole workflow to find out
moves the input as well as the code, so the two numbers are not comparable and the change
cannot be attributed. A replay holds the input still.

What it is, precisely: stand at the commit that landed a flow, undo what that flow wrote,
and run the flow again from scratch. From scratch is the load-bearing half —

* a **fresh clone per trial**, so no run dir, no checkpoint and no agent state survives
  from the previous trial or from the run that landed the commit in the first place;
* **no `session_id` in the params**, ever. Passing one resumes the conversation that
  already documented this story, and the lane then answers out of its own memory instead
  of reading the tree — a re-run that costs one turn and writes nothing. A replay is not
  a resumption; it is the same work done again by an agent that has never seen it.

The seed carries the repository, history included, which is what makes a pin a checkout
rather than a second fixture. It must not carry an agent's session store: capture the seed
with `--exclude .opencode` (and the equivalent for whatever backend the round runs on), or
the trials inherit exactly the memory this module exists to deny them.

Everything about *what the numbers mean* — laps, escalations, the time partition — is
`_forensics.py`'s and is shared verbatim with the greenfield and frozen-app rounds.

The leading underscore keeps `paddock.loader` from treating this as a task module: it is
the library each replay task imports, not a second declaration.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import _forensics as fx
import _stablemate as sm
from _frozenapp import QA_OUTPUTS, capture_witness
from paddock import Run, Score

#: The flows this module knows how to rewind, and therefore the flows a fixture may
#: declare. A flow with no rewind rule would be entered on a tree that already holds its
#: own output, which measures a lane confirming its own work — the most expensive way
#: there is to learn nothing.
KNOWN_FLOWS = ("qa", "docs")

#: The default wall-clock budget for one trial, in seconds. Enforced by workhorse between
#: states, so an over-budget trial stops at a node boundary with its telemetry intact and
#: still reports a partial lap count — a budget death is a measurement.
BUDGET_S = 2400.0

#: Where the round's own ledger lives inside the stage. Named explicitly rather than via
#: `run.artifacts`, which is relative to the current step and `score` runs outside them.
TRIALS = ("artifacts", "trials")

#: The story section some fixtures predate. `registry.STORY_SECTIONS` gained a leading
#: `## Dependencies`, and `coder/shared/story.py` refuses to plan against a story.md that
#: is missing a required section — so a bundle captured before it stops at the first node
#: with "story.md is still a bare scaffold", on every flow, and measures nothing at all.
DEPS_SECTION = "## Dependencies\n\n(none)\n\n"


@dataclass(frozen=True, slots=True)
class Pin:
    """One story and the commit each flow's replay is entered at.

    One commit per flow because a story's flows were landed separately: `qa` is the commit
    that carries the story's implementation and its QA outputs, `docs` the one that carries
    its book entry. Replaying a flow means standing at its commit and removing what that
    flow wrote — see `rewind`.
    """

    story: str
    commits: Mapping[str, str]
    #: The ref whose book the docs flow is entered with, when the default is wrong.
    #: The default — the docs commit's parent — is right for a story whose book entry was
    #: landed by a run: the book then lags this story by exactly one story, which is the
    #: real historical input. It is wrong for a story whose docs flow **never ran**, where
    #: there is no commit to be the parent of and the entry state is a tree as it stands.
    #: Naming that tree here is what lets such a story be replayed at all.
    book_from: str = ""

    def commit(self, flow: str) -> str:
        commit = self.commits.get(flow, "")
        if not commit:
            raise sm.TrialError(f"no {flow} commit pinned for story {self.story!r}")
        return commit

    def book_ref(self, flow: str) -> str:
        return self.book_from or f"{self.commit(flow)}~"


@dataclass(frozen=True, slots=True)
class Fixture:
    """One app's replay: which tree, which stories, which lanes, and what it needs patched.

    The patch fields are all the same kind of thing — a gap between what the bundle was
    captured with and what the current toolchain requires — and they exist so a schema
    addition is not a reason to recapture. Recapturing moves every pin, and the pins are
    the one thing a replay fixture is: stories landed by real runs, at the commits that
    landed them.
    """

    #: The seed's `repo_dir`, and the name each trial's tree gets under `scratch/`.
    app: str
    pins: tuple[Pin, ...]
    #: The flows a round replays unless `--param flows=` narrows it.
    flows: tuple[str, ...] = KNOWN_FLOWS
    #: Where the docs flow writes. Rewound wholesale.
    book: str = "docs/features"
    budget_s: float = BUDGET_S
    #: Packs to add to `agents.yml` when the capture is missing them. The docs lane's
    #: prompts carry a `skill_load_ref` to `ostler-documentation`, which farrier ships in
    #: the `stablemate` pack: without it the prompt renders its placeholder text and the
    #: agent improvises the doctrine it was supposed to be handed, so the flow is measured
    #: on inventing a standard rather than on applying one.
    packs: tuple[str, ...] = ()
    #: Paths restored from `harness_ref` after the pin is checked out — the repo's own
    #: configuration (`agents.yml`, a Makefile, `.gitignore`) when the history predates
    #: tracking it. Without them a clone at a pin has no `agents.yml`, farrier installs
    #: nothing, and every prompt path in the run fails to resolve.
    harness: tuple[str, ...] = ()
    harness_ref: str = ""
    #: Give every `story.md` the `## Dependencies` section the schema now requires.
    backfill_dependencies: bool = False
    extra_witness: tuple[str, ...] = field(default_factory=tuple)


def trials_dir(run: Run) -> Path:
    directory = run.stage.joinpath(*TRIALS)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def plan_round(run: Run, fixture: Fixture) -> list[tuple[Pin, str]]:
    """The trials to run: every pinned story on every selected flow, stories outermost."""
    wanted = set(run.param_list("stories"))
    if missing := wanted - {pin.story for pin in fixture.pins}:
        raise sm.TrialError(
            f"--param stories names stories this fixture has no pin for: "
            f"{', '.join(sorted(missing))}"
        )
    pins = [pin for pin in fixture.pins if not wanted or pin.story in wanted]
    flows = run.param_list("flows") or fixture.flows
    if unknown := set(flows) - set(fixture.flows):
        raise sm.TrialError(
            f"--param flows={','.join(sorted(unknown))}: this fixture replays "
            f"{', '.join(fixture.flows)}"
        )
    return [(pin, flow) for pin in pins for flow in flows if flow in pin.commits]


def rewind(repo: Path, fixture: Fixture, pin: Pin, flow: str) -> None:
    """Put the checked-out tree back into the state the flow was entered in.

    Per flow, because the two write to different places:

      * **qa** removes the story's plan and evidence from its spec dir, leaving the story,
        the implementation plan and the code — what `run qa` was handed.
      * **docs** restores the book to `pin.book_ref(flow)`, by default the docs commit's
        *parent*, so the book lags this story by exactly one story. That is the real
        historical input, and the distinction matters: a book rewound further would be
        missing entries outside this story's obligations, which is a different and easier
        complaint for a reviewer to make.
    """
    if flow == "qa":
        spec = repo / "docs" / "specs" / pin.story
        if not spec.is_dir():
            raise sm.TrialError(
                f"no spec dir {spec} at {pin.commit(flow)} — is the pin for "
                f"{pin.story!r} still right?"
            )
        for name in QA_OUTPUTS:
            target = spec / name
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
    else:
        # Delete first, then restore: `git checkout <tree> -- <path>` copies the tree's
        # files over the working tree but leaves behind anything the commit *added*, so on
        # its own it does not rewind a story that introduced a book entry — it hands the
        # docs flow the entry it is being measured on writing.
        book, ref = fixture.book, pin.book_ref(flow)
        sm.git("rm", "-r", "--quiet", "--force", "--ignore-unmatch", "--", book, cwd=repo)
        if sm.git("ls-tree", "--name-only", ref, book, cwd=repo).strip():
            sm.git("checkout", ref, "--", book, cwd=repo)


def restore_harness(repo: Path, fixture: Fixture) -> None:
    """Copy the repo's own configuration in from a later commit that tracks it.

    A separate step from `rewind` and deliberately after it: this is not part of the state
    the flow was entered in, it is the part of the tree the capture failed to record at
    all. Nothing under it is input to the lane under measurement — `agents.yml` names the
    packs and the workspace, not the work.
    """
    if not fixture.harness:
        return
    if not fixture.harness_ref:
        raise sm.TrialError("fixture declares `harness` paths but no `harness_ref` to take them from")
    sm.git("checkout", fixture.harness_ref, "--", *fixture.harness, cwd=repo)


def backfill_story_sections(repo: Path) -> None:
    """Give every story.md the `## Dependencies` section the schema now requires.

    A migration, not a favor to the flow under test. `(none)` is the stub the current
    authoring writes and `story_dependencies` reads no edge from it, so the story graph a
    trial is handed is byte-for-byte the one the original run was handed — the heading only
    satisfies the gate that did not exist when these commits were made.
    """
    for story_md in sorted(repo.glob("docs/epics/*/stories/*/story.md")):
        text = story_md.read_text(encoding="utf-8")
        if "\n## Dependencies" in f"\n{text}":
            continue
        # Ahead of the first section, because Dependencies leads in `STORY_SECTIONS` and a
        # reader looking for what blocks a story should not have to scroll past the prose.
        head, marker, rest = text.partition("\n## ")
        if not marker:
            raise sm.TrialError(f"{story_md} has no `## ` section to insert Dependencies before")
        story_md.write_text(f"{head}\n{DEPS_SECTION}## {rest}", encoding="utf-8")


def subscribe_to_packs(repo: Path, packs: tuple[str, ...]) -> None:
    """Add each missing pack to `agents.yml` so the lane's skills resolve.

    A line edit rather than a YAML round-trip, because `agents.yml` carries comments the
    trial should be handed exactly as the seed has them, and every YAML writer drops them.
    """
    if not packs:
        return
    agents_yml = repo / "agents.yml"
    if not agents_yml.is_file():
        raise sm.TrialError(f"no {agents_yml} — is the seed the app tree it should be?")
    lines = agents_yml.read_text(encoding="utf-8").splitlines(keepends=True)
    try:
        start = next(i for i, line in enumerate(lines) if line.rstrip() == "packs:")
    except StopIteration:
        raise sm.TrialError(f"{agents_yml} declares no `packs:` block") from None
    end = start + 1
    while end < len(lines) and lines[end].startswith("  - "):
        end += 1
    declared = {line.strip().removeprefix("- ") for line in lines[start + 1 : end]}
    for pack in packs:
        if pack not in declared:
            lines.insert(end, f"  - {pack}\n")
            end += 1
    agents_yml.write_text("".join(lines), encoding="utf-8")


def checkout(
    run: Run, fixture: Fixture, pin: Pin, flow: str, dest: Path, install: Callable[[Path], None]
) -> Path:
    """Clone the unpacked seed at this story's commit, rewind the flow, install the layer.

    A clone rather than a copy: the seed's working tree is whatever it was at capture, and
    the state a trial is about is the committed one. Cloning also leaves the unpacked seed
    untouched, so every trial in a round starts from the same bytes and the stage stays a
    faithful copy of what was seeded — and it is what makes a trial *cold*, since the clone
    carries no run dir and no agent state from the trial before it.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    sm.git("clone", "--quiet", str(run.repo), str(dest), cwd=run.scratch)
    sm.git("checkout", "--quiet", pin.commit(flow), cwd=dest)
    rewind(dest, fixture, pin, flow)
    restore_harness(dest, fixture)
    if fixture.backfill_dependencies:
        backfill_story_sections(dest)
    subscribe_to_packs(dest, fixture.packs)
    # `.agents/agents-context.json` is generated and gitignored, so a fresh clone has none
    # and every prompt path in the run would fail to resolve. farrier regenerates it from
    # the tracked `agents.yml`, which is what a real checkout of this repo would do too.
    install(dest)
    return dest


def run_round(run: Run, fixture: Fixture) -> None:
    """Replay each pinned story on each flow, and keep what the score reads."""
    checkout_dir = sm.stablemate_checkout(run)
    budget = run.param_float("budget", fixture.budget_s)
    config = sm.effective(run)
    runs_dir = trials_dir(run) / "runs"

    with sm.no_leaks(checkout_dir, pinned=sm.pin_held(run.pinned)):
        ledger: list[dict[str, Any]] = []
        for index, (pin, flow) in enumerate(plan_round(run, fixture), start=1):
            run_id = f"{fixture.app}-{run.label}-{flow}-{pin.story}-{index}"

            def install(repo: Path, run_id: str = run_id) -> None:
                run.cli(
                    *sm.uv_run(checkout_dir, "farrier"),
                    "farrier", "install", "--repo", str(repo),
                    cwd=checkout_dir, log_name=f"{run_id}-farrier", check=True,
                )

            repo = checkout(
                run, fixture, pin, flow, run.workdir(run_id) / fixture.app, install
            )

            # Two clocks: `monotonic` measures the trial and cannot go backwards, while the
            # epoch second is what groom's spans are stamped with, so it is the only one that
            # can bound this trial's telemetry away from an earlier round under the same id.
            started, since = time.monotonic(), time.time()
            result = run.cli(
                # `uv_run` rather than an inherited cwd: the trial process stands *in
                # the tree under test* (see `cwd=repo`), so uv is told where its workspace
                # is instead of finding it underfoot — and which member's environment to
                # run in, so the pinned checkout's code is what actually runs.
                *sm.uv_run(checkout_dir, "workhorse-workflows"),
                "workhorse-coder", "run", flow,
                "--runs-dir", str(runs_dir), "--run-id", run_id,
                # Whole-file: the round's models are the tracked config's, not whatever
                # this machine happens to have set. A label whose trials inherited the
                # shell is not a configuration anyone can compare against.
                "--config", str(config),
                # No `session_id`, and this is the contract rather than an omission: the
                # lane is entered by an agent with no memory of having done this work, on
                # a tree that says it has not been done. Seeding the conversation that
                # landed the commit would measure a resumption.
                "--params", json.dumps({"story": pin.story, "docs_path": str(repo)}),
                cwd=repo,
                env={
                    **os.environ,
                    "WORKHORSE_MAX_RUNTIME_S": str(budget),
                    "AGENT_REPO_DIR": str(repo),
                },
                log_name=f"{run_id}-{flow}",
            )
            wall = time.monotonic() - started

            # The trial tree lives in `scratch/` and is never sealed — ten copies of an
            # application is a result zip nobody keeps. `docs/` is what a reader of the
            # sealed result needs: the plan, the evidence, the book the flow wrote.
            witness = capture_witness(
                repo, trials_dir(run) / run_id / "witness", fixture.extra_witness
            )
            ledger.append({
                "run_id": run_id, "story": pin.story, "flow": flow,
                "commit": pin.commit(flow),
                "rc": result.returncode,
                "witness": str(witness.relative_to(run.stage)),
                "timing": fx.timing_of(run_id, wall, since),
                "laps": fx.laps_of(run_id, since),
            })
            run.write_json(trials_dir(run) / "trials.json", ledger)


def headline(trials: list[dict[str, Any]], runs: list[dict[str, Any]]) -> str:
    """Laps beside what stopped and what it cost — the whole of what a replay measures.

    Escalations sit on the headline rather than in the detail because they are the one
    result that is not a matter of degree: with `operator_mode: human` every one of them is
    a run that HALTED and asked a person, and a round reporting tidy lap counts over three
    of those converged in the same sense a stopped clock is on time.
    """
    by_flow = sorted({str(t["flow"]) for t in trials})
    counts = "  ".join(
        f"{sum(1 for t in trials if t['flow'] == flow)} {flow}" for flow in by_flow
    )
    blocked = sum(1 for t in trials if t["rc"])
    escalations = sum(len(r["escalations"]) for r in runs)
    wall = sum(float((t.get("timing") or {}).get("wall_s") or 0.0) for t in trials)
    parts = [f"{counts} trial(s)"]
    if blocked:
        parts.append(f"{blocked} nonzero exit(s)")
    parts.append(f"{escalations} escalation(s)" if escalations else "no escalation")
    return "  ".join(parts) + f"{fx.convergence(trials)} | {wall / 60:.0f}m"


def score_round(run: Run) -> Score:
    """Convergence, read back off what the round staged. Read-only over the stage.

    Nothing here consults an answer key — a replay has none — so every line is recomputed
    from the run dirs and the telemetry the trials left behind, and a sealed result stays
    re-scorable after the report changes without re-running a single trial.
    """
    ledger = run.stage.joinpath(*TRIALS) / "trials.json"
    if not ledger.is_file():
        return Score(headline="no trials recorded — the round did not reach a run")

    rows: list[dict[str, Any]] = json.loads(ledger.read_text(encoding="utf-8"))
    runs_dir = run.stage.joinpath(*TRIALS) / "runs"
    runs = fx.read_runs(runs_dir, sm.stablemate_checkout(run))
    leverage = fx.time_leverage(rows)
    detail = [
        *fx.reliability_lines(runs),
        *(["", f"  {leverage}"] if leverage else []),
        *fx.node_table(rows),
        *fx.timing_lines(fx.hang_candidates(runs_dir, run.stage / "artifacts")),
    ]
    return Score(
        headline=headline(rows, runs),
        detail=tuple(detail),
        data={"trials": rows, "runs": runs},
    )
