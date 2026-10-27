"""A flow step that links a passage performs the passage's interactions and stops where it lands, waiting for what the passage sends."""

from __future__ import annotations

import ast
import json

from ostler.qa.compile import Gap, Plan, Refusal, compile_plan_gaps
from ostler.qa.harness_host import load_harness_module
from ostler.qa.packet import packet_of

from test_qa_compile import _page_obligation, _step
from test_screen_state_stops import (
    ERROR,
    FLOW_ID,
    FLOW_STEM,
    LOADED,
    LOADED_ID,
    OPEN_DETAILS,
    _SCREEN,
    _context,
    _state,
)

elements = load_harness_module("ostler_qa_elements")

DETAILS = "docs/services/policy/gui/screens/details.md"
SHOWN = f"{DETAILS}#shown"
SHOWN_ID = f"okf:{SHOWN}:contract"
PASSAGE = f"{_SCREEN}#open-details"
LOOP = f"{_SCREEN}#reload"


def _passages(*, to: str = SHOWN, requests: list[str] | None = None) -> dict:
    return {PASSAGE: {"from": LOADED, "steps": [OPEN_DETAILS], "to": to,
                      "requests": ["GET /api/results/{id}"] if requests is None else requests}}


def _walk_context(refs: list[str], *, device: bool = False, passages: dict | None = None,
                  origins: dict[str, str] | None = None) -> dict:
    base = _context(device=device, steps=[LOADED])
    steps = [_step(ref, "passage" if ref == PASSAGE else "state", "policy") for ref in refs]
    for obligation in base["obligations"]:
        if obligation["nodeType"] == "flow":
            obligation["steps"] = steps
    base["obligations"].extend([
        _page_obligation(f"okf:{DETAILS}:contract", DETAILS, source=DETAILS,
                         locators={"requests": ["GET /api/details/{id}"]}, checks=[]) | {
            "nodeType": "screen", "required": False},
        _page_obligation(f"okf:{DETAILS}#details-heading:contract", f"{DETAILS}#details-heading", source=DETAILS,
                         locators={"role": ["heading"], "name": ["Details"]}, checks=[]) | {
            "nodeType": "component", "required": False},
        _state(SHOWN, SHOWN_ID, "Shown: details", ["[Details heading](#details-heading)"]) | {
            "source": DETAILS, "docPosition": [1, 0]},
    ])
    base["passages"] = _passages() if passages is None else passages
    if origins:
        base["serverOrigins"] = origins
    return base


def _compile(context: dict) -> tuple[str, dict[str, str], list[Gap]]:
    result = compile_plan_gaps(context, story="demo-story")
    if isinstance(result, Plan):
        ast.parse(result.source)
        return result.source.split("@scenario(")[-1], result.files, result.gaps
    assert isinstance(result, Refusal)
    return "", {}, result.gaps


def _settles(journey: str) -> list[str]:
    parts = journey.split("qa.settle(")[1:]
    return [part.split("    )  # ", 1)[0] for part in parts]


def test_a_web_walk_over_a_passage_clicks_then_waits_for_what_it_sends_and_what_the_next_screen_loads() -> None:
    journey, _, gaps = _compile(_walk_context([LOADED, PASSAGE], origins={_SCREEN: "http://127.0.0.1:8099"}))

    first, second = _settles(journey)
    assert 'expect="loaded"' in first and "origins=" not in first
    assert 'expect="shown"' in second
    assert second.index('("GET", "/api/results/{id}")') < second.index('("GET", "/api/details/{id}")')
    assert "origins=[\"http://127.0.0.1:8099\"]" in second
    opened = journey.index("qa.settle(")
    assert journey.index("mark = qa.mark()", opened) < journey.index('"Open details"', opened) < journey.index("qa.settle(", opened + 1)
    assert SHOWN_ID in second
    assert [gap for gap in gaps if gap.obligation_id == SHOWN_ID] == []


def test_a_flow_that_starts_with_a_passage_stops_at_where_it_leaves_first() -> None:
    journey, _, _ = _compile(_walk_context([PASSAGE]))

    first, second = _settles(journey)
    assert 'expect="loaded"' in first and LOADED_ID in first
    assert 'expect="shown"' in second
    assert journey.index("qa.goto(") < journey.index("qa.settle(") < journey.index('"Open details"')


def test_a_state_step_right_after_the_passage_that_lands_on_it_is_not_stopped_at_twice() -> None:
    journey, _, gaps = _compile(_walk_context([LOADED, PASSAGE, SHOWN]))

    assert len(_settles(journey)) == 2
    assert not [gap for gap in gaps if "broken" in gap.detail or "lands on" in gap.detail]


def test_a_stop_after_a_passage_that_is_not_where_it_lands_gaps_the_flow_with_the_doctors_wording() -> None:
    journey, _, gaps = _compile(_walk_context([LOADED, PASSAGE, LOADED]))

    assert "qa.settle(" not in journey
    assert any(gap.obligation_id == FLOW_ID and "before it lands on" in gap.detail for gap in gaps)


