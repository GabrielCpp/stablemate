"""Each failed check is owed to the book, its arrangement, the environment or the app by the first rule its evidence meets, and to nobody when none does."""

from __future__ import annotations

from typing import Any

import pytest

from ostler.qa.attribution import Attribution, Cause, CheckEvidence, attribute, route_shape, signatures

SIGNED_IN = "docs/features/tally/fixtures/signed-in.md"


def _failed(status: int | None, *, path: str = "/api/orders/42", expected: list[int] | None = None, **exchange: Any) -> dict[str, Any]:
    return {
        "label": "a check",
        "passed": False,
        "exchange": {
            "method": "GET", "path": path, "status": status, "expected": [200] if expected is None else expected,
            "credential_sent": False, "precondition": "", **exchange,
        },
    }


@pytest.mark.parametrize(
    ("record", "cause"),
    [
        (_failed(None), Cause.ENVIRONMENT),
        (_failed(500), Cause.APP),
        (_failed(503, expected=[503, 200]), Cause.APP),
        (_failed(500, invented=["0123456789abcdef01234567"]), Cause.BOOK),
        (_failed(404, path="/api/orders/{id}"), Cause.BOOK),
        (_failed(401, credential_sent=False), Cause.BOOK),
        (_failed(403, credential_sent=True, precondition=SIGNED_IN), Cause.ARRANGEMENT),
        (_failed(401, credential_sent=True), Cause.UNATTRIBUTED),
        (_failed(401, expected=[401], credential_sent=True), Cause.BOOK),
        (_failed(409), Cause.BOOK),
        (_failed(200), Cause.BOOK),
        ({**_failed(200), "raised": "KeyError"}, Cause.UNATTRIBUTED),
        ({"label": "a check", "passed": False, "command_ending": {"exit_code": 1, "stderr": ""}}, Cause.BOOK),
        ({"label": "a check", "passed": False}, Cause.UNATTRIBUTED),
    ],
)
def test_the_first_rule_the_evidence_meets_names_the_cause(record: dict[str, Any], cause: Cause) -> None:
    assert attribute(CheckEvidence.model_validate(record)).cause is cause


def test_a_refused_credential_blames_the_precondition_that_issued_it_whatever_the_route() -> None:
    record = _failed(401, credential_sent=True, precondition=SIGNED_IN)

    assert attribute(CheckEvidence.model_validate(record)) == Attribution(Cause.ARRANGEMENT, SIGNED_IN, "401")


def test_a_fixture_that_broke_inside_a_claim_blames_its_page() -> None:
    record = {**_failed(None), "raised": "RuntimeError", "fault": {"fault_class": "defect", "fixture": "signed-in", "page": SIGNED_IN}}

    assert attribute(CheckEvidence.model_validate(record)) == Attribution(Cause.ARRANGEMENT, SIGNED_IN)


def test_an_environment_fault_is_the_environment_s_even_on_a_book_fixture() -> None:
    record = {"label": "a check", "passed": False, "fault": {"fault_class": "environment", "fixture": "signed-in", "page": SIGNED_IN}}

    assert attribute(CheckEvidence.model_validate(record)).cause is Cause.ENVIRONMENT


def test_an_absent_capability_is_the_environment_s_and_names_the_gap() -> None:
    page = "docs/features/billing/fixtures/payment-provider.md"
    record = {"label": "a check", "passed": False, "fault": {"fault_class": "capability", "fixture": "payment-provider", "page": page}}

    assert attribute(CheckEvidence.model_validate(record)) == Attribution(Cause.ENVIRONMENT, page, gap="payment provider")


def test_an_absent_qa_tool_names_the_gap_and_no_page() -> None:
    record = {"label": "a check", "passed": False, "fault": {"fault_class": "capability", "fixture": "qa-tool-ostler", "page": ""}}

    assert attribute(CheckEvidence.model_validate(record)) == Attribution(Cause.ENVIRONMENT, "", gap="qa tool ostler")


def test_a_fault_outside_the_book_s_fixtures_falls_through_to_the_reply() -> None:
    record = {**_failed(500), "fault": {"fault_class": "defect", "fixture": "a-scenario", "page": ""}}

    assert attribute(CheckEvidence.model_validate(record)).cause is Cause.APP


def test_a_route_shape_keeps_the_method_and_first_segment() -> None:
    assert route_shape("POST", "/projects/7/members") == "POST /projects/…"
    assert route_shape("GET", "/") == "GET /"


def test_failures_sharing_a_key_are_one_signature_with_their_count() -> None:
    app = Attribution(Cause.APP, status="500", shape="GET /orders/…")
    arranged = Attribution(Cause.ARRANGEMENT, SIGNED_IN, "401")

    grouped = signatures([(app, "first 500"), (arranged, "a 401"), (app, "second 500"), (app, "third 500")])

    assert [(s.cause, s.count, s.sample) for s in grouped] == [(Cause.APP, 3, "first 500"), (Cause.ARRANGEMENT, 1, "a 401")]
    assert grouped[1].text() == f"arrangement: {SIGNED_IN} answered 401"


def test_failures_on_one_absent_capability_are_one_gapped_signature() -> None:
    gap = Attribution(Cause.ENVIRONMENT, "docs/features/billing/fixtures/payment-provider.md", gap="payment provider")

    grouped = signatures([(gap, "no key"), (gap, "no key again")])

    assert [(s.count, s.gap) for s in grouped] == [(2, "payment provider")]
    assert grouped[0].text() == "gapped: payment provider absent"
