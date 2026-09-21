"""End-to-end drives of the okf-builder workflow (`okf_builder/workflow.py`)."""
from __future__ import annotations

import json
import shutil
import subprocess
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from ostler import stamp as stamp_mod
from git import Repo
from _fakes import StubRunner
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow import activity as pyflow_activity
from workhorse.pyflow.graph import state_graph
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import drive, read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import PyflowCheckpoint, parse_checkpoint

from workhorse_workflows import okf_builder
from workhorse_workflows.okf_builder.main.flow import investigation_power, repair_power
from workhorse_workflows.okf_builder.shared import paths
from workhorse_workflows.okf_builder.shared.worklist import MAX_TARGET_ATTEMPTS
from workhorse_workflows.okf_builder.workflow import OkfBuilder

SERVICE = "acme"
BOOK = f"docs/features/{SERVICE}"
REFUND = f"{BOOK}/concepts/refund.md"
REPAIR = f"{REFUND}#{REFUND}#missing-code-symbol"

SURFACE = {"kind": "surface", "target": "acme/service.py", "context": "the billing entry"}

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




class _Agent:
    """A scripted stand-in for the workflow's four agent turns."""

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
        commit_message: str = "",
    ) -> None:
        self.repo = repo
        self.surfaces = [dict(SURFACE)] if surfaces is None else surfaces
        self.spawn = dict(spawn or {})
        self.writes = dict(writes or {})
        self.repair = repair
        self.doc_status = doc_status
        self.note = note
        self.verdict = verdict
        self.lands_on = lands_on
        self.commit_message = commit_message
        self.explode = set(explode or ())
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []
        self.cwds: list[str] = []
        self.targets: list[str] = []
        self.add_dirs: list[list[str]] = []
        self.powers: list[str | None] = []


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
            doc = self.repo / target.split("#")[0]
            doc.unlink(missing_ok=True)
        status = self.doc_status if str(data["item_kind"]).startswith("fix:") else "documented"
        return {
            "doc_status": status,
            "note": self.note if status != "documented" else "",
            "discovered": self.spawn.get(target, []),
            "commit_message": self.commit_message,
        }

    _repair = _investigate

    def _adjudicate(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "chain": f"1. why: {data['item_code']} stands on {data['nodes']}; "
            f"2. cause: scripted; 3. side: {self.verdict}",
            "seed_summary": "the source leaves it unnamed" if self.verdict == "code" else "",
        }

    def _recheck_coverage(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"needs_journeys": False, "discovered": list(self.surfaces)}




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


