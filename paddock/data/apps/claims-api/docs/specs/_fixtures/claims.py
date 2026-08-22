"""The request bodies a claims-api QA plan files claims with.

One shape with defaults rather than a shape per plan: what varies between scenarios is the
policy number and, occasionally, the description — everything else was different only
because it was retyped. A scenario that needs a particular value says so at the call site,
where the assertion that reads it can be seen next to it.
"""

from typing import Any

#: A well-formed submission. Every field the book documents as required is here, so a plan
#: overriding one is choosing a value rather than completing the body.
_SUBMISSION: dict[str, Any] = {
    "policy_number": "PL-4471",
    "incident_date": "2099-03-14",
    "amount_cents": 125000,
    "description": "Hail damage to the roof of the insured property.",
}


def submission(policy_number: str = _SUBMISSION["policy_number"], **overrides: Any) -> dict:
    """A claim submission body, with `policy_number` first because that is what varies.

    Two claims filed with the same policy number and incident date are the duplicate the
    book documents a `409` for, so a scenario that wants two *distinct* claims has to say
    a distinct policy number — and one that wants the duplicate says nothing at all.
    """
    return {**_SUBMISSION, "policy_number": policy_number, **overrides}
