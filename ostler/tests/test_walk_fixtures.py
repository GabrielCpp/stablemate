"""A screen reached by walking the book's navigation arranges the fixtures the walk's acts read facts from."""

from __future__ import annotations

from typing import Any

from ostler.qa.compile import Plan, compile_plan_gaps

SIGN_UP = "docs/services/web/gui/screens/sign-up.md"
LIST = "docs/services/web/gui/screens/list.md"
BASE_URL = "http://localhost:3000"
FRESH = {"name": "fresh-identity", "args": [], "provides": "an address no account has registered",
         "providesKeys": ["fresh-identity.email"]}
EMAIL_FIELD = {"node": f"{SIGN_UP}#email-field", "locators": {"role": ["textbox"], "name": ["Email"]}}
HEADING = {"node": f"{LIST}#heading", "locators": {"role": ["heading"], "name": ["Your todos"]}}


def _node(oid: str, node: str, source: str, kind: str, node_type: str, **extra: Any) -> dict[str, Any]:
    return {"id": f"okf:{oid}", "kind": kind, "node": node, "nodeType": node_type, "source": source,
            "surface": "web", "requirement": "x", "required": True, **extra}


def _context(*, fixtures_on_heading: bool = False) -> dict[str, Any]:
    submit = _node(
        f"{SIGN_UP}#submit:does:1", f"{SIGN_UP}#submit", SIGN_UP, "does", "interaction",
        locators={"on": ["[sign-up-button](#sign-up-button)"], "trigger": ["click"], "does": ["signs up"]},
        actsDeclared=[{"call": 'fill(locator="#email-field", value="@fresh-identity.email")', "name": "fill",
                       "args": {"locator": "#email-field", "value": "@fresh-identity.email"},
                       "locates": {"locator": EMAIL_FIELD}}],
        checksDeclared=[{"call": 'visible(locator="list.md#heading")', "name": "visible",
                         "args": {"locator": "list.md#heading"}, "locates": {"locator": HEADING}}],
        fixturesDeclared=[FRESH], docPosition=[1, 1])
    button = _node(
        f"{SIGN_UP}#sign-up-button:name:1", f"{SIGN_UP}#sign-up-button", SIGN_UP, "name", "component",
        locators={"role": ["button"], "name": ["Sign up"]}, docPosition=[2, 1])
    heading = _node(
        f"{LIST}#heading:name:1", f"{LIST}#heading", LIST, "name", "component",
        locators={"role": ["heading"], "name": ["Your todos"]},
        checksDeclared=[{"call": 'visible(locator="#heading")', "name": "visible",
                         "args": {"locator": "#heading"}, "locates": {"locator": HEADING}}],
        docPosition=[3, 1], **({"fixturesDeclared": [FRESH]} if fixtures_on_heading else {}))
    navigation = {"web": {
        "start": SIGN_UP, "surface": "web", "driver": "web", "rootPath": "/", "entryUrl": BASE_URL,
        "counts": {"screens": 2, "reachable": 2, "unreachable": 0, "undeclared": 0, "nav_edges": 1},
        "routes": {SIGN_UP: [], LIST: [{"node": f"{SIGN_UP}#sign-up-button", "from": SIGN_UP, "label": "Sign up"}]},
        "unreachable": [], "undeclared": []}}
    return {"story": {"slug": "demo-story"}, "obligations": [submit, button, heading], "navigation": navigation,
            "screenRoutes": {SIGN_UP: "/", LIST: "/list"}}


def _function(source: str, name: str) -> str:
    start = source.index(f"def {name}(")
    end = source.find("\n@scenario(", start)
    return source[start:] if end == -1 else source[start:end]


def _plan(context: dict[str, Any]) -> str:
    result = compile_plan_gaps(context, story="demo-story", base_url=BASE_URL)
    assert isinstance(result, Plan), result
    return result.source


def test_an_arrival_reached_by_a_walk_that_reads_a_fixture_arranges_it_ahead_of_the_walk() -> None:
    body = _function(_plan(_context()), "docs_services_web_gui_screens_list_arrival")

    assert body.count('qa.fixture("fresh-identity")') == 1
    assert body.index('qa.fixture("fresh-identity")') < body.index('qa.goto("/")') < body.index("qa.resolve(")


def test_the_fixture_a_walk_reads_is_named_among_the_scenarios_preconditions() -> None:
    source = _plan(_context())
    head = source[:source.index("def docs_services_web_gui_screens_list_arrival(")]

    assert '"an address no account has registered"' in head[head.rindex("@scenario("):]


def test_a_fixture_the_claims_already_arrange_is_not_arranged_twice() -> None:
    body = _function(_plan(_context(fixtures_on_heading=True)), "docs_services_web_gui_screens_list_arrival")

    assert body.count('qa.fixture("fresh-identity")') == 1


def test_a_journey_whose_walk_reads_a_fixture_the_flow_does_not_arrange_arranges_it() -> None:
    context = _context()
    refresh = _node(
        f"{LIST}#refresh:does:1", f"{LIST}#refresh", LIST, "does", "interaction",
        locators={"on": ["[heading](#heading)"], "trigger": ["load"], "does": ["loads"]}, required=False)
    flow = _node(
        "docs/services/web/flows/start.md:end-state", "docs/services/web/flows/start.md#flow",
        "docs/services/web/flows/start.md", "end-state", "flow",
        steps=[{"ref": f"{LIST}#refresh", "href": "refresh", "nodeType": "interaction", "surface": "web"}],
        checksDeclared=[{"call": 'visible(locator="list.md#heading")', "name": "visible",
                         "args": {"locator": "list.md#heading"}, "locates": {"locator": HEADING}}],
        arrangesNothing=True)
    context["obligations"] = [flow, *(o for o in context["obligations"] if o["source"] != LIST), refresh,
                              _node(f"{LIST}#heading:carrier", f"{LIST}#heading", LIST, "name", "component",
                                    locators={"role": ["heading"], "name": ["Your todos"]}, required=False)]

    body = _function(_plan(context), "docs_services_web_flows_start_journey")

    assert body.count('qa.fixture("fresh-identity")') == 1
    assert body.index('qa.fixture("fresh-identity")') < body.index("qa.resolve(")
