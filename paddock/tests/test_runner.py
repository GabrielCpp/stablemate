"""Running a task: the run name, the copied data, the merged config, the ledger and the read-only score rule."""

from __future__ import annotations

import json
import threading
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from paddock import loader, names, paths
from paddock.loader import Benchmark
from paddock.runner import Run, RunError, RunResult, execute

from smoke import BASE_CONFIG, SMOKE_TASKS, git

MakeBenchmark = Callable[..., Benchmark]


def run(
    make_benchmark: MakeBenchmark, root: Path, checkout: Path, body: str = SMOKE_TASKS, **kwargs: Any
) -> RunResult:
    return execute(make_benchmark(body), root=root, checkout=checkout, **kwargs)


def test_a_run_is_named_by_its_axes(make_benchmark: MakeBenchmark, root: Path, repo: Path) -> None:
    result = run(make_benchmark, root, repo)
    data = root / "gold" / "smoke" / "data"
    expected = f"smoke/smoke/{git(data, 'rev-parse', 'HEAD')[:12]}-{git(repo, 'rev-parse', 'HEAD')[:12]}/1"
    assert str(result.name) == expected
    assert result.workspace == root / "workspace" / expected
    assert result.stage == result.workspace / "stage"


def test_the_stablemate_sha_is_the_checkout_paddock_is_imported_from(
    make_benchmark: MakeBenchmark, root: Path
) -> None:
    result = execute(make_benchmark(), root=root, pin_project=False)
    assert result.name.stablemate == git(paths.checkout_root(), "rev-parse", "HEAD")


