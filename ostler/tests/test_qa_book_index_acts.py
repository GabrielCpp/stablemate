"""A node's acts merge its claims' arrangements without losing a step one claim repeats."""

from __future__ import annotations

from ostler.qa.book_index import node_acts
from ostler.qa.obligation import Obligation
from ostler.qa.obligation import obligation_of

_NODE = "docs/features/acme/gui/screens/items.md#reopen-item"


def _claim(kind: str, position: int, calls: list[str]) -> Obligation:
    return obligation_of({
        "id": f"okf:{_NODE}:{kind}:1",
        "kind": kind,
        "node": _NODE,
        "nodeType": "interaction",
        "source": "docs/features/acme/gui/screens/items.md",
        "docPosition": [position],
        "actsDeclared": [{"call": call, "name": call.split("(")[0]} for call in calls],
    })


def test_a_step_one_claim_repeats_is_kept_each_time() -> None:
    visit = 'visit(path="/dashboard")'
    pick = 'click(locator="#item-picker")'
    save = 'click(locator="#save-button")'

    acts = node_acts([_claim("does", 1, [visit, pick, save, visit, pick])])

    assert [row.call for row in acts.by_node[_NODE]] == [visit, pick, save, visit, pick]


def test_claims_that_share_a_step_run_it_once() -> None:
    visit = 'visit(path="/dashboard")'
    pick = 'click(locator="#item-picker")'
    save = 'click(locator="#save-button")'

    acts = node_acts([_claim("does", 1, [visit, pick]), _claim("when", 2, [visit, pick, save])])

    assert [row.call for row in acts.by_node[_NODE]] == [visit, pick, save]
