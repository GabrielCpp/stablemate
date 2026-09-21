"""`ostler reach` — the documented click-path to a screen, and the screens that have none."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from ostler import cli, graph, reach
from ostler.model import load

from conftest import present, write

LANDING = """\
---
type: screen
slug: landing
title: Landing
---
# Landing

- route: `/`
- requires: none
- params: none

## Components

### landing-sign-in-link
- selector: `a`
- leads-to: [Sign in](sign-in.md)

### landing-hero
- selector: `.hero`
- extends: [panel](../components/ds.md#panel)
"""

SIGN_IN = """\
---
type: screen
slug: sign-in
title: Sign in
---
# Sign in

- route: `/sign-in`
- requires: none
- params: none

## Components

### sign-in-forgot-link
- selector: `a`
- leads-to: [Forgot password](forgot-password.md)

## Interactions

### submit-sign-in
- on: sign-in-form
- trigger: submit
"""

FORGOT = """\
---
type: screen
slug: forgot-password
title: Forgot password
---
# Forgot password

- route: `/forgot-password`
- requires: none
- params: none
"""

DASHBOARD = """\
---
type: screen
slug: dashboard
title: Dashboard
---
# Dashboard

- route: `/dashboard/:projectId`
- requires:
  - [protected-route](../components/auth-guards.md#protected-route)
- params:
  - projectId: from [submit-sign-in](sign-in.md#submit-sign-in)
"""

ORPHAN = """\
---
type: screen
slug: archive
title: Archive
---
# Archive

- route: `/archive`
"""

GUARDS = """\
---
type: feature
slug: auth-guards
title: Auth guards
---
# Auth guards

## protected-route

Redirects an unauthenticated caller to `/sign-in`.
"""

FLOW = """\
---
type: flow
slug: sign-in-to-dashboard
title: Sign in to dashboard
---
# Sign in to dashboard

- start: a visitor on [Sign in](../gui/screens/sign-in.md)
- steps:
  - [submit-sign-in](../gui/screens/sign-in.md#submit-sign-in) posts the credential
  - [Dashboard](../gui/screens/dashboard.md) renders the billing summary
"""

DS = """\
---
type: feature
slug: ds
title: DS
---
# DS

## panel

A panel.
"""

SCREENS = "docs/features/web/gui/screens"
LAND = f"{SCREENS}/landing.md"
SIGNIN = f"{SCREENS}/sign-in.md"
FORGOT_ID = f"{SCREENS}/forgot-password.md"
DASH = f"{SCREENS}/dashboard.md"
ARCHIVE = f"{SCREENS}/archive.md"


def _repo(repo: Path):
    write(repo / SCREENS / "landing.md", LANDING)
    write(repo / SCREENS / "sign-in.md", SIGN_IN)
    write(repo / SCREENS / "forgot-password.md", FORGOT)
    write(repo / SCREENS / "dashboard.md", DASHBOARD)
    write(repo / SCREENS / "archive.md", ORPHAN)
    write(repo / "docs/features/web/flows/sign-in-to-dashboard.md", FLOW)
    write(repo / "docs/features/web/gui/components/ds.md", DS)
    write(repo / "docs/features/web/gui/components/auth-guards.md", GUARDS)
    return load(repo)


def _edges(repo: Path):
    return reach.navigation_edges(graph.build(_repo(repo), surface="web"))


def test_edges_are_attributed_by_bullet(repo: Path):
    """A `leads-to:` link and an `extends:` link are the same shape until `via` separates them."""
    data = graph.build(_repo(repo), surface="web")
    hero = next(n for n in data["nodes"] if n["id"].endswith("#landing-hero"))
    assert hero["edges"][0]["via"] == "extends"

    link = next(n for n in data["nodes"] if n["id"].endswith("#landing-sign-in-link"))
    assert link["edges"][0]["via"] == "leads-to"

    assert all("via" in e for e in data["edges"])


def test_prose_links_are_not_navigation(repo: Path):
    """Only bullets are traversable; a link in a paragraph names a screen, it does not reach it."""
    write(repo / SCREENS / "landing.md",
          LANDING + "\nSee also [Archive](archive.md) for old work.\n")
    edges = reach.navigation_edges(graph.build(load(repo), surface="web"))
    assert not any(e["to"] == ARCHIVE for e in edges)


def test_leads_to_builds_a_click_path(repo: Path):
    path = present(reach.route(_edges(repo), LAND, FORGOT_ID))
    assert [h["to"] for h in path] == [SIGNIN, FORGOT_ID]
    assert path[0]["action"] == "activate"
    assert path[0]["node"].endswith("#landing-sign-in-link")


def test_flow_steps_are_navigation_edges(repo: Path):
    """Consecutive `steps:` on different screens are a recorded transition."""
    path = present(reach.route(_edges(repo), SIGNIN, DASH))
    assert len(path) == 1
    assert path[0]["kind"] == "flow-step"
    assert path[0]["node"].endswith("#submit-sign-in")


def test_route_crosses_both_edge_kinds(repo: Path):
    path = present(reach.route(_edges(repo), LAND, DASH))
    assert [h["kind"] for h in path] == ["leads-to", "flow-step"]


def test_unreachable_screen_is_a_finding_not_a_fallback(repo: Path):
    """Archive has a `route:` bullet; reach must still refuse rather than hand back a URL."""
    assert reach.route(_edges(repo), LAND, ARCHIVE) is None

    report = reach.reachability(_repo(repo), surface="web", start=LAND)
    assert report["unreachable"] == [ARCHIVE]
    assert report["counts"]["reachable"] == 4
    assert report["counts"]["screens"] == 5


def _by_id(repo: Path):
    return {n["id"]: n for n in graph.build(_repo(repo), surface="web")["nodes"]}


def test_none_is_declared_not_absent(repo: Path):
    """The whole point of requiring the bullets: `none` and missing must not look alike."""
    by_id = _by_id(repo)
    landing = reach.preconditions(by_id[LAND])
    assert landing["declared"] and landing["guards"] == [] and landing["params"] == []

    archive = reach.preconditions(by_id[ARCHIVE])
    assert not archive["declared"]
    assert archive["guards"] == [] and archive["params"] == []


def test_preconditions_parse_guards_and_params(repo: Path):
    pre = reach.preconditions(_by_id(repo)[DASH])
    assert pre["declared"]
    assert [g["node"] for g in pre["guards"]] == ["../components/auth-guards.md#protected-route"]
    assert pre["params"][0]["name"] == "projectId"
    assert pre["params"][0]["from"] == "sign-in.md#submit-sign-in"


def test_route_hops_carry_destination_preconditions(repo: Path):
    """A caller walking the route must know what to satisfy on arrival, per hop."""
    _repo(repo)
    by_id = _by_id(repo)
    path = present(reach.route(_edges(repo), LAND, DASH, by_id))
    assert path[-1]["preconditions"]["guards"][0]["text"].startswith("[protected-route]")
    assert path[-1]["preconditions"]["params"][0]["name"] == "projectId"
    assert path[0]["preconditions"] == {"declared": True, "guards": [], "params": []}


def test_undeclared_preconditions_are_reported_separately(repo: Path):
    """Unreachable and undeclared are different defects; a screen can be either or both."""
    report = reach.reachability(_repo(repo), surface="web", start=LAND)
    assert report["undeclared"] == [ARCHIVE]
    assert report["counts"]["undeclared"] == 1


def test_same_screen_is_a_zero_hop_route(repo: Path):
    assert reach.route(_edges(repo), LAND, LAND) == []


def _entry(text: str, how: str) -> str:
    """Add an `entry:` bullet after the screen's `route:` — the one bullet every fixture has."""
    lines = text.splitlines()
    at = next(i for i, ln in enumerate(lines) if ln.startswith("- route:"))
    lines.insert(at + 1, f"- entry: {how}")
    return "\n".join(lines) + "\n"


def _doctor(repo: Path):
    from ostler import doctor
    return doctor.run(load(repo))


def _codes(report, severity: str = "error"):
    return [f.code for f in report.findings if f.severity == severity]


SERVER = "docs/features/web/http/web.md"


def _server(entry_url: str) -> str:
    return f"""\
---
type: server
slug: web
title: Web
---
# Web

- launch: `npm start`
- entry-url: `{entry_url}` — the local stand-in
"""


def test_doctor_warns_rather_than_errors_when_no_screen_is_at_the_root(repo: Path):
    """No root means the question is unanswerable — which is not the same as a pass."""
    _repo(repo)
    write(repo / SCREENS / "landing.md", LANDING.replace("- route: `/`", "- route: `/home`"))
    report = _doctor(repo)

    assert "unreachable-screen" not in _codes(report)
    warn = next(f for f in report.findings if f.code == "no-root-screen")
    assert "`/`" in warn.message and "no server contract" in warn.message


def test_no_root_screen_now_also_fires_on_a_mobile_surface(repo: Path):
    """`no-root-screen` must keep firing on a `web` surface with a real, book-stated defect (no screen at the root the book states no root for) — and, now that a mobile surface can state its root via `launch-screen:`, a mobile surface that has not settled one gets the same warning too, in its own words: no mention of `route:` or `/`, a suggestion naming `launch-screen:` instead."""
    _repo(repo)
    write(repo / SCREENS / "landing.md", LANDING.replace("- route: `/`", "- route: `/home`"))
    write(repo / "docs/features/mobile/gui/screens/widget-list.md", """\
---
type: screen
slug: widget-list
title: Widget list
---
# Widget list

- route: WidgetList
- requires: none
- params: none
""")
    write(repo / "docs/features/mobile/ops/qa-stack.md", """\
---
type: runbook
title: QA stack
---

# QA stack

- driver: mobile
- surfaces: [Widget list](../gui/screens/widget-list.md)

## Steps

### serve

- kind: service
- run: ./serve.sh
""")
    report = _doctor(repo)

    warnings = [f for f in report.findings if f.code == "no-root-screen"]
    assert {f.ref for f in warnings} == {"web", "mobile"}
    web_warn = next(f for f in warnings if f.ref == "web")
    assert "`/`" in web_warn.message and "no server contract" in web_warn.message
    mobile_warn = next(f for f in warnings if f.ref == "mobile")
    assert "`launch-screen:`" in mobile_warn.message
    assert "route:" not in mobile_warn.message and "`/`" not in mobile_warn.message
    assert "launch-screen:" in mobile_warn.suggestion


def test_the_root_is_the_screen_at_the_route_of_the_server_entry_url(repo: Path):
    """A walk opens the server's `entry-url:`; the screen serving that path is where it starts."""
    _repo(repo)
    write(repo / SERVER, _server("http://localhost:3000/app/"))
    write(repo / SCREENS / "app.md", """\
---
type: screen
slug: app
title: App
---
# App

- route: `/app`
- requires: none
- params: none
""")
    report = _doctor(repo)

    flagged = {f.path for f in report.findings if f.code == "unreachable-screen"}
    app = f"{SCREENS}/app.md"
    assert app not in flagged
    assert LAND in flagged
    assert all(f"from {app}" in f.message for f in report.findings
               if f.code == "unreachable-screen")


def test_a_server_entry_url_with_no_matching_screen_names_the_server(repo: Path):
    _repo(repo)
    write(repo / SERVER, _server("http://localhost:3000/admin"))
    report = _doctor(repo)

    warn = next(f for f in report.findings if f.code == "no-root-screen")
    assert "`/admin`" in warn.message and SERVER in warn.message


def test_several_servers_settle_on_the_first_by_node_id(repo: Path):
    """Two contracts on one surface: the engine reads the root off the first by node id rather than leaving a surface that plainly states an address rootless."""
    _repo(repo)
    write(repo / SERVER, _server("http://localhost:3000/app"))
    write(repo / "docs/features/web/http/static.md",
          _server("http://localhost:8080/static").replace("slug: web", "slug: static"))
    data = graph.build(load(repo), surface="web")

    assert reach.root_path(data) == ("/static", "docs/features/web/http/static.md")
    assert reach.root_screen(data) is None


def test_root_path_is_unchanged_for_web_and_none_for_a_driver_with_no_path_grammar(repo: Path):
    """A `web` surface's root path is derived from its server contract exactly as before this change — asserted against a fixture with a real `entry-url:`, so a regression here shows up as a *changed path*, not merely as "still not None"."""
    _repo(repo)
    write(repo / SERVER, _server("http://localhost:3000/app/"))
    write(repo / SCREENS / "app.md", """\
---
type: screen
slug: app
title: App
---
# App

- route: `/app`
- requires: none
- params: none
""")
    data = graph.build(load(repo), surface="web")
    server_id = SERVER

    assert reach.root_path(data, "web") == ("/app", server_id)
    assert reach.root_path(data) == ("/app", server_id)
    assert reach.root_path(data, "mobile") == (None, None)


def test_doctor_flags_a_screen_no_path_reaches(repo: Path):
    _repo(repo)
    report = _doctor(repo)

    unreachable = [f for f in report.findings if f.code == "unreachable-screen"]
    assert [f.path for f in unreachable] == [ARCHIVE]
    assert unreachable[0].severity == "error"
    assert f"from {LAND}" in unreachable[0].message


def test_doctor_flags_an_island_that_has_an_inbound_edge(repo: Path):
    """The case that rules out an inbound-degree test: linked, but hanging off nothing."""
    _repo(repo)
    write(repo / SCREENS / "archive.md", ORPHAN + """
## Components

### archive-detail-link
- leads-to: [Archive detail](archive-detail.md)
""")
    write(repo / SCREENS / "archive-detail.md", """\
---
type: screen
slug: archive-detail
title: Archive detail
---
# Archive detail

- route: `/archive/detail`
- requires: none
- params: none
""")
    report = _doctor(repo)

    flagged = {f.path for f in report.findings if f.code == "unreachable-screen"}
    detail = f"{SCREENS}/archive-detail.md"
    assert detail in flagged
    assert ARCHIVE in flagged


def test_a_route_valued_entry_makes_a_screen_a_seed(repo: Path):
    """A deep link is an address the walk can open, so the screen behind it is a root too."""
    _repo(repo)
    write(repo / SCREENS / "archive.md", _entry(ORPHAN, "/archive?token=…"))
    report = _doctor(repo)

    assert "unreachable-screen" not in _codes(report)


def test_a_prose_entry_does_not_exempt_a_screen(repo: Path):
    """"Reached by typing the URL" is a claim about the outside world the edge check cannot verify; a book where every screen makes it has no navigation in it and used to pass."""
    _repo(repo)
    write(repo / SCREENS / "archive.md", _entry(ORPHAN, "emailed deep link"))
    report = _doctor(repo)

    unreachable = [f for f in report.findings if f.code == "unreachable-screen"]
    assert [f.path for f in unreachable] == [ARCHIVE]
    assert "`entry: emailed deep link` is not a route" in unreachable[0].message


MOBILE_SCREENS = "docs/features/mobile-app/gui/screens"


def _mobile_repo(repo: Path, launch_screen: bool = False):
    """A surface whose runbook drives it with `mobile` — screen names, no paths anywhere."""
    write(repo / MOBILE_SCREENS / "widget-list.md", (
        "---\ntype: screen\nslug: widget-list\ntitle: Widgets\n---\n# Widgets\n\n"
        "- route: `WidgetList`\n- requires: none\n- params: none\n"
    ))
    launch = ("- launch-screen: [widget-list](../gui/screens/widget-list.md)\n"
              if launch_screen else "")
    write(repo / "docs/features/mobile-app/ops/stack.md", (
        "---\ntype: runbook\nslug: stack\ntitle: Stack\n---\n# Stack\n\n"
        "- driver: mobile\n- surfaces: [widget-list](../gui/screens/widget-list.md)\n"
        f"{launch}\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `metro`\n"
    ))
    return load(repo)


def _mobile_repo_with_an_unusable_launch_screen(repo: Path):
    """A `mobile` runbook whose `launch-screen:` names a component rather than a screen."""
    write(repo / MOBILE_SCREENS / "widget-list.md", (
        "---\ntype: screen\nslug: widget-list\ntitle: Widgets\n---\n# Widgets\n\n"
        "- route: `WidgetList`\n- requires: none\n- params: none\n"
    ))
    write(repo / "docs/features/mobile-app/gui/components/toolbar.md", (
        "---\ntype: component\nslug: toolbar\ntitle: Toolbar\n---\n# Toolbar\n\n"
        "- renders: a row of actions\n"
    ))
    write(repo / "docs/features/mobile-app/ops/stack.md", (
        "---\ntype: runbook\nslug: stack\ntitle: Stack\n---\n# Stack\n\n"
        "- driver: mobile\n- surfaces: [widget-list](../gui/screens/widget-list.md)\n"
        "- launch-screen: [toolbar](../gui/components/toolbar.md)\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `metro`\n"
    ))
    return load(repo)


def _mobile_repo_with_two_launch_screens(repo: Path):
    """Two runbooks over `mobile-app`, each naming a different `launch-screen:` — the shape `surface_launch_screen` settles by node id (`current.md` before `legacy.md`) rather than refusing to pick one."""
    write(repo / MOBILE_SCREENS / "widget-list.md", (
        "---\ntype: screen\nslug: widget-list\ntitle: Widgets\n---\n# Widgets\n\n"
        "- route: `WidgetList`\n- requires: none\n- params: none\n"
    ))
    write(repo / MOBILE_SCREENS / "new-widget.md", (
        "---\ntype: screen\nslug: new-widget\ntitle: New widget\n---\n# New widget\n\n"
        "- route: `NewWidget`\n- requires: none\n- params: none\n"
    ))
    write(repo / "docs/features/mobile-app/ops/legacy.md", (
        "---\ntype: runbook\nslug: legacy\ntitle: Legacy\n---\n# Legacy\n\n"
        "- driver: mobile\n"
        "- surfaces: [widget-list](../gui/screens/widget-list.md)\n"
        "- launch-screen: [widget-list](../gui/screens/widget-list.md)\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `metro`\n"
    ))
    write(repo / "docs/features/mobile-app/ops/current.md", (
        "---\ntype: runbook\nslug: current\ntitle: Current\n---\n# Current\n\n"
        "- driver: mobile\n"
        "- surfaces: [widget-list](../gui/screens/widget-list.md)\n"
        "- launch-screen: [new-widget](../gui/screens/new-widget.md)\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `metro --current`\n"
    ))
    return load(repo)


def test_a_mobile_surface_is_not_told_to_look_for_a_screen_at_the_root_path(repo: Path):
    """`root_path` has been driver-aware since the route grammars landed, but `resolve_start` never asked for a driver — so the one command a person runs by hand kept the web answer and quoted a `/` no mobile book ever writes."""
    import pytest

    data = graph.build(_mobile_repo(repo), surface="mobile-app")

    with pytest.raises(reach.UnknownStart) as exc:
        reach.resolve_start(data, None, "mobile")
    assert "`mobile` surface states no root path" in str(exc.value)
    assert "/" not in str(exc.value).replace("--from", "")


def test_the_reach_command_reads_the_surface_driver_off_the_runbook(repo: Path, capsys):
    """The driver is not the command's to guess and not its to report: `_cmd_reach` resolves it from the book like every other reader, so the message a person sees is this surface's."""
    graph_obj = _mobile_repo(repo)
    args = SimpleNamespace(surface="mobile-app", start=None, target=None, json=True)

    assert cli._cmd_reach(graph_obj, args) == 2
    assert json.loads(capsys.readouterr().out)["error"] == (
        "a `mobile` surface states no `launch-screen:` on its runbook and no root path "
        "to start from; pass --from")


def test_a_mobile_surfaces_launch_screen_is_the_start(repo: Path):
    """The fact `surface_launch_screen` already resolves was simply unwired: once `resolve_start` is given `surface`, a `mobile` surface's `launch-screen:` becomes its start."""
    data = graph.build(_mobile_repo(repo, launch_screen=True), surface="mobile-app")

    assert reach.resolve_start(data, None, "mobile", surface="mobile-app") == (
        f"{MOBILE_SCREENS}/widget-list.md")


def test_a_mobile_surface_with_no_launch_screen_still_raises_unknown_start(repo: Path):
    """No `launch-screen:` and no root path leaves nothing to start from — the message must name `launch-screen:` so the operator knows which bullet would have settled it."""
    import pytest

    data = graph.build(_mobile_repo(repo), surface="mobile-app")

    with pytest.raises(reach.UnknownStart) as exc:
        reach.resolve_start(data, None, "mobile", surface="mobile-app")
    assert "`launch-screen:`" in str(exc.value)


def test_a_stated_launch_screen_that_is_not_a_screen_says_so(repo: Path):
    """`surface_launch_screen` type-checks nothing, so a `launch-screen:` naming a component comes back settled and unusable."""
    import pytest

    data = graph.build(_mobile_repo_with_an_unusable_launch_screen(repo), surface="mobile-app")

    with pytest.raises(reach.UnknownStart) as exc:
        reach.resolve_start(data, None, "mobile", surface="mobile-app")

    message = str(exc.value)
    assert "docs/features/mobile-app/gui/components/toolbar.md" in message
    assert "not a screen on this surface" in message
    assert "states no `launch-screen:`" not in message


def test_two_launch_screens_settle_on_one_start_rather_than_refusing(repo: Path):
    """Two runbooks correctly covering one surface is a real book's shape, so `resolve_start` must hand back a start rather than a refusal — the ranked read settles it by node id, and the screen `current.md` names is the one a cold launch opens."""
    data = graph.build(_mobile_repo_with_two_launch_screens(repo), surface="mobile-app")

    assert reach.resolve_start(data, None, "mobile", surface="mobile-app") == (
        "docs/features/mobile-app/gui/screens/new-widget.md"
    )


def test_a_mobile_surface_with_no_surface_argument_keeps_the_original_message(repo: Path):
    """`resolve_start` called the way every caller called it before this change — with no `surface` — must behave exactly as before: `launch-screen:` is never consulted."""
    import pytest

    data = graph.build(_mobile_repo(repo, launch_screen=True), surface="mobile-app")

    with pytest.raises(reach.UnknownStart) as exc:
        reach.resolve_start(data, None, "mobile")
    assert str(exc.value) == "a `mobile` surface states no root path to start from; pass --from"


def test_a_path_addressed_surface_never_consults_a_launch_screen(repo: Path):
    """`web` has a path grammar, so `resolve_start` must still resolve its root screen and never so much as ask `surface_launch_screen` — passing `surface` through must not change a path-addressed surface's answer."""
    data = graph.build(_repo(repo), surface="web")

    assert reach.resolve_start(data, None, "web", surface="web") == LAND


def _cli_repo_with_no_screens(repo: Path):
    """A `cli` surface: a `type: cli` node under its own directory, no screens anywhere — the shape `workflows`, `farrier` and `workhorse` actually take in this repo's own book."""
    write(repo / "docs/features/toolbox/toolbox.md", (
        "---\ntype: cli\nslug: toolbox\ntitle: Toolbox\n---\n# Toolbox\n\n"
        "- binary: `toolbox`\n"
    ))
    write(repo / "docs/features/toolbox/ops/stack.md", (
        "---\ntype: runbook\nslug: stack\ntitle: Stack\n---\n# Stack\n\n"
        "- driver: cli\n- surfaces: [toolbox](../toolbox.md)\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `toolbox --help`\n"
    ))
    return load(repo)


def test_a_surface_with_no_screens_says_so_instead_of_launch_screen_or_a_root_path(repo: Path):
    """An empty domain is not a failed search: `workflows`, `farrier` and `workhorse` in this repo's own book each declare zero screens under `driver: cli`, and neither `--from` nor `launch-screen:` names anything to repair when there is no screen for either to point at."""
    import pytest

    data = graph.build(_cli_repo_with_no_screens(repo), surface="toolbox")

    with pytest.raises(reach.UnknownStart) as exc:
        reach.resolve_start(data, None, "cli", surface="toolbox")

    message = str(exc.value)
    assert "declares no screens" in message
    assert "launch-screen" not in message
    assert "--from" not in message


def test_the_reach_command_reports_no_screens_for_a_cli_surface(repo: Path, capsys):
    """The same empty-domain message, through `_cmd_reach` the way a person actually runs it — on stdout with exit 0, since asking the open question and finding nothing to start from is not the same fact as a route that fails."""
    graph_obj = _cli_repo_with_no_screens(repo)
    args = SimpleNamespace(surface="toolbox", start=None, target=None, json=True)

    assert cli._cmd_reach(graph_obj, args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["start"] is None
    message = payload["message"]
    assert "declares no screens" in message
    assert "launch-screen" not in message
    assert "--from" not in message


def test_the_reach_command_degrades_when_the_book_does_not_settle_a_driver(repo: Path, capsys):
    """Two runbooks disagreeing is `doctor`'s finding to raise."""
    _repo(repo)
    for slug, driver in (("deployed", "web"), ("local-cli", "cli")):
        write(repo / f"docs/features/web/ops/{slug}.md", (
            f"---\ntype: runbook\nslug: {slug}\ntitle: {slug}\n---\n# {slug}\n\n"
            f"- driver: {driver}\n- surfaces: [landing](../gui/screens/landing.md)\n\n"
            "## Steps\n\n### serve\n- kind: service\n- run: `serve`\n"
        ))
    graph_obj = load(repo)
    args = SimpleNamespace(surface="web", start=None, target=None, json=True)
    cli._cmd_reach(graph_obj, args)

    assert json.loads(capsys.readouterr().out)["start"] == LAND


def test_reachability_defaults_to_the_root_and_rejects_an_unknown_start(repo: Path):
    """A typo in `--from` used to route from nowhere and report every screen as a hole."""
    import pytest

    report = reach.reachability(_repo(repo), surface="web")
    assert report["start"] == LAND

    with pytest.raises(reach.UnknownStart, match="did you mean .*landing.md"):
        reach.reachability(load(repo), surface="web", start="landing")


def test_reachable_screens_are_not_flagged(repo: Path):
    _repo(repo)
    report = _doctor(repo)

    flagged = {f.path for f in report.findings if f.code == "unreachable-screen"}
    assert SIGNIN not in flagged and DASH not in flagged


def test_intra_screen_leads_to_is_not_navigation(repo: Path):
    """A `leads-to:` pointing inside its own screen is a state change, not a transition."""
    write(repo / SCREENS / "dashboard.md", DASHBOARD + """
## Components

### dash-tab
- leads-to: [Dashboard panel](dashboard.md#dash-panel)

### dash-panel
- selector: `.panel`
""")
    edges = reach.navigation_edges(graph.build(load(repo), surface="web"))
    assert not any(e["from"] == DASH and e["to"] == DASH for e in edges)


def test_none_with_a_reason_still_reads_as_none(repo: Path):
    """Authors write `none — public route, no auth guard`; the reason must not become a guard."""
    _repo(repo)
    write(repo / SCREENS / "landing.md", LANDING.replace(
        "- requires: none",
        "- requires:\n  - none — public route, no auth guard, no route loader"))
    pre = reach.preconditions(_by_id(repo)[LAND])
    assert pre["declared"] and pre["guards"] == []


def _mobile_repo_with_an_unreachable_screen(repo: Path):
    """A mobile surface with a settled `launch-screen:` and a second screen no navigation reaches from it — the shape `unreachable-screen` exists to catch, now that a mobile surface's root can be stated at all."""
    write(repo / MOBILE_SCREENS / "widget-list.md", (
        "---\ntype: screen\nslug: widget-list\ntitle: Widgets\n---\n# Widgets\n\n"
        "- route: `WidgetList`\n- requires: none\n- params: none\n"
    ))
    write(repo / MOBILE_SCREENS / "widget-detail.md", (
        "---\ntype: screen\nslug: widget-detail\ntitle: Widget detail\n---\n# Widget detail\n\n"
        "- route: `WidgetDetail`\n- requires: none\n- params: none\n"
    ))
    write(repo / "docs/features/mobile-app/ops/stack.md", (
        "---\ntype: runbook\nslug: stack\ntitle: Stack\n---\n# Stack\n\n"
        "- driver: mobile\n"
        "- surfaces: [widget-list](../gui/screens/widget-list.md)\n"
        "- launch-screen: [widget-list](../gui/screens/widget-list.md)\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `metro`\n"
    ))
    return load(repo)


def test_a_settled_mobile_launch_screen_gets_its_reachability_checked(repo: Path):
    """The debt `_check_reachability` used to skip is paid: a mobile surface with a settled `launch-screen:` is now walked like any other surface, and a screen no navigation reaches from it is reported as `unreachable-screen`."""
    _mobile_repo_with_an_unreachable_screen(repo)
    report = _doctor(repo)

    unreachable = [f for f in report.findings if f.code == "unreachable-screen"]
    assert [f.path for f in unreachable] == [f"{MOBILE_SCREENS}/widget-detail.md"]
    assert f"from {MOBILE_SCREENS}/widget-list.md" in unreachable[0].message
    assert "no-root-screen" not in {f.code for f in report.findings}


def test_a_mobile_surface_with_no_launch_screen_gets_no_root_screen_not_route(repo: Path):
    """No `launch-screen:` on a mobile surface's runbook is a `no-root-screen` warning that names the bullet the book is missing — never `route:` or `/`, which this driver has no grammar for at all."""
    _mobile_repo(repo)
    report = _doctor(repo)

    warn = next(f for f in report.findings if f.code == "no-root-screen")
    assert warn.ref == "mobile-app"
    assert "route:" not in warn.message and "`/`" not in warn.message
    assert "`launch-screen:`" in warn.message
    assert "launch-screen:" in warn.suggestion
    assert "unreachable-screen" not in {f.code for f in report.findings}


def test_a_path_addressed_surfaces_findings_are_unchanged(repo: Path):
    """The pre-existing `web` behaviour must come out byte-identical: this change only adds reachability checking to a driver that had none, it does not touch the one that already worked."""
    _repo(repo)
    report = _doctor(repo)

    unreachable = [f for f in report.findings if f.code == "unreachable-screen"]
    assert [f.path for f in unreachable] == [ARCHIVE]
    assert "no-root-screen" not in {f.code for f in report.findings}

