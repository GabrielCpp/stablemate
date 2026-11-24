"""The greenfield round's inputs and the fixtures it reads beside the benchmark's tasks."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from fakes import DOCS, PRODUCTS, fake_run, folder_run, init_repo

from ostler.milestones import BOOKS_DIR
from stablemate_core import config as core_config
from paddock.runner import CommandResult, RoundInterrupted, Run
from paddock.tasks import greenfield, replay
from paddock.tasks.stablemate import TrialError, uv_run
from smoke import git

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

    kept = list(greenfield.artifacts_of(run).glob(f"products/*/milestones/m1/{greenfield.MILESTONE_FILE}"))
    assert len(kept) == 1, kept
    assert kept[0] == greenfield.produced_milestone(run, FIXTURE)
    assert not (run.stage / "docs" / "milestones").exists()
    assert (run.stage / BOOKS_DIR / "api").is_dir()


def test_a_missing_milestone_is_named(tmp_path: Path) -> None:
    with pytest.raises(TrialError, match="no milestone at"):
        greenfield.seed_milestone(fake_run(tmp_path), FIXTURE)


def test_decision_records_land_in_the_product_folder_and_no_docs_decisions_is_made(tmp_path: Path) -> None:
    run = fake_run(tmp_path)
    records = run.benchmark.root / "records"
    records.mkdir(parents=True)
    (records / "0001.md").write_text("# one\n", encoding="utf-8")

    greenfield.seed_decision_records(run, FIXTURE)

    kept = list(greenfield.artifacts_of(run).glob("products/*/0001.md"))
    assert [path.read_text(encoding="utf-8") for path in kept] == ["# one\n"]
    assert not (run.stage / "docs" / "decisions").exists()
    assert not (greenfield.artifacts_of(run) / "docs" / "decisions").exists()


def test_a_book_kept_in_the_repo_takes_the_records_in_its_product_folder(tmp_path: Path) -> None:
    run = fake_run(tmp_path)
    records = run.benchmark.root / "records"
    records.mkdir(parents=True)
    (records / "0001.md").write_text("# one\n", encoding="utf-8")
    replay.keep_book_in_repo(run.stage)

    greenfield.seed_decision_records(run, FIXTURE)

    assert (run.stage / "product" / "0001.md").read_text(encoding="utf-8") == "# one\n"
    assert not (run.stage / "docs" / "decisions").exists()


def test_a_fixture_has_no_decision_records_path() -> None:
    assert not hasattr(FIXTURE, "decision_records_path")


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


def test_a_folder_seeds_each_surfaces_book_in_its_member_folder_of_the_docs_home(tmp_path: Path) -> None:
    run = folder_run(tmp_path)
    _seed_milestone_source(run)

    greenfield.seed_milestone(run, FOLDER_FIXTURE)

    books = run.stage / DOCS / BOOKS_DIR
    assert (books / PRODUCTS[0] / "api" / "service.py").is_file()
    assert (books / PRODUCTS[1] / "web" / "service.py").is_file()
    assert not (books / "api").exists()
    assert not (books / "web").exists()


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
    kept = list(home.glob(f"products/*/milestones/m1/{greenfield.MILESTONE_FILE}"))
    assert len(kept) == 1, kept
    assert kept[0] == greenfield.produced_milestone(run, FOLDER_FIXTURE)
    assert not (home / "docs" / "milestones").exists()
    assert (home / BOOKS_DIR / PRODUCTS[1] / "web").is_dir()
    assert len(list(home.glob("products/*/0001.md"))) == 1
    assert not (home / "docs" / "decisions").exists()
    assert not (run.stage / PRODUCTS[0] / "docs" / "milestones").exists()


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


def test_the_rounds_own_ledger_never_dirties_the_repo_it_builds(tmp_path: Path) -> None:
    run = fake_run(tmp_path)
    init_repo(run.stage, {"main.go": "package main\n"})
    run.write_json(greenfield.runs_dir(run) / "genesis" / "run.json", {"rc": 0})

    greenfield.ignore_agent_runtime(run)
    greenfield.commit_baseline(run)
    run.write_json(greenfield.ledger_path(run), [{"phase": "coder"}])
    run.write_json(greenfield.runs_dir(run) / "coder" / "run.json", {"rc": None})

    assert git(run.stage, "status", "--porcelain") == ""
    assert git(run.stage, "ls-files", "artifacts") == ""


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
    assert (entry["phase"], entry["rc"], entry["run_dir"]) == ("author", rc, f"author-{greenfield.phase_run_id(run, 'author')}")


def test_a_fresh_phase_names_its_run_dir_and_records_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = folder_run(tmp_path)
    calls = _recording_cli(run, monkeypatch, tmp_path)

    greenfield.run_phase(run, FOLDER_FIXTURE, "coder", "workhorse-coder", "run")

    argv = calls[0]
    assert argv[argv.index("--run-id") + 1] == "task-aaaaaaaaaaaa-bbbbbbbbbbbb-3-coder"
    (entry,) = greenfield.phases_of(run)
    assert (entry["phase"], entry["rc"], entry["run_dir"]) == (
        "coder", 0, "coder-task-aaaaaaaaaaaa-bbbbbbbbbbbb-3-coder")


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


def test_genesis_accepts_every_param_the_round_passes(tmp_path: Path) -> None:
    genesis = pytest.importorskip("workhorse_workflows.coder.genesis.flow").Genesis
    params = json.loads(FIXTURE.params(tmp_path, FIXTURE.surfaces[0]))
    assert set(params) <= set(genesis.model_fields)
    assert params["assistants"] == "claude,codex"


@pytest.mark.parametrize("make_run", [fake_run, folder_run])
def test_a_phase_keeps_its_artifacts_inside_the_round(tmp_path: Path, make_run: Callable[[Path], Run]) -> None:
    run = make_run(tmp_path)
    env = greenfield.phase_env(run, FIXTURE, "author")
    assert Path(env[core_config.ARTIFACTS_DIR_ENV]).is_relative_to(tmp_path)


def test_epics_are_read_from_the_rounds_artifacts_by_their_slug(tmp_path: Path) -> None:
    run = fake_run(tmp_path)
    milestone = greenfield.produced_milestone(run, FIXTURE)
    milestone.parent.mkdir(parents=True)
    milestone.write_text("---\nepics: [shorten-links]\n---\n", encoding="utf-8")
    for folder, slug in (("STAG-01", "shorten-links"), ("STAG-02", "stray")):
        epic = greenfield.artifacts_of(run) / "epics" / folder / "epic.md"
        epic.parent.mkdir(parents=True)
        epic.write_text(f"---\nslug: {slug}\n---\n", encoding="utf-8")
    assert greenfield.unlisted_epics(run, FIXTURE) == ["STAG-02"]