def test_a_repeat_of_the_same_name_takes_the_next_number(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    first = run(make_benchmark, root, repo)
    second = execute(loader.load_benchmark(root, "smoke"), root=root, checkout=repo)
    assert (first.name.n, second.name.n) == (1, 2)
    assert first.name.key == second.name.key


def test_a_new_data_commit_is_a_new_name(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    first = run(make_benchmark, root, repo)
    data = root / "gold" / "smoke" / "data"
    (data / "more.txt").write_text("more\n", encoding="utf-8")
    git(data, "add", "-A")
    git(data, "commit", "-m", "more")
    second = execute(loader.load_benchmark(root, "smoke"), root=root, checkout=repo)
    assert second.name.data_commit != first.name.data_commit
    assert second.name.n == 1


def test_the_data_commit_is_recorded_in_the_ledger(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    result = run(make_benchmark, root, repo)
    ledger = json.loads((result.result / "ledger.json").read_text(encoding="utf-8"))
    data = root / "gold" / "smoke" / "data"
    assert ledger["data_commit"] == git(data, "rev-parse", "HEAD")
    assert ledger["stablemate"] == git(repo, "rev-parse", "HEAD")
    assert ledger["name"] == str(result.name)
    assert [step["name"] for step in ledger["steps"]] == ["touch"]
    assert ledger["steps"][0]["commands"] == [["/bin/sh", "-c", "echo hello"]]


def test_the_stage_is_the_data_at_head_with_no_remote(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    benchmark = make_benchmark()
    (benchmark.data / "README.md").write_text("edited, not committed\n", encoding="utf-8")
    result = execute(benchmark, root=root, checkout=repo)
    assert (result.stage / "app.py").is_file()
    assert (result.stage / "README.md").read_text(encoding="utf-8") == "smoke\n"
    assert (result.stage / "made-by-the-step.txt").is_file()
    assert git(result.stage, "remote") == ""
    assert git(result.stage, "rev-parse", "HEAD") == result.name.data_commit


def test_the_task_override_is_laid_over_the_base_config(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    body = SMOKE_TASKS.replace(
        'task(name="smoke")',
        'task(name="smoke", config={"profiles": {"claude": {"model": "task-model"}}, "extra": 1})',
    )
    result = run(make_benchmark, root, repo, body)
    merged = tomllib.loads((result.workspace / "config.toml").read_text(encoding="utf-8"))
    assert merged == {
        "library_dir": "/nowhere",
        "default_cli": "claude",
        "profiles": {"claude": {"cli": "claude", "model": "task-model"}},
        "extra": 1,
    }


def test_no_override_leaves_the_base_config_verbatim(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    base = BASE_CONFIG.replace('library_dir = "/nowhere"', "# kept as written\nlibrary_dir   =   '/nowhere'")
    benchmark = make_benchmark(base=base)
    result = execute(benchmark, root=root, checkout=repo)
    assert (result.workspace / "config.toml").read_text(encoding="utf-8") == base


def test_a_step_gets_the_merged_config_and_nothing_from_the_command_line(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    body = SMOKE_TASKS.replace(
        '    run.cli("/bin/sh", "-c", "echo hello", check=True)\n',
        '    assert not hasattr(run, "params")\n'
        '    assert not hasattr(run, "param")\n'
        '    (run.artifacts / "config-path.txt").write_text(str(run.config), encoding="utf-8")\n',
    )
    result = run(make_benchmark, root, repo, body)
    assert result.ok
    recorded = (result.workspace / "artifacts" / "touch" / "config-path.txt").read_text(encoding="utf-8")
    assert Path(recorded) == result.workspace / "config.toml"


def test_scratch_and_artifacts_stay_out_of_the_stage(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    body = SMOKE_TASKS.replace(
        '    run.cli("/bin/sh", "-c", "echo hello", check=True)\n',
        '    (run.workdir("trial-1") / "scratch-only.txt").write_text("no", encoding="utf-8")\n'
        '    (run.artifacts / "kept.txt").write_text("yes", encoding="utf-8")\n',
    )
    result = run(make_benchmark, root, repo, body)
    assert not list(result.stage.rglob("scratch-only.txt"))
    assert not list(result.stage.rglob("kept.txt"))
    assert (result.workspace / "scratch" / "trial-1" / "scratch-only.txt").is_file()
    assert (result.workspace / "artifacts" / "touch" / "kept.txt").is_file()


def test_the_score_is_written_next_to_the_stage(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    result = run(make_benchmark, root, repo)
    assert result.score is not None
    assert result.score.headline == "1/1 fine"
    written = json.loads((result.result / "score.json").read_text(encoding="utf-8"))
    assert written["data"] == {"caught": 1}


def test_a_score_that_mutates_the_result_is_refused(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    body = SMOKE_TASKS.replace(
        "def score(run):\n",
        'def score(run):\n    (run.repo / "written-by-score.txt").write_text("no", encoding="utf-8")\n',
    )
    with pytest.raises(RunError, match="read-only"):
        run(make_benchmark, root, repo, body)


def test_a_score_may_still_log_into_its_own_artifact_directory(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    body = SMOKE_TASKS.replace(
        "def score(run):\n",
        'def score(run):\n    (run.artifacts / "judge.log").write_text("ok", encoding="utf-8")\n',
    )
    result = run(make_benchmark, root, repo, body)
    assert (result.workspace / "artifacts" / "score" / "judge.log").is_file()


FAILING = SMOKE_TASKS.replace(
    '    (run.repo / "made-by-the-step.txt").write_text("yes", encoding="utf-8")',
    '    raise RuntimeError("boom")',
) + '''
@step()
def after(run):
    pass
'''


def test_a_failing_step_stops_the_run_and_the_rest_are_skipped(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    result = run(make_benchmark, root, repo, FAILING)
    assert not result.ok
    assert [(o.name, o.status) for o in result.outcomes] == [("touch", "failed"), ("after", "skipped")]
    assert "boom" in result.outcomes[0].error


def test_a_failed_step_is_a_caveat_in_the_ledger(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    result = run(make_benchmark, root, repo, FAILING)
    ledger = json.loads((result.result / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["caveats"] == ["step 'touch' failed", "step 'after' skipped"]


def test_a_nonzero_command_with_check_fails_its_step(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    body = SMOKE_TASKS.replace('"echo hello"', '"exit 3"')
    result = run(make_benchmark, root, repo, body)
    assert result.outcomes[0].status == "failed"
    assert "exited 3" in result.outcomes[0].error


def test_a_scores_caveats_reach_the_ledger(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    body = SMOKE_TASKS.replace(
        'data={"caught": 1})',
        'data={"caught": 1}, caveats=("operator gate parked: context.md",))',
    )
    result = run(make_benchmark, root, repo, body)
    ledger = json.loads((result.result / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["caveats"] == ["operator gate parked: context.md"]


def test_a_self_touch_reaches_the_ledger(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    body = SMOKE_TASKS.replace(
        '    (run.repo / "made-by-the-step.txt").write_text("yes", encoding="utf-8")',
        '    (run.project / "README.md").write_text("patched mid-round", encoding="utf-8")',
    )
    result = run(make_benchmark, root, repo, body)
    ledger = json.loads((result.result / "ledger.json").read_text(encoding="utf-8"))
    assert [c for c in ledger["caveats"] if c.startswith("self-touched: ")]


def test_a_command_is_teed_to_stderr_while_it_runs(
    make_benchmark: MakeBenchmark, root: Path, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(make_benchmark, root, repo)
    assert "00-sh| hello" in capsys.readouterr().err


def test_quiet_suppresses_the_tee_without_touching_the_log(
    make_benchmark: MakeBenchmark, root: Path, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = run(make_benchmark, root, repo, echo=False)
    assert "hello" not in capsys.readouterr().err
    log = result.workspace / "artifacts" / "touch" / "00-sh.log"
    assert "hello" in log.read_text(encoding="utf-8")


def test_a_data_directory_that_is_not_a_repository_is_refused(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    benchmark = make_benchmark()
    (benchmark.data / ".git").rename(benchmark.data / "git-moved")
    with pytest.raises(RunError, match="not a git repository"):
        execute(benchmark, root=root, checkout=repo)


@pytest.mark.stress
def test_a_json_file_is_never_readable_half_written(
    make_benchmark: MakeBenchmark, root: Path, tmp_path: Path
) -> None:
    """A reader polling one of these files sees the old bytes or the new ones, never none."""
    benchmark = make_benchmark()
    handle = Run(
        task=benchmark.task,
        name=names.RunName("smoke", "smoke", "a" * 12, "b" * 12, 1),
        stage=tmp_path / "stage",
        scratch=tmp_path / "scratch",
        workspace=tmp_path,
        config=tmp_path / "config.toml",
        data=benchmark.data,
        benchmark=benchmark,
    )
    path = tmp_path / "ledger.json"
    handle.write_json(path, {"steps": []})

    torn: list[Exception] = []
    stop = threading.Event()

    def poll() -> None:
        while not stop.is_set():
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except Exception as err:  # noqa: BLE001 - the failure is the assertion
                torn.append(err)
                return

    reader = threading.Thread(target=poll)
    reader.start()
    try:
        for n in range(400):
            handle.write_json(path, {"steps": [{"name": f"step-{n}"}] * 40})
    finally:
        stop.set()
        reader.join(timeout=10)

    assert not torn, f"a reader saw a half-written file: {torn[0]!r}"


def test_a_result_is_a_folder_of_four_entries(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    result = run(make_benchmark, root, repo)
    assert result.result == root / "results" / str(result.name)
    assert sorted(entry.name for entry in result.result.iterdir()) == [
        "config.toml", "ledger.json", "score.json", "stage",
    ]
    assert (result.result / "config.toml").read_bytes() == (result.workspace / "config.toml").read_bytes()
    assert git(result.result / "stage", "rev-parse", "HEAD") == result.name.data_commit


def test_the_result_stage_matches_the_after_state(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    result = run(make_benchmark, root, repo)
    kept = result.result / "stage"
    assert (kept / "made-by-the-step.txt").is_file()
    here = sorted(p.relative_to(result.stage).as_posix() for p in result.stage.rglob("*") if ".git/" not in p.as_posix())
    there = sorted(p.relative_to(kept).as_posix() for p in kept.rglob("*") if ".git/" not in p.as_posix())
    assert here == there


def test_the_ledger_records_each_commands_exit_code(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    result = run(make_benchmark, root, repo)
    ledger = json.loads((result.result / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["steps"][0]["exit_codes"] == [0]


def test_a_commands_environment_names_the_merged_config(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    body = SMOKE_TASKS.replace(
        '    run.cli("/bin/sh", "-c", "echo hello", check=True)\n',
        '    run.cli("/bin/sh", "-c", "echo $STABLEMATE_CONFIG > seen.txt", check=True)\n',
    )
    result = run(make_benchmark, root, repo, body)
    seen = (result.stage / "seen.txt").read_text(encoding="utf-8").strip()
    assert Path(seen) == result.workspace / "config.toml"


def test_a_step_reads_the_tasks_inputs_and_the_benchmark(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    body = SMOKE_TASKS.replace(
        'task(name="smoke")', 'task(name="smoke", inputs={"budget": 2.5, "only": ["a", "b"]})'
    ).replace(
        '    run.cli("/bin/sh", "-c", "echo hello", check=True)\n',
        '    assert run.inputs["budget"] == 2.5\n'
        '    assert run.inputs["only"] == ["a", "b"]\n'
        '    assert run.benchmark.name == "smoke"\n'
        '    assert run.benchmark.root == run.benchmark.data.parent\n'
        '    assert run.benchmark.root.joinpath("tasks.py").is_file()\n',
    )
    assert run(make_benchmark, root, repo, body).ok
