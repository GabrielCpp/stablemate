"""The policy bodies every policy-desk QA plan writes with.

Declared in `agents.yml` under `qa: {fixture_modules: [policies]}` and linted by the same
AST allowlist a plan is. `valid_policy` was byte-identical in `create-policy` and
`policy-list`, and `edit-policy` held a third copy of the same record under a different
name — three spellings of one arrangement, which is three places for the app's field names
and this plan's to drift apart.

The desk opens empty: nothing seeds the ledger, so a scenario creates the record it needs
through the public API. These are the bodies it posts, not the records it reads back.
"""

from typing import Any


def valid_policy(number: str, email: str = "alex@example.com", coverage: str = "auto") -> dict:
    """A policy the desk accepts, in the coverage type named.

    `auto` carries a VIN and `home` an address because the desk refuses each without the
    other — a scenario asking for one of those coverages is asking for the field that goes
    with it, and spelling that out at every call site is how the two drift apart.
    """
    return {
        "policy_number": number,
        "holder_email": email,
        "coverage_type": coverage,
        "vehicle_vin": "1HGCM82633A004352" if coverage == "auto" else "",
        "property_address": "10 Main Street" if coverage == "home" else "",
        "start_date": "2099-01-01",
        "end_date": "2099-12-31",
        "premium": 1000 if coverage == "auto" else 200,
    }


def amendment_body(policy: dict, premium: Any) -> dict:
    """A full amendment of `policy` changing only the premium, quoting the version read.

    The version is carried from the record the caller read rather than re-fetched: an
    amendment that re-reads the policy first is quoting a version that is current by
    construction, which proves nothing about the stale-write refusal.
    """
    return {
        "holder_email": policy["holder_email"],
        "coverage_type": policy["coverage_type"],
        "vehicle_vin": policy.get("vehicle_vin", ""),
        "property_address": policy.get("property_address", ""),
        "start_date": policy["start_date"],
        "end_date": policy["end_date"],
        "premium": premium,
        "version": policy["version"],
    }
