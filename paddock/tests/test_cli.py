"""What `paddock` resolves before it runs anything, and the commands that remain."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from paddock import paths
from paddock.cli import main
from paddock.loader import Benchmark

from smoke import INTERRUPTIBLE_TASKS, git

MakeBenchmark = Callable[..., Benchmark]


def test_the_benchmark_root_is_the_home_configs_paddock_dir(root: Path) -> None:
    assert paths.root() == root.resolve()


def test_the_checkout_is_the_repository_paddock_is_imported_from() -> None:
    assert (paths.checkout_root() / "paddock" / "paddock" / "cli.py").is_file()


def test_list_sees_the_benchmark(
    make_benchmark: MakeBenchmark, capsys: pytest.CaptureFixture[str]
) -> None:
    make_benchmark()
    with pytest.raises(SystemExit) as stopped:
        main(["list"])
    assert stopped.value.code == 0
    assert capsys.readouterr().out.startswith("smoke  smoke  1 steps  scored")


TWO_TASKS = '''
from paddock import Score, score, step, task

task(name="alpha")

@step()
def mark(run):
    (run.repo / "alpha.txt").write_text("a", encoding="utf-8")

@score()
def grade_alpha(run):
    return Score(headline="alpha scored")

task(name="beta")

@step()
def mark_beta(run):
    (run.repo / "beta.txt").write_text("b", encoding="utf-8")

@step()
def mark_more(run):
    pass
'''


def test_list_prints_one_line_per_task(
    make_benchmark: MakeBenchmark, capsys: pytest.CaptureFixture[str]
) -> None:
    make_benchmark(TWO_TASKS)
    with pytest.raises(SystemExit):
        main(["list"])
    assert capsys.readouterr().out.splitlines() == [
        "smoke  alpha  1 steps  scored",
        "smoke  beta  2 steps  unscored",
    ]


def test_run_picks_the_task_by_name(
    make_benchmark: MakeBenchmark, capsys: pytest.CaptureFixture[str]
) -> None:
    benchmark = make_benchmark(TWO_TASKS)
    with pytest.raises(SystemExit) as stopped:
        main(["run", "smoke", "beta", "--no-pin-project", "--quiet"])
    assert stopped.value.code == 0
    out = capsys.readouterr().out
    assert "run     smoke/beta/" in out
    assert "ok   mark_beta" in out
    assert "ok   mark  " not in out
    assert "alpha scored" not in out
    assert benchmark.task("beta").name == "beta"


def test_run_of_an_unknown_task_names_the_known_ones(
    make_benchmark: MakeBenchmark, caplog: pytest.LogCaptureFixture
) -> None:
    make_benchmark(TWO_TASKS)
    with pytest.raises(SystemExit) as stopped:
        main(["run", "smoke", "gamma", "--no-pin-project", "--quiet"])
    assert stopped.value.code == 1
    assert "Known: alpha, beta" in caplog.text


def test_list_on_an_empty_root_says_where_it_looked(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        main(["list"])
    assert str(root.resolve() / "gold") in capsys.readouterr().out


def test_run_takes_a_benchmark_and_a_task(
    make_benchmark: MakeBenchmark, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    benchmark = make_benchmark()
    with pytest.raises(SystemExit) as stopped:
        main(["run", "smoke", "smoke", "--no-pin-project", "--quiet"])
    assert stopped.value.code == 0
    out = capsys.readouterr().out
    assert f"run     smoke/smoke/{git(benchmark.data, 'rev-parse', 'HEAD')[:12]}-" in out
    assert "1/1 fine" in out


@pytest.mark.parametrize("flag", ["--param", "--label", "--keep", "--no-seal"])
def test_the_flags_that_changed_a_run_from_the_command_line_are_gone(
    make_benchmark: MakeBenchmark, flag: str
) -> None:
    make_benchmark()
    with pytest.raises(SystemExit) as stopped:
        main(["run", "smoke", "smoke", flag, "x=1"])
    assert stopped.value.code == 2


@pytest.mark.parametrize("command", ["capture", "unpack", "fetch", "seed"])
def test_the_seed_commands_are_gone(command: str) -> None:
    with pytest.raises(SystemExit) as stopped:
        main([command])
    assert stopped.value.code == 2


def test_an_interrupted_run_exits_130_naming_the_resume_command_and_resume_finishes_it(
    make_benchmark: MakeBenchmark, capsys: pytest.CaptureFixture[str]
) -> None:
    benchmark = make_benchmark(INTERRUPTIBLE_TASKS)
    stop = benchmark.root / "stop"
    stop.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit) as stopped:
        main(["run", "smoke", "smoke", "--no-pin-project", "--quiet"])
    assert stopped.value.code == 130
    assert "paddock resume smoke smoke 1" in capsys.readouterr().err
    stop.unlink()
    with pytest.raises(SystemExit) as resumed:
        main(["resume", "smoke", "smoke", "1", "--quiet"])
    assert resumed.value.code == 0
    out = capsys.readouterr().out
    assert "run     smoke/smoke/" in out
    assert "ok   second" in out


def test_resume_with_nothing_to_resume_exits_1(
    make_benchmark: MakeBenchmark, caplog: pytest.LogCaptureFixture
) -> None:
    make_benchmark(TWO_TASKS)
    with pytest.raises(SystemExit) as stopped:
        main(["resume", "smoke", "alpha", "--quiet"])
    assert stopped.value.code == 1
    assert "no workspace holds" in caplog.text
