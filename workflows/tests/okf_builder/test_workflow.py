"""End-to-end drives of the okf-builder workflow (`okf_builder/workflow.py`).

Nothing is stubbed except the agent turn. `prepare`, `select_item`, `record`,
`checkpoint_book`, `inventory_source`, `compute_coverage` and
`detect_webapp` all run for real against the `booked` / `dirty` fixtures — so a drive
here exercises ostler's real `fmt` and `doctor`, the real source walk, and the real
coverage join. The verdicts under test are arithmetic and ostler's, not a script's.

The agent seam is patched where the engine reads it
(`RunEnv.agent_runner`) and dispatches on the prompt's stem,
the same key the engine derives its node id from. Unlike author's stub this one mostly
does *not* write artifacts: the book is the fixture, and the point of most drives here is
that the deterministic gates rule on a book the agent did not touch. The one handler that
does write is the fixup repair, because a fixup loop that never converges is a different
test from one that does — and both are below.

What the port could get wrong, and what is therefore under test here:

* the run's one entry decision, read off the book rather than passed in: an empty book is
  filled top-down from the code's surfaces (`unbooked`), a populated one is reconciled to
  HEAD from the checkpoint (`booked`) — which is what the retired `recheck_only` used to
  ask for by hand.
* the drain: seed, pick, investigate, record, re-pick, and the dry exit into the
  convergence gate — with `rnd`/`rescan`/`stall`/`signature` riding through five states
  as parameters where the YAML kept them in one run-global `vars` namespace. The bug that
  namespace caused (`round` and `rescan_round` sharing a counter) cannot be reproduced
  here because it cannot be *written* here, but the round numbering it corrupted is
  asserted directly.
* the two arms of `checkpoint`: a dirty book queues one repair item per offending node and
  doctor code and re-enters the drain; a repaired book converges to the coverage re-scan.
* `MAX_TARGET_ATTEMPTS`: a repair that never lands blocks its own row and parks the run on
  an operator gate naming it, rather than being re-drilled forever or quietly waived.
* the `max_items` valve, which is an **operator gate** and not a quiet success: a partial
  book must not read as a finished one, and a budget stop is not a defect, so the run
  blocks on an `Await` and a refuel answer grants another allowance.
* `handoff` into `walkthrough-web`, whose own `detect_webapp` gates it — a service with no
  documented screen surface is walked by a no-op, and the run's value is the sub-flow's.
* resume, which is why the checkpoint lands before the agent turn: a run killed while
  investigating re-investigates that item and no earlier one.
* `labels()`, which reads `self.output(select_item)` and must not crash before the first
  pick.
"""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from _fakes import StubRunner
from workhorse._vendor.stablemate_core.base_cache import cache_root
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow import activity as pyflow_activity
from workhorse.pyflow.graph import state_graph
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import drive, read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows import okf_builder
from workhorse_workflows.okf_builder.main.flow import investigation_power, repair_power
from workhorse_workflows.okf_builder.shared import paths
from workhorse_workflows.okf_builder.shared.worklist import MAX_TARGET_ATTEMPTS
from workhorse_workflows.okf_builder.walkthrough_web.flow import WalkthroughWeb
from workhorse_workflows.okf_builder.workflow import OkfBuilder

SERVICE = "acme"
BOOK = f"docs/features/{SERVICE}"
REFUND = f"{BOOK}/concepts/refund.md"
#: The repair item `dirty` produces, minus its round prefix: `<path>#<node>#<code>`, which is
#: what makes two findings of different codes on one node two separately-promptable turns.
#: `missing-code-symbol` refs a *source* symbol rather than a book node, so its item groups by
#: the document — the only place the repair turn could open.
REPAIR = f"{REFUND}#{REFUND}#missing-code-symbol"

#: What the scripted enumeration hands back by default: one surface, whose investigation
#: this book does not actually need — the fixture is already complete, which is what makes
#: the coverage verdict below a statement about the join rather than about the stub.
SURFACE = {"kind": "surface", "target": "acme/service.py", "context": "the billing entry"}

#: What an investigation of that surface writes into an empty book. A first fill converges
#: only if the turn actually documents something, so the drives against `unbooked` hand the
#: scripted turn the one doc the `booked` fixture ships with.
CHARGE_DOC = """---
type: concept
slug: charge
title: Charge
---
# Charge

- code: `acme/service.py::charge`

Charging.
"""
FILLS = {"acme/service.py": {f"{BOOK}/concepts/charge.md": CHARGE_DOC}}


# ------------------------------------------------------------------ the scripted agent


