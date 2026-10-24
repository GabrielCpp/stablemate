"""What `paddock` resolves before it runs anything, and the commands that remain."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from paddock import paths
from paddock.cli import main
from paddock.loader import Benchmark

from smoke import git

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
