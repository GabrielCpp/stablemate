"""The evidence gate's report check — `_report_problems`.

`ostler qa run` ends by rendering `qa-report.md`, the per-criterion account a reviewer reads
instead of the ledger, and stamps the run id into it. The gate holds a claimed pass to that:
no report, or one rendered from some other run, is a pass nobody can check by hand.
"""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.coder.qa.nodes import evidence


def _report(spec: Path, run_id: str) -> None:
    (spec / "qa-report.md").write_text(
        f"# QA report — story\n\n<!-- run: {run_id} status: passed -->\n", encoding="utf-8"
    )


def test_a_report_from_the_same_run_is_no_problem(tmp_path: Path) -> None:
    _report(tmp_path, "qa-run-7")
    assert evidence._report_problems(tmp_path, {"runId": "qa-run-7"}) == []


def test_a_missing_report_fails_the_pass(tmp_path: Path) -> None:
    problems = evidence._report_problems(tmp_path, {"runId": "qa-run-7"})
    assert len(problems) == 1
    assert problems[0].startswith("qa-report.md is missing")


def test_a_report_from_an_earlier_run_fails_the_pass(tmp_path: Path) -> None:
    _report(tmp_path, "qa-run-6")
    problems = evidence._report_problems(tmp_path, {"runId": "qa-run-7"})
    assert len(problems) == 1
    assert "rendered from run 'qa-run-6'" in problems[0]
    assert "'qa-run-7'" in problems[0]


def test_a_hand_written_report_fails_the_pass(tmp_path: Path) -> None:
    (tmp_path / "qa-report.md").write_text("# QA report\n\nall good, trust me\n", encoding="utf-8")
    problems = evidence._report_problems(tmp_path, {"runId": "qa-run-7"})
    assert len(problems) == 1
    assert "no run marker" in problems[0]
