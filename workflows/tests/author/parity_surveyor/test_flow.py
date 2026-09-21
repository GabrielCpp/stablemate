"""End-to-end drives of the parity surveyor (`author/parity_surveyor/flow.py`)."""
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
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow import activity as pyflow_activity
from workhorse.pyflow.driver import drive, read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows import author
from workhorse_workflows.author.parity_surveyor.flow import ParitySurveyor
from workhorse_workflows.author.shared.schemas import EmitResult

BASELINE = "docs/legacy/inventory.json"
SURVEY_DIR = "docs/survey/legacy-vs-new"
INVENTORY = f"{SURVEY_DIR}/inventory.json"
FINDINGS = f"{SURVEY_DIR}/findings"
MANIFEST = f"{SURVEY_DIR}/unit-manifest.json"
BACKLOG = "docs/backlog.md"

INVOICES = "legacy/billing/invoices"
STATEMENTS = "legacy/billing/statements"




@pytest.fixture
def surveyed(repo: Path, write_json: Callable[[Path, Any], Path]) -> Path:
    """A repo with a legacy baseline to survey and a feature book to survey it against."""
    write_json(
        repo / BASELINE,
        {
            "entries": [
                {"area": "billing", "slug": "invoices", "title": "Invoices",
                 "route": "/invoices"},
                {"area": "billing", "slug": "statements", "title": "Statements",
                 "route": "/statements"},
                {"area": "admin", "slug": "users", "rewriteSurface": True},
            ]
        },
    )
    (repo / "docs/features").mkdir(parents=True, exist_ok=True)
    (repo / "docs/epics").mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(
        ["git", "commit", "-qm", "seed"], cwd=repo, check=True, stdout=subprocess.DEVNULL
    )
    return repo


def _record(unit_id: str, *, owner: str = "", status: str = "assessed") -> str:
    """One finding record, as the assessor writes it."""
    front: dict[str, Any] = {
        "type": "survey-finding",
        "unit": unit_id,
        "status": status,
    }
    if owner:
        front["existing_owner"] = owner
    if status == "assessed":
        front["findings"] = [
            {
                "description": f"{unit_id} has no home in the new app",
                "remediation_pattern": "legacy-surface-parity",
                "effort": "small",
                "evidence": [f"{unit_id}.php:12"],
            }
        ]
    return f"---\n{json.dumps(front, indent=2)}\n---\n\n# Parity finding\n"


