"""The greenfield round's inputs and the fixtures it reads beside the benchmark's tasks."""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import fake_run

from paddock.tasks import greenfield
from paddock.tasks.stablemate import TrialError

FIXTURE = greenfield.Fixture(
    milestone="milestones/m1",
    decision_records="records",
    surfaces=(greenfield.Surface(service="api", service_root="api"),),
    budget_s={"genesis": 60.0},
)


def test_a_budget_input_overrides_the_fixtures_phase_budget(tmp_path: Path) -> None:
    assert greenfield.budget_of(fake_run(tmp_path), FIXTURE, "genesis") == 60.0
    assert greenfield.budget_of(fake_run(tmp_path), FIXTURE, "author") == 0.0
    run = fake_run(tmp_path, inputs={"budget_genesis": 5.0})
    assert greenfield.budget_of(run, FIXTURE, "genesis") == 5.0


def test_the_milestone_is_copied_from_beside_the_tasks_module(tmp_path: Path) -> None:
    run = fake_run(tmp_path)
    (run.stage / "docs").mkdir()
    milestone = run.benchmark.root / "milestones" / "m1"
    milestone.mkdir(parents=True)
    (milestone / greenfield.MILESTONE_FILE).write_text("# m\n", encoding="utf-8")

    greenfield.seed_milestone(run, FIXTURE)

    assert (run.stage / greenfield.MILESTONES_DIR / "m1" / greenfield.MILESTONE_FILE).is_file()
    assert (run.stage / greenfield.SERVICES_DIR / "api").is_dir()


def test_a_missing_milestone_is_named(tmp_path: Path) -> None:
    with pytest.raises(TrialError, match="no milestone at"):
        greenfield.seed_milestone(fake_run(tmp_path), FIXTURE)


def test_decision_records_are_copied_into_the_produced_repo(tmp_path: Path) -> None:
    run = fake_run(tmp_path)
    records = run.benchmark.root / "records"
    records.mkdir(parents=True)
    (records / "0001.md").write_text("# one\n", encoding="utf-8")

    greenfield.seed_decision_records(run, FIXTURE)

    assert (run.stage / "docs" / "decisions" / "0001.md").read_text(encoding="utf-8") == "# one\n"


def test_missing_decision_records_are_named(tmp_path: Path) -> None:
    with pytest.raises(TrialError, match="no decision records at"):
        greenfield.seed_decision_records(fake_run(tmp_path), FIXTURE)