class _Agent:
    """A scripted stand-in for the workflow's four agent turns.

    It dispatches on the prompt's filename — the same key the engine derives its node id
    from, and the same key the registry's dry-run stubs use.

    The knobs are the graph's branches: `surfaces` is what the enumeration discovers,
    `spawn` lets one item's investigation open deeper ones, `repair` makes the
    investigation of a fixup item actually delete the offending doc (the convergent
    fixup loop; without it the loop stalls, which is the other test), and `explode` raises
    instead of investigating — a run killed mid-turn.
    """

    def __init__(
        self,
        repo: Path,
        *,
        surfaces: list[dict[str, Any]] | None = None,
        spawn: dict[str, list[dict[str, Any]]] | None = None,
        repair: bool = False,
        explode: set[str] | None = None,
        doc_status: str = "documented",
        note: str = "",
        writes: dict[str, dict[str, str]] | None = None,
        verdict: str = "story",
        lands_on: str = "",
    ) -> None:
        self.repo = repo
        self.surfaces = [dict(SURFACE)] if surfaces is None else surfaces
        self.spawn = dict(spawn or {})
        #: Per-target `{repo-relative path: text}` the investigation writes — how a first
        #: fill of an empty book gets a book to measure.
        self.writes = dict(writes or {})
        self.repair = repair
        #: What a *repair* turn reports back. `documented` is the scripted default; a
        #: `partial`/`skipped` is the turn saying the finding cannot be cleared from the
        #: book, which is what spends the target's attempt allowance.
        self.doc_status = doc_status
        self.note = note
        #: What the *adjudication* turn says about a row at the attempt limit — which side
        #: of the book/code correspondence is wrong. `story` is the default because it is
        #: the one verdict that routes straight to the operator gate, which is the
        #: behaviour the gate tests were written against.
        self.verdict = verdict
        #: A substring of a repair item's context that makes the turn land — how a test
        #: says "the repair turn can fix it once it is told this".
        self.lands_on = lands_on
        self.explode = set(explode or ())
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []
        self.cwds: list[str] = []
        self.targets: list[str] = []
        self.add_dirs: list[list[str]] = []
        self.powers: list[str | None] = []

    # -- the seam ---------------------------------------------------------

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        self.cwds.append(str(node.cwd))
        self.add_dirs.append([str(path) for path in node.add_dirs or []])
        self.powers.append(node.power)
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        return f"(scripted) {node.prompt}", handler(data, self.counts()[stem])

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]

    def powers_for(self, stem: str) -> list[str | None]:
        return [p for s, p in zip(self.calls, self.powers, strict=True) if s == stem]

    # -- the turns --------------------------------------------------------

    def _enumerate_surfaces(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"discovered": self.surfaces}

    def _investigate(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        target = str(data["item_target"])
        self.targets.append(target)
        if target in self.explode:
            raise RuntimeError(f"killed while investigating {target}")
        for rel, text in self.writes.get(target, {}).items():
            doc = self.repo / rel
            doc.parent.mkdir(parents=True, exist_ok=True)
            doc.write_text(text, encoding="utf-8")
        if self.lands_on and self.lands_on in str(data.get("item_context", "")):
            self.repair, self.doc_status = True, "documented"
        if self.repair and str(data["item_kind"]).startswith("fix:"):
            # A repair target is `<path>#<node>#<code>` — no round prefix, because the round
            # is not part of a finding's identity. The repair the doctor finding calls for is
            # "stop citing a symbol that does not exist", and deleting the doc does it.
            doc = self.repo / target.split("#")[0]
            doc.unlink(missing_ok=True)
        status = self.doc_status if str(data["item_kind"]).startswith("fix:") else "documented"
        return {
            "doc_status": status,
            "note": self.note if status != "documented" else "",
            "discovered": self.spawn.get(target, []),
        }

    #: A `fix:` item renders `main/prompts/repair.md` instead, so the dispatch above sees a
    #: different stem for the same node. Same turn, same seam — the prompt is what differs.
    _repair = _investigate

    def _adjudicate(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "chain": f"1. why: {data['item_code']} stands on {data['nodes']}; "
            f"2. cause: scripted; 3. side: {self.verdict}",
            "seed_summary": "the source leaves it unnamed" if self.verdict == "code" else "",
        }

    def _recheck_coverage(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"needs_journeys": False, "discovered": []}

    def _walkthrough_web(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"walk_status": "confirmed", "discovered": []}


# ------------------------------------------------------------------------- the harness


def _env(tmp: Path, *, run_dir: Path | None = None) -> RunEnv:
    writer = (
        ArtifactWriter.resume(run_dir)
        if run_dir is not None
        else ArtifactWriter("okf-builder", tmp / "runs", run_id="t")
    )
    return RunEnv(
        writer=writer,
        workflow_dir=Path(okf_builder.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
    )


def _drive(env: RunEnv, agent: _Agent, **inputs: Any) -> Any:
    inputs.setdefault("service", SERVICE)
    return drive(OkfBuilder(**inputs), replace(env, agent_runner=StubRunner(agent)))


def _worklist(repo: Path) -> list[dict[str, Any]]:
    wl = paths.worklist_path(repo, SERVICE)
    return json.loads(wl.read_text())["items"]


# ---------------------------------------------------------------------- repair power


def test_repair_power_keeps_a_single_mechanical_first_attempt_low() -> None:
    """A machine-rechecked one-finding repair should start on the cheapest model."""
    context = {"grounded": False, "findings": [{"code": "undeclared-obligation"}]}

    assert repair_power({"attempts": 0}, json.dumps(context)) == "low"


@pytest.mark.parametrize(
    ("current", "context"),
    [
        ({"attempts": 0}, {"grounded": True, "findings": [{}]}),
        ({"attempts": 0}, {"grounded": False, "related": ["docs/features/acme/a.md#a"]}),
        ({"attempts": 0}, {"grounded": False, "paths": ["a.md", "b.md"]}),
        ({"attempts": 0}, {"grounded": False, "findings": [{}, {}, {}]}),
    ],
)
def test_repair_power_routes_difficult_first_attempts_to_medium(
    current: dict[str, Any], context: dict[str, Any]
) -> None:
    """Source grounding, grouped scope, and large batches need Terra, not Luna."""
    assert repair_power(current, json.dumps(context)) == "medium"


def test_repair_power_climbs_the_ladder_only_after_each_tier_fails() -> None:
    """One failed Luna repair buys Terra; two failed attempts finally buy Sol."""
    context = json.dumps({"grounded": False, "findings": [{}]})

    assert repair_power({"attempts": 1}, context) == "medium"
    assert repair_power({"attempts": 2}, context) == "high"


def test_investigation_power_promotes_only_a_retried_item() -> None:
    """The high-volume crawl starts on Luna and buys Terra only after a failed visit."""
    assert investigation_power({"attempts": 0}) == "low"
    assert investigation_power({"attempts": 1}) == "medium"


# ---------------------------------------------------------------------------- the drain


def test_an_empty_book_is_filled_top_down_from_the_code_s_surfaces(
    unbooked: Path, tmp_path: Path, read_json: Callable[[Path], Any]
) -> None:
    """The first fill: seed one surface, document it, converge, hand off.

    There is no book to reconcile against, so the entry is the enumeration — and every
    artifact below is the YAML's artifact: the worklist with its item closed, the source
    inventory walked from `acme/`, and the coverage join written into the book the turn
    just wrote. The verdict is arithmetic — one module and one symbol, both cited by the
    doc the investigation produced.
    """
    agent = _Agent(unbooked, writes=FILLS)
    result = _drive(_env(tmp_path), agent)

    assert agent.counts() == {"enumerate-surfaces": 1, "investigate": 1}, agent.counts()
    assert agent.powers == ["low", "low"]

    # The drain closed what it opened.
    items = _worklist(unbooked)
    assert [(i["kind"], i["target"], i["status"]) for i in items] == [
        ("surface", "acme/service.py", "done")
    ], items

    # The coverage join ran for real and is complete: 2 units, 2 covered.
    coverage = read_json(unbooked / BOOK / "coverage.json")
    assert coverage["total"] == 2, coverage
    assert coverage["covered"] == 2, coverage
    inventory = read_json(paths.source_inventory_path(paths.worklist_path(unbooked, SERVICE)))
    assert {u["code"] for u in inventory["units"]} == {
        "acme/service.py",
        "acme/service.py::charge",
    }, inventory

    # `recheck` never ran, because the join was already complete.
    assert "recheck-coverage" not in agent.counts(), agent.counts()

    # The run's value is the sub-flow's: this service documents no screen, so the walk is
    # a no-op that booted nothing.
    assert result.is_webapp is False, result
    assert result.entry_url == "", result


def test_a_book_that_exists_is_reconciled_to_head_rather_than_re_enumerated(
    booked: Path, tmp_path: Path, read_json: Callable[[Path], Any]
) -> None:
    """The other entry, and the reason `recheck_only` is retired.

    A populated book has a checkpoint and a coverage join that between them name every
    unit it owes work on, so re-enumerating its surfaces buys nothing and costs a turn per
    run. This book owes nothing: doctor is green, the join is 2/2, and the run converges
    without spending a single agent turn — which is exactly what an operator who forgot to
    pass `recheck_only` did *not* get before.
    """
    agent = _Agent(booked)
    result = _drive(_env(tmp_path), agent)

    assert agent.counts() == {}, agent.counts()
    assert _worklist(booked) == [], _worklist(booked)
    coverage = read_json(booked / BOOK / "coverage.json")
    assert (coverage["covered"], coverage["total"]) == (2, 2), coverage
    assert result.is_webapp is False, result


@pytest.mark.parametrize(
    ("story", "expected_message"),
    [
        ("", "docs: update the OKF book"),
        ("PRED-123", "docs: update the OKF book\n\nStory: PRED-123"),
    ],
)
def test_a_completed_book_is_committed_with_optional_story_provenance(
    booked: Path,
    tmp_path: Path,
    story: str,
    expected_message: str,
) -> None:
    """The successful tail commits the book, and nothing beside that book.

    A bulk reconciliation has no story to cite. A narrowed run may still carry the
    retiring story input, and that provenance belongs in git's parsed trailer rather
    than in the subject. In either mode, another process's work outside this service's
    book must remain untouched.
    """
    unrelated = booked / "notes.txt"
    unrelated.write_text("another process is working here\n", encoding="utf-8")

    result = _drive(_env(tmp_path), _Agent(booked), story=story)

    message = subprocess.run(
        ["git", "log", "-1", "--format=%B"],
        cwd=booked,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    committed = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
        cwd=booked,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", str(unrelated.relative_to(booked))],
        cwd=booked,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    assert result.is_webapp is False, result
    assert message == expected_message
    assert committed
    assert all(path.startswith(f"{BOOK}/") for path in committed), committed
    assert status == "?? notes.txt\n"


def test_the_build_scratch_ignores_itself_so_a_commit_all_cannot_eat_it(
    booked: Path, tmp_path: Path
) -> None:
    """`.agents/okf-build/` carries its own `.gitignore`, from the first run onward.

    What is left in it is run state — worklists, the source inventory — and it lives inside
    the docs repo. A coder run in the same checkout commits with `commit_all` (`git add
    -A`), so an unignored scratch is swept into a story commit and then lives in every
    clone's history, where only a rewrite removes it. That is not hypothetical; it is why
    this test exists.
    """
    _drive(_env(tmp_path), _Agent(booked))

    assert (booked / paths.BUILD_DIRNAME / ".gitignore").read_text() == "*\n"

    # The property, not the file: git offers nothing here to `add -A`.
    stray = booked / paths.BUILD_DIRNAME / "acme.worklist.json.source.json"
    stray.write_text("{}")
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=booked, capture_output=True, text=True, check=True
    ).stdout
    assert paths.BUILD_DIRNAME not in status, status


def test_the_browser_profile_is_not_in_the_repo_at_all(
    booked: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stronger guarantee: the profile is machine scratch, so it is in the cache.

    An ignore rule only protects a repo that has it — and it still leaves tens of thousands
    of Chrome files inside a checkout that other processes crawl, diff and archive. The
    profile is state no resume needs, which is precisely what the stablemate cache is for,
    so the question "will something commit it" stops being askable.
    """
    # Sandboxed, so the suite never writes into the developer's real cache — and so the
    # `$STABLEMATE_CACHE_DIR` override the resolver documents is exercised rather than
    # assumed.
    monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path / "cache"))
    scratch = paths.walkthrough_scratch(booked)

    assert not scratch.is_relative_to(booked), scratch
    assert scratch.is_relative_to(cache_root()), scratch
    # Two checkouts of the same repo must not share one profile: same basename, and a
    # browser answers CDP for whichever bound the port first.
    twin = booked.parent / "twin" / booked.name
    twin.mkdir(parents=True)
    assert paths.walkthrough_scratch(twin) != scratch


def test_an_investigation_opens_the_items_it_reveals(unbooked: Path, tmp_path: Path) -> None:
    """The drain is a crawl, not a list: `record_item` writes back what the turn found.

    That write is its own state precisely so a crash mid-turn re-investigates rather than
    closing an item nothing documented — which is what the resume test below drives.
    """
    agent = _Agent(
        unbooked,
        writes=FILLS,
        spawn={
            "acme/service.py": [
                {"kind": "layer", "target": "acme/service.py::charge", "context": "the handler"}
            ]
        },
    )
    _drive(_env(tmp_path), agent)

    assert agent.counts()["investigate"] == 2, agent.counts()
    assert agent.targets == ["acme/service.py", "acme/service.py::charge"], agent.targets
    assert all(i["status"] == "done" for i in _worklist(unbooked)), _worklist(unbooked)


def test_a_source_root_that_is_not_a_directory_fails_the_run(
    booked: Path, tmp_path: Path
) -> None:
    """`prepare` carries its failure as data and `start` is where it becomes a failed run.

    A build whose instrument is missing must not be indistinguishable from a build that
    is done, so this is `WorkflowFailed` rather than an early `Done` — and the message is
    `prepare`'s own, which the YAML's `type: fail` node could not carry.
    """
    agent = _Agent(booked)
    with pytest.raises(WorkflowFailed, match="is not a directory"):
        _drive(_env(tmp_path), agent, source_path="nope")

    assert agent.counts() == {}, agent.counts()


# ----------------------------------------------------------------------- the fixup loop


def test_a_dirty_doctor_queues_one_repair_per_node_and_code_and_reconverges(
    dirty: Path, tmp_path: Path
) -> None:
    """A book that exists re-enters at the checkpoint, which is the repair mode's shape.

    Round 1 finds the ungrounded `code:` citation, queues one `fix:missing-code-symbol` item
    targeting the offending node, and sends it back through the drain. The scripted repair
    lands, round 2 is clean, and the coverage re-scan closes the run. The target carries no
    round: a finding's identity is where it is and what it is, so a second round's item is
    the *same* row `record` reopens rather than a new one its dedupe cannot recognise.
    """
    agent = _Agent(dirty, repair=True)
    result = _drive(_env(tmp_path), agent)

    # Discovery was skipped entirely, and the one turn rendered the *repair* prompt —
    # `investigate.md` no longer carries repair instructions, so the stem is the assertion.
    assert agent.counts() == {"repair": 1}, agent.counts()
    assert agent.powers_for("repair") == ["medium"]
    assert agent.targets == [REPAIR], agent.targets
    args = agent.args_for("repair")[0]
    assert args["item_kind"] == "fix:missing-code-symbol", args
    # The bare code rides separately, because that is what the repair prompt dispatches on.
    assert args["item_code"] == "missing-code-symbol", args
    # The finding's own JSON travels to the turn as its context, not just the file name.
    assert "missing-code-symbol" in args["item_context"]

    assert not (dirty / REFUND).exists()
    assert result.is_webapp is False, result


def test_a_repair_that_never_lands_blocks_the_target_and_parks_on_the_gate(
    dirty: Path, tmp_path: Path
) -> None:
    """The per-target bound: one row, spent, then a human — not a fourth identical turn.

    The finding is the same one every round, so it is the same worklist row every round:
    `_repair_items` mints an identity that does not carry the round, and `record` reopens
    the row it already holds instead of appending a twin. Three reopens exhaust the
    allowance, the fourth blocks the row, and with nothing else pending the run `Await`s.

    That is the whole termination argument. The old shape asserted the defect — a fresh
    `r{n}:` row per round, unrecognisable as a repeat — and the run only ever stopped
    because the *set-level* stall counter happened to hold on a one-finding book. On a real
    book any other finding moving anywhere reset it, which is how a run reached round
    nineteen re-drilling sixteen findings it was not fixing.

    Blocking is not waiving: doctor still reports the finding, and the gate says so.
    """
    agent = _Agent(dirty, doc_status="partial", note="the symbol is gone from source")
    seen: list[str] = []
    with (
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        _drive(_env(tmp_path), agent)

    # One repair turn per attempt, and every one against the same target — no round prefix,
    # so `record`'s `(kind, target)` dedupe sees the repeat it is there to see.
    assert agent.counts()["repair"] == MAX_TARGET_ATTEMPTS, agent.counts()
    assert agent.targets == [REPAIR] * MAX_TARGET_ATTEMPTS, agent.targets

    # One row, blocked — not three rows, and not a row still being handed out.
    rows = [i for i in _worklist(dirty) if str(i["kind"]).startswith("fix:")]
    assert [(i["target"], i["status"], i["attempts"]) for i in rows] == [
        (REPAIR, "blocked", MAX_TARGET_ATTEMPTS)
    ], rows

    # The gate names the target and quotes the turn's own sentence, so the operator reads
    # what could not be repaired rather than only that something could not be.
    assert REPAIR in seen[0], seen[0]
    assert "the symbol is gone from source" in seen[0], seen[0]
    # And it says plainly that nothing was excused on the way here.
    assert "not excused" in seen[0], seen[0]

    # Nothing was repaired, which is the honest outcome the book still shows.
    assert (dirty / REFUND).exists()


def test_answering_the_blocked_gate_returns_the_target_with_a_fresh_allowance(
    dirty: Path, tmp_path: Path
) -> None:
    """The gate is a block, not an end — answering resumes the drain.

    `workflows/AGENTS.md` puts no cap on how many times a run may bounce off an operator
    gate, so `retry_blocked` clears `attempts` rather than nudging it: an operator who says
    "try again" is buying another full allowance, not one more turn. Here the operator's
    answer is followed by a repair that finally lands, and the run converges.
    """
    agent = _Agent(dirty, doc_status="partial", note="cannot reach it from the book")
    seen: list[str] = []

    def answer_then_repair(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        agent.repair = True  # whatever the operator did, the next turn can land it
        agent.doc_status = "documented"
        path.write_text("STATUS: ANSWERED\n\nFixed by hand.\n", encoding="utf-8")

    with patch.object(pyflow_driver, "wait_for_answer", answer_then_repair):
        result = _drive(_env(tmp_path), agent)

    # Three spent attempts, the gate, then one more turn that repaired it.
    assert agent.counts()["repair"] == MAX_TARGET_ATTEMPTS + 1, agent.counts()
    assert not (dirty / REFUND).exists()
    assert result.is_webapp is False, result

    # The row was returned to the drain and closed, with its counter reset on the way.
    rows = [i for i in _worklist(dirty) if str(i["kind"]).startswith("fix:")]
    assert [(i["status"], i["attempts"]) for i in rows] == [("done", 0)], rows


class _Parked(Exception):
    """Raised by the patched `wait_for_answer` to stop a run right at its `Await`.

    A budget stop always escalates now, and never terminates on its own — so a test that
    only wants to prove the gate was reached, without scripting an answer and the drain
    that follows it, stops the run here. Nothing in `drive()` catches around the
    `wait_for_answer` call, so this propagates cleanly to `pytest.raises`.
    """


def _parked_at(seen: list[str]) -> Callable[..., None]:
    """Capture the escalation body the `Await` wrote, then stop the run there."""

    def stop(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        raise _Parked

    return stop


def _answers(seen: list[str]) -> Callable[..., None]:
    """A stand-in for the operator: flip the gate's `STATUS:` line to `ANSWERED`."""

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        path.write_text("STATUS: ANSWERED\n\nCarry on.\n", encoding="utf-8")

    return answered


def test_the_item_ceiling_blocks_on_an_operator_gate_not_a_finished_book(
    unbooked: Path, tmp_path: Path
) -> None:
    """`max_items` is a safety valve for a quota-limited run, and reaching it *blocks*.

    A budget stop is not a defect, so the run parks on an `Await` instead of dying —
    `ended_at: null` abandonment was the normal ending of a real backfill campaign, and
    this is the shape that retires it. The partial book is canonicalized on the way out —
    the checkpoint runs — so what is left behind is well-formed, and the pending item
    survives in the worklist the gate's eventual answer resumes into.
    """
    agent = _Agent(
        unbooked,
        writes=FILLS,
        surfaces=[
            {"kind": "surface", "target": "acme/service.py", "context": "one"},
            {"kind": "surface", "target": "acme/other.py", "context": "two"},
        ],
    )
    seen: list[str] = []
    with (
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        _drive(_env(tmp_path), agent, max_items=1)

    # The gate says what stopped and what an answer buys — the operator reads this cold.
    assert len(seen) == 1, seen
    assert "1-item ceiling with 1 item(s) still pending" in seen[0], seen[0]
    assert "fresh allowance" in seen[0], seen[0]
    assert agent.counts()["investigate"] == 1, agent.counts()
    assert {i["target"]: i["status"] for i in _worklist(unbooked)} == {
        "acme/service.py": "done",
        "acme/other.py": "pending",
    }, _worklist(unbooked)


def test_a_refuel_answer_grants_another_allowance_and_the_drain_finishes(
    unbooked: Path, tmp_path: Path
) -> None:
    """The far side of the gate: `refuel` multiplies the ceiling instead of resetting it.

    `done_baseline` is frozen at setup, so a fresh allowance cannot come from a new
    baseline mid-run — it comes from `max_items * (refuels + 1)`. One answered gate must
    therefore finish this two-item drain under `max_items=1`, and the run must converge
    exactly as an unbounded one would.
    """
    agent = _Agent(
        unbooked,
        writes=FILLS,
        surfaces=[
            {"kind": "surface", "target": "acme/service.py", "context": "one"},
            {"kind": "surface", "target": "acme/other.py", "context": "two"},
        ],
    )
    seen: list[str] = []
    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = _drive(_env(tmp_path), agent, max_items=1)

    # Blocked exactly once: item one spent the first allowance, the answer bought the
    # second, and the drain went dry before a third was needed.
    assert len(seen) == 1, seen
    assert agent.counts()["investigate"] == 2, agent.counts()
    assert all(i["status"] == "done" for i in _worklist(unbooked)), _worklist(unbooked)
    assert result.is_webapp is False, result


# -------------------------------------------------------------------------------- resume


def test_a_run_killed_mid_investigation_resumes_on_that_item_alone(
    unbooked: Path, tmp_path: Path
) -> None:
    """The drain's state is the worklist, not the machine.

    So the checkpoint written *before* the agent turn is enough: the resumed run
    re-investigates the item that was in flight and no earlier one, because the earlier
    one is already `done` on disk and `select_item` hands out the `active` one first. This
    is the YAML's resume behavior — its `refuel` node re-entered the same way —
    reproduced without a gas tank.
    """
    first = _Agent(
        unbooked,
        writes=FILLS,
        surfaces=[
            {"kind": "surface", "target": "acme/service.py", "context": "one"},
            {"kind": "surface", "target": "acme/other.py", "context": "two"},
        ],
        explode={"acme/other.py"},
    )
    env = _env(tmp_path)
    run_dir = env.writer.run_dir
    with pytest.raises(RuntimeError, match="killed while investigating acme/other.py"):
        _drive(env, first)

    assert first.targets == ["acme/service.py", "acme/other.py"], first.targets
    assert {i["target"]: i["status"] for i in _worklist(unbooked)} == {
        "acme/service.py": "done",
        "acme/other.py": "active",
    }, _worklist(unbooked)

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "investigate", resume
    assert resume.params["item_target"] == "acme/other.py", resume.params
    assert resume.flow == "OkfBuilder", resume

    second = _Agent(unbooked, writes=FILLS)
    result = drive(
        OkfBuilder(**resume.inputs),
        replace(_env(tmp_path, run_dir=run_dir), agent_runner=StubRunner(second)),
        resume,
    )

    # Nothing upstream re-ran: not the enumeration, not the first item.
    assert second.counts() == {"investigate": 1}, second.counts()
    assert second.targets == ["acme/other.py"], second.targets
    assert all(i["status"] == "done" for i in _worklist(unbooked)), _worklist(unbooked)
    assert result.is_webapp is False, result


# -------------------------------------------------------------------------------- labels


def test_the_labels_name_the_service_and_the_item(unbooked: Path, tmp_path: Path) -> None:
    """The YAML's three `labels:` templates, as one method reading `self.output(...)`.

    Before the first pick there is no output to read, and that is the normal state of a
    run's first transitions — the guard against `NodeNotRunError` is what makes those
    service-only transitions rather than crashed ones.
    """
    seen: list[dict[str, str]] = []
    real_rebase = pyflow_activity.ActivityLog.rebase

    def capture(self: Any, labels: dict[str, str]) -> Any:
        seen.append(dict(labels))
        return real_rebase(self, labels)

    with patch.object(pyflow_activity.ActivityLog, "rebase", capture):
        _drive(_env(tmp_path), _Agent(unbooked, writes=FILLS))

    assert seen[0] == {"service": SERVICE}, seen[0]
    stamped = [labels for labels in seen if labels.get("work_id")]
    assert stamped, seen
    assert {labels["work_id"] for labels in stamped} == {"acme/service.py"}, stamped
    # `progress` is the worklist's own count, so a dashboard can read it without knowing
    # anything about OKF.
    assert any(labels.get("progress") for labels in stamped), stamped
    # Unprefixed, unlike the YAML engine's `wf.work_id`.
    assert not any(k.startswith("wf.") for labels in seen for k in labels), seen


# ------------------------------------------------------------------- adjudication

#: A screen whose two buttons share a role and an accessible name — the collision class
#: of finding. Doctor raises `ambiguous-locator` on each node, and the book alone cannot
#: say whether the book or the source is the side that is wrong.
COLLIDING_SCREEN = """\
---
type: screen
slug: dashboard
title: Dashboard
---
# Dashboard

- route: `/dashboard`
- entry: app root
- requires: none
- params: none

## Components

### save-button
- selector: `.btn-save`
- role: button
- name: Save
- verify: created(subject="draft")

### footer-save-button
- selector: `.footer .btn-save`
- role: button
- name: Save
- verify: created(subject="draft")
"""
DASHBOARD = f"{BOOK}/screens/dashboard.md"


def _blocked_rows(repo: Path) -> list[dict[str, Any]]:
    return [i for i in _worklist(repo) if str(i["kind"]).startswith("fix:")]


def test_a_book_verdict_returns_the_row_to_the_drain_with_the_chain(
    dirty: Path, tmp_path: Path
) -> None:
    """`book`: the source is right and the book misdescribes it, so the row is not a
    gate — it is one more repair, with the adjudicator's chain as the fact the repair
    turn was missing. No operator is asked."""
    # The chain reaches the next repair turn as context, and that turn lands it.
    agent = _Agent(
        dirty, doc_status="partial", note="cannot tell from the book", verdict="book",
        lands_on="adjudication",
    )
    seen: list[str] = []
    with patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        result = _drive(_env(tmp_path), agent)

    assert seen == [], seen  # never parked
    assert agent.counts()["adjudicate"] == 1, agent.counts()
    assert agent.counts()["repair"] == MAX_TARGET_ATTEMPTS + 1, agent.counts()
    assert not (dirty / REFUND).exists()
    assert result.is_webapp is False, result
    rows = _blocked_rows(dirty)
    assert [(i["status"], i["attempts"], i["verdict"]) for i in rows] == [("done", 0, "book")]
    assert "side: book" in json.loads(rows[0]["context"])["adjudication"]


def test_a_code_verdict_files_a_seed_and_records_the_defect_on_the_nodes(
    booked: Path, tmp_path: Path, write: Callable[[Path, str], Path]
) -> None:
    """`code` on a UI node: the source is the side at fault, so the book keeps saying
    what it says and carries the record — a seed in the invariant epic (no story covers
    the nodes) and a `known-defect:` bullet naming it on each node. Doctor takes the
    finding back while the seed is open, and the run converges without a gate."""
    from ostler import Ostler

    from workhorse_workflows.okf_builder.main.nodes.adjudicate import INVARIANT_EPIC

    write(booked / DASHBOARD, COLLIDING_SCREEN)
    subprocess.run(["git", "add", "-A"], cwd=booked, check=True)
    subprocess.run(["git", "commit", "-qm", "a colliding screen"], cwd=booked, check=True)

    agent = _Agent(booked, doc_status="partial", note="both buttons are in the source", verdict="code")
    seen: list[str] = []
    with patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        _drive(_env(tmp_path), agent)

    assert seen == [], seen
    # One finding per node, so one adjudication per node — each with its own seed.
    assert agent.counts()["adjudicate"] == 2, agent.counts()
    rows = _blocked_rows(booked)
    assert {(i["status"], i["doc_status"], i["verdict"]) for i in rows} == {
        ("done", "code-defect", "code")
    }, rows
    seeds = sorted(str(i["seed"]) for i in rows)
    assert len(set(seeds)) == 2, seeds

    text = (booked / DASHBOARD).read_text(encoding="utf-8")
    for seed in seeds:
        assert f"- known-defect: {seed} ambiguous-locator — " in text, text
    graph = Ostler(booked).graph
    epic = next(e for e in graph.epics if e.name.endswith(INVARIANT_EPIC))
    assert sorted(s.id for s in epic.seeds) == seeds, epic.seeds
    assert all(s.status == "backlog" for s in epic.seeds)
    # One bullet under each heading, not two under one: the finding is raised per node and
    # the record sits on the node it excuses.
    head, _, tail = text.partition("### footer-save-button")
    assert head.count("- known-defect:") == 1 and tail.count("- known-defect:") == 1, text


def test_a_story_verdict_with_no_story_parks_with_the_chain_on_the_gate(
    dirty: Path, tmp_path: Path
) -> None:
    """`story`: the intent itself is in conflict, which is the operator's to rewrite. The
    row stays blocked exactly as the repair turn left it, and the gate prints the verdict
    and the chain beside the turn's own sentence — nothing is excused, and the operator
    reads what was decided rather than only that something could not be repaired."""
    agent = _Agent(dirty, doc_status="partial", note="the symbol is gone", verdict="story")
    seen: list[str] = []
    with (
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        _drive(_env(tmp_path), agent)

    assert agent.counts()["adjudicate"] == 1, agent.counts()
    rows = _blocked_rows(dirty)
    assert [(i["status"], i["verdict"], i["blocked_reason"]) for i in rows] == [
        ("blocked", "story", "the symbol is gone")
    ], rows
    assert "adjudicated `story`" in seen[0], seen[0]
    assert "side: story" in seen[0], seen[0]
    assert "the symbol is gone" in seen[0], seen[0]
    assert "not excused" in seen[0], seen[0]


def test_every_okf_builder_transition_says_why_it_is_taken() -> None:
    """The diagram's edge labels and the run log's `— why` come from `.because(...)` on
    each transition; a transition landed without one reads as bare plumbing on both."""
    for flow in (OkfBuilder, WalkthroughWeb):
        unlabelled = [
            f"{flow.__name__}.{node.name} -> {edge.target or 'END'}"
            for node in state_graph(flow).states
            for edge in node.edges
            if not edge.reason
        ]
        assert not unlabelled, f"transitions with no reason: {unlabelled}"
