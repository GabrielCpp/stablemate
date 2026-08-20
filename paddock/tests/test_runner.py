"""Running a task: staging, the ledger, failure handling, and the read-only score rule."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from paddock import loader, seeds
from paddock.pointer import ResultPointer
from paddock.runner import RunError, execute

TASK = '''
from paddock import Score, step, task

task(name="demo", seed="acme", config="benchmarks/configs/test.toml")

@step()
def touch(run):
    (run.repo / "made-by-the-step.txt").write_text("yes", encoding="utf-8")
    run.cli("/bin/sh", "-c", "echo hello", check=True)

@step()
def fan_out(run):
    tree = run.workdir("trial-1")
    (tree / "scratch-only.txt").write_text("not in the result", encoding="utf-8")
    (run.artifacts / "kept.txt").write_text("kept on purpose", encoding="utf-8")

def score(run):
    return Score(headline="2/2 fine", detail=("one", "two"), data={"caught": 2})
'''


def prepare(repo: Path, data_dir: Path, store: Path, body: str = TASK) -> object:
    seeds.capture(repo, name="acme", data_dir=data_dir, store=store)
    (data_dir / "tasks" / "demo.py").write_text(body, encoding="utf-8")
    return loader.load_named(data_dir, "demo")


def run(repo: Path, data_dir: Path, store: Path, body: str = TASK, **kwargs: object):
    task = prepare(repo, data_dir, store, body)
    return execute(task, label="t1", data_dir=data_dir, store=store, **kwargs)  # ty: ignore[invalid-argument-type]


def test_a_run_stages_the_repo_the_artifacts_and_the_ledger(
    repo: Path, data_dir: Path, store: Path
) -> None:
    result = run(repo, data_dir, store)
    assert result.ok
    assert (result.stage / "acme-api" / "made-by-the-step.txt").is_file()
    assert (result.stage / "artifacts" / "fan_out" / "kept.txt").is_file()
    ledger = json.loads((result.stage / "steps.json").read_text(encoding="utf-8"))
    assert [step["name"] for step in ledger["steps"]] == ["touch", "fan_out"]
    assert ledger["steps"][0]["commands"] == [["/bin/sh", "-c", "echo hello"]]
    assert ledger["seed"]["name"] == "acme"


def test_scratch_stays_out_of_the_result(repo: Path, data_dir: Path, store: Path) -> None:
    # A task that fans out one tree per trial would otherwise seal nine repos into a zip
    # nobody keeps; what a step wants preserved it copies into its artifact directory.
    result = run(repo, data_dir, store)
    assert not list(result.stage.rglob("scratch-only.txt"))
    assert (result.stage.parent / "scratch" / "trial-1" / "scratch-only.txt").is_file()


def test_the_score_is_written_and_the_result_is_sealed(
    repo: Path, data_dir: Path, store: Path
) -> None:
    result = run(repo, data_dir, store)
    assert result.score is not None
    assert result.score.headline == "2/2 fine"
    assert json.loads((result.stage / "score.json").read_text(encoding="utf-8"))["data"] == {
        "caught": 2
    }
    assert result.zip_path is not None and result.zip_path.exists()
    assert result.pointer_path is not None
    pointer = ResultPointer.load(result.pointer_path)
    assert pointer.task == "demo"
    assert pointer.scored is True
    pointer.verify(result.zip_path)


def test_a_score_that_mutates_the_result_is_refused(
    repo: Path, data_dir: Path, store: Path
) -> None:
    # Decision 14: scored and unscored runs must produce byte-identical results apart
    # from score.json, or the zip records the scoring instead of the run.
    body = TASK.replace(
        "def score(run):\n",
        'def score(run):\n    (run.repo / "written-by-score.txt").write_text("no", encoding="utf-8")\n',
    )
    with pytest.raises(RunError, match="read-only"):
        run(repo, data_dir, store, body)


def test_a_score_may_still_log_into_its_own_artifact_directory(
    repo: Path, data_dir: Path, store: Path
) -> None:
    body = TASK.replace(
        "def score(run):\n",
        'def score(run):\n    (run.artifacts / "judge.log").write_text("ok", encoding="utf-8")\n',
    )
    result = run(repo, data_dir, store, body)
    assert (result.stage / "artifacts" / "score" / "judge.log").is_file()


def test_a_failing_step_stops_the_run_and_the_rest_are_skipped(
    repo: Path, data_dir: Path, store: Path
) -> None:
    # A later step's meaning is conditional on the earlier ones having happened, so a
    # result produced past a failure scores as something rather than as nothing.
    body = TASK.replace(
        '    (run.repo / "made-by-the-step.txt").write_text("yes", encoding="utf-8")',
        '    raise RuntimeError("boom")',
    )
    result = run(repo, data_dir, store, body)
    assert not result.ok
    assert [(o.name, o.status) for o in result.outcomes] == [("touch", "failed"), ("fan_out", "skipped")]
    assert "boom" in result.outcomes[0].error


def test_a_nonzero_command_with_check_fails_its_step(
    repo: Path, data_dir: Path, store: Path
) -> None:
    body = TASK.replace('"echo hello"', '"exit 3"')
    result = run(repo, data_dir, store, body)
    assert result.outcomes[0].status == "failed"
    assert "exited 3" in result.outcomes[0].error


def test_no_seal_leaves_the_stage_and_writes_no_pointer(
    repo: Path, data_dir: Path, store: Path
) -> None:
    result = run(repo, data_dir, store, seal=False)
    assert result.zip_path is None
    assert result.pointer_path is None
    assert (result.stage / "acme-api").is_dir()


def test_a_missing_config_is_named_before_anything_runs(
    repo: Path, data_dir: Path, store: Path
) -> None:
    body = TASK.replace("benchmarks/configs/test.toml", "benchmarks/configs/absent.toml")
    with pytest.raises(RunError, match="does not exist"):
        run(repo, data_dir, store, body)
