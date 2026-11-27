"""A live check stands only on a runbook in plan-qa form for the environment at hand."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from workhorse.pyflow.engine import RunEnv
from workhorse_workflows.coder.qa.flow import Qa
from workhorse_workflows.coder.qa.nodes.live import LIVE_RUNBOOK_FILE, runbook_problems

from coder.qa.test_flow import STORY, _Agent, _Ostler, spec_dir

LIVE = ["ac:2: the nightly export job writes the bucket"]

RUNBOOK = """# Manual QA: nightly export on local

QA_DIR="docs/specs/s/qa"
mkdir -p "$QA_DIR/ac2-export"

## 1) Trigger the export job

    kubectl create job export-now --from=cronjob/export > "$QA_DIR/ac2-export/trigger.txt"

Verdict: pass when the job reports `created`.

## 2) Read the bucket

    aws s3 ls s3://exports/today/ > "$QA_DIR/ac2-export/listing.txt"

Verdict: pass when today's file is listed.

## Cleanup

    kubectl delete job export-now

## Evidence manifest

- ac2-export/trigger.txt: the job ran
- ac2-export/listing.txt: the bucket holds today's export
"""


def _problems(tmp_path: Path, text: str, live: list[str] | None = None) -> list[str]:
    (tmp_path / LIVE_RUNBOOK_FILE).write_text(text, encoding="utf-8")
    return runbook_problems(tmp_path, LIVE if live is None else live, "local")


def test_a_runbook_in_plan_qa_form_passes(tmp_path: Path) -> None:
    assert _problems(tmp_path, RUNBOOK) == []


@pytest.mark.parametrize(
    ("broken", "problem"),
    [
        (RUNBOOK.replace(" on local", ""), "never names the environment"),
        (RUNBOOK.replace("mkdir -p", "mkdir"), "`QA_DIR=` and `mkdir -p`"),
        (RUNBOOK.replace("## 2) Read", "## 3) Read"), "not 1 to 2 in order"),
        (RUNBOOK.replace("Verdict: pass when today's", "Pass when today's"), "states no verdict rule"),
        (RUNBOOK.replace("## Cleanup", "## Tidy"), "no cleanup section"),
        (RUNBOOK.replace("## Evidence manifest", "## Files"), "not the `Evidence manifest`"),
        (RUNBOOK + "\n| a | b |\n|---|---|\n", "Markdown table"),
        (RUNBOOK.replace("    kubectl delete", "    #!/bin/sh\n    kubectl delete"), "shell script block"),
        (RUNBOOK.replace("s3://exports", "s3://<bucket>"), "no `Inputs Needed` section"),
    ],
)
def test_a_runbook_off_the_plan_qa_form_is_refused(tmp_path: Path, broken: str, problem: str) -> None:
    assert any(problem in p for p in _problems(tmp_path, broken)), _problems(tmp_path, broken)


def test_a_live_criterion_the_runbook_never_proves_is_refused(tmp_path: Path) -> None:
    problems = _problems(tmp_path, RUNBOOK, [*LIVE, "ac:3: the export is encrypted"])

    assert problems == [
        "no step saves evidence for ac:3 under `$QA_DIR/ac3-<slug>/`",
        "the evidence manifest lists nothing for ac:3",
    ]


def test_a_live_entry_with_no_criterion_and_no_runbook_is_refused(tmp_path: Path) -> None:
    problems = runbook_problems(tmp_path, ["the export works"], "local")

    assert problems[0] == "the live entry `the export works` does not start with `ac:<n>: `"
    assert problems[1].endswith(f"{LIVE_RUNBOOK_FILE}` does not exist")


class _LiveAgent(_Agent):
    """An owner that leaves a criterion to a live check, and writes its runbook from `runbooks`."""

    def __init__(self, docs: Path, runbooks: list[str]) -> None:
        super().__init__(docs)
        self.runbooks = runbooks

    def _qa_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        text = self.runbooks[min(nth, len(self.runbooks)) - 1]
        if text:
            (Path(data["spec_dir"]) / LIVE_RUNBOOK_FILE).write_text(text, encoding="utf-8")
        return super()._qa_story(data, nth) | {"live": LIVE}


@pytest.fixture
def qa_with_live(
    docs: Path, ostler: Callable[..., _Ostler], env: Callable[..., RunEnv], drive_flow: Callable[..., Any]
) -> Callable[[list[str]], tuple[_LiveAgent, Any]]:
    def run(runbooks: list[str]) -> tuple[_LiveAgent, Any]:
        ostler()
        agent = _LiveAgent(docs, runbooks)
        return agent, drive_flow(Qa(story=STORY), env(), agent)

    return run


def test_a_live_claim_with_no_runbook_goes_back_to_the_owner(
    qa_with_live: Callable[[list[str]], tuple[_LiveAgent, Any]],
) -> None:
    agent, result = qa_with_live(["", RUNBOOK])

    assert result.status == "passed", result
    assert agent.calls.count("qa-story") == 2, agent.calls
    report = agent.args_for("qa-story")[1]["report"]
    assert "Check: the live-check runbook" in report
    assert f"{spec_dir()}/{LIVE_RUNBOOK_FILE}` does not exist" in report


def test_a_live_claim_with_a_runbook_in_form_passes_in_one_turn(
    qa_with_live: Callable[[list[str]], tuple[_LiveAgent, Any]],
) -> None:
    agent, result = qa_with_live([RUNBOOK])

    assert result.status == "passed", result
    assert agent.calls.count("qa-story") == 1, agent.calls


BOTH = ["ac:1: the export job ran", *LIVE]
BOTH_RUNBOOK = (
    RUNBOOK.replace("ac2-export/trigger", "ac1-export/trigger")
    .replace('mkdir -p "$QA_DIR/ac2-export"', 'mkdir -p "$QA_DIR/ac1-export" "$QA_DIR/ac2-export"')
)


def test_the_two_criteria_runbook_stands_on_its_own(tmp_path: Path) -> None:
    assert _problems(tmp_path, BOTH_RUNBOOK, BOTH) == []


class _LiveOnlyAgent(_Agent):
    """An owner that leaves every criterion to a live check and writes no scenario plan."""

    def __init__(self, docs: Path, lives: list[list[str]]) -> None:
        super().__init__(docs)
        self.lives = lives

    def _qa_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        (Path(data["spec_dir"]) / LIVE_RUNBOOK_FILE).write_text(BOTH_RUNBOOK, encoding="utf-8")
        live = self.lives[min(nth, len(self.lives)) - 1]
        return {"status": "passed", "notes": f"owner turn {nth}", "live": live}


@pytest.fixture
def qa_live_only(
    docs: Path, ostler: Callable[..., _Ostler], env: Callable[..., RunEnv], drive_flow: Callable[..., Any]
) -> Callable[[list[list[str]]], tuple[_LiveOnlyAgent, Any, Any]]:
    def run(lives: list[list[str]]) -> tuple[_LiveOnlyAgent, Any, Any]:
        okf = ostler()
        agent = _LiveOnlyAgent(docs, lives)
        return agent, drive_flow(Qa(story=STORY), env(), agent), okf

    return run




def test_a_story_whose_every_criterion_is_a_live_check_passes_on_its_runbook(
    qa_live_only: Callable[[list[list[str]]], tuple[_LiveOnlyAgent, Any, Any]],
) -> None:
    """A plan must hold a scenario, so without this route a live-only story could never pass."""
    agent, result, okf = qa_live_only([BOTH])

    assert result.status == "passed", result
    assert agent.calls.count("qa-story") == 1, agent.calls
    assert okf.runs == 0


def test_a_story_with_no_plan_and_a_criterion_left_unproved_goes_back_to_the_owner(
    qa_live_only: Callable[[list[list[str]]], tuple[_LiveOnlyAgent, Any, Any]],
) -> None:
    agent, result, _ = qa_live_only([LIVE, BOTH])

    assert result.status == "passed", result
    report = agent.args_for("qa-story")[1]["report"]
    assert "no scenario plan stands, and ac:1 is not a live check" in report
