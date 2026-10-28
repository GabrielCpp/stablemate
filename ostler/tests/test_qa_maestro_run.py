"""A maestro flow owns the device alone: the resident screen reader is stopped before it starts."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from ostler.qa.harness_host import load_harness_module

harness = load_harness_module("ostler_qa")
hierarchy = load_harness_module("ostler_qa_hierarchy")


def test_a_flow_releases_the_resident_reader_before_maestro_test_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        events.append(" ".join(command[:2]))
        return subprocess.CompletedProcess(command, 0, "", "")

    qa = SimpleNamespace(
        scenario_id="s1", dir=tmp_path, root=tmp_path, artifact=lambda path, kind: None,
    )
    monkeypatch.setattr(harness.shutil, "which", lambda name: "/usr/bin/maestro")
    monkeypatch.setattr(hierarchy, "release_device", lambda: events.append("release"))
    monkeypatch.setattr(harness.subprocess, "run", run)

    result = harness.Maestro(qa).run("appId: x\n---\n- launchApp\n")

    assert result.ok
    assert events == ["release", "maestro test"]
