"""`ostler reach` — the documented click-path to a screen, and the screens that have none."""

from __future__ import annotations

from pathlib import Path

from ostler import graph, reach
from ostler.model import load

from conftest import write

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

# Documented, but nothing navigates to it — and its preconditions are never stated. Both gaps
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
    path = reach.route(_edges(repo), LAND, FORGOT_ID)
    assert [h["to"] for h in path] == [SIGNIN, FORGOT_ID]
    assert path[0]["action"] == "activate"
    assert path[0]["node"].endswith("#landing-sign-in-link")  # what to click, not just where


def test_flow_steps_are_navigation_edges(repo: Path):
    """Consecutive `steps:` on different screens are a recorded transition."""
    path = reach.route(_edges(repo), SIGNIN, DASH)
    assert len(path) == 1
    assert path[0]["kind"] == "flow-step"
    # the hop is caused by the *previous* step's interaction, not by the arriving node
    assert path[0]["node"].endswith("#submit-sign-in")


def test_route_crosses_both_edge_kinds(repo: Path):
    path = reach.route(_edges(repo), LAND, DASH)
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
    path = reach.route(_edges(repo), LAND, DASH, by_id)
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
