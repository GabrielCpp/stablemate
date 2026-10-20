"""A claim that states its condition with `when:` reads the linked data state from the API before its checks."""

from __future__ import annotations

import ast

from ostler.qa.compile import Plan, compile_plan_gaps

from test_qa_compile import (
    _SCREEN,
    _arrival_navigation,
    _gap_kinds,
    _located,
    _navigation_context,
    _page_obligation,
    _visible,
)
from test_screen_state_stops import (
    ERROR_ID,
    FLOW_ID,
    LOADED,
    LOADED_ID,
    OPEN_DETAILS,
    _compile,
    _compile_all,
    _context,
    _scenarios,
    _walk_context,
)

API = "api-service/http/api-service.md"
NONE_LOW = f"{API}#none-low"
SOME_LOW = f"{API}#some-low"
STATES = {
    NONE_LOW: {"of": "widget", "observe": f"{API}#list-widgets", "method": "GET", "path": "/api/widgets",
               "verify": ['count(subject="$.widgets[?(@.quantity<5)]", equals=0)']},
    SOME_LOW: {"of": "widget", "observe": f"{API}#list-widgets", "method": "GET", "path": "/api/widgets",
               "verify": ['count(subject="$.widgets[?(@.quantity<5)]", greater_than=0)']},
}
ORIGINS = {API: "http://localhost:18101"}
NODE = f"{_SCREEN}#low-stock-panel"
STATE_ID = "okf:widget-list:low-stock-panel:states:1"
FIXTURE = {"name": "well-stocked", "args": [], "provides": "every widget holds at least 5"}


def _arrival(*, conditions: list[str] | None, states: dict | None = None, origins: dict | None = None) -> dict:
    claim = _page_obligation(
        STATE_ID, NODE, kind="states", requirement="shows when no widget is below 5.",
        locators={"role": ["status"], "name": ["Low stock"]}, checks=[_visible("status:Low stock")],
        fixtures=[FIXTURE])
    if conditions is not None:
        claim["conditionsDeclared"] = conditions
    context = _navigation_context(claim, navigation=_arrival_navigation())
    context["dataStates"] = STATES if states is None else states
    context["serverOrigins"] = ORIGINS if origins is None else origins
    return context


def _arrival_body(context: dict) -> str:
    result = compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Plan)
    ast.parse(result.source)
    return result.source


def test_an_arrival_reads_the_condition_from_the_api_origin_before_the_claims_checks() -> None:
    source = _arrival_body(_arrival(conditions=[NONE_LOW]))
    assert 'held_1 = qa.http.get("http://localhost:18101/api/widgets")' in source
    assert 'qa.condition("none-low", "' + _SCREEN + '", {"none-low": [' in source
    assert '"some-low": [' in source
    assert source.index("qa.condition(") < source.index("status:Low stock")
    assert source.index('qa.fixture("well-stocked")') < source.index("qa.condition(")


def test_an_arrival_without_when_compiles_to_the_same_lines_as_before() -> None:
    source = _arrival_body(_arrival(conditions=None))
    assert "qa.condition(" not in source
    assert "held_1" not in source


def test_a_condition_that_links_no_data_state_files_unread_condition_and_no_scenario() -> None:
    result = compile_plan_gaps(_arrival(conditions=[f"{API}#missing"]), story="demo-story")
    assert _gap_kinds(result.gaps, STATE_ID) == ["unread-condition"]
    assert "status:Low stock" not in getattr(result, "source", "")


def test_a_condition_with_no_known_origin_files_unread_condition() -> None:
    result = compile_plan_gaps(_arrival(conditions=[NONE_LOW], origins={}), story="demo-story")
    assert _gap_kinds(result.gaps, STATE_ID) == ["unread-condition"]
    [gap] = [gap for gap in result.gaps if gap.obligation_id == STATE_ID]
    assert "no API origin" in gap.detail


def test_a_condition_read_by_a_post_files_unread_condition() -> None:
    states = {NONE_LOW: STATES[NONE_LOW] | {"method": "POST"}}
    result = compile_plan_gaps(_arrival(conditions=[NONE_LOW], states=states), story="demo-story")
    [gap] = [gap for gap in result.gaps if gap.obligation_id == STATE_ID]
    assert gap.kind == "unread-condition"
    assert "only a GET reads a condition" in gap.detail


