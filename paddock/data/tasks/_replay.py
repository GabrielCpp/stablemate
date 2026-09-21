"""Replay one lane of the coder workflow, cold, on a tree that already ran it once."""

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

KNOWN_FLOWS = ("qa", "docs", "dev")

BUDGET_S = 2400.0

TRIALS = ("artifacts", "trials")

DEPS_SECTION = "## Dependencies\n\n(none)\n\n"


@dataclass(frozen=True, slots=True)
class Pin:
    """One story and the commit each flow's replay is entered at."""

    story: str
    commits: Mapping[str, str]
    book_from: str = ""

    def commit(self, flow: str) -> str:
        commit = self.commits.get(flow, "")
        if not commit:
            raise sm.TrialError(f"no {flow} commit pinned for story {self.story!r}")
        return commit

    def entry_ref(self, flow: str) -> str:
        return self.book_from or f"{self.commit(flow)}~"


@dataclass(frozen=True, slots=True)
class Fixture:
    """One app's replay: which tree, which stories, which lanes, and what it needs patched."""

    app: str
    pins: tuple[Pin, ...]
    flows: tuple[str, ...] = KNOWN_FLOWS
    book: str = "docs/features"
    budget_s: float = BUDGET_S
    packs: tuple[str, ...] = ()
    harness: tuple[str, ...] = ()
    harness_ref: str = ""
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
    """Put the checked-out tree back into the state the flow was entered in."""
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
    elif flow == "dev":
        ref = pin.entry_ref(flow)
        sm.git("rm", "-r", "--quiet", "--force", "--ignore-unmatch", "--", ".", cwd=repo)
        sm.git("checkout", ref, "--", ".", cwd=repo)
        story_md = repo / "docs" / "epics"
        if not any(story_md.glob(f"*/stories/{pin.story}/story.md")):
            raise sm.TrialError(
                f"no story.md for {pin.story!r} at {ref} — the dev pin names a commit "
                f"whose parent predates the story it is supposed to implement"
            )
    else:
        book, ref = fixture.book, pin.entry_ref(flow)
        sm.git("rm", "-r", "--quiet", "--force", "--ignore-unmatch", "--", book, cwd=repo)
        if sm.git("ls-tree", "--name-only", ref, book, cwd=repo).strip():
            sm.git("checkout", ref, "--", book, cwd=repo)


def restore_harness(repo: Path, fixture: Fixture) -> None:
    """Copy the repo's own configuration in from a later commit that tracks it."""
    if not fixture.harness:
        return
    if not fixture.harness_ref:
        raise sm.TrialError("fixture declares `harness` paths but no `harness_ref` to take them from")
    sm.git("checkout", fixture.harness_ref, "--", *fixture.harness, cwd=repo)


def backfill_story_sections(repo: Path) -> None:
    """Give every story.md the `## Dependencies` section the schema now requires."""
    for story_md in sorted(repo.glob("docs/epics/*/stories/*/story.md")):
        text = story_md.read_text(encoding="utf-8")
        if "\n## Dependencies" in f"\n{text}":
            continue
        head, marker, rest = text.partition("\n## ")
        if not marker:
            raise sm.TrialError(f"{story_md} has no `## ` section to insert Dependencies before")
        story_md.write_text(f"{head}\n{DEPS_SECTION}## {rest}", encoding="utf-8")


def subscribe_to_packs(repo: Path, packs: tuple[str, ...]) -> None:
    """Add each missing pack to `agents.yml` so the lane's skills resolve."""
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
    """Clone the unpacked seed at this story's commit, rewind the flow, install the layer."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    sm.git("clone", "--quiet", str(run.repo), str(dest), cwd=run.scratch)
    sm.git("checkout", "--quiet", pin.commit(flow), cwd=dest)
    rewind(dest, fixture, pin, flow)
    restore_harness(dest, fixture)
    if fixture.backfill_dependencies:
        backfill_story_sections(dest)
    subscribe_to_packs(dest, fixture.packs)
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

            started, since = time.monotonic(), time.time()
            result = run.cli(
                *sm.uv_run(checkout_dir, "workhorse-workflows"),
                "workhorse-coder", "run", flow,
                "--runs-dir", str(runs_dir), "--run-id", run_id,
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
    """Laps beside what stopped and what it cost — the whole of what a replay measures."""
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
    """Convergence, read back off what the round staged."""
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
