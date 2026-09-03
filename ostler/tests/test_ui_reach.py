"""`ostler reach` — the documented click-path to a screen, and the screens that have none."""

from __future__ import annotations

from pathlib import Path

from ostler import graph, reach
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

# Reachable only by walking a flow's `steps:`, never by a `leads-to:` bullet. Guarded, and
# parameterized: the walk must both authenticate and mint a project before it can arrive.
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

# Documented, but nothing navigates to it — and its preconditions are never stated. Both omissions
# `reach` exists to surface, deliberately in one fixture.
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

    assert all("via" in e for e in data["edges"])  # the flat list carries it too


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
    assert path[0]["node"].endswith("#landing-sign-in-link")  # what to click, not just where


def test_flow_steps_are_navigation_edges(repo: Path):
    """Consecutive `steps:` on different screens are a recorded transition."""
    path = present(reach.route(_edges(repo), SIGNIN, DASH))
    assert len(path) == 1
    assert path[0]["kind"] == "flow-step"
    # the hop is caused by the *previous* step's interaction, not by the arriving node
    assert path[0]["node"].endswith("#submit-sign-in")


def test_route_crosses_both_edge_kinds(repo: Path):
    path = present(reach.route(_edges(repo), LAND, DASH))
    assert [h["kind"] for h in path] == ["leads-to", "flow-step"]


def test_unreachable_screen_is_a_finding_not_a_fallback(repo: Path):
    """Archive has a `route:` bullet; reach must still refuse rather than hand back a URL."""
    assert reach.route(_edges(repo), LAND, ARCHIVE) is None

    report = reach.reachability(_repo(repo), surface="web", start=LAND)
    assert report["unreachable"] == [ARCHIVE]
    # landing (the start, zero-hop) + sign-in + forgot-password + dashboard
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
    assert archive["guards"] == [] and archive["params"] == []  # same emptiness, different meaning


def test_preconditions_parse_guards_and_params(repo: Path):
    pre = reach.preconditions(_by_id(repo)[DASH])
    assert pre["declared"]
    assert [g["node"] for g in pre["guards"]] == ["../components/auth-guards.md#protected-route"]
    assert pre["params"][0]["name"] == "projectId"
    assert pre["params"][0]["from"] == "sign-in.md#submit-sign-in"  # routable dependency


def test_route_hops_carry_destination_preconditions(repo: Path):
    """A caller walking the route must know what to satisfy on arrival, per hop."""
    _repo(repo)
    by_id = _by_id(repo)
    path = present(reach.route(_edges(repo), LAND, DASH, by_id))
    assert path[-1]["preconditions"]["guards"][0]["text"].startswith("[protected-route]")
    assert path[-1]["preconditions"]["params"][0]["name"] == "projectId"
    # the sign-in hop is unconditional, and says so
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


def _server(entry_url: str, marked: bool = True) -> str:
    return f"""\
---
type: server
slug: web
title: Web
---
# Web

- launch: `npm start`
- entry-url: `{entry_url}` — the local stand-in
{"- walkthrough: true" if marked else ""}
"""


def test_doctor_warns_rather_than_errors_when_no_screen_is_at_the_root(repo: Path):
    """No root means the question is unanswerable — which is not the same as a pass."""
    _repo(repo)
    write(repo / SCREENS / "landing.md", LANDING.replace("- route: `/`", "- route: `/home`"))
    report = _doctor(repo)

    assert "unreachable-screen" not in _codes(report)
    warn = next(f for f in report.findings if f.code == "no-root-screen")
    assert "`/`" in warn.message and "no server contract" in warn.message


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
    assert LAND in flagged  # `/` is no longer the root: nothing links to it from `/app`
    assert all(f"from {app}" in f.message for f in report.findings
               if f.code == "unreachable-screen")


def test_a_server_entry_url_with_no_matching_screen_names_the_server(repo: Path):
    _repo(repo)
    write(repo / SERVER, _server("http://localhost:3000/admin"))
    report = _doctor(repo)

    warn = next(f for f in report.findings if f.code == "no-root-screen")
    assert "`/admin`" in warn.message and SERVER in warn.message


def test_several_unmarked_servers_fall_back_to_the_app_root(repo: Path):
    """Two contracts and no `walkthrough: true`: a root read off an arbitrary pick is not a root."""
    _repo(repo)
    write(repo / SERVER, _server("http://localhost:3000/app", marked=False))
    write(repo / "docs/features/web/http/static.md",
          _server("http://localhost:8080/static", marked=False).replace("slug: web", "slug: static"))
    data = graph.build(load(repo), surface="web")

    assert reach.root_path(data) == ("/", None)
    assert reach.root_screen(data) == LAND


def test_doctor_flags_a_screen_no_path_reaches(repo: Path):
    _repo(repo)
    report = _doctor(repo)

    unreachable = [f for f in report.findings if f.code == "unreachable-screen"]
    assert [f.path for f in unreachable] == [ARCHIVE]
    assert unreachable[0].severity == "error"
    assert f"from {LAND}" in unreachable[0].message


def test_doctor_flags_an_island_that_has_an_inbound_edge(repo: Path):
    """The case that rules out an inbound-degree test: linked, but hanging off nothing.

    A cluster that links to itself is exactly the shape a broken navigation graph takes, and
    counting inbound edges scores every member of it as fine.
    """
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
    assert detail in flagged  # has an inbound edge from archive, still unreachable
    assert ARCHIVE in flagged


def test_a_route_valued_entry_makes_a_screen_a_seed(repo: Path):
    """A deep link is an address the walk can open, so the screen behind it is a root too."""
    _repo(repo)
    write(repo / SCREENS / "archive.md", _entry(ORPHAN, "/archive?token=…"))
    report = _doctor(repo)

    assert "unreachable-screen" not in _codes(report)


def test_a_prose_entry_does_not_exempt_a_screen(repo: Path):
    """"Reached by typing the URL" is a claim about the outside world the edge check cannot
    verify; a book where every screen makes it has no navigation in it and used to pass."""
    _repo(repo)
    write(repo / SCREENS / "archive.md", _entry(ORPHAN, "emailed deep link"))
    report = _doctor(repo)

    unreachable = [f for f in report.findings if f.code == "unreachable-screen"]
    assert [f.path for f in unreachable] == [ARCHIVE]
    assert "`entry: emailed deep link` is not a route" in unreachable[0].message


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
    assert SIGNIN not in flagged and DASH not in flagged  # via leads-to and flow-step


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