class _Assessor:
    """A scripted assessor that writes the record its reply claims to have written."""

    def __init__(
        self,
        repo: Path,
        *,
        owners: dict[str, str] | None = None,
        corrupt: set[str] | None = None,
        explode: set[str] | None = None,
    ) -> None:
        self.repo = repo
        self.owners = owners or {}
        self.corrupt = corrupt or set()
        self.explode = explode or set()
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        data = ctx.as_dict()
        unit_id = data["unit_id"]
        self.calls.append(unit_id)
        self.args.append(data)
        if unit_id in self.explode:
            raise RuntimeError(f"killed while assessing {unit_id}")
        written = "not/the/unit" if unit_id in self.corrupt else unit_id
        path = self.repo / data["record_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_record(written, owner=self.owners.get(unit_id, "")))
        return f"(scripted) {node.prompt}", {"status": "assessed", "notes": "done"}

    def counts(self) -> Counter[str]:
        return Counter(self.calls)


def _env(tmp: Path, *, run_dir: Path | None = None) -> RunEnv:
    writer = (
        ArtifactWriter.resume(run_dir)
        if run_dir is not None
        else ArtifactWriter("parity-surveyor", tmp / "runs", run_id="t")
    )
    return RunEnv(
        writer=writer,
        workflow_dir=Path(author.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
    )


def _drive(env: RunEnv, agent: _Assessor, **inputs: Any) -> Any:
    return drive(
        ParitySurveyor(baseline_inventory=BASELINE, **inputs),
        replace(env, agent_runner=StubRunner(agent)),
    )


def _units(repo: Path) -> dict[str, str]:
    data = json.loads((repo / INVENTORY).read_text())
    return {u["id"]: u["status"] for u in data["units"]}




def test_a_two_surface_baseline_surveys_both_and_emits_only_the_unowned_one(
    surveyed: Path, tmp_path: Path
) -> None:
    """One full pass: freeze, assess each unit once, verify coverage, emit."""
    agent = _Assessor(surveyed, owners={STATEMENTS: "features/billing/statements.md"})
    result = _drive(_env(tmp_path), agent)

    assert isinstance(result, EmitResult), result
    assert result.emit_ok is True, result
    assert result.bullet_count == 1, result.emit_note
    assert agent.counts() == {INVOICES: 1, STATEMENTS: 1}, agent.counts()
    assert _units(surveyed) == {INVOICES: "assessed", STATEMENTS: "assessed"}

    backlog = (surveyed / BACKLOG).read_text()
    assert "legacy-parity-billing-invoices" in backlog, backlog
    assert "legacy-parity-billing-statements" not in backlog, backlog

    manifest = {u["id"]: u for u in json.loads((surveyed / MANIFEST).read_text())["units"]}
    assert manifest[INVOICES]["bullet"] == "legacy-parity-billing-invoices", manifest
    assert manifest[STATEMENTS]["bullet"] == "", manifest
    assert manifest[STATEMENTS]["existingOwner"] == "features/billing/statements.md"


def test_the_assessor_is_handed_the_unit_and_both_sides_of_the_compare(
    surveyed: Path, tmp_path: Path
) -> None:
    """The eight `args:` the YAML node rendered, arriving as real values."""
    agent = _Assessor(surveyed)
    _drive(_env(tmp_path), agent)

    first = agent.args[0]
    assert first["unit_id"] == INVOICES, first
    assert first["unit_kind"] == "legacy-surface", first
    assert first["record_path"] == f"{FINDINGS}/legacy-billing-invoices.md", first
    assert first["baseline_inventory"] == BASELINE, first
    assert first["target_features"] == "docs/features", first
    assert first["epics_dir"] == "docs/epics", first


def test_the_turn_runs_in_the_surveyed_repo(surveyed: Path, tmp_path: Path) -> None:
    """`cwd` decides whose CLAUDE.md, skills and git context the assessor sees."""
    captured: list[Any] = []

    class _Recording(_Assessor):
        def __call__(self, node: Any, ctx: Any, *a: Any, **kw: Any) -> Any:
            captured.append(node.cwd)
            return super().__call__(node, ctx, *a, **kw)

    _drive(_env(tmp_path), _Recording(surveyed))

    assert captured and set(captured) == {str(surveyed)}, captured




def test_an_invalid_record_fails_the_survey_and_names_the_unit(
    surveyed: Path, tmp_path: Path
) -> None:
    """There is no bounded fix loop here, unlike the surveyor flow: the parity record *is* the finding, and a malformed one would emit a bullet nobody can act on."""
    agent = _Assessor(surveyed, corrupt={INVOICES})

    with pytest.raises(WorkflowFailed) as exc:
        _drive(_env(tmp_path), agent)

    assert INVOICES in str(exc.value), exc.value
    assert "is invalid" in str(exc.value), exc.value
    assert agent.counts() == {INVOICES: 1}, agent.counts()


def test_a_baseline_with_nothing_to_survey_fails_the_freeze(
    repo: Path, tmp_path: Path, write_json: Callable[[Path, Any], Path]
) -> None:
    """Every entry already owned by the rewrite leaves no units, and a survey with no units cannot prove anything — `parity_decide_expand`'s default arm."""
    write_json(repo / BASELINE, {"entries": [{"area": "a", "slug": "b",
                                              "rewriteSurface": True}]})
    (repo / "docs/features").mkdir(parents=True, exist_ok=True)

    with pytest.raises(WorkflowFailed, match="no non-rewrite surfaces"):
        _drive(_env(tmp_path), _Assessor(repo))


def test_a_missing_baseline_fails_in_setup(repo: Path, tmp_path: Path) -> None:
    """`load_parity_config` runs in `setup()`, so this halts before the first state and before any checkpoint exists — the paths every state reads are not a state's decision."""
    (repo / "docs/features").mkdir(parents=True, exist_ok=True)

    with pytest.raises(WorkflowFailed, match="baseline inventory not found"):
        _drive(_env(tmp_path), _Assessor(repo))




def test_a_run_killed_mid_assessment_resumes_on_that_unit_alone(
    surveyed: Path, tmp_path: Path
) -> None:
    """The loop's state is the inventory file and the records, not the machine."""
    first = _Assessor(surveyed, explode={STATEMENTS})
    env = _env(tmp_path)
    run_dir = env.writer.run_dir
    with pytest.raises(RuntimeError, match="killed while assessing"):
        _drive(env, first)

    assert first.counts() == {INVOICES: 1, STATEMENTS: 1}, first.counts()
    assert _units(surveyed) == {INVOICES: "assessed", STATEMENTS: "pending"}

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "assess", resume
    assert resume.params["unit_id"] == STATEMENTS, resume.params
    assert resume.flow == "ParitySurveyor", resume

    second = _Assessor(surveyed)
    result = drive(
        ParitySurveyor(**resume.inputs),
        replace(_env(tmp_path, run_dir=run_dir), agent_runner=StubRunner(second)),
        resume,
    )

    assert second.counts() == {STATEMENTS: 1}, second.counts()
    assert result.bullet_count == 2, result.emit_note
    assert _units(surveyed) == {INVOICES: "assessed", STATEMENTS: "assessed"}


def test_a_second_run_consumes_the_frozen_list_instead_of_re_deriving_it(
    surveyed: Path, tmp_path: Path
) -> None:
    """A re-run means the same thing as the first one only if the freeze is not redone."""
    _drive(_env(tmp_path), _Assessor(surveyed))
    frozen = (surveyed / INVENTORY).read_text()

    baseline = json.loads((surveyed / BASELINE).read_text())
    baseline["entries"].append({"area": "billing", "slug": "credits"})
    (surveyed / BASELINE).write_text(json.dumps(baseline))

    agent = _Assessor(surveyed)
    result = _drive(_env(tmp_path / "second"), agent)

    assert (surveyed / INVENTORY).read_text() == frozen
    assert agent.calls == [], agent.calls
    assert result.bullet_count == 2, result.emit_note




def test_the_labels_name_the_unit_and_the_progress(surveyed: Path, tmp_path: Path) -> None:
    """The YAML's `labels:` block read `get_node_output('parity_select_unit', …)`; here `labels()` reads `self.output(select_next_unit)` and takes no parameters."""
    seen: list[dict[str, str]] = []
    real_rebase = pyflow_activity.ActivityLog.rebase

    def capture(self: Any, labels: dict[str, str]) -> Any:
        seen.append(dict(labels))
        return real_rebase(self, labels)

    with patch.object(pyflow_activity.ActivityLog, "rebase", capture):
        _drive(_env(tmp_path), _Assessor(surveyed))

    assert seen[0] == {}, seen[0]
    stamped = [labels for labels in seen if labels.get("work_id")]
    assert stamped, seen
    assert stamped[0]["work_id"] == INVOICES, stamped[0]
    assert stamped[0]["progress"], stamped[0]
    assert not any(k.startswith("wf.") for labels in seen for k in labels), seen
