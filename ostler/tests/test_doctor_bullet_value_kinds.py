"""`doctor` holds a bullet whose key declares a `value_kind` to the parser its consumer runs."""

from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.model import load

from conftest import write

SCREEN_PATH = "docs/features/acme/screens/widgets.md"
ENDPOINT_PATH = "docs/features/acme/server.md"


def _screen_book(route: str = "/widgets", entry: str = "") -> str:
    lines = ["---", "type: screen", "slug: widgets", "title: Widgets", "---", "# Widgets", "",
              f"- route: {route}", "- requires: none", "- params: none"]
    if entry:
        lines.append(f"- entry: {entry}")
    lines.append("")
    return "\n".join(lines)


def _endpoint_book(method: str = "GET", path: str = "/api/accounts") -> str:
    return f"""---
type: server
title: Acme accounts
---
# Acme accounts

## Endpoints

### list-accounts
- method: {method}
- path: {path}
- authorization: an adjuster reads every account on file.
"""


def _findings(repo: Path, code: str) -> list[doctor.Finding]:
    return [f for f in doctor.run(load(repo)).findings if f.code == code]


def test_a_nonparsing_http_method_is_reported(repo: Path) -> None:
    write(repo / ENDPOINT_PATH, _endpoint_book(method="fetch-data"))
    found = _findings(repo, "unparsable-bullet-value")
    assert [(f.severity, "#method:" in f.ref) for f in found] == [("error", True)]
    assert "method: fetch-data" in found[0].message
    assert "http-method" in found[0].message


def test_a_valid_http_method_is_clean(repo: Path) -> None:
    write(repo / ENDPOINT_PATH, _endpoint_book(method="POST"))
    assert _findings(repo, "unparsable-bullet-value") == []


