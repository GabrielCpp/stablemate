"""The greenfield round's inputs and the fixtures it reads beside the benchmark's tasks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fakes import DOCS, PRODUCTS, fake_run, folder_run

from paddock.runner import CommandResult, RoundInterrupted, Run
from paddock.tasks import greenfield
from paddock.tasks.stablemate import TrialError, uv_run

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


FOLDER_FIXTURE = greenfield.Fixture(
    milestone="milestones/m1",
    decision_records="records",
    surfaces=(
        greenfield.Surface(service="api", service_root="api", repo=PRODUCTS[0]),
        greenfield.Surface(service="web", service_root="web", repo=PRODUCTS[1]),
    ),
)


def _seed_milestone_source(run: Run) -> None:
    milestone = run.benchmark.root / "milestones" / "m1"
    milestone.mkdir(parents=True)
    (milestone / greenfield.MILESTONE_FILE).write_text("# m\n", encoding="utf-8")


def test_a_surface_names_a_repo_only_on_a_folder(tmp_path: Path) -> None:
    single = greenfield.Surface(service="api", service_root="api", repo="x")
    with pytest.raises(TrialError, match="stages one repo"):
        greenfield.surface_root(fake_run(tmp_path), single)
    folder = folder_run(tmp_path)
    with pytest.raises(TrialError, match="name one of"):
        greenfield.surface_root(folder, greenfield.Surface(service="api", service_root="api"))


def test_genesis_scaffolds_each_surface_in_its_member(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = folder_run(tmp_path)
    _seed_milestone_source(run)
    (run.benchmark.root / "records").mkdir()
    (run.benchmark.root / "records" / "0001.md").write_text("# one\n", encoding="utf-8")
    calls: list[tuple[list[str], Path]] = []

    def cli(*argv: str, cwd: Path, **_: object) -> CommandResult:
        calls.append((list(argv), cwd))
        return CommandResult(argv=argv, returncode=0, log=tmp_path / "log")

    monkeypatch.setattr(run, "cli", cli, raising=False)
    monkeypatch.setattr(greenfield, "stablemate_checkout", lambda _run: tmp_path)

    greenfield.run_genesis(run, FOLDER_FIXTURE)

    assert [cwd for _, cwd in calls] == [run.stage / PRODUCTS[0], run.stage / PRODUCTS[1]]
    for argv, cwd in calls:
        assert json.loads(argv[argv.index("--params") + 1])["target"] == str(cwd)
    home = run.stage / DOCS
    assert (home / greenfield.MILESTONES_DIR / "m1" / greenfield.MILESTONE_FILE).is_file()
    assert (home / greenfield.SERVICES_DIR / "web").is_dir()
    assert (home / "docs" / "decisions" / "0001.md").is_file()
    assert not (run.stage / PRODUCTS[0] / greenfield.MILESTONES_DIR).exists()


def test_a_phase_runs_in_the_docs_home_on_the_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = folder_run(tmp_path)
    seen: list[tuple[list[str], Path, dict[str, str]]] = []

    def cli(*argv: str, cwd: Path, env: dict[str, str], **_: object) -> CommandResult:
        seen.append((list(argv), cwd, env))
        return CommandResult(argv=argv, returncode=0, log=tmp_path / "log")

    monkeypatch.setattr(run, "cli", cli, raising=False)
    monkeypatch.setattr(greenfield, "stablemate_checkout", lambda _run: tmp_path)

    greenfield.run_phase(run, FOLDER_FIXTURE, "author", "workhorse-author", "run")

    argv, cwd, env = seen[0]
    assert argv[argv.index("--workspace") + 1] == "desk"
    assert cwd == run.stage / DOCS
    assert env["AGENT_REPO_DIR"] == str(run.stage / DOCS)


def test_the_baseline_is_committed_in_every_member(tmp_path: Path) -> None:
    run = folder_run(tmp_path)
    for name in (*PRODUCTS, DOCS):
        (run.stage / name / "scaffold.txt").write_text("x\n", encoding="utf-8")
    before = {name: greenfield.git_commits(run.stage / name) for name in (*PRODUCTS, DOCS)}

    greenfield.ignore_agent_runtime(run)
    greenfield.commit_baseline(run)

    for name in (*PRODUCTS, DOCS):
        assert greenfield.git_commits(run.stage / name) == before[name] + 1
        assert greenfield.IGNORE_HEADER in (run.stage / name / ".gitignore").read_text(encoding="utf-8")


def test_commits_are_summed_across_members(tmp_path: Path) -> None:
    run = folder_run(tmp_path)
    total = sum(greenfield.git_commits(repo) for repo in greenfield.repos_of(run))
    assert total == 3
    assert greenfield.home_of(run) == run.stage / DOCS


def _recording_cli(run: Run, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, rc: int = 0) -> list[list[str]]:
    calls: list[list[str]] = []

    def cli(*argv: str, **_: object) -> CommandResult:
        calls.append(list(argv))
        return CommandResult(argv=argv, returncode=rc, log=tmp_path / "log")

    monkeypatch.setattr(run, "cli", cli, raising=False)
    monkeypatch.setattr(greenfield, "stablemate_checkout", lambda _run: tmp_path)
    return calls


@pytest.mark.parametrize("rc", [130, -9])
def test_a_stopped_phase_interrupts_the_round(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rc: int) -> None:
    run = folder_run(tmp_path)
    _recording_cli(run, monkeypatch, tmp_path, rc=rc)

    with pytest.raises(RoundInterrupted, match="author"):
        greenfield.run_phase(run, FOLDER_FIXTURE, "author", "workhorse-author", "run")

    (entry,) = greenfield.phases_of(run)
    assert (entry["phase"], entry["rc"], entry["run_dir"]) == ("author", rc, "author-author")


def test_a_fresh_phase_names_its_run_dir_and_records_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = folder_run(tmp_path)
    calls = _recording_cli(run, monkeypatch, tmp_path)

    greenfield.run_phase(run, FOLDER_FIXTURE, "coder", "workhorse-coder", "run")

    argv = calls[0]
    assert argv[argv.index("--run-id") + 1] == "coder"
    (entry,) = greenfield.phases_of(run)
    assert (entry["phase"], entry["rc"], entry["run_dir"]) == ("coder", 0, "coder-coder")


def test_a_phase_that_finished_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = folder_run(tmp_path)
    calls = _recording_cli(run, monkeypatch, tmp_path)
    greenfield.record(run, "author", rc=0, wall_s=3.0)

    greenfield.run_phase(run, FOLDER_FIXTURE, "author", "workhorse-author", "run")

    assert calls == []


def test_an_interrupted_phase_resumes_its_run_dir_through_uv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = folder_run(tmp_path)
    calls = _recording_cli(run, monkeypatch, tmp_path)
    run.write_json(
        greenfield.ledger_path(run),
        [{"phase": "author", "run_dir": "author-author", "rc": 130, "wall_s": 5.0}],
    )
    launch = greenfield.runs_dir(run) / "author-author" / "launch.json"
    launch.parent.mkdir(parents=True)
    resume_argv = ["/old/ws/project/.venv/bin/workhorse-author", "run", "--resume-run", "/runs/author-author"]
    launch.write_text(json.dumps({"resume_argv": resume_argv}), encoding="utf-8")

    greenfield.run_phase(run, FOLDER_FIXTURE, "author", "workhorse-author", "run")

    assert calls == [[*uv_run(tmp_path, "workhorse-workflows"), "workhorse-author", "run", "--resume-run", "/runs/author-author"]]
    (entry,) = greenfield.phases_of(run)
    assert entry["rc"] == 0
    assert entry["wall_s"] >= 5.0


def test_an_interrupted_phase_without_a_launch_record_starts_fresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = folder_run(tmp_path)
    calls = _recording_cli(run, monkeypatch, tmp_path)
    run.write_json(
        greenfield.ledger_path(run),
        [{"phase": "author", "run_dir": "author-author", "rc": None, "wall_s": 0.0}],
    )

    greenfield.run_phase(run, FOLDER_FIXTURE, "author", "workhorse-author", "run")

    assert "--resume-run" not in calls[0]
    assert "--run-id" in calls[0]


def test_the_seed_is_recorded_and_never_rerun(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = folder_run(tmp_path)
    _seed_milestone_source(run)
    (run.benchmark.root / "records").mkdir()
    (run.benchmark.root / "records" / "0001.md").write_text("# one\n", encoding="utf-8")
    calls = _recording_cli(run, monkeypatch, tmp_path)

    greenfield.run_genesis(run, FOLDER_FIXTURE)

    assert [e["phase"] for e in greenfield.phases_of(run)] == ["genesis-api", "genesis-web", "seed"]
    assert len(calls) == 2

    def seeded_again(*_: object) -> None:
        raise AssertionError("the author edits what the seed wrote, so it must not be written twice")

    for name in ("seed_milestone", "seed_decision_records", "ignore_agent_runtime", "commit_baseline"):
        monkeypatch.setattr(greenfield, name, seeded_again)

    greenfield.run_genesis(run, FOLDER_FIXTURE)

    assert len(calls) == 2
    assert [e["phase"] for e in greenfield.phases_of(run)] == ["genesis-api", "genesis-web", "seed"]


def test_an_unfinished_phase_shows_in_the_report() -> None:
    lines = greenfield.phase_lines([{"phase": "coder", "run_dir": "coder-coder", "rc": None, "wall_s": 60.0}])
    assert any("unfinished" in line for line in lines)
