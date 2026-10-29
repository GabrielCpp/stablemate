"""The verification setup names a stack, so a check command written into it never reaches QA."""
from __future__ import annotations

from workhorse_workflows.coder.shared.plan import plan_document
from workhorse_workflows.coder.shared.schemas.dev import PlanFields

DEV_CHECKS = {
    "acme": [
        "cd api && make lint",
        "ostler qa run qa_plan.py --spec spec --scenario one",
    ]
}


def test_a_reply_that_lists_check_commands_keeps_none_of_them():
    plan = PlanFields.model_validate({"verification_setup": {**DEV_CHECKS, "profile": "full"}})

    dumped = plan.model_dump()["verification_setup"]

    assert "acme" not in dumped
    assert dumped["profile"] == "full"


def test_a_plan_context_written_with_check_commands_hands_qa_only_the_stack():
    doc = plan_document({"verification_setup": {**DEV_CHECKS, "profile": "full"}}, {})

    assert doc["verification_setup"] == {"profile": "full"}
