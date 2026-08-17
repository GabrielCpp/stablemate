"""The QA-plan repair's proof-of-work gate — `verify_qa_dry_run`.

A repair turn's answer is a claim: "I fixed the scenarios that failed." Believing it costs a
full suite run to disprove, and the loop that pays for it has six laps. So the gate reads the
scratch evidence the prompt requires the turn to leave — one `qa-run.ndjson` per repaired
scenario, under `<spec_dir>/qa-dry-run/<scenario>/` — and a repair that did not run what it
claimed to repair is sent straight back without spending the run.

The three refusals are the three ways a turn can look finished and not be: it never ran the
scenario, it ran it and left it red, or it left a log with nothing in it (a run that died
before its first assertion, or an out-dir the runner rmtree'd and never refilled).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from workhorse_workflows.coder.qa.nodes.qa import QA_SCRATCH_DIRNAME, verify_qa_dry_run
from workhorse_workflows.coder.shared.qa_support import QA_RUN_LOG

LOGGER = logging.getLogger("test.dry-run-gate")


def _dry_run(spec_dir: Path, scenario: str, *results: str) -> None:
    """The artifacts a single-scenario `ostler qa run --out-dir …` leaves behind."""
    out = spec_dir / QA_SCRATCH_DIRNAME / scenario
    out.mkdir(parents=True, exist_ok=True)
    (out / QA_RUN_LOG).write_text(
        "".join(
            json.dumps({"kind": "assert", "id": f"{scenario}-{n}", "result": r}) + "\n"
            for n, r in enumerate(results, start=1)
        ),
        encoding="utf-8",
    )


def test_a_green_dry_run_for_every_named_scenario_passes(tmp_path: Path) -> None:
    _dry_run(tmp_path, "create-document", "PASS", "PASS")
    _dry_run(tmp_path, "copy-link", "PASS")

    gate = verify_qa_dry_run(LOGGER, str(tmp_path), ("create-document", "copy-link"))

    assert gate.status == "passed", gate.notes
    assert gate.verified == ["create-document", "copy-link"], gate.verified


def test_a_scenario_that_was_never_dry_run_is_refused_by_name(tmp_path: Path) -> None:
    """The common shape: the turn edited the plan and returned without executing it."""
    _dry_run(tmp_path, "create-document", "PASS")

    gate = verify_qa_dry_run(LOGGER, str(tmp_path), ("create-document", "copy-link"))

    assert gate.status == "failed"
    assert "`copy-link`" in gate.notes and "no dry run" in gate.notes, gate.notes
    # The one it did prove is still recorded, so the next brief is not asked to redo it.
    assert gate.verified == ["create-document"], gate.verified
    # And the refusal teaches the command, because the turn that skipped it plainly did
    # not have it to hand.
    assert "--out-dir" in gate.notes, gate.notes


def test_a_dry_run_that_still_fails_is_not_a_finished_repair(tmp_path: Path) -> None:
    _dry_run(tmp_path, "copy-link", "PASS", "FAIL")

    gate = verify_qa_dry_run(LOGGER, str(tmp_path), ("copy-link",))

    assert gate.status == "failed"
    assert "copy-link-2" in gate.notes, gate.notes
    assert gate.verified == [], gate.verified


def test_a_log_with_no_assertion_in_it_does_not_count_as_evidence(tmp_path: Path) -> None:
    """An empty log is the cheapest forgery and the commonest accident, and both read the
    same from here: nothing ran, so nothing was proven."""
    _dry_run(tmp_path, "copy-link")

    gate = verify_qa_dry_run(LOGGER, str(tmp_path), ("copy-link",))

    assert gate.status == "failed"
    assert "no assertion" in gate.notes, gate.notes


def test_a_scenarios_own_out_dir_claims_its_unlabelled_assertions(tmp_path: Path) -> None:
    """A single-scenario run may leave the `scenario` field off its records — the out-dir
    already names it. Requiring the label would refuse every honest dry run."""
    out = tmp_path / QA_SCRATCH_DIRNAME / "copy-link"
    out.mkdir(parents=True)
    (out / QA_RUN_LOG).write_text(
        json.dumps({"kind": "assert", "id": "a1", "result": "PASS"}) + "\n", encoding="utf-8"
    )

    assert verify_qa_dry_run(LOGGER, str(tmp_path), ("copy-link",)).status == "passed"


def test_another_scenarios_records_in_the_out_dir_prove_nothing(tmp_path: Path) -> None:
    """A whole-suite run pointed at one scenario's out-dir would otherwise pass the gate for
    a scenario it left red, because *some* assertion in the file is green."""
    out = tmp_path / QA_SCRATCH_DIRNAME / "copy-link"
    out.mkdir(parents=True)
    (out / QA_RUN_LOG).write_text(
        json.dumps({"kind": "assert", "id": "x1", "scenario": "create-document", "result": "PASS"})
        + "\n",
        encoding="utf-8",
    )

    gate = verify_qa_dry_run(LOGGER, str(tmp_path), ("copy-link",))

    assert gate.status == "failed"
    assert "no assertion" in gate.notes, gate.notes


def test_no_scenarios_to_prove_is_a_pass_and_not_a_refusal(tmp_path: Path) -> None:
    """The draft path: nothing failed, so there is nothing for a dry run to demonstrate."""
    gate = verify_qa_dry_run(LOGGER, str(tmp_path), ())

    assert gate.status == "passed", gate.notes
    assert gate.scenarios == []


def test_a_missing_spec_dir_argument_fails_closed(tmp_path: Path) -> None:
    """The gate cannot read what it cannot locate, and an unreadable gate that passes is
    worse than no gate: it certifies every repair from then on."""
    gate = verify_qa_dry_run(LOGGER, "", ("copy-link",))

    assert gate.status == "failed"
    assert "spec_dir" in gate.notes, gate.notes
