"""The machine-wide lock the shared browser's runs take before they start or join it."""

from __future__ import annotations

from pathlib import Path

from ostler.qa.harness_host import load_harness_module


def test_a_released_lock_lets_the_next_run_take_it(tmp_path: Path) -> None:
    shared = load_harness_module("ostler_qa_shared_browser")

    with shared._locked(tmp_path):
        pass
    with shared._locked(tmp_path):
        pass

    assert (tmp_path / "lock").is_file()