def test_a_prose_entry_is_clean(repo: Path) -> None:
    """`entry:` says by what means the screen is reached, and a means is not an address."""
    write(repo / SCREEN_PATH, _screen_book(entry="no; it is reached from the dashboard"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#entry:" in f.ref]
    assert found == []


def test_a_route_valued_entry_is_clean(repo: Path) -> None:
    write(repo / SCREEN_PATH, _screen_book(entry="/login"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#entry:" in f.ref]
    assert found == []


def test_an_absolute_url_entry_is_clean(repo: Path) -> None:
    write(repo / SCREEN_PATH, _screen_book(entry="https://accounts.example.com/callback"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#entry:" in f.ref]
    assert found == []


def test_a_parameterized_route_does_not_raise(repo: Path) -> None:
    write(repo / SCREEN_PATH, _screen_book(route="/widgets/{id}"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#route:" in f.ref]
    assert found == []


def test_a_backtick_wrapped_route_is_clean(repo: Path) -> None:
    """The corpus writes `route:` as a markdown code span (`` `/widgets` ``), same as `role:`."""
    write(repo / SCREEN_PATH, _screen_book(route="`/widgets`"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#route:" in f.ref]
    assert found == []


def test_an_absent_entry_bullet_does_not_raise(repo: Path) -> None:
    write(repo / SCREEN_PATH, _screen_book())
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#entry:" in f.ref]
    assert found == []


def test_a_valid_endpoint_path_is_clean(repo: Path) -> None:
    write(repo / ENDPOINT_PATH, _endpoint_book(path="/api/accounts/{id}"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#path:" in f.ref]
    assert found == []


def test_a_valid_server_entry_url_is_clean(repo: Path) -> None:
    write(repo / "docs/features/app/ops/qa-stack.md", (
        "---\ntype: runbook\ntitle: QA stack\n---\n\n# QA stack\n\n"
        "- driver: web\n- entry-url: http://localhost:18099\n\n"
        "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n"
    ))
    found = [f for f in _findings(repo, "unparsable-bullet-value")
             if "#entry-url:" in f.ref]
    assert found == []


def test_a_malformed_server_entry_url_is_reported(repo: Path) -> None:
    write(repo / "docs/features/app/ops/qa-stack.md", (
        "---\ntype: runbook\ntitle: QA stack\n---\n\n# QA stack\n\n"
        "- driver: web\n- entry-url: localhost:18099\n\n"
        "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n"
    ))
    found = [f for f in _findings(repo, "unparsable-bullet-value")
             if "#entry-url:" in f.ref]
    assert len(found) == 1
    assert "url" in found[0].message


MOBILE_SCREEN_PATH = "docs/features/mobile/gui/screens/widget-list.md"
MOBILE_RUNBOOK_PATH = "docs/features/mobile/ops/qa-stack.md"


def _mobile_screen_book(route: str) -> str:
    return (f"---\ntype: screen\nslug: widget-list\ntitle: Widget list\n---\n"
            f"# Widget list\n\n- route: {route}\n- requires: none\n- params: none\n")


def _mobile_runbook() -> str:
    return ("---\ntype: runbook\ntitle: QA stack\n---\n\n# QA stack\n\n"
            "- driver: mobile\n"
            "- surfaces: [Widget list](../gui/screens/widget-list.md)\n\n"
            "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n")


def test_a_mobile_surface_route_shaped_like_a_screen_name_is_clean(repo: Path) -> None:
    """`_check_bullet_value_kinds` picks the mobile row of `routes.ROUTE_GRAMMAR`, not the path grammar, on a `mobile`-driven surface: a bare navigator screen name — never a path, since a navigator that routes on names has no path to state — is a clean `route:`."""
    write(repo / MOBILE_RUNBOOK_PATH, _mobile_runbook())
    write(repo / MOBILE_SCREEN_PATH, _mobile_screen_book("WidgetList"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#route:" in f.ref]
    assert found == []


def test_a_mobile_surface_route_shaped_like_a_path_is_reported(repo: Path) -> None:
    """The mirror of the test above, and the one that actually proves the point: were this check merely skipping validation for `mobile` rather than switching grammars, a path-shaped value would pass here too."""
    write(repo / MOBILE_RUNBOOK_PATH, _mobile_runbook())
    write(repo / MOBILE_SCREEN_PATH, _mobile_screen_book("/widget-list"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#route:" in f.ref]
    assert len(found) == 1
    assert "navigator screen name" in found[0].message


def test_a_route_on_a_surface_with_no_driver_declared_keeps_the_path_grammar(repo: Path) -> None:
    """Every surface but `mobile` — including one with no `driver:` declared at all, this file's ordinary `SCREEN_PATH` fixture — keeps being checked by `is_path_shaped`, the default row `routes.route_grammar` falls back to: a screen-name-shaped value fails it."""
    write(repo / SCREEN_PATH, _screen_book(route="WidgetList"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#route:" in f.ref]
    assert len(found) == 1
    assert "not a path" in found[0].message


CLI_SCREEN_PATH = "docs/features/tally/gui/screens/widget-list.md"
CLI_RUNBOOK_PATH = "docs/features/tally/ops/qa-stack.md"


def _cli_screen_book(route: str) -> str:
    return (f"---\ntype: screen\nslug: widget-list\ntitle: Widget list\n---\n"
            f"# Widget list\n\n- route: {route}\n- requires: none\n- params: none\n")


def _cli_runbook() -> str:
    return ("---\ntype: runbook\ntitle: QA stack\n---\n\n# QA stack\n\n"
            "- driver: cli\n"
            "- surfaces: [Widget list](../gui/screens/widget-list.md)\n\n"
            "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n")


def test_a_route_on_a_route_less_cli_surface_is_reported(repo: Path) -> None:
    """`routes.ROUTE_GRAMMAR["cli"]` is `is_never_routed` — no value passes it."""
    write(repo / CLI_RUNBOOK_PATH, _cli_runbook())
    write(repo / CLI_SCREEN_PATH, _cli_screen_book("/widget-list"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#route:" in f.ref]
    assert len(found) == 1
    assert "states no routes at all" in found[0].message


WEB_SCREEN_PATH = "docs/features/acme/gui/screens/widget-list.md"
WEB_RUNBOOK_PATH = "docs/features/acme/ops/qa-stack.md"


def _component_screen_book(selector: str) -> str:
    return (f"---\ntype: screen\nslug: widget-list\ntitle: Widget list\n---\n"
            f"# Widget list\n\n- route: /widget-list\n- requires: none\n- params: none\n\n"
            f"## Components\n\n### name-input\n- selector: {selector}\n- role: textbox\n"
            f"- name: Name\n")


def _web_runbook() -> str:
    return ("---\ntype: runbook\ntitle: QA stack\n---\n\n# QA stack\n\n"
            "- driver: web\n"
            "- surfaces: [Widget list](../gui/screens/widget-list.md)\n\n"
            "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n")


def test_a_web_surface_selector_shaped_like_a_scheme_address_is_reported(repo: Path) -> None:
    """A browser drives this surface — it queries the DOM, not a `scheme=value` address, so a `testID=...` selector copied over from a mobile screen is reported here even though it parses fine as a selector on its own terms."""
    write(repo / WEB_RUNBOOK_PATH, _web_runbook())
    write(repo / WEB_SCREEN_PATH, _component_screen_book("testID=name-input"))
    found = [f for f in _findings(repo, "conflicting-selector-driver") if "#selector:" in f.ref]
    assert len(found) == 1
    assert "browser" in found[0].message


def test_a_web_surface_selector_shaped_like_css_is_clean(repo: Path) -> None:
    write(repo / WEB_RUNBOOK_PATH, _web_runbook())
    write(repo / WEB_SCREEN_PATH, _component_screen_book("#name"))
    found = [f for f in _findings(repo, "conflicting-selector-driver") if "#selector:" in f.ref]
    assert found == []


def test_a_mobile_surface_selector_shaped_like_css_is_reported(repo: Path) -> None:
    """The mirror case: Maestro resolves a `scheme=value` address or visible text, never CSS, so a `#name` selector copied over from a web screen is reported here."""
    write(repo / MOBILE_RUNBOOK_PATH, _mobile_runbook())
    write(repo / MOBILE_SCREEN_PATH, _component_screen_book("#name"))
    found = [f for f in _findings(repo, "conflicting-selector-driver") if "#selector:" in f.ref]
    assert len(found) == 1
    assert "Maestro" in found[0].message


def test_a_mobile_surface_selector_shaped_like_a_scheme_address_is_clean(repo: Path) -> None:
    write(repo / MOBILE_RUNBOOK_PATH, _mobile_runbook())
    write(repo / MOBILE_SCREEN_PATH, _component_screen_book("testID=name-input"))
    found = [f for f in _findings(repo, "conflicting-selector-driver") if "#selector:" in f.ref]
    assert found == []


def test_a_mobile_surface_selector_shaped_like_bare_text_is_clean(repo: Path) -> None:
    """The asymmetry guard: `is_mobile_representable` only rejects unmistakable DOM syntax, so a selector that is neither CSS nor a `scheme=value` address — plain visible text, which Maestro can address directly — must not be flagged just for failing to look like CSS."""
    write(repo / MOBILE_RUNBOOK_PATH, _mobile_runbook())
    write(repo / MOBILE_SCREEN_PATH, _component_screen_book("Name field"))
    found = [f for f in _findings(repo, "conflicting-selector-driver") if "#selector:" in f.ref]
    assert found == []


def test_a_selector_on_a_never_rendering_cli_surface_is_reported(repo: Path) -> None:
    """`placement.SELECTOR_GRAMMAR["cli"]` is `is_never_selected` — no value passes it, the same as `routes.is_never_routed` for `route:`."""
    write(repo / CLI_RUNBOOK_PATH, _cli_runbook())
    write(repo / CLI_SCREEN_PATH, _component_screen_book("#name"))
    found = [f for f in _findings(repo, "conflicting-selector-driver") if "#selector:" in f.ref]
    assert len(found) == 1
    assert "renders nothing to query" in found[0].message


def _http_runbook() -> str:
    return ("---\ntype: runbook\ntitle: QA stack\n---\n\n# QA stack\n\n"
            "- driver: http\n"
            "- surfaces: [Widget list](../gui/screens/widget-list.md)\n\n"
            "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n")


def test_a_component_on_an_http_driven_surface_reads_css_like_web(repo: Path) -> None:
    """`placement.SELECTOR_GRAMMAR["http"]` reads the same `is_web_representable` grammar as `web`, mirroring `routes.ROUTE_GRAMMAR`'s identical grouping — a surface can host an `http`-driven API runbook alongside the `web`-rendered screens it serves, so a plain CSS selector on such a screen's component must stay clean, and a `scheme=value` one copied over from a mobile screen must still be reported."""
    write(repo / WEB_RUNBOOK_PATH, _http_runbook())
    write(repo / WEB_SCREEN_PATH, _component_screen_book("#name"))
    found = [f for f in _findings(repo, "conflicting-selector-driver") if "#selector:" in f.ref]
    assert found == []


def test_a_component_on_an_http_driven_surface_scheme_address_is_reported(repo: Path) -> None:
    write(repo / WEB_RUNBOOK_PATH, _http_runbook())
    write(repo / WEB_SCREEN_PATH, _component_screen_book("testID=name-input"))
    found = [f for f in _findings(repo, "conflicting-selector-driver") if "#selector:" in f.ref]
    assert len(found) == 1
    assert "browser" in found[0].message


def test_a_malformed_selector_still_trips_unaddressable_selector(repo: Path) -> None:
    """`conflicting-selector-driver` is a second, driver-aware check beside the existing driver-blind `unaddressable-selector` (`vet.placement.is_addressable`), not a replacement for it — a CSS attribute-predicate selector still can never be matched against a real census, on any driver, and must still be reported under its own code."""
    write(repo / WEB_RUNBOOK_PATH, _web_runbook())
    write(repo / WEB_SCREEN_PATH, _component_screen_book('[data-state="booked"]'))
    found = [f for f in _findings(repo, "unaddressable-selector") if "#selector:" in f.ref]
    assert len(found) == 1
