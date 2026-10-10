"""A journey step the screen runs on arrival opens that screen by its own entry, and a first step the walk's start already opened opens nothing again."""

from __future__ import annotations

import ast

from ostler.qa.compile import Plan, compile_plan_gaps

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

OTHER = "docs/features/policy/gui/screens/things.md"
OPEN_THING = f"{_SCREEN}#open-thing"
SHOW_LIST = f"{_SCREEN}#show-list"
SHOW_THINGS = f"{OTHER}#show-things"


def _carrier(ref: str, locators: dict) -> dict:
    return _page_obligation(f"{ref}:carrier", ref, source=ref.split("#")[0], locators=locators,
                            checks=[]) | {"required": False}


def _journey(steps: list[str], fixture_screens: dict[str, str], doors: dict[str, str]) -> str:
    navigation = _arrival_navigation()
    navigation["policy"]["routes"][OTHER] = []
    navigation["policy"]["doors"] = doors
    context = _navigation_context(
        _flow_obligation(
            f"okf:{_FLOW}:end-state", source=_FLOW, surface="policy",
            steps=[_step(ref, "interaction", "policy") for ref in steps],
            checks=[_located_visible(f"{_SCREEN}#things-table", {"selector": ["#things-table"]})],
        ),
        _carrier(OPEN_THING, {"on": ["[open-link](#open-link)"], "trigger": ["click"]}),
        _carrier(f"{_SCREEN}#open-link", {"selector": ["#open-link"]}),
        _carrier(SHOW_LIST, {"on": ["[things-table](#things-table)"], "trigger": ["load"]}),
        _carrier(SHOW_THINGS, {"on": ["[things-table](#things-table)"], "trigger": ["load"]}),
        navigation=navigation,
    ) | {"fixtureScreens": fixture_screens}
    result = compile_plan_gaps(context, story="demo-story")
    assert isinstance(result, Plan)
    ast.parse(result.source)
    return result.source.split("@scenario(")[-1]


def test_a_first_step_on_arrival_opens_nothing_the_fixture_already_opened() -> None:
    journey = _journey([SHOW_LIST, OPEN_THING], {"seeded-ledger": _SCREEN}, {})

    assert "qa.goto(" not in journey
    assert journey.index('qa.fixture("seeded-ledger")') < journey.index('"#open-link"')


def test_a_later_step_on_arrival_opens_its_screen_by_its_own_entry() -> None:
    journey = _journey([OPEN_THING, SHOW_THINGS], {"seeded-ledger": _SCREEN}, {OTHER: "/things"})

    after_click = journey[journey.index('"#open-link"'):]
    assert 'qa.goto("/things")' in after_click
    assert 'qa.goto("/")' not in after_click
