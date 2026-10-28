"""Replay one lane of the coder workflow, cold, on a tree that already ran it once."""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paddock.tasks import forensics as fx
from paddock.tasks import stablemate as sm
from paddock.tasks import tree
from paddock.tasks.frozenapp import QA_OUTPUTS, capture_witness
from paddock.runner import CommandResult, Run
from paddock.registry import Score
from paddock.tasks import inputs

KNOWN_FLOWS = ("qa", "docs", "dev")

BUDGET_S = 2400.0

TRIALS = ("artifacts", "trials")

DEPS_SECTION = "## Dependencies\n\n(none)\n\n"


@dataclass(frozen=True, slots=True)
class Pin:
    """One story and the commit each flow's replay is entered at.

    A folder of repos names the commit per member: `{"qa": {"api-service": "c1"}}`.
    A member left out is replayed at its staged HEAD.
    """

    story: str
    commits: Mapping[str, str | Mapping[str, str]]
    book_from: str = ""

    def commit(self, flow: str, member: str = "") -> str:
        pinned = self.commits.get(flow, "")
        if isinstance(pinned, str):
            commit = pinned
        elif member:
            commit = pinned.get(member, "")
        else:
            raise sm.TrialError(
                f"the {flow} pin for story {self.story!r} names commits per member; ask for one member"
            )
        if not commit:
            where = f" for {member}" if member else ""
            raise sm.TrialError(f"no {flow} commit pinned{where} for story {self.story!r}")
        return commit

    def commits_of(self, flow: str, members: tuple[str, ...]) -> dict[str, str]:
        """The commit each member is entered at, keyed `""` for a single repo."""
        if not members:
            return {"": self.commit(flow)}
        value = self.commits.get(flow, "")
        if isinstance(value, str):
            raise sm.TrialError(
                f"the {flow} pin for story {self.story!r} is one commit on a stage of several repos; "
                f"name each member: {{{', '.join(repr(m) for m in members)}: commit}}"
            )
        if unknown := sorted(set(value) - set(members)):
            raise sm.TrialError(
                f"the {flow} pin for story {self.story!r} names {', '.join(unknown)}, "
                f"which is not one of {', '.join(members)}"
            )
        return {member: commit for member, commit in value.items() if commit}

    def entry_ref(self, flow: str, member: str = "") -> str:
        return self.book_from or f"{self.commit(flow, member)}~"


@dataclass(frozen=True, slots=True)
class Fixture:
    """One app's replay: which tree, which stories, which lanes, and what it needs patched."""

    app: str
    pins: tuple[Pin, ...]
    flows: tuple[str, ...] = KNOWN_FLOWS
    book: str = "docs/services"
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
    wanted = set(inputs.names(run, "stories"))
    if missing := wanted - {pin.story for pin in fixture.pins}:
        raise sm.TrialError(
            f"input stories names stories this fixture has no pin for: "
            f"{', '.join(sorted(missing))}"
        )
    pins = [pin for pin in fixture.pins if not wanted or pin.story in wanted]
    flows = inputs.names(run, "flows") or fixture.flows
    if unknown := set(flows) - set(fixture.flows):
        raise sm.TrialError(
            f"input flows={','.join(sorted(unknown))}: this fixture replays "
            f"{', '.join(fixture.flows)}"
        )
    return [(pin, flow) for pin in pins for flow in flows if flow in pin.commits]


def clear_qa_outputs(spec: Path) -> None:
    for name in QA_OUTPUTS:
        target = spec / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def rewind_tree(repo: Path, ref: str) -> None:
    sm.git("rm", "-r", "--quiet", "--force", "--ignore-unmatch", "--", ".", cwd=repo)
    sm.git("checkout", ref, "--", ".", cwd=repo)


def rewind_book(repo: Path, book: str, ref: str) -> None:
    sm.git("rm", "-r", "--quiet", "--force", "--ignore-unmatch", "--", book, cwd=repo)
    if sm.git("ls-tree", "--name-only", ref, book, cwd=repo).strip():
        sm.git("checkout", ref, "--", book, cwd=repo)


