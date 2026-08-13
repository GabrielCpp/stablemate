"""The obligation→evidence join, and the judgments it replaces.

Every case here is a finding a person used to produce by reading three files side by side.
The point of the module under test is that each one is now arithmetic, so each test asserts
the *status* — the thing a downstream agent routes on — and not just that some sentence was
emitted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ostler.qa.evidence_map import EvidenceMapError, build_evidence_map, render_evidence_map

CONTRACT = "okf:docs/features/orders/publish.md:contract"
CONFLICT = "okf:docs/features/orders/publish.md:does:1"
UNTOUCHED = "okf:docs/features/orders/publish.md:does:2"

#: What the book declares for the conflict branch, canonically spelled.
DECLARED = 'conflict_on_stale(subject="manifest", token="etag")'


def _spec(
    tmp_path: Path,
    *,
    obligations: list[dict[str, Any]],
    log: list[dict[str, Any]],
    evidence: dict[str, Any] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
) -> Path:
    """A spec directory holding exactly the four files the join reads."""
    spec = tmp_path / "docs/specs/story-1"
    (spec / "qa").mkdir(parents=True, exist_ok=True)
    (spec / "qa-okf-context.json").write_text(
        json.dumps({"version": 1, "available": True, "obligations": obligations}),
        encoding="utf-8",
    )
    (spec / "qa" / "qa-run.ndjson").write_text(
        "".join(json.dumps(record) + "\n" for record in log), encoding="utf-8"
    )
    (spec / "qa" / "run-manifest.json").write_text(
        json.dumps({"runId": "qa-run-1", "artifacts": artifacts or []}), encoding="utf-8"
    )
    if evidence is not None:
        (spec / "qa-evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
    return spec


def _obligation(identifier: str, *, declared: list[str] | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": identifier,
        "kind": "contract" if identifier.endswith("contract") else "does",
        "node": "publish",
        "source": "docs/features/orders/publish.md",
        "requirement": "a stale manifest write is refused",
        "evidenceRequired": "live",
        "reasons": [],
    }
    if declared:
        row["checksDeclared"] = [
            {"call": call, "name": call.split("(", 1)[0], "args": {}} for call in declared
        ]
    return row


def _context_only(identifier: str) -> dict[str, Any]:
    """An obligation pulled into scope for reading, which owes no evidence of its own."""
    row = _obligation(identifier)
    row["required"] = False
    row["evidenceRequired"] = "context"
    return row


def _claim(scenario: str, *covers: str) -> dict[str, Any]:
    return {"kind": "scenario_start", "scenario": scenario, "covers": list(covers)}


def _assert(
    scenario: str,
    action: int,
    result: str,
    *covers: str,
    check: str = "",
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "kind": "assert",
        "scenario": scenario,
        "action": action,
        "result": result,
        "covers": list(covers),
    }
    if check:
        record["check"] = check
        record["check_args"] = args or {}
    return record


def _by_id(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in data["obligations"]}


def test_an_obligation_nobody_claimed_is_uncovered(tmp_path: Path) -> None:
    """The finding three audit refutations produced by hand: nothing observed this.

    A person had to read the plan, notice the obligation appears in no `covers=`, and then
    convince themselves they had not missed it somewhere. It is a set difference — the
    obligations in the packet, minus the ones the log mentions — and the only reason it was
    ever a judgment is that nobody had computed it.
    """
    spec = _spec(
        tmp_path,
        obligations=[_obligation(CONTRACT), _obligation(UNTOUCHED)],
        log=[_claim("publish-happy", CONTRACT), _assert("publish-happy", 1, "PASS", CONTRACT)],
    )

    rows = _by_id(build_evidence_map(spec))

    assert rows[UNTOUCHED]["status"] == "uncovered"
    assert rows[UNTOUCHED]["claimedBy"] == []
    assert rows[CONTRACT]["status"] == "covered"


def test_a_scenario_that_claims_an_obligation_and_asserts_nothing_is_separated_out(
    tmp_path: Path,
) -> None:
    """`claimed-but-unasserted` is a different repair from `uncovered`, so it is a different word.

    An obligation nobody claimed needs a scenario written. One a scenario claims and never
    asserts needs *that* scenario fixed — the plan already decided where the evidence goes.
    Collapsing the two sends the agent to write a scenario that exists.
    """
    spec = _spec(
        tmp_path,
        obligations=[_obligation(CONTRACT)],
        log=[
            _claim("publish-happy", CONTRACT),
            _assert("publish-happy", 1, "PASS", "okf:other:contract"),
        ],
    )

    row = _by_id(build_evidence_map(spec))[CONTRACT]

    assert row["status"] == "claimed-but-unasserted"
    assert row["claimedBy"] == ["publish-happy"]
    assert "publish-happy" in row["why"]


def test_an_assertion_that_is_not_the_declared_check_does_not_count_as_the_declared_check(
    tmp_path: Path,
) -> None:
    """Oracle strength, as arithmetic.

    This is the reviewer's most-repeated finding — *your assertion would still pass under the
    defect it exists to exclude*. A write followed by a read cannot tell compare-and-swap
    from an unconditional overwrite, so the book declares `conflict_on_stale`; the scenario
    asserts a 200 and moves on. The row is not `covered`, and it names the call that is
    missing rather than describing the defect in prose.
    """
    spec = _spec(
        tmp_path,
        obligations=[_obligation(CONFLICT, declared=[DECLARED])],
        log=[
            _claim("publish-happy", CONFLICT),
            _assert("publish-happy", 1, "PASS", CONFLICT, check="http_status", args={"code": 200}),
        ],
    )

    row = _by_id(build_evidence_map(spec))[CONFLICT]

    assert row["status"] == "claimed-but-unasserted"
    assert row["checksMissing"] == [DECLARED]
    assert row["checksObserved"] == ["http_status(code=200)"]
    assert DECLARED in row["why"]


def test_the_declared_check_observed_and_passing_is_covered(tmp_path: Path) -> None:
    """The other half: when the plan does invoke it, the join has to say so.

    Canonicalisation is what makes this work at all. The book's spelling and the runner's
    record go through the same `checks.bind`, so an author who wrote the arguments in a
    different order is not reported as having asserted nothing.
    """
    spec = _spec(
        tmp_path,
        obligations=[_obligation(CONFLICT, declared=[DECLARED])],
        log=[
            _claim("publish-conflict", CONFLICT),
            _assert(
                "publish-conflict",
                1,
                "PASS",
                CONFLICT,
                check="conflict_on_stale",
                # Author order, not spec order.
                args={"token": "etag", "subject": "manifest"},
            ),
        ],
        artifacts=[{"path": "qa/steps/publish-conflict.json", "sha256": "…",
                    "scenario": "publish-conflict"}],
    )

    row = _by_id(build_evidence_map(spec))[CONFLICT]

    assert row["status"] == "covered", row["why"]
    assert row["checksMissing"] == []
    assert row["evidence"] == ["qa/steps/publish-conflict.json"]


def test_a_failing_assertion_makes_the_obligation_contradicted_not_uncovered(
    tmp_path: Path,
) -> None:
    """A disproof is not a gap, and routing them together sends the wrong agent.

    An obligation with a failing assertion is a product defect: the run went and looked, and
    the product did not do this. An obligation with no assertion is a QA defect. Both are
    blocking and they need opposite work.
    """
    spec = _spec(
        tmp_path,
        obligations=[_obligation(CONTRACT)],
        log=[
            _claim("publish-happy", CONTRACT),
            _assert("publish-happy", 1, "PASS", CONTRACT),
            _assert("publish-happy", 2, "FAIL", CONTRACT),
        ],
    )

    row = _by_id(build_evidence_map(spec))[CONTRACT]

    assert row["status"] == "contradicted"
    assert row["failingLogRefs"] == ["publish-happy:assert:2"]
    assert row["assertions"] == {"passing": 1, "failing": 1}


def test_a_published_pass_the_log_does_not_hold_is_contradicted(tmp_path: Path) -> None:
    """The artifact and the ledger disagreeing, which is the case found by hand.

    `qa-evidence.json` is a summary of the run log, and an audit found a row published with a
    verdict its refs did not support under an `overall: Pass`. Every consumer downstream
    reads the summary, so a summary that is wrong about an obligation is worse than one that
    omits it — nothing below it in the pipeline goes back to the log to check.
    """
    spec = _spec(
        tmp_path,
        obligations=[_obligation(CONTRACT)],
        log=[_claim("publish-happy", CONTRACT)],
        evidence={
            "runId": "qa-run-1",
            "overall": "Pass",
            "obligations": [{"id": CONTRACT, "verdict": "Pass", "log_refs": [], "evidence": []}],
        },
    )

    row = _by_id(build_evidence_map(spec))[CONTRACT]

    assert row["status"] == "contradicted"
    assert row["publishedVerdict"] == "Pass"
    assert "does not hold" in row["why"] or "ledger does not hold" in row["why"]


def test_a_missing_run_log_refuses_rather_than_reporting_everything_uncovered(
    tmp_path: Path,
) -> None:
    """The join has one dangerous failure mode, and it is silence.

    With no log, every obligation has no bound assertion, and the map would read exactly like
    a run that asserted nothing — a report that looks like a finding about the QA plan when
    it is a finding about the caller's arguments. So it refuses.
    """
    spec = _spec(tmp_path, obligations=[_obligation(CONTRACT)], log=[])
    (spec / "qa" / "qa-run.ndjson").unlink()

    with pytest.raises(EvidenceMapError, match="run log is missing"):
        build_evidence_map(spec)


def test_an_obligation_in_scope_only_for_context_is_not_a_gap(tmp_path: Path) -> None:
    """A packet is mostly neighbours, and counting them would drown the answer.

    `qa context` pulls in every obligation a reader needs to understand the change — flow
    closures, contracts of nodes downstream — and marks them `required: false`. On a real
    story they outnumber the owed ones ten to one, so treating scope as debt reports a fully
    evidenced run as a thousand gaps. They are counted, separately, and not as a status.
    """
    spec = _spec(
        tmp_path,
        obligations=[_obligation(CONTRACT), _context_only(UNTOUCHED)],
        log=[_claim("publish-happy", CONTRACT), _assert("publish-happy", 1, "PASS", CONTRACT)],
    )

    data = build_evidence_map(spec)

    assert [row["id"] for row in data["obligations"]] == [CONTRACT]
    assert data["counts"]["uncovered"] == 0
    assert data["contextOnly"] == 1


def test_the_counts_and_the_rendering_lead_with_what_needs_work(tmp_path: Path) -> None:
    """Triage order, not audit order: the rows that are fine are the ones nobody reads."""
    spec = _spec(
        tmp_path,
        obligations=[_obligation(CONTRACT), _obligation(UNTOUCHED)],
        log=[_claim("publish-happy", CONTRACT), _assert("publish-happy", 1, "PASS", CONTRACT)],
    )

    data = build_evidence_map(spec)
    lines = render_evidence_map(data)

    assert data["counts"] == {
        "contradicted": 0,
        "uncovered": 1,
        "claimed-but-unasserted": 0,
        "covered": 1,
    }
    body = "\n".join(lines)
    assert body.index("## uncovered") < body.index("## covered")
    assert "\n".join(render_evidence_map(data, only="uncovered")).count("## covered") == 0
