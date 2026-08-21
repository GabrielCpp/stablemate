"""expense-split — does a review loop converge, on a fixture that has no answer key.

The other frozen-app tasks ask a detection question: seed a defect, see whether QA notices.
This one asks the question underneath it — **how much does the machinery talk to itself
before it will let a story go** — and it asks it of a real five-story application built by
the coder workflow rather than of a hand-frozen fixture.

That question needs no answer key, which is why this task has one and the round is scored
on convergence alone: laps per node, operator-gate escalations, cost and wall clock. There
is nothing here to be right or wrong about, so nothing here can be gamed in the direction
detection can: a lane that refutes everything catches every defect and never terminates,
and this is the number that says so.

The seed is the finished app with its whole history, so a trial does not materialize a
tree — it checks one out. Each story was landed by a real run, and the commit that landed
it is the exact state the flow was entered in; `PINS` below is that correspondence, and it
is tracked data rather than a fixture file because it is five rows that change only when
the bundle is recaptured.

Everything about *what the numbers mean* — laps, escalations, the time partition — is
`_forensics.py`'s and is shared verbatim with the greenfield and frozen-app rounds.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import _forensics as fx
import _stablemate as sm
from _frozenapp import QA_OUTPUTS, capture_witness
from paddock import Run, Score, step, task

task(
    name="expense-split",
    seed="expense-split",
    config="configs/opencode.toml",
)


@dataclass(frozen=True, slots=True)
class Pin:
    """One story and the commit each flow's replay is entered at.

    Two commits because the two flows were landed separately: `qa` is the commit that
    carries the story's implementation and its QA outputs, `docs` the one that carries its
    book entry. Replaying a flow means standing at its commit and removing what that flow
    wrote — see `rewind`.
    """

    story: str
    qa: str
    docs: str

    def commit(self, flow: str) -> str:
        commit = self.qa if flow == "qa" else self.docs
        if not commit:
            raise sm.TrialError(f"no {flow} commit pinned for story {self.story!r}")
        return commit


#: The five stories, in the order they were built. Reachable in the seed's own `.git` —
#: `paddock seed capture` zipped the repository, history included, which is what makes a
#: per-story pin a checkout rather than a second fixture.
PINS = (
    Pin(story="create-group", qa="b3b0e0c", docs="e1b9785"),
    Pin(story="group-membership", qa="a4b70c2", docs="a4b70c2"),
    Pin(story="expense-record", qa="b0464ec", docs="b8b3ffc"),
    Pin(story="expense-list", qa="c0478a9", docs="c0478a9"),
    Pin(story="balance-settlement", qa="99fff2b", docs="321d39a"),
)

#: The flows a round replays unless `--param flows=` narrows it. Both, by default: the
#: fixture's whole point is that it carries a QA loop *and* a documentation loop, and a
#: change that quiets one by pushing the work into the other has not quieted anything.
FLOWS = ("qa", "docs")

#: Where the docs flow writes. Rewound wholesale, so the path is named once.
BOOK = "docs/features"

#: The default wall-clock budget for one trial, in seconds. Enforced by workhorse between
#: states, so an over-budget trial stops at a node boundary with its telemetry intact and
#: still reports a partial lap count — a budget death is a measurement.
BUDGET_S = 2400.0

#: Where the round's own ledger lives inside the stage. Named explicitly rather than via
#: `run.artifacts`, which is relative to the current step and `score` runs outside them.
TRIALS = ("artifacts", "trials")


def trials_dir(run: Run) -> Path:
    directory = run.stage.joinpath(*TRIALS)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def plan_round(run: Run) -> list[tuple[Pin, str]]:
    """The trials to run: every pinned story on every selected flow, stories outermost."""
    wanted = set(run.param_list("stories"))
    if missing := wanted - {pin.story for pin in PINS}:
        raise sm.TrialError(
            f"--param stories names stories this fixture has no pin for: "
            f"{', '.join(sorted(missing))}"
        )
    pins = [pin for pin in PINS if not wanted or pin.story in wanted]
    flows = run.param_list("flows") or FLOWS
    if unknown := set(flows) - set(FLOWS):
        raise sm.TrialError(f"--param flows={','.join(sorted(unknown))}: known flows are qa, docs")
    return [(pin, flow) for pin in pins for flow in flows]


def rewind(repo: Path, pin: Pin, flow: str) -> None:
    """Put the checked-out tree back into the state the flow was entered in.

    Per flow, because the two write to different places:

      * **qa** removes the story's plan and evidence from its spec dir, leaving the story,
        the implementation plan and the code — what `run qa` was handed.
      * **docs** restores `docs/features` to the commit's *parent*, so the book lags this
        story by exactly one story. That is the real historical input, and the distinction
        matters: a book rewound further would be missing entries outside this story's
        obligations, which is a different and easier complaint for a reviewer to make.
    """
    if flow == "qa":
        spec = repo / "docs" / "specs" / pin.story
        if not spec.is_dir():
            raise sm.TrialError(
                f"no spec dir {spec} at {pin.qa} — is the pin for {pin.story!r} still right?"
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
        parent = f"{pin.commit(flow)}~"
        sm.git("rm", "-r", "--quiet", "--force", "--ignore-unmatch", "--", BOOK, cwd=repo)
        if sm.git("ls-tree", "--name-only", parent, BOOK, cwd=repo).strip():
            sm.git("checkout", parent, "--", BOOK, cwd=repo)


#: The story section this fixture predates. `registry.STORY_SECTIONS` gained a leading
#: `## Dependencies` after the bundle was captured, and `coder/shared/story.py` refuses to
#: plan against a story.md that is missing a required section — so every pin in `PINS`
#: stops at the first node with "story.md is still a bare scaffold", on both flows, and the
#: fixture measures nothing at all.
DEPS_SECTION = "## Dependencies\n\n(none)\n\n"


def backfill_story_sections(repo: Path) -> None:
    """Give every story.md the `## Dependencies` section the schema now requires.

    A migration, not a favor to the flow under test. `(none)` is the stub the current
    authoring writes and `story_dependencies` reads no edge from it, so the story graph a
    trial is handed is byte-for-byte the one the original run was handed — the heading only
    satisfies the gate that did not exist when these commits were made.

    The alternative is recapturing the bundle, which would move all ten pins and throw away
    the one thing this fixture is: five stories landed by real runs, at the commits that
    landed them. A schema addition is not a reason to lose that history.
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


