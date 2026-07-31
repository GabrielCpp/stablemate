"""End-to-end drives of the okf-builder workflow (`okf_builder/workflow.py`).

Nothing is stubbed except the agent turn. `prepare`, `select_item`, `record`,
`checkpoint_book`, `auto_waive`, `inventory_source`, `compute_coverage` and
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

* the drain: seed, pick, investigate, record, re-pick, and the dry exit into the
  convergence gate — with `rnd`/`rescan`/`stall`/`signature` riding through five states
  as parameters where the YAML kept them in one run-global `vars` namespace. The bug that
  namespace caused (`round` and `rescan_round` sharing a counter) cannot be reproduced
  here because it cannot be *written* here, but the round numbering it corrupted is
  asserted directly.
* the two arms of `checkpoint`: a dirty book queues one repair item per offending file and
  re-enters the drain; a repaired book converges to the coverage re-scan.
* `MAX_STALL_ROUNDS` and the `waive` hand-off, including its honest failure on a finding
  that is not auto-waivable — the YAML could only name a `type: fail` node here.
* the `max_items` valve, which is a **failure** and not a quiet success: a partial book
  must not read as a finished one.
* `handoff` into `walkthrough-web`, whose own `detect_webapp` gates it — a service with no
  documented screen surface is walked by a no-op, and the run's value is the sub-flow's.
* resume, which is why the checkpoint lands before the agent turn: a run killed while
  investigating re-investigates that item and no earlier one.
* `labels()`, which reads `self.output(select_item)` and must not crash before the first
  pick.
"""
from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from _fakes import StubRunner
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow import activity as pyflow_activity
from workhorse.pyflow.driver import drive, read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows import okf_builder
from workhorse_workflows.okf_builder.shared import paths
from workhorse_workflows.okf_builder.workflow import MAX_STALL_ROUNDS, OkfBuilder

SERVICE = "acme"
BOOK = f"docs/features/{SERVICE}"
REFUND = f"{BOOK}/concepts/refund.md"

