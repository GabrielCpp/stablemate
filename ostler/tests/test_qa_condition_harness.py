"""The harness side of a claim's condition: `qa.condition`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module


def _qa(tmp_path: Path, emitted: list[dict[str, Any]]) -> Any:
    harness = load_harness_module("ostler_qa")
    recorder = harness._Recorder(fd=-1)
    recorder.emit = emitted.append
    return harness.Qa(
        scenario_id="widget-list-shows",
        target=harness.Target("web", driver="playwright"),
        root=tmp_path,
        spec_dir=tmp_path,
        qa_dir=tmp_path / "qa",
        covers=["okf:docs/a.md#shown:states:1"],
        recorder=recorder,
    )


def _states() -> dict[str, list[tuple[str, Any, dict[str, Any]]]]:
    return {
        "none-low": [("count", [], {"equals": 0})],
        "some-low": [("count", [], {"equals": 1})],
    }


def test_a_held_condition_is_remembered_and_clears_the_exchange(tmp_path: Path) -> None:
    emitted: list[dict[str, Any]] = []
    qa = _qa(tmp_path, emitted)
    qa._exchange = object()

    qa.condition("none-low", "screens/widget-list.md", _states())

    assert qa._held == ["none-low"]
    assert qa._exchange is None
    assert {"type": "condition", "state": "none-low", "held": True} in emitted


def test_a_condition_that_reads_false_faults_the_book_and_stops_the_scenario(tmp_path: Path) -> None:
    harness = load_harness_module("ostler_qa")
    emitted: list[dict[str, Any]] = []
    qa = _qa(tmp_path, emitted)

    with pytest.raises(harness.CheckFailed):
        qa.condition("some-low", "screens/widget-list.md", _states())

    failed = [record for record in emitted if record.get("passed") is False]
    assert failed
    assert failed[-1]["state"] == "some-low"
    assert failed[-1]["holds"] == "none-low"
    assert qa._claim_fault.fault_class == "condition"
    assert qa._claim_fault.page == "screens/widget-list.md"
    assert qa._held == []


def test_a_check_that_fails_after_a_held_condition_carries_it(tmp_path: Path) -> None:
    emitted: list[dict[str, Any]] = []
    qa = _qa(tmp_path, emitted)
    qa.condition("none-low", "screens/widget-list.md", _states())

    qa.check("the notice shows", False, actual="absent")

    failed = [record for record in emitted if record.get("passed") is False]
    assert failed[-1]["held"] == ["none-low"]
