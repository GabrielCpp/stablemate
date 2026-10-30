"""A component a screen's arrival state lists absent is gapped, not asserted on arrival."""

from __future__ import annotations

from typing import Any

from ostler.qa.compile import Plan, Refusal, compile_plan_gaps

SCREEN = "docs/services/web/gui/screens/sign-up.md"
BASE_URL = "http://localhost:3000"
NOTICE = {"node": f"{SCREEN}#sign-up-error", "locators": {"role": ["alert"], "name": ["Sign up failed"]}}


def _node(oid: str, node: str, kind: str, node_type: str, **extra: Any) -> dict[str, Any]:
    return {"id": f"okf:{oid}", "kind": kind, "node": node, "nodeType": node_type, "source": SCREEN,
            "surface": "web", "requirement": "x", "required": True, **extra}


def _state(name: str, shows: list[str], position: int, **extra: Any) -> dict[str, Any]:
    return _node(f"{SCREEN}#{name}:contract", f"{SCREEN}#{name}", "contract", "state",
                 locators={"shows": shows}, required=False, docPosition=[position, 0], **extra)


def _context(states: list[dict[str, Any]]) -> dict[str, Any]:
    notice = _node(
        f"{SCREEN}#sign-up-error:name:1", f"{SCREEN}#sign-up-error", "name", "component",
        locators={"role": ["alert"], "name": ["Sign up failed"]},
        checksDeclared=[{"call": 'visible(locator="#sign-up-error")', "name": "visible",
                         "args": {"locator": "#sign-up-error"}, "locates": {"locator": NOTICE}}],
        docPosition=[9, 1])
    navigation = {"web": {
        "start": SCREEN, "surface": "web", "driver": "web", "rootPath": "/", "entryUrl": BASE_URL,
        "counts": {"screens": 1, "reachable": 1, "unreachable": 0, "undeclared": 0, "nav_edges": 0},
        "routes": {SCREEN: []}, "unreachable": [], "undeclared": []}}
    return {"story": {"slug": "demo-story"}, "obligations": [notice, *states], "navigation": navigation,
            "screenRoutes": {SCREEN: "/"}}


IDLE_SHOWS = ["[Sign up error](#sign-up-error) absent"]
FAILED_SHOWS = ["[Sign up error](#sign-up-error)"]


def _compile(context: dict[str, Any]) -> Plan | Refusal:
    return compile_plan_gaps(context, story="demo-story", base_url=BASE_URL)


def _source(result: Plan | Refusal) -> str:
    return result.source if isinstance(result, Plan) else ""


def test_a_component_the_arrival_state_lists_absent_is_gapped_naming_the_states_and_the_remedy() -> None:
    plan = _compile(_context([
        _state("idle", IDLE_SHOWS, 1, arrangesNothing=True),
        _state("failed", FAILED_SHOWS, 2, fixturesDeclared=[{"name": "bad-sign-up", "args": [], "provides": "x"}]),
    ]))

    assert "#sign-up-error" not in _source(plan)
    gap = next(g for g in plan.gaps if g.kind == "unarranged-state" and "sign-up-error:name:1" in g.obligation_id)
    assert "`docs/services/web/gui/screens/sign-up.md#sign-up-error` is absent in " in gap.detail
    assert "`docs/services/web/gui/screens/sign-up.md#idle`" in gap.detail
    assert "shown in `docs/services/web/gui/screens/sign-up.md#failed`" in gap.detail
    assert "arrange that state (its own `fixture:`)" in gap.detail
    assert "put a `when:` on the component" in gap.detail


def test_a_component_the_arrival_state_shows_is_still_asserted_on_arrival() -> None:
    plan = _compile(_context([
        _state("idle", FAILED_SHOWS, 1, arrangesNothing=True),
        _state("failed", FAILED_SHOWS, 2, fixturesDeclared=[{"name": "bad-sign-up", "args": [], "provides": "x"}]),
    ]))

    assert "#sign-up-error" in _source(plan)
    assert not [g for g in plan.gaps if g.kind == "unarranged-state"]


def test_a_screen_with_two_states_that_arrange_nothing_keeps_asserting_the_component() -> None:
    plan = _compile(_context([
        _state("idle", IDLE_SHOWS, 1, arrangesNothing=True),
        _state("failed", FAILED_SHOWS, 2, arrangesNothing=True),
    ]))

    assert "#sign-up-error" in _source(plan)
    assert not [g for g in plan.gaps if g.kind == "unarranged-state"]
