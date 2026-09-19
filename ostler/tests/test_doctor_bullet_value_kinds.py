"""`doctor` holds a bullet whose key declares a `value_kind` to the parser its consumer runs.

`BulletKey.required` checks presence only — a role, not a grammar. `value_kind` is the flag
that says what the value may *say*, checked by calling the exact parser a consumer (the route
reader, the reachability walk, the HTTP-verb table) already runs over it, never a second one
invented for the declaration. See `ostler.values` and `_check_bullet_value_kinds` (doctor.py).
"""

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
    """`entry:` says by what means the screen is reached, and a means is not an address.

    It was held to a route grammar once, which made this the only illegal spelling of the
    one thing the key exists to say. `reach.prose_entry` reads exactly this value, so the
    grammar and the consumer disagreed in writing about the same bullet.
    """
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
    """The corpus writes `route:` as a markdown code span (`` `/widgets` ``), same as `role:`.

    `node.meta` hands the value back with the backticks still on it; the value kind must
    unwrap it the same way `ostler.routes.screen_routes` and `bullet_value` already do, not
    fall through to `why_unreadable` on a string that merely *starts* with a backtick.
    """
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


#: A surface whose runbook declares `driver: mobile` — `_check_bullet_value_kinds` asks
#: `routes.route_grammar("mobile")` for its screens' `route:` bullets, which names
#: `routes.is_screen_name_shaped` instead of the `is_path_shaped` grammar `web`/`http` (and
#: any undeclared driver) get, per `routes.ROUTE_GRAMMAR`.
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
    """`_check_bullet_value_kinds` picks the mobile row of `routes.ROUTE_GRAMMAR`, not the
    path grammar, on a `mobile`-driven surface: a bare navigator screen name — never a path,
    since a navigator that routes on names has no path to state — is a clean `route:`."""
    write(repo / MOBILE_RUNBOOK_PATH, _mobile_runbook())
    write(repo / MOBILE_SCREEN_PATH, _mobile_screen_book("WidgetList"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#route:" in f.ref]
    assert found == []


def test_a_mobile_surface_route_shaped_like_a_path_is_reported(repo: Path) -> None:
    """The mirror of the test above, and the one that actually proves the point: were this
    check merely skipping validation for `mobile` rather than switching grammars, a path-shaped
    value would pass here too. It does not — the mobile row rejects it, same as the path
    grammar would reject a bare screen name on a `web` surface."""
    write(repo / MOBILE_RUNBOOK_PATH, _mobile_runbook())
    write(repo / MOBILE_SCREEN_PATH, _mobile_screen_book("/widget-list"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#route:" in f.ref]
    assert len(found) == 1
    assert "navigator screen name" in found[0].message


def test_a_route_on_a_surface_with_no_driver_declared_keeps_the_path_grammar(repo: Path) -> None:
    """Every surface but `mobile` — including one with no `driver:` declared at all, this
    file's ordinary `SCREEN_PATH` fixture — keeps being checked by `is_path_shaped`, the
    default row `routes.route_grammar` falls back to: a screen-name-shaped value fails it."""
    write(repo / SCREEN_PATH, _screen_book(route="WidgetList"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#route:" in f.ref]
    assert len(found) == 1
    assert "not a path" in found[0].message


#: A surface whose runbook declares `driver: cli` — `iac`/`cli` are the `routes.ROUTE_GRAMMAR`
#: rows that state no driver *ever* addresses by route (`routes.is_never_routed`). No corpus
#: book puts a `screen` on such a surface — neither driver owns one by design — but the doctor
#: check must not special-case that away: were `_check_bullet_value_kinds` still reaching
#: `route_grammar` only for `mobile`, a `cli` surface's stray `route:` would silently keep the
#: path grammar instead of being held to the row the table already claims for it. This fixture
#: forces the case the table has stated since `cli` was added to it, and proves the doctor
#: actually reads that row rather than merely declaring it.
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
    """`routes.ROUTE_GRAMMAR["cli"]` is `is_never_routed` — no value passes it. A `route:` that
    would be perfectly clean on a `web` surface (a leading-`/` path) must still be reported
    here, because it is the surface's driver, not the bullet's shape, that this row objects to.
    """
    write(repo / CLI_RUNBOOK_PATH, _cli_runbook())
    write(repo / CLI_SCREEN_PATH, _cli_screen_book("/widget-list"))
    found = [f for f in _findings(repo, "unparsable-bullet-value") if "#route:" in f.ref]
    assert len(found) == 1
    assert "states no routes at all" in found[0].message
