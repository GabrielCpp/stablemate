"""A flow step that links a screen state is a stop: the walk waits for the screen to settle there, checks the state, and goes on."""

from __future__ import annotations

import ast
import re

from ostler.qa.compile import Gap, Plan, Refusal, compile_plan_gaps

from test_qa_compile import (
    _covers,
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
EMPTY = f"{_SCREEN}#empty"
LOADED_ID = f"okf:{LOADED}:contract"
EMPTY_ID = f"okf:{EMPTY}:contract"
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
    context = _navigation_context(
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
    if device:
        context["screenRoutes"][_SCREEN] = "PolicyList"
    return context


def _compile(context: dict) -> tuple[str, list[Gap]]:
    source, _, gaps = _compile_files(context)
    return source, gaps


def _compile_files(context: dict) -> tuple[str, dict[str, str], list[Gap]]:
    result = compile_plan_gaps(context, story="demo-story")
    if isinstance(result, Plan):
        ast.parse(result.source)
        return result.source.split("@scenario(")[-1], result.files, result.gaps
    assert isinstance(result, Refusal)
    return "", {}, result.gaps


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
    assert [gap.kind for gap in gaps if gap.obligation_id == ERROR_ID] == ["unarranged-state"]
    [gap] = [gap for gap in gaps if gap.obligation_id == ERROR_ID]
    assert "no compiled flow stops at" in gap.detail
    assert "Indent a `fixture:` under the state" in gap.detail
    assert "fixture: none, because ..." in gap.detail


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


FLOW_STEM = "maestro/okf_docs_features_demo_flows_add_a_thing_md_end_state"


def test_a_stop_on_a_device_settles_between_two_flow_files_and_goes_on_tapping() -> None:
    journey, files, gaps = _compile_files(_context(device=True))

    assert not [gap for gap in gaps if gap.detail.startswith("step 1 stops at")]
    first = journey.index(f'qa.maestro.run(qa.spec_dir / "{FLOW_STEM}-1.yaml", require=True)')
    settle = journey.index("qa.settle(")
    second = journey.index(f'journey_result = qa.maestro.run(qa.spec_dir / "{FLOW_STEM}-2.yaml")')
    assert first < settle < second < journey.index("qa.verify(")
    assert files[f"{FLOW_STEM}-1.yaml"] == 'appId: "com.example.mobile-app"\n---\n- launchApp:\n    clearState: true\n'
    assert "- launchApp" not in files[f"{FLOW_STEM}-2.yaml"]
    assert 'text: "Open details"' in files[f"{FLOW_STEM}-2.yaml"]
    assert f"{FLOW_STEM}.yaml" not in files


def test_a_device_stop_lists_every_state_and_names_no_request_nor_number_of_seconds() -> None:
    journey, _ = _compile(_context(device=True))
    settle = journey[journey.index("qa.settle("):journey.index("# step 1: stop at")]

    assert 'expect="loaded"' in settle
    assert '"loaded"' in settle and '"error"' in settle
    assert '"role": "progressbar"' in settle
    assert LOADED_ID in settle
    assert ERROR_ID not in settle
    assert "since=" not in settle
    assert "requests=" not in settle
    assert not re.search(r"\d+\.\d|timeout|seconds|_s=|_ms", settle)


def test_a_device_stop_covers_its_state_obligation() -> None:
    journey, gaps = _compile(_context(device=True))

    assert LOADED_ID in journey
    assert [gap.kind for gap in gaps if gap.obligation_id == LOADED_ID] == []


def test_an_expanded_modifier_on_a_device_stop_is_a_gap_naming_the_hierarchy() -> None:
    journey, gaps = _compile(_context(device=True, loaded_shows=["[Results table](#results-table) expanded"]))

    assert "qa.settle(" not in journey
    assert any("is checked for `expanded`, which a device's view hierarchy does not report" in gap.detail
               for gap in gaps)


def test_the_same_stop_compiles_on_the_web_and_on_a_device() -> None:
    for device in (False, True):
        journey, gaps = _compile(_context(device=device))

        assert "qa.settle(" in journey
        assert not [gap for gap in gaps if gap.detail.startswith("step 1 stops at")]


def test_a_device_flow_with_no_stop_is_one_flow_file_that_launches_first() -> None:
    journey, files, _ = _compile_files(_context(device=True, steps=[OPEN_DETAILS]))

    assert files[f"{FLOW_STEM}.yaml"] == (
        'appId: "com.example.mobile-app"\n---\n- launchApp:\n    clearState: true\n'
        '- scrollUntilVisible:\n    element:\n      text: "Open details"\n    direction: DOWN\n'
        '- tapOn:\n    text: "Open details"\n'
        '- scrollUntilVisible:\n    element:\n      text: "Results"\n    direction: DOWN\n'
        '- assertVisible:\n    text: "Results"\n')
    assert f'    journey_result = qa.maestro.run(qa.spec_dir / "{FLOW_STEM}.yaml")' in journey
    assert "require=True" not in journey
    assert "qa.settle(" not in journey


def _walk_context(*, device: bool = False, error_fixtures: list[dict] | None = None,
                  empty_arrangement: bool = True, fixture_screens: dict[str, str] | None = None) -> dict:
    context = _context(steps=[LOADED], device=device)
    for row in context["obligations"]:
        if row["id"] == ERROR_ID and error_fixtures is not None:
            row["fixturesDeclared"] = error_fixtures
    empty = _state(EMPTY, EMPTY_ID, "Empty: no results", ["[No results](#no-results)"]) | {"docPosition": [3, 0]}
    if empty_arrangement:
        empty["arrangesNothing"] = True
    context["obligations"].extend([empty, _component("no-results", "status", "No results")])
    if fixture_screens is not None:
        context["fixtureScreens"] = fixture_screens
    return context


_RESULTS_FAIL = [{"name": "results-fail", "args": [], "provides": "the results request fails"}]


def _scenarios(source: str) -> dict[str, str]:
    return {
        match.group(1): body
        for body in source.split("@scenario(")[1:]
        if (match := re.search(r"def (\w+)\(qa: Qa\)", body))
    }


def _compile_all(context: dict) -> tuple[str, dict[str, str], list[Gap]]:
    result = compile_plan_gaps(context, story="demo-story")
    if isinstance(result, Plan):
        ast.parse(result.source)
        return result.source, result.files, result.gaps
    assert isinstance(result, Refusal)
    return "", {}, result.gaps


def test_a_state_no_flow_stops_at_gets_a_one_screen_walk_on_the_web() -> None:
    source, _, gaps = _compile_all(_walk_context(error_fixtures=_RESULTS_FAIL))
    scenarios = _scenarios(source)

    assert not [gap for gap in gaps if gap.obligation_id in (LOADED_ID, ERROR_ID, EMPTY_ID)]
    assert not [name for name in scenarios if name.endswith("loaded_settles")]
    error = next(body for name, body in scenarios.items() if name.endswith("error_settles"))
    assert f'covers=[\n        "{ERROR_ID}",\n    ]' in error
    assert 'qa.fixture("results-fail")' in error
    assert error.index('qa.fixture("results-fail")') < error.index("mark = qa.mark()") < error.index("qa.goto(")
    assert error.index("qa.goto(") < error.index("qa.settle(")
    assert "since=mark" in error
    assert '("GET", "/api/results")' in error
    assert 'expect="error"' in error
    assert f'covers=["{ERROR_ID}"]' in error
    assert LOADED_ID not in error and EMPTY_ID not in error
    assert error.index("qa.settle(") < error.index(f'qa.vet("{_SCREEN}"') and "qa.window(" not in error
    empty = next(body for name, body in scenarios.items() if name.endswith("empty_settles"))
    assert "qa.fixture(" not in empty
    assert empty.index("mark = qa.mark()") < empty.index("qa.goto(") < empty.index("qa.settle(")
    assert 'expect="empty"' in empty
    assert f'covers=["{EMPTY_ID}"]' in empty
    assert "Arrive at" in empty and "check it settles in Empty" in empty


def test_a_state_walk_on_a_device_launches_cold_and_settles_without_a_request_feed() -> None:
    source, files, gaps = _compile_all(_walk_context(device=True, error_fixtures=_RESULTS_FAIL))
    scenarios = _scenarios(source)

    assert not [gap for gap in gaps if gap.obligation_id in (LOADED_ID, ERROR_ID, EMPTY_ID)]
    for name, expect in (("error", ERROR_ID), ("empty", EMPTY_ID)):
        function = next(fn for fn in scenarios if fn.endswith(f"{name}_settles"))
        body = scenarios[function]
        flow = f"maestro/{function}.yaml"
        assert f'qa.maestro.run(qa.spec_dir / "{flow}", require=True)' in body
        assert files[flow] == 'appId: "com.example.mobile-app"\n---\n- launchApp:\n    clearState: true\n'
        settle = body[body.index("qa.settle("):]
        assert f'expect="{name}"' in settle
        assert "since=" not in settle and "requests=" not in settle
        assert f'covers=["{expect}"]' in settle
        assert f'qa.vet("{_SCREEN}")' in settle
    assert 'qa.fixture("results-fail")' in scenarios[next(fn for fn in scenarios if fn.endswith("error_settles"))]


def test_a_state_walk_vets_the_screen_it_settled_so_the_harness_takes_its_evidence() -> None:
    """The harness fails a UI scenario that vetted no screen, so a walk that only settled would never go green."""
    web, _, _ = _compile_all(_walk_context(error_fixtures=_RESULTS_FAIL))
    device, _, _ = _compile_all(_walk_context(device=True, error_fixtures=_RESULTS_FAIL))
    for source in (web, device):
        for name, body in _scenarios(source).items():
            if name.endswith("_settles"):
                assert body.index("qa.settle(") < body.index(f'qa.vet("{_SCREEN}"'), name


def test_a_state_with_no_condition_and_no_flow_is_a_gap_naming_the_edit_and_no_scenario() -> None:
    source, _, gaps = _compile_all(_walk_context(empty_arrangement=False))

    [gap] = [gap for gap in gaps if gap.obligation_id == EMPTY_ID]
    assert gap.kind == "unarranged-state"
    assert "Indent a `fixture:` under the state" in gap.detail
    assert "fixture: none, because ..." in gap.detail
    assert not [name for name in _scenarios(source) if name.endswith("empty_settles")]
    assert EMPTY_ID not in _covers(source)


def test_a_fixture_that_lands_on_the_screen_is_marked_before_it_and_no_goto_follows() -> None:
    context = _walk_context(error_fixtures=_RESULTS_FAIL, fixture_screens={"results-fail": _SCREEN})
    source, _, _ = _compile_all(context)
    error = next(body for name, body in _scenarios(source).items() if name.endswith("error_settles"))

    assert error.index("mark = qa.mark()") < error.index('qa.fixture("results-fail")') < error.index("qa.settle(")
    assert "qa.goto(" not in error


def test_every_state_obligation_is_covered_by_a_scenario_or_gapped() -> None:
    for device in (False, True):
        for fixtures in (_RESULTS_FAIL, None):
            source, _, gaps = _compile_all(_walk_context(device=device, error_fixtures=fixtures))
            covered = _covers(source)
            gapped = {gap.obligation_id for gap in gaps}

            for state_id in (LOADED_ID, ERROR_ID, EMPTY_ID):
                assert (state_id in covered) != (state_id in gapped), (device, fixtures, state_id)
