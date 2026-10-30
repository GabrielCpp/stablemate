"""The plan the QA flow starts from, compiled out of the book."""
from __future__ import annotations

import logging
from pathlib import Path

from _compiling_book import write_packet

from workhorse_workflows.coder.qa.nodes.qa import compile_story_plan

LOG = logging.getLogger("test")


def test_a_compilable_packet_writes_the_plan(tmp_path: Path) -> None:
    spec = tmp_path / "spec"
    write_packet(tmp_path, spec, runbook=True)

    result = compile_story_plan(LOG, spec_dir=str(spec), story="STORY-1")

    assert result.compiled
    assert result.scenarios == 1, result
    assert "@scenario(" in (spec / "qa_plan.py").read_text(encoding="utf-8")


def test_a_refusal_writes_nothing(tmp_path: Path) -> None:
    spec = tmp_path / "spec"
    write_packet(tmp_path, spec, runbook=False)

    result = compile_story_plan(LOG, spec_dir=str(spec), story="STORY-1")

    assert not result.compiled
    assert result.gaps > 0
    assert not (spec / "qa_plan.py").exists()


def test_a_plan_that_stands_is_left_alone(tmp_path: Path) -> None:
    spec = tmp_path / "spec"
    write_packet(tmp_path, spec, runbook=True)
    _ = (spec / "qa_plan.py").write_text("standing\n", encoding="utf-8")

    result = compile_story_plan(LOG, spec_dir=str(spec), story="STORY-1")

    assert not result.compiled
    assert (spec / "qa_plan.py").read_text(encoding="utf-8") == "standing\n"
