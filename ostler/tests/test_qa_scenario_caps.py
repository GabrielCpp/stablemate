from __future__ import annotations

from pathlib import Path

import pytest

from ostler.qa import harness_host


def test_a_scenario_runs_uncapped_where_systemd_run_is_absent(tmp_path: Path) -> None:
    argv = ["python", "-m", "ostler_qa", "run"]

    assert harness_host.capped_argv(argv, {"PATH": str(tmp_path)}) == argv


def test_a_scenario_runs_in_a_scope_capping_memory_and_cpu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    systemd_run = tmp_path / "systemd-run"
    systemd_run.write_text("#!/bin/false\n", encoding="utf-8")
    systemd_run.chmod(0o755)
    monkeypatch.setattr(harness_host, "_scopes_answer", lambda *_: True)

    capped = harness_host.capped_argv(["python", "-m", "ostler_qa"], {"PATH": str(tmp_path)})

    assert capped[:3] == [str(systemd_run), "--user", "--scope"]
    assert f"MemoryMax={harness_host.SCENARIO_MEMORY_MAX}" in capped
    assert "MemorySwapMax=0" in capped
    assert "OOMPolicy=kill" in capped
    assert f"CPUQuota={harness_host.SCENARIO_CPU_QUOTA}" in capped
    assert capped[-4:] == ["--", "python", "-m", "ostler_qa"]


def test_a_scenario_runs_uncapped_when_the_user_manager_does_not_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    systemd_run = tmp_path / "systemd-run"
    systemd_run.write_text("#!/bin/false\n", encoding="utf-8")
    systemd_run.chmod(0o755)
    monkeypatch.setattr(harness_host, "_scopes_answer", lambda *_: False)

    assert harness_host.capped_argv(["python"], {"PATH": str(tmp_path)}) == ["python"]
