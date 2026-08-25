"""The two questions every coder node's return can now be asked, and their edges.

`blocked` decides whether a node hands its work on rather than churning; `actionable`
decides *who* it hands it to — a fixer who was given somewhere to go and something to
change, or the operator. Both are derived rather than declared, and the reason is a
failure mode rather than a preference, so each of those derivations is pinned here.
"""
from __future__ import annotations

import pathlib

from workhorse_workflows.coder.shared.schemas._base import (
    BLOCKED_STATUSES,
    CoderResult,
    Finding,
)
from workhorse_workflows.coder.shared.schemas.docs import (
    DocumentationFinding,
    DocumentationReview,
)
from workhorse_workflows.coder.shared.schemas.qa import QaAssessment, QaFinding
from workhorse_workflows.coder.shared.schemas.review import CodeReviewResult


class _Stated(CoderResult):
    """A result with a status, which is what `blocked` reads."""

    status: str = ""


def test_every_spelling_of_giving_up_reads_as_blocked() -> None:
    """Four schemas grew four words for one thing; the router only ever needed one."""
    for status in BLOCKED_STATUSES:
        assert _Stated(status=status).blocked, status


def test_an_unanswered_node_is_not_blocked() -> None:
    """The load-bearing edge.

    After the resilience ladder's last rung a node emits its keys as null, `_drop_nulls`
    drops them and every field falls back to its default. If "hand this to the operator"
    were a defaulted field it would fire on every node the ladder failed to answer, and the
    conservative arm would silently become an escalation.
    """
    assert not _Stated().blocked
    assert not _Stated.model_validate({"status": None}).blocked
    assert not CoderResult().blocked  # no status field at all


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
    """`findings` is read off the subclass, so each lane's own element type must work.

    `QaAssessment` and `DocumentationReview` narrow the list to their own `Finding`
    subclass. A field declared on the base would have made both an incompatible override;
    reading it by name is what lets them keep the type they need.
    """
    assessment = QaAssessment(
        findings=[
            QaFinding(scope="product-test", target="web/tests/todo.spec.ts:40",
                      issue="no assertion", repair="assert the row disappears"),
            QaFinding(scope="plan", issue="thin"),
        ]
    )
    assert [f.target for f in assessment.actionable] == ["web/tests/todo.spec.ts:40"]

    review = DocumentationReview(
        status="revise",
        findings=[
            DocumentationFinding(id="D1", target="okf/api.md", issue="stale",
                                 repair="cite the new handler"),
            DocumentationFinding(id="D2", target="okf/api.md"),
        ],
    )
    # `actionable` answers in the shared vocabulary, not each lane's — the id and the
    # closed `kind` axis stay on the concrete list, which is where their consumers read them.
    assert [f.repair for f in review.actionable] == ["cite the new handler"]


def test_the_review_lane_parses_the_loose_findings_it_used_to_declare() -> None:
    """`CodeReviewResult.findings` was `list[dict[str, Any]]`.

    The prompt's own keys still parse — extras are ignored — so the change is not a break
    in what the turn may say, only in what the router may believe about it.
    """
    result = CodeReviewResult.model_validate(
        {
            "status": "blocked",
            "findings": [
                {"target": "api/db.go:20", "issue": "n+1", "repair": "batch the query",
                 "severity": "high"},
                {"issue": "naming"},
            ],
        }
    )
    assert result.blocked
    assert [f.repair for f in result.actionable] == ["batch the query"]


def test_the_shape_the_review_prompt_emits_is_actionable() -> None:
    """The finding the prompt asks for, parsed by the model that receives it.

    These two documents drifted once: the prompt emitted `repo`/`file`/`line`/`required_fix`
    while the model declared `target`/`issue`/`repair`, and `extra="ignore"` made the
    disagreement silent — every finding arrived with its repair stripped, so none was ever
    `actionable` and a block that a fixer could have taken went to the operator instead.
    Nothing but a test holds a prompt and a schema together, so this is that test.
    """
    result = CodeReviewResult.model_validate(
        {
            "status": "findings",
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
                    "category": "Missed Utility",
                    "score": 84,
                },
            ],
        }
    )
    assert len(result.actionable) == 2
    assert [f.category for f in result.findings] == ["Bug", "Missed Utility"]
    assert [f.score for f in result.findings] == [92, 84]


def test_the_review_prompt_asks_for_the_keys_the_model_reads() -> None:
    """The other half of the pairing: read the prompt, not a copy of it.

    A shape-check on hand-written JSON only proves the model parses what this file typed.
    The document the agent is handed is the one that has to name `target` and `repair`, and
    must not go back to naming the keys the model drops on the floor.
    """
    prompt = (
        pathlib.Path(__file__).resolve().parents[3]
        / "src/workhorse_workflows/coder/review/prompts/code-review.md"
    ).read_text()
    body = prompt.split("Return this JSON as your final response:")[1]
    for key in ("target", "issue", "repair", "category", "score"):
        assert f'"{key}"' in body, key
    for dropped in ("required_fix", '"repo"', '"file"', '"line"'):
        assert dropped not in body, dropped
