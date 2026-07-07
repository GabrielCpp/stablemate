"""Tests for groom.docker_io's git-diff helpers, with subprocess.run mocked
out so nothing here actually shells out to docker.

Run: uv run pytest tests/test_docker_io.py
"""
from __future__ import annotations

import subprocess
from unittest.mock import patch

from groom import docker_io


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_list_container_ids_returns_short_id_set():
    out = "abcdef012345678\n0123456789abcdef\n\n"  # blank line ignored
    with patch.object(docker_io.subprocess, "run", return_value=_completed(stdout=out)):
        ids = docker_io.list_container_ids()
    assert ids == {"abcdef012345", "0123456789ab"}  # truncated to 12


def test_list_container_ids_returns_none_on_docker_failure():
    # None (not empty set) so a caller can tell "docker down" from "no containers".
    with patch.object(docker_io.subprocess, "run", return_value=_completed(returncode=1)):
        assert docker_io.list_container_ids() is None


def test_list_container_ids_empty_when_no_containers():
    with patch.object(docker_io.subprocess, "run", return_value=_completed(stdout="")):
        assert docker_io.list_container_ids() == set()


def test_find_repo_dir_extracts_parent_of_dot_git():
    with patch.object(
        docker_io.subprocess, "run", return_value=_completed(stdout="/vol/Predykt/.git\n")
    ):
        assert docker_io.find_repo_dir("vol-1") == "Predykt"


def test_find_repo_dir_returns_empty_when_none_found():
    with patch.object(docker_io.subprocess, "run", return_value=_completed(stdout="")):
        assert docker_io.find_repo_dir("vol-1") == ""


def test_find_repo_dir_returns_empty_on_docker_failure():
    with patch.object(docker_io.subprocess, "run", return_value=_completed(returncode=1)):
        assert docker_io.find_repo_dir("vol-1") == ""


def test_git_diff_returns_empty_when_no_repo_found():
    with patch.object(docker_io, "find_repo_dir", return_value=""):
        assert docker_io.git_diff("vol-1") == ""


def test_git_diff_returns_stdout_on_success():
    diff_text = "diff --git a/x b/x\n+added line\n"
    with patch.object(docker_io, "find_repo_dir", return_value="Predykt"), \
         patch.object(docker_io.subprocess, "run", return_value=_completed(stdout=diff_text)) as run:
        result = docker_io.git_diff("vol-1")
    assert result == diff_text
    args = run.call_args[0][0]
    assert "/vol/Predykt" in args
    assert "safe.directory=*" in args


def test_git_diff_returns_empty_on_git_failure():
    with patch.object(docker_io, "find_repo_dir", return_value="Predykt"), \
         patch.object(docker_io.subprocess, "run", return_value=_completed(returncode=128)):
        assert docker_io.git_diff("vol-1") == ""


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
