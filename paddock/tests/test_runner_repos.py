"""Staging a folder of repositories: the copied history, the ledger's repos and the data commit."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from smoke import git
from test_runner import MakeBenchmark, run, smoke

from paddock import names
from paddock.loader import Benchmark
from paddock.names import RunName
from paddock.runner import Run, RunError, execute


def add_repo(parent: Path, name: str) -> Path:
    repo = parent / name
    repo.mkdir(parents=True)
    (repo / "README.md").write_text(f"{name}\n", encoding="utf-8")
    git(repo, "init", "--initial-branch", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "initial")
    return repo


def make_folder_of_repos(benchmark: Benchmark) -> tuple[Path, Path]:
    for entry in benchmark.data.iterdir():
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    return add_repo(benchmark.data, "api"), add_repo(benchmark.data, "web")


def test_a_folder_of_repos_is_staged_under_each_name_with_its_history(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    benchmark = make_benchmark()
    api, _web = make_folder_of_repos(benchmark)
    (api / "more.txt").write_text("more\n", encoding="utf-8")
    git(api, "add", "-A")
    git(api, "commit", "-m", "second")
    result = execute(*smoke(benchmark), root=root, checkout=repo)
    assert (result.stage / "api" / "more.txt").is_file()
    assert (result.stage / "web" / "README.md").read_text(encoding="utf-8") == "web\n"
    assert git(result.stage / "api", "log", "--format=%s").splitlines() == ["second", "initial"]
    assert git(result.stage / "api", "remote") == ""
    assert git(result.stage / "web", "remote") == ""


def test_a_folders_data_commit_is_a_digest_that_follows_each_repo(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    benchmark = make_benchmark()
    api, web = make_folder_of_repos(benchmark)
    lines = f"api {git(api, 'rev-parse', 'HEAD')}\nweb {git(web, 'rev-parse', 'HEAD')}\n"
    first = execute(*smoke(benchmark), root=root, checkout=repo)
    assert first.name.data_commit == hashlib.sha1(lines.encode("utf-8")).hexdigest()
    (web / "more.txt").write_text("more\n", encoding="utf-8")
    git(web, "add", "-A")
    git(web, "commit", "-m", "more")
    second = execute(*smoke(benchmark), root=root, checkout=repo)
    assert second.name.data_commit != first.name.data_commit


def test_the_ledger_lists_each_staged_repos_head(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    benchmark = make_benchmark()
    api, web = make_folder_of_repos(benchmark)
    result = execute(*smoke(benchmark), root=root, checkout=repo)
    ledger = json.loads((result.result / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["repos"] == {"api": git(api, "rev-parse", "HEAD"), "web": git(web, "rev-parse", "HEAD")}


def test_a_single_repo_ledger_lists_the_benchmark_name_and_the_data_head(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    result = run(make_benchmark, root, repo)
    ledger = json.loads((result.result / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["repos"] == {"smoke": ledger["data_commit"]}


def test_a_child_without_a_repository_is_refused_by_name(
    make_benchmark: MakeBenchmark, root: Path, repo: Path
) -> None:
    benchmark = make_benchmark()
    make_folder_of_repos(benchmark)
    (benchmark.data / "notes").mkdir()
    with pytest.raises(RunError, match="notes"):
        execute(*smoke(benchmark), root=root, checkout=repo)


def bare_run(benchmark: Benchmark, workspace: Path) -> Run:
    return Run(
        task=benchmark.task("smoke"),
        name=RunName(benchmark.name, "smoke", "d", "s", 0),
        stage=workspace / "stage",
        scratch=workspace / "scratch",
        workspace=workspace,
        config=workspace / "config.toml",
        data=benchmark.data,
        benchmark=benchmark,
        echo=False,
    )


def test_a_single_repo_runs_repos_is_the_benchmark_name_and_the_stage(
    make_benchmark: MakeBenchmark, tmp_path: Path
) -> None:
    benchmark = make_benchmark()
    handle = bare_run(benchmark, tmp_path / "ws")
    assert dict(handle.repos) == {"smoke": handle.stage}
    assert handle.repo == handle.stage


def test_a_folder_of_repos_run_maps_each_child_to_its_place_in_the_stage(
    make_benchmark: MakeBenchmark, tmp_path: Path
) -> None:
    benchmark = make_benchmark()
    make_folder_of_repos(benchmark)
    handle = bare_run(benchmark, tmp_path / "ws")
    assert dict(handle.repos) == {"api": handle.stage / "api", "web": handle.stage / "web"}


def test_repo_on_a_folder_of_repos_names_the_repos_and_the_way_to_reach_one(
    make_benchmark: MakeBenchmark, tmp_path: Path
) -> None:
    benchmark = make_benchmark()
    make_folder_of_repos(benchmark)
    handle = bare_run(benchmark, tmp_path / "ws")
    with pytest.raises(RunError, match=r"api, web.*run\.repos"):
        handle.repo


def test_cli_without_a_cwd_on_a_folder_of_repos_raises(
    make_benchmark: MakeBenchmark, tmp_path: Path
) -> None:
    benchmark = make_benchmark()
    make_folder_of_repos(benchmark)
    handle = bare_run(benchmark, tmp_path / "ws")
    with pytest.raises(RunError, match="several repos"):
        handle.cli("true")


def test_cli_in_one_repo_of_a_folder_of_repos_works(
    make_benchmark: MakeBenchmark, tmp_path: Path
) -> None:
    benchmark = make_benchmark()
    make_folder_of_repos(benchmark)
    handle = bare_run(benchmark, tmp_path / "ws")
    handle.stage.mkdir(parents=True)
    (handle.stage / "api").mkdir()
    assert handle.cli("true", cwd=handle.repos["api"]).ok


def test_data_commit_reads_a_repository_and_a_folder_of_repositories(tmp_path: Path) -> None:
    single = add_repo(tmp_path, "single")
    assert names.data_commit(single) == names.git_head(single)
    folder = tmp_path / "folder"
    api = add_repo(folder, "api")
    web = add_repo(folder, "web")
    (folder / ".hidden").mkdir()
    lines = f"api {names.git_head(api)}\nweb {names.git_head(web)}\n"
    assert names.data_commit(folder) == hashlib.sha1(lines.encode("utf-8")).hexdigest()
    git(web, "commit", "--allow-empty", "-m", "next")
    assert names.data_commit(folder) != hashlib.sha1(lines.encode("utf-8")).hexdigest()


def test_data_commit_is_empty_when_a_child_has_no_commit_or_there_is_none(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    assert names.data_commit(folder) == ""
    add_repo(folder, "api")
    (folder / "blank").mkdir()
    git(folder / "blank", "init", "--initial-branch", "main")
    assert names.data_commit(folder) == ""
