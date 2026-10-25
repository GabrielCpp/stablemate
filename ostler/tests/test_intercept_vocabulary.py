"""The intercept effects: a vocabulary of their own, parsed by the check grammar and counted as no coverage."""

from __future__ import annotations

import pytest

from ostler import checks
from ostler.qa.obligation_frame import BookNode, ObligationFrame, obligation_frame

_REWRITE = 'rewrite(event="POST /api/report/data", find="1300", replace="4200")'


def test_a_valid_rewrite_binds_its_three_arguments() -> None:
    call = checks.parse_intercept(_REWRITE)

    assert isinstance(call, checks.CheckCall)
    assert (call.name, call.args) == (
        "rewrite", {"event": "POST /api/report/data", "find": "1300", "replace": "4200"})


def test_the_check_vocabulary_does_not_know_an_effect_and_the_effects_do_not_know_a_check() -> None:
    assert isinstance(checks.parse_check(_REWRITE), checks.Refusal)
    assert isinstance(checks.parse_intercept('visible(locator="#a")'), checks.Refusal)
    assert "rewrite" not in checks.CHECK_BY_NAME


@pytest.mark.parametrize("value", [
    'rewrite(event="POST /api/report/data", replace="4200")',
    'rewrite(event="POST /api/report/data", find="1300")',
    'rewrite(find="1300", replace="4200")',
    'rewrite(event="POST /api/report/data", find="", replace="4200")',
    'rewrite(event="POST /api/report/data", find="1300", replace="")',
    'rewrite(event="/api/report/data", find="1300", replace="4200")',
    'rewrite(event="POST /api/report/data", find=1300, replace="4200")',
    'rewrite(event="POST /api/report/data", find="1", replace="2", extra="x")',
    'swap(event="POST /api/report/data", find="1300", replace="4200")',
    "rewrite",
    "",
])
def test_a_malformed_rewrite_is_refused(value: str) -> None:
    assert isinstance(checks.parse_intercept(value), checks.Refusal)


def test_a_path_segment_placeholder_is_a_valid_event() -> None:
    call = checks.parse_intercept('rewrite(event="GET /api/{id}/data", find="a", replace="b")')

    assert isinstance(call, checks.CheckCall)


def test_a_frame_carries_its_intercepts_into_the_obligation_row() -> None:
    call = checks.parse_intercept(_REWRITE)
    assert isinstance(call, checks.CheckCall)
    frame = ObligationFrame(
        surface="web", steps=(), on_cli_page=False, locators={}, extends_unresolved=False,
        repeat=None, intercepts=(call,))

    assert frame.row()["intercepts"] == [{"effect": "rewrite", "args": call.args}]
    assert "intercepts" not in ObligationFrame(
        surface="web", steps=(), on_cli_page=False, locators={}, extends_unresolved=False,
        repeat=None).row()


def test_a_flow_node_hands_its_parsed_intercepts_to_the_frame_and_drops_a_bad_one() -> None:
    flow = BookNode(
        id="docs/services/web-app/flows/f.md", type="flow", page_type="", surface="web-app",
        bullets={"intercept": (_REWRITE, "make the total wrong")}, edges=(),
    )

    frame = obligation_frame(flow, None, {})

    assert [(call.name, call.args["find"]) for call in frame.intercepts] == [("rewrite", "1300")]
    assert obligation_frame(
        BookNode(id="x", type="flow", page_type="", surface="", bullets={}, edges=()), None, {}
    ).intercepts == ()