#: The pack the docs lane's prompts hard-reference. `document-story.md` and
#: `repair-documentation.md` both carry a `skill_load_ref` to `ostler-documentation`, which
#: farrier ships in the `stablemate` pack — and the captured app subscribes to
#: `product-planning` and `go` only. seat-booking and policy-desk both subscribe to it; this
#: fixture was captured without it.
DOCS_PACK = "stablemate"


def subscribe_to_the_docs_pack(repo: Path) -> None:
    """Add the `stablemate` pack to `agents.yml` so the docs lane's skills resolve.

    Same shape as `backfill_story_sections`, and for the same reason: a capture-time gap the
    fixture would otherwise carry into every trial. Without it farrier installs no
    `ostler-documentation`, the prompt renders its placeholder text instead of a path, and
    the agent improvises the documentation doctrine it was supposed to be handed — so the
    docs flow is measured on inventing a standard rather than on applying one.

    A line edit rather than a YAML round-trip, because `agents.yml` carries comments the
    trial should be handed exactly as the seed has them, and every YAML writer drops them.
    """
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
    if any(line.strip() == f"- {DOCS_PACK}" for line in lines[start + 1 : end]):
        return
    lines.insert(end, f"  - {DOCS_PACK}\n")
    agents_yml.write_text("".join(lines), encoding="utf-8")


def checkout(
    run: Run, pin: Pin, flow: str, dest: Path, install: Callable[[Path], None]
) -> Path:
    """Clone the unpacked seed at this story's commit, rewind the flow, install the layer.

    A clone rather than a copy: the seed's working tree is whatever it was at capture (the
    pointer records `dirty = true`), and the state a trial is about is the committed one.
    Cloning also leaves the unpacked seed untouched, so every trial in a round starts from
    the same bytes and the stage stays a faithful copy of what was seeded.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    sm.git("clone", "--quiet", str(run.repo), str(dest), cwd=run.scratch)
    sm.git("checkout", "--quiet", pin.commit(flow), cwd=dest)
    rewind(dest, pin, flow)
    backfill_story_sections(dest)
    subscribe_to_the_docs_pack(dest)
    # `.agents/agents-context.json` is generated and gitignored, so a fresh clone has none
    # and every prompt path in the run would fail to resolve. farrier regenerates it from
    # the tracked `agents.yml`, which is what a real checkout of this repo would do too.
    install(dest)
    return dest


def run_round(run: Run) -> None:
    """Replay each pinned story on each flow, and keep what the score reads."""
    checkout_dir = sm.stablemate_checkout(run)
    budget = run.param_float("budget", BUDGET_S)
    config = sm.effective(run)
    runs_dir = trials_dir(run) / "runs"

    with sm.no_leaks(checkout_dir, pinned=sm.pin_held(run.pinned)):
        ledger: list[dict[str, Any]] = []
        for index, (pin, flow) in enumerate(plan_round(run), start=1):
            run_id = f"expense-split-{run.label}-{flow}-{pin.story}-{index}"

            def install(repo: Path, run_id: str = run_id) -> None:
                run.cli(
                    *sm.uv_run(checkout_dir, "farrier"),
                    "farrier", "install", "--repo", str(repo),
                    cwd=checkout_dir, log_name=f"{run_id}-farrier", check=True,
                )

            repo = checkout(run, pin, flow, run.workdir(run_id) / "expense-split", install)

            started = time.monotonic()
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
            witness = capture_witness(repo, trials_dir(run) / run_id / "witness")
            ledger.append({
                "run_id": run_id, "story": pin.story, "flow": flow,
                "commit": pin.commit(flow),
                "rc": result.returncode,
                "witness": str(witness.relative_to(run.stage)),
                "timing": fx.timing_of(run_id, wall),
                "laps": fx.laps_of(run_id),
            })
            run.write_json(trials_dir(run) / "trials.json", ledger)


def headline(trials: list[dict[str, Any]], runs: list[dict[str, Any]]) -> str:
    """Laps beside what stopped and what it cost — the whole of what this round measures.

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


@step()
def pin_config(run: Run) -> None:
    sm.pin_config(run)


@step()
def trials(run: Run) -> None:
    run_round(run)


def score(run: Run) -> Score:
    """Convergence, read back off what the round staged. Read-only over the stage.

    Nothing here consults an answer key — there is none — so every line is recomputed from
    the run dirs and the telemetry the trials left behind, and a sealed result stays
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
