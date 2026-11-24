from __future__ import annotations

from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

PLUGIN_DIR = Path(__file__).resolve().parents[2] / "scripts" / "pytest_plugins"

INNER_TEST = """
import subprocess
import sys
import tempfile


def test_creates_temp_entries():
    tempfile.mkdtemp()
    subprocess.run(
        [sys.executable, "-c", "import tempfile; tempfile.mkdtemp()"], check=True
    )
    assert {FAIL}
"""


@pytest.fixture
def outer(tmp_path, monkeypatch):
    folder = tmp_path / "outer"
    folder.mkdir()
    monkeypatch.setenv("TMPDIR", str(folder))
    monkeypatch.setenv("PYTHONPATH", str(PLUGIN_DIR))
    return folder


def _run(pytester, *args):
    pytester.makepyfile(test_inner=INNER_TEST.replace("{FAIL}", "True"))
    return pytester.runpytest_subprocess("-p", "private_tmp", "-p", "no:cacheprovider", *args)


def test_green_run_leaves_the_temp_folder_empty(pytester, outer):
    result = _run(pytester)
    result.assert_outcomes(passed=1)
    assert list(outer.iterdir()) == []


def test_green_run_under_xdist_leaves_the_temp_folder_empty(pytester, outer):
    result = _run(pytester, "-n", "2")
    result.assert_outcomes(passed=1)
    assert list(outer.iterdir()) == []


def test_workers_use_the_private_folder(pytester, outer):
    pytester.makepyfile(
        test_inner="""
import os
import tempfile


def test_worker_temp():
    assert os.path.basename(tempfile.gettempdir()).startswith("sm-t-")
"""
    )
    result = pytester.runpytest_subprocess("-p", "private_tmp", "-p", "no:cacheprovider", "-n", "2")
    result.assert_outcomes(passed=1)


def test_run_that_collects_nothing_leaves_the_temp_folder_empty(pytester, outer):
    result = pytester.runpytest_subprocess("-p", "private_tmp", "-p", "no:cacheprovider")
    assert result.ret == pytest.ExitCode.NO_TESTS_COLLECTED
    assert list(outer.iterdir()) == []


def test_red_run_keeps_the_folder_and_prints_its_path(pytester, outer):
    pytester.makepyfile(test_inner=INNER_TEST.replace("{FAIL}", "False"))
    result = pytester.runpytest_subprocess("-p", "private_tmp", "-p", "no:cacheprovider")
    result.assert_outcomes(failed=1)
    kept = [entry for entry in outer.iterdir() if entry.name.startswith("sm-t-")]
    assert len(kept) == 1
    result.stdout.fnmatch_lines([f"private temp folder kept: {kept[0]}"])
