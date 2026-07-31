"""End-to-end drives of the surveyor (`author/flows/surveyor.py`).

Nothing is stubbed except the agent turn. `load_survey_config`, `check_inventory`,
`expand_inventory`, `select_next_unit`, `split_unit`, `validate_record`, `mark_unit`,
`verify_records`, `validate_partition` and `emit_artifacts` all run for real against the
`repo` fixture, so a drive here exercises the granularity expansion, the worklist, the
record ruleset, the coverage gate, the orphan sweep and the emitter.

The agent seam is patched where the engine reads it
(`RunEnv.agent_runner`) and the stub **writes the artifacts its
reply claims to have written** — the rules file, the finding record, the partition. The
loop's state lives in those files, not in the machine, so an agent that only replied would
leave every node downstream of it with nothing to read.

What the port could get wrong, and what is therefore under test here:

* the three bounded loops and their give-up arms — plan rework, record fix, partition
  rework — each ending somewhere other than "stuck";
* the three operator gates, which are the flow's (and the whole port's) first `Await`
  sites. The YAML sent `resolve_plan` and `resolve_partition` into `await_*`
  *unconditionally* and let `await-operator.py` decide whether to wait by reading a
  `STATUS:` line; the driver's `Await` waits unconditionally, so the port branches on the
  reply instead. Both arms of all three gates are driven below — an autonomous resolution
  must NOT block, and an escalation must.
* resume, which is why the checkpoint lands before the agent turn: a run killed
  mid-assessment re-runs that one unit and nothing before it.
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
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import activity as pyflow_activity
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import drive, read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows import author
from workhorse_workflows.author.flows.surveyor import Surveyor
from workhorse_workflows.author.nodes.survey import record_slug
from workhorse_workflows.author.schemas import EmitResult

SURVEY_DIR = "docs/survey"
RUBRIC = f"{SURVEY_DIR}/rubric.md"
RULES = f"{SURVEY_DIR}/units.yml"
INVENTORY = f"{SURVEY_DIR}/inventory.json"
FINDINGS = f"{SURVEY_DIR}/findings"
PARTITION = f"{SURVEY_DIR}/partition.yaml"
MANIFEST = f"{SURVEY_DIR}/unit-manifest.json"
CONTEXT = f"{SURVEY_DIR}/_survey-context.md"
BACKLOG = "docs/backlog.md"

BUTTON = "src/components/button"
MODAL = "src/components/modal"
#: The one child `src/components/modal` splits into.
MODAL_CHILD = "src/components/modal/index.tsx"
CLUSTER = "missing-accessible-name"


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def surveyed(repo: Path, write: Callable[[Path, str], Path]) -> Path:
    """A repo with a rubric and two component folders, and nothing else.

    No rules file and no inventory, so `check_inventory` reports `needs_plan` and the
    granularity planner runs — the survey's one planning judgment is in the drive rather
    than pinned by the fixture. Two units is the smallest list that can show the loop
    taking one unit per pass.
    """
    write(repo / RUBRIC, "# Accessibility rubric\n\nEvery control needs a name.\n")
    write(repo / BUTTON / "index.tsx", "export const Button = () => <button />\n")
    write(repo / MODAL / "index.tsx", "export const Modal = () => <div />\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(
        ["git", "commit", "-qm", "seed"], cwd=repo, check=True, stdout=subprocess.DEVNULL
    )
    return repo


def _rules(glob: str = "src/components/*") -> str:
    """The enumeration rules the planner writes. JSON is valid YAML."""
    return json.dumps({"rules": [{"kind": "folder", "glob": glob}]}, indent=2) + "\n"


def _record(unit_id: str, kind: str = "folder", *, status: str = "assessed") -> str:
    """One finding record, as the assessor writes it."""
    front: dict[str, Any] = {
        "type": "survey-finding",
        "unit": unit_id,
        "kind": kind,
        "status": status,
    }
    if status == "assessed":
        front["findings"] = [
            {
                "description": f"{unit_id} renders an icon-only control with no name",
                "remediation_pattern": CLUSTER,
                "effort": "small",
                "evidence": f"{unit_id}/index.tsx:1 — no aria-label on the button",
            }
        ]
    if status == "blocked":
        front["openGaps"] = [f"{unit_id} cannot be rendered without a live backend"]
        front["disposition"] = "accepted"
    return f"---\n{json.dumps(front, indent=2)}\n---\n\n# Survey finding: {unit_id}\n"


def _assessed(repo: Path) -> list[str]:
    """Every inventory unit currently `assessed` — the units a partition must cover."""
    data = json.loads((repo / INVENTORY).read_text())
    return [str(u["id"]) for u in data["units"] if u.get("status") == "assessed"]


def _partition(repo: Path, *, orphan: bool = False) -> str:
    """One mechanical cluster over the assessed units.

    `orphan=True` leaves the last assessed unit out, which is exactly what the orphan
    sweep in `validate_partition` exists to catch — and the only way to drive the
    partition rework loop with the real gate rather than a stubbed verdict.
    """
    units = _assessed(repo)
    return json.dumps(
        {
            "clusters": [
                {
                    "id": CLUSTER,
                    "title": "Give every icon-only control an accessible name",
                    "remediation_pattern": CLUSTER,
                    "strategy": "mechanical",
                    "order": 1,
                    "units": units[:1] if orphan else units,
                    "notes": "One checklist story; trivial per unit.",
                }
            ]
        },
        indent=2,
    )


def _accept_blocked(repo: Path) -> list[str]:
    """What the resolver agent does for a `survey-coverage` block, for real.

    The prompt tells it to either re-pend a blocked unit or record `disposition:
    accepted` in its record. This takes the second branch, so the coverage gate has a
    real reason to go green on the next pass rather than a patched one.
    """
    data = json.loads((repo / INVENTORY).read_text())
    accepted = []
    for unit in data["units"]:
        if unit.get("status") != "blocked":
            continue
        unit_id = str(unit["id"])
        path = repo / FINDINGS / f"{record_slug(unit_id)}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_record(unit_id, str(unit.get("kind", "")), status="blocked"))
        accepted.append(unit_id)
    return accepted


class _Agent:
    """A scripted stand-in for all five of the flow's agent turns.

    It dispatches on the prompt's filename, the same key the engine derives its node id
    from, and every handler leaves behind the artifact the next deterministic node reads.
    The knobs are the flow's branches: `blocked` returns a stage's blocked reply once,
    `corrupt` writes a record with unparseable front-matter, `split_units` takes the
    granularity escape hatch, `unfixable` refuses the repair, `escalate` makes the
    operator stand-in hand the block to a human, and `explode` raises instead of
    assessing — a run killed mid-turn.
    """

    def __init__(
        self,
        repo: Path,
        *,
        blocked: set[str] | None = None,
        corrupt: set[str] | None = None,
        explode: set[str] | None = None,
        split_units: set[str] | None = None,
        empty_rules_first: bool = False,
        unfixable: bool = False,
        escalate: bool = False,
        orphan_first: bool = False,
    ) -> None:
        self.repo = repo
        self.blocked = blocked or set()
        self.corrupt = corrupt or set()
        self.explode = explode or set()
        self.split_units = set(split_units or ())
        self.empty_rules_first = empty_rules_first
        self.unfixable = unfixable
        self.escalate = escalate
        self.orphan_first = orphan_first
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []

    # -- the seam ---------------------------------------------------------

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        return f"(scripted) {node.prompt}", handler(data, self.counts()[stem])

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]

    # -- one handler per prompt -------------------------------------------

    def _plan_units(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if "plan-units" in self.blocked and nth == 1:
            return {"status": "blocked", "notes": "is the design system in scope?"}
        glob = "src/nowhere/*" if self.empty_rules_first and nth == 1 else "src/components/*"
        (self.repo / data["rules_path"]).write_text(_rules(glob))
        return {"status": "complete", "notes": "one unit per component folder"}

    def _assess_unit(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        unit_id = data["unit_id"]
        if unit_id in self.explode:
            raise RuntimeError(f"killed while assessing {unit_id}")
        if unit_id in self.split_units:
            self.split_units.discard(unit_id)
            return {"status": "split", "notes": "a dozen surfaces in one folder"}
        path = self.repo / data["record_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        if unit_id in self.corrupt:
            # Unparseable front-matter, not a wrong `unit:`: `mark_unit`'s lenient reader
            # would accept a well-formed record for the wrong unit and mark the unit
            # assessed, which would hide the give-up path this drives.
            path.write_text("---\nunit: [oops\n")
            return {"status": "assessed", "notes": "wrote the record"}
        path.write_text(_record(unit_id, data["unit_kind"]))
        return {"status": "assessed", "notes": "one finding"}

    def _fix_record(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if self.unfixable:
            return {"status": "unfixable", "notes": "nothing salvageable in the record"}
        unit_id = data["unit_id"]
        self.corrupt.discard(unit_id)
        (self.repo / data["record_path"]).write_text(_record(unit_id))
        return {"status": "fixed", "notes": "closed the front-matter fence"}

    def _partition_findings(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if "partition-findings" in self.blocked and nth == 1:
            return {"status": "blocked", "notes": "one story or one per area?"}
        orphan = self.orphan_first and nth == 1
        (self.repo / data["partition_path"]).write_text(_partition(self.repo, orphan=orphan))
        return {"status": "complete", "notes": "one mechanical cluster"}

    def _resolve_operator(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if self.escalate:
            return {"decision": "escalated", "notes": "needs a product call"}
        if data["block_stage"] == "survey-coverage":
            _accept_blocked(self.repo)
        return {"decision": "answered", "notes": f"resolved {data['block_stage']}"}


def _env(tmp: Path, *, run_dir: Path | None = None) -> RunEnv:
    writer = (
        ArtifactWriter.resume(run_dir)
        if run_dir is not None
        else ArtifactWriter("surveyor", tmp / "runs", run_id="t")
    )
    return RunEnv(
        writer=writer,
        # The *author* package: `handoff` subscopes the writer, not the env, so a
        # sub-flow's prompt paths resolve against its parent's directory.
        workflow_dir=Path(author.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
    )


def _drive(env: RunEnv, agent: _Agent, **inputs: Any) -> Any:
    return drive(Surveyor(**inputs), replace(env, agent_runner=StubRunner(agent)))


def _units(repo: Path) -> dict[str, str]:
    data = json.loads((repo / INVENTORY).read_text())
    return {u["id"]: u["status"] for u in data["units"]}


# ------------------------------------------------------------------- the happy path


def test_two_components_are_planned_assessed_verified_and_emitted(
    surveyed: Path, tmp_path: Path
) -> None:
    """One full pass over a repo with nothing pinned: plan, freeze, assess each unit
    once, verify coverage, cluster, emit.

    Every stage runs exactly once — that the loop takes one unit per pass and exits on
    the empty pending set is the whole shape of the flow.
    """
    agent = _Agent(surveyed)
    result = _drive(_env(tmp_path), agent)

    assert isinstance(result, EmitResult), result
    assert result.emit_ok is True, result
    assert result.bullet_count == 1, result.emit_note
    assert agent.counts() == {
        "plan-units": 1,
        "assess-unit": 2,
        "partition-findings": 1,
    }, agent.counts()
    assert _units(surveyed) == {BUTTON: "assessed", MODAL: "assessed"}

    backlog = (surveyed / BACKLOG).read_text()
    assert f"[survey-{CLUSTER}]" in backlog, backlog
    assert "2 unit(s), mechanical" in backlog, backlog

    manifest = json.loads((surveyed / MANIFEST).read_text())
    assert {u["id"] for u in manifest["units"]} == {BUTTON, MODAL}, manifest
    assert manifest["units"][0]["bullets"] == [f"survey-{CLUSTER}"], manifest


def test_operator_pinned_rules_skip_the_planner(
    surveyed: Path, tmp_path: Path, write: Callable[[Path, str], Path]
) -> None:
    """`check_inventory`'s point: a rules file on disk is a decision already made.

    The planner is the flow's one expensive judgment, and re-deciding a granularity an
    operator pinned would silently overwrite it.
    """
    write(surveyed / RULES, _rules())
    agent = _Agent(surveyed)
    result = _drive(_env(tmp_path), agent)

    assert result.emit_ok is True, result
    assert agent.counts()["plan-units"] == 0, agent.counts()
    assert _units(surveyed) == {BUTTON: "assessed", MODAL: "assessed"}


def test_the_assessor_is_handed_the_unit_the_rubric_and_the_context_file(
    surveyed: Path, tmp_path: Path
) -> None:
    """The six `args:` the YAML's `assess_unit` node rendered, arriving as real values.

    `record_path` is derived once, by `select_next_unit`, so assess/validate/mark cannot
    disagree about where the record lives.
    """
    agent = _Agent(surveyed)
    _drive(_env(tmp_path), agent)

    first = agent.args_for("assess-unit")[0]
    assert first["unit_id"] == BUTTON, first
    assert first["unit_path"] == BUTTON, first
    assert first["unit_kind"] == "folder", first
    assert first["record_path"] == f"{FINDINGS}/src-components-button.md", first
    assert first["rubric"] == RUBRIC, first
    assert first["context_path"] == CONTEXT, first


def test_every_turn_runs_in_the_surveyed_repo(surveyed: Path, tmp_path: Path) -> None:
    """`cwd` decides whose CLAUDE.md, skills and git context each turn sees. It is the
    field every agent node carried as `cwd: "{{ cfg.repo_root }}"`, and a port that
    dropped it would run the turns wherever the engine happened to be."""
    captured: list[Any] = []

    class _Recording(_Agent):
        def __call__(self, node: Any, ctx: Any, *a: Any, **kw: Any) -> Any:
            captured.append(node.cwd)
            return super().__call__(node, ctx, *a, **kw)

    _drive(_env(tmp_path), _Recording(surveyed))

    assert captured and set(captured) == {str(surveyed)}, captured


# ----------------------------------------------------------------- the bounded loops


def test_an_invalid_record_is_repaired_once_and_the_unit_lands_assessed(
    surveyed: Path, tmp_path: Path
) -> None:
    """The record-fix loop's happy exit: `validate_record` rejects, one repair turn,
    re-validate, mark.

    Nothing branches on the repair's own reply — `validate_record` is what decides — so
    the loop re-checks either way.
    """
    agent = _Agent(surveyed, corrupt={BUTTON})
    result = _drive(_env(tmp_path), agent)

    assert result.emit_ok is True, result
    assert agent.counts()["fix-record"] == 1, agent.counts()
    assert _units(surveyed) == {BUTTON: "assessed", MODAL: "assessed"}
    assert agent.args_for("fix-record")[0]["record_errors"], agent.args_for("fix-record")


def test_an_unfixable_record_blocks_its_unit_and_the_coverage_gate_resolves_it(
    surveyed: Path, tmp_path: Path
) -> None:
    """The give-up path, end to end, which is the one that must not wedge the survey.

    Two repairs fail, so the unit is marked `blocked` with the validator's errors as its
    reason and the loop moves on. `verify_records` then re-surfaces it — a blocked unit
    is an OPEN gap, never a silent drop — and the autonomous operator closes it by
    recording an accepted disposition, exactly as its prompt specifies. The survey ends
    with a partition over what was actually assessed.
    """
    agent = _Agent(surveyed, corrupt={BUTTON}, unfixable=True)
    result = _drive(_env(tmp_path), agent)

    assert result.emit_ok is True, result
    assert result.bullet_count == 1, result.emit_note
    assert agent.counts()["fix-record"] == 2, agent.counts()
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert _units(surveyed) == {BUTTON: "blocked", MODAL: "assessed"}

    resolve = agent.args_for("resolve-operator")[0]
    assert resolve["block_stage"] == "survey-coverage", resolve
    # The record the fix loop gave up on is still on disk and still unparseable, so the
    # gate re-surfaces the unit as an invalid record rather than as an open gap — either
    # way it is accounted for by name, which is the property that matters.
    assert "[invalid-record]" in resolve["block_notes"], resolve
    assert BUTTON in resolve["block_notes"], resolve

    # The blocked unit is in the manifest with no bullet: accounted for, not dropped.
    manifest = {u["id"]: u for u in json.loads((surveyed / MANIFEST).read_text())["units"]}
    assert manifest[BUTTON]["bullets"] == [], manifest
    assert manifest[MODAL]["bullets"] == [f"survey-{CLUSTER}"], manifest


def test_rules_that_expand_to_nothing_send_the_flow_back_to_the_planner(
    surveyed: Path, tmp_path: Path
) -> None:
    """An expansion that yields no units is a granularity problem, not a repo with no
    surfaces — so it is the planner's to fix, with the expansion's own errors in hand.

    This is the plan-rework loop the YAML wrote as `guard_plan` + `incr_plan`, bounded
    here by `plan_rework` and a state parameter rather than a counter file.
    """
    agent = _Agent(surveyed, empty_rules_first=True)
    result = _drive(_env(tmp_path), agent)

    assert result.emit_ok is True, result
    assert agent.counts()["plan-units"] == 2, agent.counts()
    rework = agent.args_for("plan-units")[1]
    assert "matched no folders" in rework["plan_errors"], rework
    assert _units(surveyed) == {BUTTON: "assessed", MODAL: "assessed"}


def test_a_partition_that_orphans_a_unit_is_sent_back_with_the_orphan_named(
    surveyed: Path, tmp_path: Path
) -> None:
    """The orphan sweep is the gate that matters: a cluster set that drops an assessed
    unit would drop its findings out of the generated backlog silently.

    The rework carries the gate's own words, so the partitioner is told which unit it
    left out rather than being asked to guess.
    """
    agent = _Agent(surveyed, orphan_first=True)
    result = _drive(_env(tmp_path), agent)

    assert result.emit_ok is True, result
    assert agent.counts()["partition-findings"] == 2, agent.counts()
    rework = agent.args_for("partition-findings")[1]
    assert "appears in NO cluster" in rework["partition_errors"], rework
    assert MODAL in rework["partition_errors"], rework


def test_a_unit_too_big_to_assess_is_split_into_its_children(
    surveyed: Path, tmp_path: Path
) -> None:
    """The granularity escape hatch: `split` replaces the unit with its children rather
    than letting the assessor sample it.

    The parent leaves the inventory and its children enter it `pending`, so the coverage
    claim follows the split — `verify_records` reads the lineage off the child paths.
    """
    agent = _Agent(surveyed, split_units={MODAL})
    result = _drive(_env(tmp_path), agent)

    assert result.emit_ok is True, result
    assert _units(surveyed) == {BUTTON: "assessed", MODAL_CHILD: "assessed"}
    # The split unit was assessed twice: once to ask for the split, once as its child.
    assert agent.counts()["assess-unit"] == 3, agent.counts()
    kinds = [a["unit_kind"] for a in agent.args_for("assess-unit")]
    assert kinds == ["folder", "folder", "file"], kinds


# ------------------------------------------------------------------ the three gates


def test_a_blocked_plan_is_resolved_by_the_operator_stand_in_without_waiting(
    surveyed: Path, tmp_path: Path
) -> None:
    """The gate the YAML got wrong, driven on its autonomous arm.

    `resolve_plan` ran into `await_plan` unconditionally there; whether it *waited* was
    decided inside `await-operator.py`, by reading a `STATUS:` line the resolver had
    written. `Await` in the driver always waits, so an answered resolution has to be a
    branch in the flow — and this test is what proves that branch does not block: no
    patched poll, so a wait here would hang the suite.
    """
    agent = _Agent(surveyed, blocked={"plan-units"})
    result = _drive(_env(tmp_path), agent)

    assert result.emit_ok is True, result
    assert agent.counts()["plan-units"] == 2, agent.counts()
    resolve = agent.args_for("resolve-operator")[0]
    assert resolve["block_stage"] == "plan-units", resolve
    assert resolve["block_notes"] == "is the design system in scope?", resolve
    assert resolve["context_path"] == CONTEXT, resolve


def test_an_escalated_partition_block_waits_on_the_operator_context_file(
    surveyed: Path, tmp_path: Path
) -> None:
    """The same gate's other arm: the resolver escalates, so the flow waits on a human.

    The ask lands in the context file and the wait is a poll on that file's mtime — the
    driver's portable replacement for `await-operator.py`'s inotify. Patching the poll is
    the operator answering.
    """
    seen: list[str] = []

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text())

    agent = _Agent(surveyed, blocked={"partition-findings"}, escalate=True)
    with patch.object(pyflow_driver, "poll_until_touched", answered):
        result = _drive(_env(tmp_path), agent)

    assert result.emit_ok is True, result
    assert agent.counts()["partition-findings"] == 2, agent.counts()
    assert agent.args_for("resolve-operator")[0]["block_stage"] == "partition"
    # The question the operator was woken for is in the file they were pointed at.
    assert seen == ["one story or one per area?"], seen
    assert (surveyed / CONTEXT).read_text() == "one story or one per area?"


def test_human_operator_mode_sends_the_block_straight_to_the_context_file(
    surveyed: Path, tmp_path: Path
) -> None:
    """`operator_mode: human` is the YAML's `cases: {human: …}` arm: no stand-in turn at
    all, the block goes to the person.

    It is also the only setting under which the resolver never runs, which is what makes
    the autonomous arm a choice rather than the only path through the gate.
    """
    seen: list[str] = []

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text())

    agent = _Agent(surveyed, blocked={"plan-units"})
    with patch.object(pyflow_driver, "poll_until_touched", answered):
        result = _drive(_env(tmp_path), agent, operator_mode="human")

    assert result.emit_ok is True, result
    assert agent.counts()["resolve-operator"] == 0, agent.counts()
    assert agent.counts()["plan-units"] == 2, agent.counts()
    assert seen == ["is the design system in scope?"], seen


# ------------------------------------------------------------------------- resume


def test_a_run_killed_mid_assessment_resumes_on_that_unit_alone(
    surveyed: Path, tmp_path: Path
) -> None:
    """The loop's state is the inventory file and the records, not the machine.

    So the checkpoint written *before* the agent turn is enough: the resumed run
    re-assesses the unit that was in flight and no earlier one, because the earlier ones
    are already marked on disk. This is the YAML's resume behavior — its `refuel: unit_id`
    node re-entered the same way — reproduced without a gas tank.
    """
    first = _Agent(surveyed, explode={MODAL})
    env = _env(tmp_path)
    run_dir = env.writer.run_dir
    with pytest.raises(RuntimeError, match="killed while assessing"):
        _drive(env, first)

    assert first.counts()["assess-unit"] == 2, first.counts()
    assert _units(surveyed) == {BUTTON: "assessed", MODAL: "pending"}

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "assess", resume
    assert resume.params["unit_id"] == MODAL, resume.params
    assert resume.flow == "Surveyor", resume

    second = _Agent(surveyed)
    result = drive(
        Surveyor(**resume.inputs),
        replace(_env(tmp_path, run_dir=run_dir), agent_runner=StubRunner(second)),
        resume,
    )

    # Only the interrupted unit ran again, and the planner did not re-run: the frozen
    # list is the coverage claim, so a resume consumes it rather than re-deriving it.
    assert second.counts() == {
        "assess-unit": 1,
        "partition-findings": 1,
    }, second.counts()
    assert result.bullet_count == 1, result.emit_note
    assert _units(surveyed) == {BUTTON: "assessed", MODAL: "assessed"}


# ------------------------------------------------------------------------- labels


def test_the_labels_name_the_unit_and_the_progress(surveyed: Path, tmp_path: Path) -> None:
    """The YAML's `labels:` block read `get_node_output('select_unit', …)`; here
    `labels()` reads `self.output(select_next_unit)` and takes no parameters.

    Before the first pick there is no output to read, and that is the normal state of a
    run's first transition — the guard against `NodeNotRunError` is what makes it a
    label-less transition rather than a crashed one.
    """
    seen: list[dict[str, str]] = []
    real_rebase = pyflow_activity.ActivityLog.rebase

    def capture(self: Any, labels: dict[str, str]) -> Any:
        seen.append(dict(labels))
        return real_rebase(self, labels)

    with patch.object(pyflow_activity.ActivityLog, "rebase", capture):
        _drive(_env(tmp_path), _Agent(surveyed))

    assert seen[0] == {}, seen[0]
    stamped = [labels for labels in seen if labels.get("work_id")]
    assert stamped, seen
    assert stamped[0]["work_id"] == BUTTON, stamped[0]
    # `progress` is the worklist's own count, so the dashboard can read it without
    # knowing anything about surveys.
    assert stamped[0]["progress"], stamped[0]
    # Unprefixed, unlike the YAML engine's `wf.work_id`.
    assert not any(k.startswith("wf.") for labels in seen for k in labels), seen