def rewind(repo: Path, fixture: Fixture, pin: Pin, flow: str, *, run: Run | None = None) -> None:
    """Put the checked-out tree back into the state the flow was entered in."""
    member_names = tree.members(repo)
    if member_names and run is None:
        raise sm.TrialError(f"{repo} is a folder of repos; rewind needs the run to find its docs home")
    if flow == "qa":
        spec = tree.spec_dir(run, repo, pin.story) if run is not None else sm.spec_dir(repo, pin.story)
        if not spec.is_dir():
            pinned = pin.commits_of(flow, member_names)
            raise sm.TrialError(
                f"no spec dir {spec} at {', '.join(pinned.values())} — is the pin for "
                f"{pin.story!r} still right?"
            )
        clear_qa_outputs(spec)
    elif flow == "dev":
        pinned = pin.commits_of(flow, member_names)
        refs = {member: pin.entry_ref(flow, member) for member in pinned}
        for member, ref in refs.items():
            rewind_tree(repo / member, ref)
        home = tree.docs_home(run, repo) if run is not None and member_names else repo
        if not any(
            any(root.glob(f"*/stories/{pin.story}/story.md")) for root in (home / "docs" / "epics", home / "epics")
        ):
            shown = ", ".join(refs.values()) if not member_names else ", ".join(
                f"{member} at {ref}" for member, ref in refs.items()
            )
            raise sm.TrialError(
                f"no story.md for {pin.story!r} at {shown} — the dev pin names a commit "
                f"whose parent predates the story it is supposed to implement"
            )
    elif member_names and run is not None:
        home = tree.docs_home(run, repo)
        member = home.relative_to(repo).parts[0]
        root = repo / member
        rewind_book(root, (home.relative_to(root) / fixture.book).as_posix(), pin.entry_ref(flow, member))
    else:
        rewind_book(repo, fixture.book, pin.entry_ref(flow))


def restore_harness(repo: Path, fixture: Fixture) -> None:
    """Copy the repo's own configuration in from a later commit that tracks it."""
    if not fixture.harness:
        return
    if not fixture.harness_ref:
        raise sm.TrialError("fixture declares `harness` paths but no `harness_ref` to take them from")
    sm.git("checkout", fixture.harness_ref, "--", *fixture.harness, cwd=repo)


def backfill_story_sections(repo: Path) -> None:
    """Give every story.md the `## Dependencies` section the schema now requires."""
    for story_md in sorted([*repo.glob("docs/epics/*/stories/*/story.md"), *repo.glob("epics/*/stories/*/story.md")]):
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
    member_names = tree.stage_members(run)
    pinned = pin.commits_of(flow, member_names)
    sources = tree.repos_at(run.stage, member_names)
    for key, target in tree.repos_at(dest, member_names).items():
        sm.git("clone", "--quiet", str(sources[key]), str(target), cwd=run.scratch)
        if key in pinned:
            sm.git("checkout", "--quiet", pinned[key], cwd=target)
    if not member_names:
        sm.upgrade_layout(dest)
    rewind(dest, fixture, pin, flow, run=run)
    if not member_names:
        sm.upgrade_layout(dest)
    home = tree.witness_docs(run, dest)
    restore_harness(home, fixture)
    if fixture.backfill_dependencies:
        backfill_story_sections(home)
    installable = [
        repo for repo in tree.repos_at(dest, member_names).values()
        if not member_names or (repo / "agents.yml").is_file()
    ]
    if member_names and fixture.packs and not installable:
        raise sm.TrialError(f"no repo of {dest} has an agents.yml to subscribe to {', '.join(fixture.packs)}")
    for repo in installable:
        subscribe_to_packs(repo, fixture.packs)
    for repo in installable:
        install(repo)
    return dest


def launch_flow(
    run: Run, repo: Path, flow: str, *, run_id: str, story: str, budget: float, runs_dir: Path
) -> CommandResult:
    """Drive `workhorse-coder run <flow>` over the trial tree at *repo*, under the workspace a folder of repos carries."""
    launch = tree.launch(run, repo)
    return run.cli(
        *sm.uv_run(sm.stablemate_checkout(run), "workhorse-workflows"),
        "workhorse-coder", "run", flow,
        "--runs-dir", str(runs_dir), "--run-id", run_id,
        *launch.flags(),
        "--params", json.dumps({"story": story, "repo_dir": str(launch.repo_dir)}),
        cwd=launch.repo_dir,
        env={
            **launch.env,
            "WORKHORSE_MAX_RUNTIME_S": str(budget),
            "AGENT_REPO_DIR": str(launch.repo_dir),
        },
        log_name=f"{run_id}-{flow}",
    )


def run_round(run: Run, fixture: Fixture) -> None:
    """Replay each pinned story on each flow, and keep what the score reads."""
    checkout_dir = sm.stablemate_checkout(run)
    budget = inputs.number(run, "budget", fixture.budget_s)
    runs_dir = trials_dir(run) / "runs"
    member_names = tree.stage_members(run)

    with sm.no_leaks(checkout_dir, pinned=sm.pin_held(run.pinned)):
        ledger: list[dict[str, Any]] = []
        for index, (pin, flow) in enumerate(plan_round(run, fixture), start=1):
            run_id = f"{fixture.app}-{run.name.n}-{flow}-{pin.story}-{index}"

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
            result = launch_flow(
                run, repo, flow, run_id=run_id, story=pin.story, budget=budget, runs_dir=runs_dir
            )
            wall = time.monotonic() - started

            witness = capture_witness(
                repo, trials_dir(run) / run_id / "witness", fixture.extra_witness, run=run
            )
            commits = pin.commits_of(flow, member_names)
            ledger.append({
                "run_id": run_id, "story": pin.story, "flow": flow,
                "commit": commits[""] if not member_names else commits,
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
