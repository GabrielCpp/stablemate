"""A flow step that links a screen state is a stop: the walk waits for the screen to settle there, checks the state, and goes on."""

from __future__ import annotations

import ast
import re

from ostler.qa.compile import Gap, Plan, Refusal, compile_plan_gaps

from test_qa_compile import (
    _FLOW,
    _SCREEN,
    _arrival_navigation,
    _flow_obligation,
    _located_visible,
    _navigation_context,
    _page_obligation,
    _step,
)

LOADED = f"{_SCREEN}#loaded"
ERROR = f"{_SCREEN}#error"
OPEN_DETAILS = f"{_SCREEN}#open-details-click"
LOADED_ID = f"okf:{LOADED}:contract"
ERROR_ID = f"okf:{ERROR}:contract"
FLOW_ID = f"okf:{_FLOW}:end-state"


def _component(anchor: str, role: str | None, name: str | None) -> dict:
    locators: dict = {}
    if role:
        locators["role"] = [role]
    if name:
        locators["name"] = [name]
    return _page_obligation(f"okf:{_SCREEN}#{anchor}:contract", f"{_SCREEN}#{anchor}", locators=locators,
                            checks=[]) | {"nodeType": "component", "required": False}


def _state(node: str, oid: str, title: str, shows: list[str]) -> dict:
    return _page_obligation(oid, node, locators={"shows": shows}, checks=[], requirement=title) | {
        "nodeType": "state", "kind": "contract", "docPosition": [1, 0] if node == LOADED else [2, 0],
    }


def _screen() -> dict:
    return _page_obligation(
        f"okf:{_SCREEN}:contract", _SCREEN,
        locators={"requests": ["GET /api/results"], "busy": ["[Loading results](#loading-results)"]},
        checks=[],
    ) | {"nodeType": "screen", "required": False}


def _context(*, loaded_shows: list[str] | None = None, components: dict | None = None,
             steps: list[str] | None = None, device: bool = False) -> dict:
    parts = components or {
        "loading-results": ("progressbar", "Loading results"),
        "results-table": ("table", "Results"),
        "load-error": ("alert", "Could not load results"),
    }
    walk = steps if steps is not None else [LOADED, OPEN_DETAILS]
    navigation = _arrival_navigation()
    if device:
        navigation["policy"]["driver"] = "mobile"
        navigation["policy"]["bundleId"] = "com.example.mobile-app"
        navigation["policy"]["launchScreen"] = _SCREEN
    return _navigation_context(
        _flow_obligation(
            FLOW_ID, source=_FLOW, surface="policy",
            steps=[_step(ref, "state" if "click" not in ref else "interaction", "policy") for ref in walk],
            checks=[_located_visible(f"{_SCREEN}#results-table", {"role": ["table"], "name": ["Results"]})],
        ),
        _screen(),
        _state(LOADED, LOADED_ID, "Loaded: results",
               loaded_shows or ["[Results table](#results-table)", "[Load error](#load-error) absent"]),
        _state(ERROR, ERROR_ID, "Error: load error", ["[Load error](#load-error)"]),
        _page_obligation(f"okf:{OPEN_DETAILS}:contract", OPEN_DETAILS,
                         locators={"on": ["[Open details](#open-details)"], "trigger": ["click"]}, checks=[]),
        _component("open-details", "button", "Open details"),
        *(_component(anchor, role, name) for anchor, (role, name) in parts.items()),
        navigation=navigation,
    )


def _compile(context: dict) -> tuple[str, list[Gap]]:
    result = compile_plan_gaps(context, story="demo-story")
    if isinstance(result, Plan):
        ast.parse(result.source)
        return result.source.split("@scenario(")[-1], result.gaps
    assert isinstance(result, Refusal)
    return "", result.gaps


def test_a_stop_waits_for_the_screen_before_the_click_that_follows_it() -> None:
    journey, _ = _compile(_context())

    assert "    mark = qa.mark()" in journey
    assert journey.index("mark = qa.mark()") < journey.index("qa.goto(")
    assert journey.index("qa.goto(") < journey.index("qa.settle(")
    assert journey.index("qa.settle(") < journey.index('"Open details"')
    assert journey.count("mark = qa.mark()") == 2


def test_a_stop_lists_every_state_of_the_screen_and_names_the_one_expected() -> None:
    journey, _ = _compile(_context())
    settle = journey[journey.index("qa.settle("):journey.index("# step 1: stop at")]

    assert f'"{LOADED}"' in settle
    assert 'expect="loaded"' in settle
    assert '"loaded"' in settle and '"error"' in settle
    assert '("GET", "/api/results")' in settle
    assert '"role": "progressbar"' in settle
    assert '"absent": True' in settle
    assert LOADED_ID in settle
    assert ERROR_ID not in settle


def test_a_stop_names_no_number_of_seconds() -> None:
    journey, _ = _compile(_context())
    settle = journey[journey.index("qa.settle("):journey.index("# step 1: stop at")]

    assert not re.search(r"\d+\.\d|timeout|seconds|_s=|_ms", settle)


def test_a_stop_covers_its_state_and_the_other_state_is_left_to_a_walk_that_stops_at_it() -> None:
    journey, gaps = _compile(_context())

    assert LOADED_ID in journey
    assert [gap.kind for gap in gaps if gap.obligation_id == LOADED_ID] == []
    assert [gap.kind for gap in gaps if gap.obligation_id == ERROR_ID] == ["uncompilable-claim"]
    [gap] = [gap for gap in gaps if gap.obligation_id == ERROR_ID]
    assert "no compiled flow stops at" in gap.detail


def test_a_shown_component_with_no_role_and_name_stops_the_walk_with_a_gap() -> None:
    components = {
        "loading-results": ("progressbar", "Loading results"),
        "results-table": ("table", None),
        "load-error": ("alert", "Could not load results"),
    }
    journey, gaps = _compile(_context(components=components))

    assert "qa.settle(" not in journey
    assert any("is found by no role and accessible name" in gap.detail for gap in gaps)


def test_a_flow_with_no_stop_emits_no_mark() -> None:
    journey, _ = _compile(_context(steps=[OPEN_DETAILS]))

    assert "qa.mark()" not in journey
    assert "qa.settle(" not in journey
    assert '"Open details"' in journey


def test_a_stop_in_a_flow_on_a_device_is_a_gap_not_a_skip() -> None:
    _, gaps = _compile(_context(device=True))

    assert any("stops are not compiled for devices yet" in gap.detail for gap in gaps)
