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


def test_grep_awaiting_files_prunes_heavy_dirs_and_parses_paths():
    captured = {}

    def _fake_run(args, **kwargs):
        captured["args"] = args
        return _completed(stdout="/vol/docs/a.md\n/vol/docs/b.md\n")

    with patch.object(docker_io.subprocess, "run", _fake_run):
        paths = docker_io.grep_awaiting_files("workhorse_workspace")

    assert paths == ["docs/a.md", "docs/b.md"]
    # The sweep must prune vendor/VCS dirs (a naive `grep -r` over .venv/.git
    # measured ~10s); assert we go through find+prune, not `grep -r`.
    assert "find" in captured["args"]
    assert "-prune" in captured["args"]
    for skip in docker_io._SKIP_DIRS:
        assert skip in captured["args"]
    assert "-r" not in captured["args"]  # the old slow flag is gone


def test_grep_awaiting_files_empty_on_docker_failure():
    with patch.object(docker_io.subprocess, "run", return_value=_completed(returncode=2)):
        assert docker_io.grep_awaiting_files("vol-1") == []


def test_docker_exec_builds_user_and_env_flags():
    captured = {}

    def _fake_run(args, **kwargs):
        captured["args"] = args
        return _completed(stdout="ok")

    with patch.object(docker_io.subprocess, "run", _fake_run):
        docker_io.docker_exec("abc123", ["echo", "hi"], user="nobody", env={"HOME": "/claude-state"})

    assert captured["args"] == [
        "docker", "exec", "-u", "nobody", "-e", "HOME=/claude-state", "abc123", "echo", "hi",
    ]


def test_sidecar_query_parses_snapshot_json():
    snap = '{"current_node": "n1", "terminal": "", "gates": [{"file_path": "a.md", "question": "Q?"}]}'
    with patch.object(docker_io.subprocess, "run", return_value=_completed(stdout=snap)):
        out = docker_io.sidecar_query("abc123")
    assert out["current_node"] == "n1"
    assert out["gates"][0]["file_path"] == "a.md"


def test_sidecar_query_returns_none_on_nonzero_exit():
    # e.g. container not running, or a legacy image without --query.
    with patch.object(docker_io.subprocess, "run", return_value=_completed(returncode=1, stderr="no such flag")):
        assert docker_io.sidecar_query("abc123") is None


def test_sidecar_query_returns_none_on_non_json_output():
    with patch.object(docker_io.subprocess, "run", return_value=_completed(stdout="not json")):
        assert docker_io.sidecar_query("abc123") is None


def test_sidecar_query_returns_none_when_docker_missing():
    with patch.object(docker_io.subprocess, "run", side_effect=FileNotFoundError):
        assert docker_io.sidecar_query("abc123") is None


def test_sidecar_query_returns_none_on_timeout():
    with patch.object(docker_io.subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=20)):
        assert docker_io.sidecar_query("abc123") is None


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