def test_a_passage_that_leaves_another_state_than_the_walk_is_at_gaps_the_flow() -> None:
    _, _, gaps = _compile(_walk_context([ERROR, PASSAGE]))

    assert any(gap.obligation_id == FLOW_ID and "which leaves" in gap.detail for gap in gaps)


def test_a_passage_the_packet_does_not_carry_gaps_the_flow() -> None:
    _, _, gaps = _compile(_walk_context([LOADED, PASSAGE], passages={}))

    assert any(gap.obligation_id == FLOW_ID and "passage" in gap.detail for gap in gaps)


def test_a_passage_within_one_screen_waits_only_for_what_it_sends() -> None:
    passages = {PASSAGE: {"from": LOADED, "steps": [OPEN_DETAILS], "to": f"{_SCREEN}#error",
                          "requests": ["POST /api/results/retry"]}}
    journey, _, _ = _compile(_walk_context([LOADED, PASSAGE], passages=passages))

    second = _settles(journey)[1]
    assert '("POST", "/api/results/retry")' in second
    assert '("GET", "/api/results")' not in second


def test_a_book_with_no_server_origin_adds_no_origins_to_the_stop() -> None:
    journey, _, _ = _compile(_walk_context([LOADED, PASSAGE]))

    assert "origins=" not in "".join(_settles(journey))


def test_a_flow_without_a_passage_compiles_with_no_origins_whatever_the_book_serves() -> None:
    plain = _context()
    with_origins = _context() | {"serverOrigins": {_SCREEN: "http://127.0.0.1:8099"}, "passages": _passages()}
    assert "origins=" not in _compile(with_origins)[0]
    assert _compile(plain)[0] == _compile(plain | {"passages": _passages()})[0]


def test_a_device_walk_over_a_passage_cuts_at_its_stop_with_no_requests_and_no_origins() -> None:
    journey, files, _ = _compile(_walk_context([LOADED, PASSAGE], device=True, origins={_SCREEN: "http://127.0.0.1:8099"}))

    first, second = _settles(journey)
    assert 'expect="shown"' in second
    assert "requests=" not in first + second and "origins=" not in first + second and "since=" not in second
    assert f"{FLOW_STEM}-1.yaml" in files and f"{FLOW_STEM}-2.yaml" in files
    opens = f"text: {json.dumps(elements.maestro_pattern('Open details'))}"
    assert opens in files[f"{FLOW_STEM}-2.yaml"] or opens in files[f"{FLOW_STEM}-1.yaml"]


def test_the_packet_carries_the_passages_and_a_passage_owes_nothing() -> None:
    packet = packet_of(_walk_context([LOADED, PASSAGE]))

    assert packet.passages[PASSAGE].end == SHOWN
    assert packet.passages[PASSAGE].requests == ("GET /api/results/{id}",)


def _acting_walk(refs: list[str], *, arrival: bool = False) -> dict:
    base = _walk_context([LOADED], passages={})
    kinds = {OPEN_DETAILS: "interaction", RELOAD: "interaction"}
    steps = [_step(ref, kinds.get(ref, "state"), "policy") for ref in refs]
    for obligation in base["obligations"]:
        if obligation["nodeType"] == "flow":
            obligation["steps"] = steps
    if arrival:
        base["obligations"].append(
            _page_obligation(f"okf:{RELOAD}:contract", RELOAD, locators={"trigger": ["load"]}, checks=[]))
    return base


RELOAD = f"{_SCREEN}#reload-click"


def test_a_stop_after_an_interaction_on_the_same_screen_waits_for_none_of_its_requests() -> None:
    journey, _, _ = _compile(_acting_walk([LOADED, OPEN_DETAILS, ERROR]))

    opening, after = _settles(journey)
    assert '("GET", "/api/results")' in opening
    assert "requests=[]" in after
    assert '"role": "progressbar"' in after
    assert '"error"' in after and 'expect="error"' in after


def test_a_stop_after_an_interaction_on_another_screen_keeps_that_screens_requests() -> None:
    journey, _, _ = _compile(_acting_walk([LOADED, OPEN_DETAILS, SHOWN]))

    after = _settles(journey)[1]
    assert '("GET", "/api/details/{id}")' in after
    assert 'expect="shown"' in after


def test_the_opening_stop_keeps_its_screens_requests() -> None:
    journey, _, _ = _compile(_acting_walk([LOADED, OPEN_DETAILS, ERROR]))

    assert '("GET", "/api/results")' in _settles(journey)[0]


def test_a_stop_after_an_arrival_trigger_on_the_same_screen_keeps_its_requests() -> None:
    journey, _, _ = _compile(_acting_walk([LOADED, RELOAD, ERROR], arrival=True))

    assert len(_settles(journey)) == 2
    assert '("GET", "/api/results")' in _settles(journey)[1]