def _run_worklist_path(env: RunEnv) -> Path:
    checkpoint = parse_checkpoint((env.run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    assert isinstance(checkpoint, PyflowCheckpoint)
    return Path(checkpoint.ctx["worklist_path"])




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




def test_an_empty_book_is_filled_top_down_from_the_code_s_surfaces(
    unbooked: Path, tmp_path: Path, read_json: Callable[[Path], Any]
) -> None:
    """The first fill: seed one surface, document it, converge, hand off."""
    agent = _Agent(unbooked, writes=FILLS)
    env = _env(tmp_path)
    result = _drive(env, agent)

    assert agent.counts() == {"recheck-coverage": 1, "investigate": 1}, agent.counts()
    assert agent.powers == ["medium", "low"]

    items = _worklist(unbooked)
    assert [(i["kind"], i["target"], i["status"]) for i in items] == [
        ("surface", "acme/service.py", "done")
    ], items

    coverage = read_json(unbooked / BOOK / "coverage.json")
    assert coverage["total"] == 2, coverage
    assert coverage["covered"] == 2, coverage
    inventory = read_json(paths.source_inventory_path(_run_worklist_path(env)))
    assert {u["code"] for u in inventory["units"]} == {
        "acme/service.py",
        "acme/service.py::charge",
    }, inventory

    assert agent.counts()["recheck-coverage"] == 1, agent.counts()

    assert result["reports"] == [], result


def test_a_book_that_exists_is_reconciled_to_head_rather_than_re_enumerated(
    booked: Path, tmp_path: Path, read_json: Callable[[Path], Any]
) -> None:
    """The other entry, and the reason `recheck_only` is retired."""
    agent = _Agent(booked)
    result = _drive(_env(tmp_path), agent)

    assert agent.counts() == {}, agent.counts()
    assert _worklist(booked) == [], _worklist(booked)
    coverage = read_json(booked / BOOK / "coverage.json")
    assert (coverage["covered"], coverage["total"]) == (2, 2), coverage
    assert result["reports"] == [], result


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
    """The successful tail commits the book, and nothing beside that book."""
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

    assert result["reports"] == [], result
    assert message == expected_message
    assert committed
    assert all(path.startswith(f"{BOOK}/") for path in committed), committed
    assert status == "?? notes.txt\n"


def test_the_build_scratch_ignores_itself_so_a_commit_all_cannot_eat_it(
    booked: Path, tmp_path: Path
) -> None:
    """`.agents/okf-build/` carries its own `.gitignore`, from the first run onward."""
    _drive(_env(tmp_path), _Agent(booked))

    assert (booked / paths.BUILD_DIRNAME / ".gitignore").read_text() == "*\n"

    stray = booked / paths.BUILD_DIRNAME / "acme.worklist.json.source.json"
    stray.write_text("{}")
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=booked, capture_output=True, text=True, check=True
    ).stdout
    assert paths.BUILD_DIRNAME not in status, status


def test_an_investigation_opens_the_items_it_reveals(unbooked: Path, tmp_path: Path) -> None:
    """The drain is a crawl, not a list: `record_item` writes back what the turn found."""
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
    """`prepare` carries its failure as data and `start` is where it becomes a failed run."""
    agent = _Agent(booked)
    with pytest.raises(WorkflowFailed, match="is not a directory"):
        _drive(_env(tmp_path), agent, source_path="nope")

    assert agent.counts() == {}, agent.counts()




def test_a_dirty_doctor_queues_one_repair_per_node_and_code_and_reconverges(
    dirty: Path, tmp_path: Path
) -> None:
    """A book that exists re-enters at the checkpoint, which is the repair mode's shape."""
    agent = _Agent(dirty, repair=True)
    result = _drive(_env(tmp_path), agent)

    assert agent.counts() == {"repair": 1}, agent.counts()
    assert agent.powers_for("repair") == ["medium"]
    assert agent.targets == [REPAIR], agent.targets
    args = agent.args_for("repair")[0]
    assert args["item_kind"] == "fix:missing-code-symbol", args
    assert args["item_code"] == "missing-code-symbol", args
    assert "missing-code-symbol" in args["item_context"]
    baseline = Path(args["baseline"])
    assert not baseline.is_relative_to(dirty), baseline
    assert (baseline / Path(REFUND).relative_to(BOOK)).is_file(), sorted(baseline.rglob("*"))

    assert not (dirty / REFUND).exists()
    assert result["reports"] == [], result


def test_a_turn_commits_its_book_edits_under_its_own_subject_past_a_rejecting_hook(
    dirty: Path, tmp_path: Path
) -> None:
    """Each turn lands as its own commit, so `HEAD` is where the next turn starts."""
    hook = dirty / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    before = Repo(dirty).head.commit.hexsha
    subject = "docs(acme): drop the refund concept citing no symbol"

    _drive(_env(tmp_path), _Agent(dirty, repair=True, commit_message=subject))

    repo = Repo(dirty)
    subjects = [c.summary for c in repo.iter_commits(f"{before}..HEAD")]
    assert subject in subjects, subjects
    turn = next(c for c in repo.iter_commits(f"{before}..HEAD") if c.summary == subject)
    assert f"{BOOK}/concepts/refund.md" not in repo.git.ls_tree("-r", "--name-only", turn.hexsha)
    assert f"{BOOK}/concepts/refund.md" in repo.git.ls_tree("-r", "--name-only", turn.parents[0].hexsha)


def test_a_repair_that_never_lands_blocks_the_target_and_parks_on_the_gate(
    dirty: Path, tmp_path: Path
) -> None:
    """The per-target bound: one row, spent, then a human — not a fourth identical turn."""
    agent = _Agent(dirty, doc_status="partial", note="the symbol is gone from source")
    seen: list[str] = []
    with (
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        _drive(_env(tmp_path), agent)

    assert agent.counts()["repair"] == MAX_TARGET_ATTEMPTS, agent.counts()
    assert agent.targets == [REPAIR] * MAX_TARGET_ATTEMPTS, agent.targets

    rows = [i for i in _worklist(dirty) if str(i["kind"]).startswith("fix:")]
    assert [(i["target"], i["status"], i["attempts"]) for i in rows] == [
        (REPAIR, "blocked", MAX_TARGET_ATTEMPTS)
    ], rows

    assert REPAIR in seen[0], seen[0]
    assert "the symbol is gone from source" in seen[0], seen[0]
    assert "not excused" in seen[0], seen[0]

    assert (dirty / REFUND).exists()


def test_answering_the_blocked_gate_returns_the_target_with_a_fresh_allowance(
    dirty: Path, tmp_path: Path
) -> None:
    """The gate is a block, not an end — answering resumes the drain."""
    agent = _Agent(dirty, doc_status="partial", note="cannot reach it from the book")
    seen: list[str] = []

    def answer_then_repair(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        agent.repair = True
        agent.doc_status = "documented"
        path.write_text("STATUS: ANSWERED\n\nFixed by hand.\n", encoding="utf-8")

    with patch.object(pyflow_driver, "wait_for_answer", answer_then_repair):
        result = _drive(_env(tmp_path), agent)

    assert agent.counts()["repair"] == MAX_TARGET_ATTEMPTS + 1, agent.counts()
    assert not (dirty / REFUND).exists()
    assert result["reports"] == [], result

    rows = [i for i in _worklist(dirty) if str(i["kind"]).startswith("fix:")]
    assert [(i["status"], i["attempts"]) for i in rows] == [("done", 0)], rows


DRIFTED_SOURCE = '''"""The billing service."""


def charge(amount):
    """Charge an amount, in cents."""
    return amount * 100
'''


def _stamp_charge(repo: Path) -> None:
    """Stamp `charge`'s citation with the digest of the file it currently cites."""
    result = stamp_mod.stamp_page(
        repo, paths.features_root(repo, SERVICE), f"{BOOK}/concepts/charge.md",
    )
    assert not result.unresolved, result.unresolved


def _park_stale_citation(repo: Path) -> None:
    """A `fix:stale-citation` row for `charge` that has already spent its attempts."""
    wl = paths.worklist_path(repo, SERVICE)
    data = json.loads(wl.read_text())
    node = f"{BOOK}/concepts/charge.md"
    data["items"].append({
        "kind": "fix:stale-citation", "target": "acme/service.py",
        "context": json.dumps({
            "code": "stale-citation", "grounded": True, "file": "acme/service.py",
            "nodes": [node], "citations": {node: "acme/service.py::charge"},
        }),
        "status": "blocked", "attempts": MAX_TARGET_ATTEMPTS,
        "blocked_reason": "the last turn reported `partial` and the finding still stands",
    })
    wl.write_text(json.dumps(data))


def test_a_blocked_regrounding_row_with_nothing_uncovered_parks_on_the_gate(
    booked: Path, tmp_path: Path
) -> None:
    """A requeue that lands on a blocked row is dropped by `record`, on purpose — so the state around it must not hand the drain an empty worklist and let the re-scan lap the same join until its round cap."""
    _drive(_env(tmp_path), _Agent(booked))
    _stamp_charge(booked)
    (booked / "acme/service.py").write_text(DRIFTED_SOURCE, encoding="utf-8")
    _park_stale_citation(booked)
    agent = _Agent(booked)
    seen: list[str] = []
    with (
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        _drive(_env(tmp_path / "again"), agent)

    assert len(seen) == 1, seen
    assert "cannot re-ground 1 file(s)" in seen[0], seen[0]
    assert "acme/service.py" in seen[0], seen[0]
    assert "recheck-coverage" not in agent.counts(), agent.counts()
    rows = [i for i in _worklist(booked) if i["kind"] == "fix:stale-citation"]
    assert [(i["status"], i["attempts"]) for i in rows] == [("blocked", MAX_TARGET_ATTEMPTS)]


def test_a_blocked_regrounding_row_does_not_starve_the_uncovered_units(
    booked: Path, tmp_path: Path
) -> None:
    """The other arm: an uncovered unit still gets its adjudication turn while the re-grounding row stays blocked, instead of the recheck being skipped every round."""
    _drive(_env(tmp_path), _Agent(booked))
    (booked / "acme/service.py").write_text(
        DRIFTED_SOURCE + "\n\ndef refund(amount):\n    return -amount\n", encoding="utf-8"
    )
    _park_stale_citation(booked)
    agent = _Agent(booked)
    seen: list[str] = []
    with (
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        _drive(_env(tmp_path / "again"), agent)

    assert agent.counts()["recheck-coverage"] >= 1, agent.counts()
    assert len(seen) == 1, seen


def test_the_rescan_cap_gate_answers_through_the_unblock() -> None:
    """The cap gate's answer must go through `retry_blocked`: a fresh round allowance on a worklist whose rows are still blocked re-scans the same book six more times."""
    (checkpoint,) = [s for s in state_graph(OkfBuilder).states if s.name == "checkpoint"]
    (edge,) = [e for e in checkpoint.edges if "re-scan cap hit" in (e.reason or "")]
    assert edge.target == "retry_blocked", edge


class _Parked(Exception):
    """Raised by the patched `wait_for_answer` to stop a run right at its `Await`."""


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
    """`max_items` is a safety valve for a quota-limited run, and reaching it *blocks*."""
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
    """The far side of the gate: `refuel` multiplies the ceiling instead of resetting it."""
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

    assert len(seen) == 1, seen
    assert agent.counts()["investigate"] == 2, agent.counts()
    assert all(i["status"] == "done" for i in _worklist(unbooked)), _worklist(unbooked)
    assert result["reports"] == [], result




def test_a_run_killed_mid_investigation_resumes_on_that_item_alone(
    unbooked: Path, tmp_path: Path
) -> None:
    """The drain's state is the worklist, not the machine."""
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

    assert second.counts() == {"investigate": 1}, second.counts()
    assert second.targets == ["acme/other.py"], second.targets
    assert all(i["status"] == "done" for i in _worklist(unbooked)), _worklist(unbooked)
    assert result["reports"] == [], result




def test_the_labels_name_the_service_and_the_item(unbooked: Path, tmp_path: Path) -> None:
    """The YAML's three `labels:` templates, as one method reading `self.output(...)`."""
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
    assert any(labels.get("progress") for labels in stamped), stamped
    assert not any(k.startswith("wf.") for labels in seen for k in labels), seen



COLLIDING_SCREEN = """\
---
type: screen
slug: dashboard
title: Dashboard
---
# Dashboard

- route: `/dashboard`
- entry: `/dashboard`
- requires: none
- params: none

## Components

### save-button
- selector: `button.btn-save`
- role: button
- name: Save
- verify: created(subject="draft")

### footer-save-button
- selector: `button.btn-save`
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
    """`book`: the source is right and the book misdescribes it, so the row is not a gate — it is one more repair, with the adjudicator's chain as the fact the repair turn was missing."""
    agent = _Agent(
        dirty, doc_status="partial", note="cannot tell from the book", verdict="book",
        lands_on="adjudication",
    )
    seen: list[str] = []
    with patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        result = _drive(_env(tmp_path), agent)

    assert seen == [], seen
    assert agent.counts()["adjudicate"] == 1, agent.counts()
    assert agent.counts()["repair"] == MAX_TARGET_ATTEMPTS + 1, agent.counts()
    assert not (dirty / REFUND).exists()
    assert result["reports"] == [], result
    rows = _blocked_rows(dirty)
    assert [(i["status"], i["attempts"], i["verdict"]) for i in rows] == [("done", 0, "book")]
    assert "side: book" in json.loads(rows[0]["context"])["adjudication"]


def test_a_code_verdict_files_a_seed_and_records_the_defect_on_the_nodes(
    booked: Path, tmp_path: Path, write: Callable[[Path, str], Path]
) -> None:
    """`code` on a UI node: the source is the side at fault, so the book keeps saying what it says and carries the record — a seed in the invariant epic (no story covers the nodes) and a `known-defect:` bullet naming it on each node."""
    from ostler import Ostler

    from workhorse_workflows.okf_builder.main.nodes.adjudicate import INVARIANT_EPIC

    write(booked / DASHBOARD, COLLIDING_SCREEN)
    subprocess.run(["git", "add", "-A"], cwd=booked, check=True)
    subprocess.run(["git", "commit", "-qm", "a colliding screen"], cwd=booked, check=True)

    agent = _Agent(booked, doc_status="partial", note="both buttons are in the source", verdict="code")
    seen: list[str] = []
    with patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)), pytest.raises(_Parked):
        _drive(_env(tmp_path), agent)
    assert seen and "live audit" in seen[0], seen

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
    head, _, tail = text.partition("### footer-save-button")
    assert head.count("- known-defect:") == 1 and tail.count("- known-defect:") == 1, text


class _CapturedHandoff(Exception):
    """Raised in place of actually driving `LiveAudit`, carrying what it was called with."""

    def __init__(self, kwargs: dict[str, Any]) -> None:
        super().__init__("captured live-audit handoff")
        self.kwargs = kwargs


def _ctx(env: RunEnv) -> dict[str, Any]:
    checkpoint = parse_checkpoint((env.run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    assert isinstance(checkpoint, PyflowCheckpoint)
    return checkpoint.ctx


def test_semantic_audit_hands_live_audit_the_checkout_not_the_source_subtree(
    booked: Path, tmp_path: Path
) -> None:
    """`semantic_audit` must call `handoff(LiveAudit, docs_path=repo_root, repo_dir=repo_root)`, not `repo_dir=source_root` — the regression that blocked every multi-surface book's audit with a "separate docs repo" note the checkout never earned."""
    from workhorse_workflows.okf_builder.main import flow as main_flow

    def _capture(**kwargs: Any) -> Any:
        raise _CapturedHandoff(kwargs)

    env = _env(tmp_path)
    agent = _Agent(booked)
    with (
        patch.object(main_flow, "LiveAudit", _capture),
        pytest.raises(_CapturedHandoff) as excinfo,
    ):
        _drive(env, agent)

    ctx = _ctx(env)
    assert ctx["repo_root"] != ctx["source_root"], ctx
    kwargs = excinfo.value.kwargs
    assert kwargs["repo_dir"] == ctx["repo_root"], kwargs
    assert kwargs["docs_path"] == ctx["repo_root"], kwargs


def test_a_story_verdict_with_no_story_parks_with_the_chain_on_the_gate(
    dirty: Path, tmp_path: Path
) -> None:
    """`story`: the intent itself is in conflict, which is the operator's to rewrite."""
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


def test_an_adjudication_that_names_no_side_parks_instead_of_killing_the_run(
    dirty: Path, tmp_path: Path
) -> None:
    """A turn that generates nothing is a block, not a death."""
    agent = _Agent(dirty, doc_status="partial", note="the symbol is gone", verdict="")
    seen: list[str] = []
    with (
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        _drive(_env(tmp_path), agent)

    assert seen, "the run parked rather than dying"
    assert "could not adjudicate" in seen[0], seen[0]
    rows = _blocked_rows(dirty)
    assert [(i["status"], i.get("verdict", "")) for i in rows] == [("blocked", "")], rows


def test_every_okf_builder_transition_says_why_it_is_taken() -> None:
    """The diagram's edge labels and the run log's `— why` come from `.because(...)` on each transition; a transition landed without one reads as bare plumbing on both."""
    unlabelled = [
        f"{OkfBuilder.__name__}.{node.name} -> {edge.target or 'END'}"
        for node in state_graph(OkfBuilder).states
        for edge in node.edges
        if not edge.reason
    ]
    assert not unlabelled, f"transitions with no reason: {unlabelled}"



class _ScratchCleanupAgent(_Agent):
    def _investigate(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if nth == 1:
            shutil.rmtree(paths.build_dir(self.repo))
        return super()._investigate(data, nth)


def test_build_scratch_cleanup_during_a_turn_preserves_the_pending_queue(
    unbooked: Path, tmp_path: Path,
) -> None:
    """The observed missing-worklist crash: scratch vanishes before record writes back."""
    child = {"kind": "surface", "target": "acme/other.py", "context": "second item"}
    agent = _ScratchCleanupAgent(
        unbooked, writes=FILLS, spawn={"acme/service.py": [child]},
    )
    env = _env(tmp_path)
    _drive(env, agent)
    assert agent.targets == ["acme/service.py", "acme/other.py"]
    worklist = _run_worklist_path(env)
    assert worklist.is_relative_to(env.run_dir)
    rows = json.loads(worklist.read_text())["items"]
    assert {row["target"]: row["status"] for row in rows} == {
        "acme/service.py": "done", "acme/other.py": "done",
    }


def test_a_second_run_cannot_overwrite_the_first_runs_active_queue(
    unbooked: Path, tmp_path: Path,
) -> None:
    first_env = _env(tmp_path)
    first = _Agent(unbooked, explode={"acme/service.py"})
    with pytest.raises(RuntimeError, match="killed while investigating"):
        _drive(first_env, first)
    first_path = _run_worklist_path(first_env)
    before = first_path.read_bytes()
    second_env = _env(tmp_path / "second")
    _drive(second_env, _Agent(unbooked, writes=FILLS))
    assert first_path.read_bytes() == before
    second_path = _run_worklist_path(second_env)
    assert first_path != second_path
    assert all(row["status"] == "done" for row in json.loads(second_path.read_text())["items"])
    assert paths.worklist_path(unbooked, SERVICE).resolve() == second_path