def test_a_state_walk_reads_the_condition_after_the_arrival_and_before_the_settle() -> None:
    context = _walk_context()
    context["dataStates"] = STATES
    context["serverOrigins"] = ORIGINS
    for row in context["obligations"]:
        if row["id"] == ERROR_ID:
            row["conditionsDeclared"] = [NONE_LOW]
            row["fixturesDeclared"] = [FIXTURE]
    source, _, gaps = _compile_all(context)
    error = next(body for name, body in _scenarios(source).items() if name.endswith("error_settles"))
    assert not [gap for gap in gaps if gap.obligation_id == ERROR_ID]
    assert 'qa.http.get("http://localhost:18101/api/widgets")' in error
    assert error.index("qa.goto(") < error.index("qa.condition(") < error.index("qa.settle(")


def test_a_state_walk_whose_condition_cannot_be_read_files_a_gap_and_no_scenario() -> None:
    context = _walk_context()
    for row in context["obligations"]:
        if row["id"] == ERROR_ID:
            row["conditionsDeclared"] = [NONE_LOW]
            row["fixturesDeclared"] = [FIXTURE]
    source, _, gaps = _compile_all(context)
    assert [gap.kind for gap in gaps if gap.obligation_id == ERROR_ID] == ["unread-condition"]
    assert not [name for name in _scenarios(source) if name.endswith("error_settles")]


BUTTON = f"{_SCREEN}#restock-button"
RESTOCK_ID = "okf:widget-list:restock:does:1"


def _restock(*, conditions: list[str]) -> dict:
    claim = _page_obligation(
        RESTOCK_ID, f"{_SCREEN}#restock", kind="does",
        locators={"on": ["[restock-button](#restock-button)"], "trigger": ["click"], "does": ["restocks"]},
        checks=[_located("#restocked", f"{_SCREEN}#restocked", {"selector": ["`#restocked`"]})])
    claim["conditionsDeclared"] = conditions
    context = _navigation_context(
        _page_obligation("okf:widget-list:restock-button:visible:1", BUTTON,
                         locators={"role": ["button"], "name": ["Restock"]}, checks=[_visible("button:Restock")]),
        claim, navigation=_arrival_navigation())
    context["dataStates"] = STATES
    context["serverOrigins"] = ORIGINS
    return context


def test_an_interaction_reads_the_condition_after_the_arrival_and_before_the_act() -> None:
    source = _arrival_body(_restock(conditions=[SOME_LOW]))
    restock = source[source.index("_restock(qa: Qa)"):]
    assert 'qa.condition("some-low", "' in restock
    assert restock.index("qa.goto(") < restock.index("qa.condition(") < restock.index("# trigger: click")


def test_an_interaction_whose_condition_cannot_be_read_files_a_gap_and_no_scenario() -> None:
    result = compile_plan_gaps(_restock(conditions=[f"{API}#missing"]), story="demo-story")
    assert _gap_kinds(result.gaps, RESTOCK_ID) == ["unread-condition"]
    assert "_restock(qa: Qa)" not in getattr(result, "source", "")


def _journey(*, conditions: list[str]) -> dict:
    context = _context(steps=[LOADED, OPEN_DETAILS, LOADED])
    context["dataStates"] = STATES
    context["serverOrigins"] = ORIGINS
    for row in context["obligations"]:
        if row["id"] == LOADED_ID:
            row["conditionsDeclared"] = conditions
    return context


def test_a_journey_reads_a_stop_before_its_settle_until_an_act_and_after_its_settle_from_then_on() -> None:
    journey, gaps = _compile(_journey(conditions=[SOME_LOW]))
    assert not [gap for gap in gaps if gap.obligation_id == FLOW_ID]
    first, act, second = (journey.index("qa.condition("), journey.index('"Open details"'),
                          journey.rindex("qa.condition("))
    assert journey.index("qa.settle(") > first
    assert first < act < journey.rindex("qa.settle(") < second


def test_a_journey_stop_whose_condition_cannot_be_read_files_a_gap_and_no_journey() -> None:
    journey, gaps = _compile(_journey(conditions=[f"{API}#missing"]))
    [gap] = [gap for gap in gaps if gap.obligation_id == FLOW_ID]
    assert gap.kind == "unread-condition"
    assert gap.detail.startswith(f"step 1 stops at `{LOADED}`: ")
    assert "qa.settle(" not in journey
