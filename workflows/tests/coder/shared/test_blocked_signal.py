"""The two questions every coder node's return can now be asked, and their edges."""
from __future__ import annotations

import json
import pathlib

from workhorse_workflows.coder.shared.schemas._base import (
    BLOCKED_STATUSES,
    CoderResult,
    Finding,
)
from workhorse_workflows.coder.shared.schemas.qa import QaFinding, QaOwnerResult
from workhorse_workflows.coder.shared.schemas.render import schema_block
from workhorse_workflows.coder.shared.schemas.review import ReviewFinding
from workhorse_workflows.coder.shared.schemas.dev_story import DevResult


class _Stated(CoderResult):
    """A result with a status, which is what `blocked` reads."""

    status: str = ""


def test_every_spelling_of_giving_up_reads_as_blocked() -> None:
    """Four schemas grew four words for one thing; the router only ever needed one."""
    for status in BLOCKED_STATUSES:
        assert _Stated(status=status).blocked, status


def test_an_unanswered_node_is_not_blocked() -> None:
    """The load-bearing edge."""
    assert not _Stated().blocked
    assert not _Stated.model_validate({"status": None}).blocked
    assert not CoderResult().blocked


def test_blocked_ignores_case_and_surrounding_space() -> None:
    """An agent writes prose; the vocabulary is matched, not the typography."""
    assert _Stated(status="  Blocked \n").blocked
    assert _Stated(status="NOT_PASSED").blocked


def test_a_passing_status_is_not_blocked() -> None:
    assert not _Stated(status="passed").blocked
    assert not _Stated(status="approved").blocked


def test_a_finding_needs_both_a_target_and_a_repair() -> None:
    """Either half alone names a problem and nominates nobody."""
    assert Finding(target="web/src/App.tsx:12", repair="await the fetch").actionable
    assert not Finding(target="web/src/App.tsx:12", issue="it is wrong").actionable
    assert not Finding(repair="await the fetch").actionable
    assert not Finding().actionable
    assert not Finding(target="   ", repair="  ").actionable


class _Complaining(CoderResult):
    status: str = ""
    findings: list[Finding] = []


def test_actionable_keeps_only_the_findings_a_fixer_could_act_on() -> None:
    """A non-empty list of complaints reads as evidence and is not."""
    result = _Complaining(
        status="blocked",
        findings=[
            Finding(target="api/handler.go:88", repair="return the 409"),
            Finding(issue="the flow feels wrong"),
        ],
    )
    assert result.blocked
    assert [f.target for f in result.actionable] == ["api/handler.go:88"]


def test_a_block_with_no_evidence_is_a_block_with_nothing_to_route() -> None:
    """This is the case that has to reach the operator rather than the loop."""
    assert _Complaining(status="unfixable").actionable == []


def test_the_narrowed_finding_lists_still_answer_actionable() -> None:
    """`findings` is read off the subclass, so each lane's own element type must work."""
    verdict = QaOwnerResult(
        status="findings",
        findings=[
            QaFinding(target="web/src/todo.ts:40", issue="the row stays",
                      repair="remove the row on delete"),
            QaFinding(issue="thin"),
        ]
    )
    assert [f.target for f in verdict.actionable] == ["web/src/todo.ts:40"]


def test_the_dev_owner_parses_loose_review_findings() -> None:
    """A finding with no target or repair parses, and nothing can act on it."""
    result = DevResult.model_validate(
        {
            "status": "ready",
            "findings": [
                {"target": "api/db.go:20", "issue": "n+1", "repair": "batch the query",
                 "category": "Bug", "severity": "high"},
                {"issue": "naming", "category": "Standard"},
            ],
        }
    )
    assert not result.blocked
    assert [f.repair for f in result.actionable] == ["batch the query"]


def test_the_review_shape_the_dev_prompt_emits_is_actionable() -> None:
    """The finding the prompt asks for, parsed by the model that receives it."""
    result = DevResult.model_validate(
        {
            "status": "ready",
            "findings": [
                {
                    "target": "api-service/internal/link/store.go:118",
                    "issue": "the short code is generated without checking for a collision",
                    "repair": "insert with a unique constraint and retry on conflict",
                    "category": "Bug",
                    "score": 92,
                },
                {
                    "target": "api-service/internal/link/path.go:14",
                    "issue": "re-derives the canonical path",
                    "repair": "call pkg/urlpath.Canonical",
                    "category": "Reuse",
                    "score": 84,
                },
            ],
        }
    )
    assert len(result.actionable) == 2
    assert [f.category for f in result.findings] == ["Bug", "Reuse"]
    assert [f.score for f in result.findings] == [92, 84]


def test_the_dev_owner_prompt_asks_for_the_finding_keys_the_model_reads() -> None:
    """The other half of the pairing: read the prompt, not a copy of it."""
    prompt = (
        pathlib.Path(__file__).resolve().parents[3]
        / "src/workhorse_workflows/coder/dev/prompts/dev-story.md"
    ).read_text()
    assert "{{ result_schema }}" in prompt
    body = schema_block(DevResult)
    for key in ("target", "issue", "repair", "category", "score"):
        assert f'"{key}"' in body, key
    finding = json.dumps(ReviewFinding.model_json_schema())
    for dropped in ("required_fix", '"repo"', '"file"', '"line"'):
        assert dropped not in finding, dropped
