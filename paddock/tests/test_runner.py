"""Running a task: staging, the ledger, failure handling, and the read-only score rule."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from paddock import loader, seeds
from paddock.pointer import DIAGNOSTIC_MARKER, ResultPointer
from paddock.runner import RunError, execute

TASK = '''
from paddock import Score, step, task

task(name="demo", seed="acme", config="configs/test.toml")

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
    body = TASK.replace("configs/test.toml", "configs/absent.toml")
    with pytest.raises(RunError, match="does not exist"):
        run(repo, data_dir, store, body)


PARAMS_TASK = '''
from paddock import Score, step, task

task(name="demo", seed="acme", config="configs/test.toml")

@step()
def record(run):
    run.write_json(run.artifacts / "seen.json", {
        "defects": list(run.param_list("defects")),
        "budget": run.param_float("budget", 2400.0),
        "control": run.param_bool("control", True),
        "missing": run.param("nobody", "fallback"),
    })

def score(run):
    return Score(headline="read the knobs", detail=(), data={})
'''


def test_params_reach_the_steps_and_are_recorded(repo: Path, data_dir: Path, store: Path) -> None:
    result = run(
        repo,
        data_dir,
        store,
        PARAMS_TASK,
        params={"defects": "PD-1, PD-2", "budget": "600", "control": "no"},
    )
    seen = json.loads((result.stage / "artifacts" / "record" / "seen.json").read_text(encoding="utf-8"))
    assert seen == {
        "defects": ["PD-1", "PD-2"],
        "budget": 600.0,
        "control": False,
        "missing": "fallback",
    }
    ledger = json.loads((result.stage / "steps.json").read_text(encoding="utf-8"))
    assert ledger["params"] == {"defects": "PD-1, PD-2", "budget": "600", "control": "no"}
    # The tracked pointer says the run was narrowed, so it is never silently compared
    # against a full one.
    assert result.pointer_path is not None
    assert "budget=600" in ResultPointer.load(result.pointer_path).note


@pytest.mark.parametrize(
    ("body", "message"),
    [("budget", "not a number"), ("control", "not a boolean")],
)
def test_a_malformed_param_is_named(
    repo: Path, data_dir: Path, store: Path, body: str, message: str
) -> None:
    # A knob that does not parse fails the step that read it, by name — it is not
    # silently coerced into the default the task would have used anyway.
    result = run(repo, data_dir, store, PARAMS_TASK, params={body: "sideways"})
    assert not result.ok
    assert message in (result.outcomes[0].error or "")


def test_a_command_is_teed_to_stderr_while_it_runs(
    repo: Path, data_dir: Path, store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The log a step writes is three directories deep and named after a step that has not
    # finished yet, so `paddock run > run.log` is the only progress an operator — or the
    # agent polling on their behalf — can actually watch.
    run(repo, data_dir, store)
    assert "00-sh| hello" in capsys.readouterr().err


def test_quiet_suppresses_the_tee_without_touching_the_log(
    repo: Path, data_dir: Path, store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = run(repo, data_dir, store, echo=False)
    assert "hello" not in capsys.readouterr().err
    log = result.stage / "artifacts" / "touch" / "00-sh.log"
    assert "hello" in log.read_text(encoding="utf-8")


def test_a_scores_caveats_mark_the_pointer_note(
    repo: Path, data_dir: Path, store: Path
) -> None:
    # The scorecard already warns at length, but the scorecard is printed once to a
    # terminal and the pointer is what a later comparison actually reads. An honest
    # number and a compromised one look identical there once the warning is gone.
    body = TASK.replace(
        'data={"caught": 2})',
        'data={"caught": 2}, caveats=("operator gate parked: context.md",))',
    )
    result = run(repo, data_dir, store, body)
    pointer = ResultPointer.load(result.pointer_path)
    assert pointer.caveats == ["operator gate parked: context.md"]
    assert pointer.note.startswith(DIAGNOSTIC_MARKER)


def test_a_failed_step_is_a_caveat_the_runner_derives_itself(
    repo: Path, data_dir: Path, store: Path
) -> None:
    # This is the half a ruler cannot see: a pin that drifted or a build that aborted
    # fails a step *before* score() gets a turn, so nobody is left to declare it.
    body = TASK.replace(
        '    (run.repo / "made-by-the-step.txt").write_text("yes", encoding="utf-8")',
        '    raise RuntimeError("boom")',
    )
    result = run(repo, data_dir, store, body)
    pointer = ResultPointer.load(result.pointer_path)
    # The step that raised and the one skipped behind it are different facts.
    assert pointer.caveats == ["step 'touch' failed", "step 'fan_out' skipped"]
    assert pointer.note.startswith(DIAGNOSTIC_MARKER)


def stub(note: str, caveats: list[str]) -> ResultPointer:
    """A pointer with the archive fields filled in, so a test can vary only the note."""
    return ResultPointer(
        name="demo/x", repo_dir="x", sha256="0" * 64, bytes=1, note=note, caveats=caveats
    )


def test_a_caveated_result_cannot_be_written_with_a_clean_note() -> None:
    with pytest.raises(ValidationError, match="does not say so"):
        stub(note="87% clean", caveats=["operator gate parked"])


def test_the_marker_cannot_be_left_behind_on_a_clean_note() -> None:
    # Enforced in the other direction too: a marker that could arrive by accident —
    # a copied note, a caveat later removed — is a marker nobody would trust.
    with pytest.raises(ValidationError, match="records no"):
        stub(note=f"{DIAGNOSTIC_MARKER}87%", caveats=[])


def test_a_self_touch_reaches_the_pointer_not_just_the_log(
    repo: Path, data_dir: Path, store: Path
) -> None:
    # A warning is printed once to a terminal nobody kept. The pointer is what a later
    # comparison reads, so the round that reached past its pin has to be a diagnostic
    # there — same fail-close as a parked gate or a failed step.
    body = '''
from paddock import step, task

task(name="demo", seed="acme", config="configs/test.toml")

@step()
def sneak(run):
    (run.project / "README.md").write_text("patched mid-round", encoding="utf-8")
'''
    result = run(repo, data_dir, store, body, project=repo)
    pointer = ResultPointer.load(result.pointer_path)
    assert [c for c in pointer.caveats if c.startswith("self-touched: ")]
    assert pointer.note.startswith(DIAGNOSTIC_MARKER)