#: What the scripted enumeration hands back by default: one surface, whose investigation
#: this book does not actually need — the fixture is already complete, which is what makes
#: the coverage verdict below a statement about the join rather than about the stub.
SURFACE = {"kind": "surface", "target": "acme/service.py", "context": "the billing entry"}


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
    ) -> None:
        self.repo = repo
        self.surfaces = [dict(SURFACE)] if surfaces is None else surfaces
        self.spawn = dict(spawn or {})
        self.repair = repair
        self.explode = set(explode or ())
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []
        self.cwds: list[str] = []
        self.targets: list[str] = []

    # -- the seam ---------------------------------------------------------

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        self.cwds.append(str(node.cwd))
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        return f"(scripted) {node.prompt}", handler(data, self.counts()[stem])

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]

    # -- the turns --------------------------------------------------------

    def _enumerate_surfaces(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"discovered": self.surfaces}

    def _investigate(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        target = str(data["item_target"])
        self.targets.append(target)
        if target in self.explode:
            raise RuntimeError(f"killed while investigating {target}")
        if self.repair and data["item_kind"] in {"fixup", "backfill"}:
            # A fixup target is `r<round>:<path>`; the repair the doctor finding calls for
            # is "stop citing a symbol that does not exist", and deleting the doc is the
            # smallest edit that does it.
            doc = self.repo / target.split(":", 1)[1]
            doc.unlink(missing_ok=True)
        return {"doc_status": "documented", "discovered": self.spawn.get(target, [])}

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


# ---------------------------------------------------------------------------- the drain


def test_a_complete_book_drains_converges_and_skips_the_walk(
    booked: Path, tmp_path: Path, read_json: Callable[[Path], Any]
) -> None:
    """The straight-through run: seed one surface, investigate it, converge, hand off.

    Every artifact below is the YAML's artifact: the worklist with its item closed, the
    source inventory walked from `acme/`, and the coverage join written into the book. The
    verdict is arithmetic — one module and one symbol, both cited by `charge.md` — so the
    fact that the scripted turn wrote nothing is exactly the point.
    """
    agent = _Agent(booked)
    result = _drive(_env(tmp_path), agent)

    assert agent.counts() == {"enumerate-surfaces": 1, "investigate": 1}, agent.counts()

    # The drain closed what it opened.
    items = _worklist(booked)
    assert [(i["kind"], i["target"], i["status"]) for i in items] == [
        ("surface", "acme/service.py", "done")
    ], items

    # The coverage join ran for real and is complete: 2 units, 2 covered.
    coverage = read_json(booked / BOOK / "coverage.json")
    assert coverage["total"] == 2, coverage
    assert coverage["covered"] == 2, coverage
    inventory = read_json(paths.source_inventory_path(paths.worklist_path(booked, SERVICE)))
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


def test_an_investigation_opens_the_items_it_reveals(booked: Path, tmp_path: Path) -> None:
    """The drain is a crawl, not a list: `record_item` writes back what the turn found.

    That write is its own state precisely so a crash mid-turn re-investigates rather than
    closing an item nothing documented — which is what the resume test below drives.
    """
    agent = _Agent(
        booked,
        spawn={
            "acme/service.py": [
                {"kind": "layer", "target": "acme/service.py::charge", "context": "the handler"}
            ]
        },
    )
    _drive(_env(tmp_path), agent)

    assert agent.counts()["investigate"] == 2, agent.counts()
    assert agent.targets == ["acme/service.py", "acme/service.py::charge"], agent.targets
    assert all(i["status"] == "done" for i in _worklist(booked)), _worklist(booked)


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


def test_a_dirty_doctor_queues_one_repair_per_file_and_reconverges(
    dirty: Path, tmp_path: Path
) -> None:
    """`recheck_only` re-enters at the checkpoint, which is the repair mode's whole shape.

    Round 1 finds the ungrounded `code:` citation, queues one `fixup` item targeting the
    offending file, and sends it back through the drain. The scripted repair lands, round
    2 is clean, and the coverage re-scan closes the run. The `r1:` prefix on the target is
    what keeps a second round's item distinct from the first's under `record`'s dedupe.
    """
    agent = _Agent(dirty, repair=True)
    result = _drive(_env(tmp_path), agent, recheck_only=True)

    # Discovery was skipped entirely: the only turn was the repair.
    assert agent.counts() == {"investigate": 1}, agent.counts()
    assert agent.targets == [f"r1:{REFUND}"], agent.targets
    assert agent.args_for("investigate")[0]["item_kind"] == "fixup", agent.args_for("investigate")
    # The finding's own JSON travels to the turn as its context, not just the file name.
    assert "missing-code-symbol" in agent.args_for("investigate")[0]["item_context"]

    assert not (dirty / REFUND).exists()
    assert result.is_webapp is False, result


def test_a_repair_that_never_lands_stops_the_run_rather_than_looping(
    dirty: Path, tmp_path: Path
) -> None:
    """The stall bound, and the honest end when `auto_waive` cannot take the finding.

    Three rounds of an unchanged finding set is a repair that cannot land in the book, so
    the fourth hands it to `auto_waive` — which finds a `missing-code-symbol`, a code
    outside `AUTO_WAIVABLE`, and the run fails saying so. Papering it over with a waiver
    would make an unfixed book report as converged.
    """
    agent = _Agent(dirty)  # repair=False: the turn documents nothing.
    with pytest.raises(WorkflowFailed, match="neither doc-repairable nor auto-waivable"):
        _drive(_env(tmp_path), agent, recheck_only=True)

    # One investigation per tolerated round, then the give-up arm instead of a fourth.
    assert agent.counts()["investigate"] == MAX_STALL_ROUNDS, agent.counts()
    # Each round's item is distinct, which is what let the loop run at all.
    assert agent.targets == [f"r{n}:{REFUND}" for n in (1, 2, 3)], agent.targets
    assert (dirty / REFUND).exists()


def test_the_item_ceiling_is_a_failure_and_not_a_finished_book(
    booked: Path, tmp_path: Path
) -> None:
    """`max_items` is a safety valve for a quota-limited run, and reaching it is a failure.

    The partial book is canonicalized on the way out — the checkpoint runs — so what is
    left behind is well-formed, and the pending item survives for a resume that gets its
    own allowance off a fresh `done_baseline`.
    """
    agent = _Agent(
        booked,
        surfaces=[
            {"kind": "surface", "target": "acme/service.py", "context": "one"},
            {"kind": "surface", "target": "acme/other.py", "context": "two"},
        ],
    )
    with pytest.raises(WorkflowFailed, match="1-item ceiling with 1 item"):
        _drive(_env(tmp_path), agent, max_items=1)

    assert agent.counts()["investigate"] == 1, agent.counts()
    assert {i["target"]: i["status"] for i in _worklist(booked)} == {
        "acme/service.py": "done",
        "acme/other.py": "pending",
    }, _worklist(booked)


# -------------------------------------------------------------------------------- resume


def test_a_run_killed_mid_investigation_resumes_on_that_item_alone(
    booked: Path, tmp_path: Path
) -> None:
    """The drain's state is the worklist, not the machine.

    So the checkpoint written *before* the agent turn is enough: the resumed run
    re-investigates the item that was in flight and no earlier one, because the earlier
    one is already `done` on disk and `select_item` hands out the `active` one first. This
    is the YAML's resume behavior — its `refuel` node re-entered the same way —
    reproduced without a gas tank.
    """
    first = _Agent(
        booked,
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
    assert {i["target"]: i["status"] for i in _worklist(booked)} == {
        "acme/service.py": "done",
        "acme/other.py": "active",
    }, _worklist(booked)

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "investigate", resume
    assert resume.params["item_target"] == "acme/other.py", resume.params
    assert resume.flow == "OkfBuilder", resume

    second = _Agent(booked)
    result = drive(
        OkfBuilder(**resume.inputs),
        replace(_env(tmp_path, run_dir=run_dir), agent_runner=StubRunner(second)),
        resume,
    )

    # Nothing upstream re-ran: not the enumeration, not the first item.
    assert second.counts() == {"investigate": 1}, second.counts()
    assert second.targets == ["acme/other.py"], second.targets
    assert all(i["status"] == "done" for i in _worklist(booked)), _worklist(booked)
    assert result.is_webapp is False, result


# -------------------------------------------------------------------------------- labels


def test_the_labels_name_the_service_and_the_item(booked: Path, tmp_path: Path) -> None:
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
        _drive(_env(tmp_path), _Agent(booked))

    assert seen[0] == {"service": SERVICE}, seen[0]
    stamped = [labels for labels in seen if labels.get("work_id")]
    assert stamped, seen
    assert {labels["work_id"] for labels in stamped} == {"acme/service.py"}, stamped
    # `progress` is the worklist's own count, so a dashboard can read it without knowing
    # anything about OKF.
    assert any(labels.get("progress") for labels in stamped), stamped
    # Unprefixed, unlike the YAML engine's `wf.work_id`.
    assert not any(k.startswith("wf.") for labels in seen for k in labels), seen
