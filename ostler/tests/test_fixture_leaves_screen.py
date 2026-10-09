"""A fixture whose browser steps open a screen leaves the browser there, so a page scenario on that screen does not navigate away from what the fixture arranged."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ostler.qa.compile import Plan, compile_plan_gaps
from ostler.qa.context import book_context

from conftest import screen_md, write

LIST_PATH = "docs/features/app/document-list.md"
OPEN_PATH = "docs/features/app/fixtures/create-form-open.md"
SEEDED_PATH = "docs/features/app/fixtures/seeded.md"
IDLE_PATH = "docs/features/app/fixtures/create-form-idle.md"
SCREEN = "docs/features/policy/gui/screens/policy-list.md"
BASE_URL = "http://localhost:5173"

LIST_COMPONENTS = """
## Components

### create-button

- role: button
- name: New document
"""

OPEN_FIXTURE = """---
type: fixture
title: Create form open
---
# Create form open

- lifetime: scenario

## Steps

### open-create-form

- kind: seed
- open: [Document list](../document-list.md)
- arrange: click("../document-list.md#create-button")
"""

SEEDED_FIXTURE = """---
type: fixture
title: Seeded
---
# Seeded

## Steps

### seed

- kind: seed
- run: ./scripts/seed.sh
"""

IDLE_FIXTURE = """---
type: fixture
title: Create form idle
---
# Create form idle

- needs:
  - [Seeded](seeded.md)
  - [Create form open](create-form-open.md)

## Steps

### settle

- kind: seed
- run: true
"""


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.email=qa@example.com", "-c", "user.name=QA", *args],
                   cwd=root, check=True, capture_output=True, text=True)


def test_the_context_names_the_screen_a_fixtures_own_browser_steps_open(repo: Path) -> None:
    write(repo / LIST_PATH, screen_md("document-list", "Document list", body=LIST_COMPONENTS))
    write(repo / OPEN_PATH, OPEN_FIXTURE)
    write(repo / SEEDED_PATH, SEEDED_FIXTURE)
    _git(repo, "init")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")

    assert book_context(repo)["fixtureScreens"] == {"create-form-open": LIST_PATH}


def test_a_fixture_with_no_browser_steps_leaves_the_browser_where_the_last_fixture_it_needs_did(repo: Path) -> None:
    write(repo / LIST_PATH, screen_md("document-list", "Document list", body=LIST_COMPONENTS))
    write(repo / OPEN_PATH, OPEN_FIXTURE)
    write(repo / SEEDED_PATH, SEEDED_FIXTURE)
    write(repo / IDLE_PATH, IDLE_FIXTURE)
    _git(repo, "init")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")

    assert book_context(repo)["fixtureScreens"] == {"create-form-idle": LIST_PATH, "create-form-open": LIST_PATH}


def test_a_fixture_a_whole_lap_shares_leaves_the_scenarios_browser_where_it_was(repo: Path) -> None:
    write(repo / LIST_PATH, screen_md("document-list", "Document list", body=LIST_COMPONENTS))
    write(repo / OPEN_PATH, OPEN_FIXTURE.replace("- lifetime: scenario\n\n", ""))
    write(repo / SEEDED_PATH, SEEDED_FIXTURE)
    _git(repo, "init")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")

    assert book_context(repo)["fixtureScreens"] == {}


def _context(fixture_screens: dict[str, str]) -> dict:
    obligation = {
        "id": "okf:policy-list:create-dialog:visible:1", "node": f"{SCREEN}#create-dialog",
        "nodeType": "component", "source": SCREEN, "surface": "policy",
        "requirement": "shows the create form", "required": True,
        "locators": {"role": ["dialog"], "name": ["New document"]},
        "checksDeclared": [{"call": "it", "name": "visible", "args": {"locator": "dialog:New document"}}],
        "fixturesDeclared": [{"name": "create-form-open", "args": [], "provides": "the form is open",
                              "providesKeys": []}],
    }
    navigation = {"policy": {
        "start": SCREEN, "surface": "policy", "driver": "web", "rootPath": "/", "entryUrl": BASE_URL,
        "counts": {"screens": 1, "reachable": 1, "unreachable": 0, "undeclared": 0, "nav_edges": 0},
        "routes": {SCREEN: []}, "unreachable": [], "undeclared": [],
    }}
    return {"story": {"slug": "demo-story"}, "obligations": [obligation], "navigation": navigation,
            "screenRoutes": {SCREEN: "/policy-list"}, "fixtureScreens": fixture_screens}


def _source(fixture_screens: dict[str, str]) -> str:
    result = compile_plan_gaps(_context(fixture_screens), story="demo-story", base_url=BASE_URL)
    assert isinstance(result, Plan)
    return result.source


def test_a_fixture_that_left_the_browser_on_the_screen_is_not_navigated_away_from() -> None:
    source = _source({"create-form-open": SCREEN})

    assert 'qa.fixture("create-form-open")' in source
    assert "qa.goto(" not in source


def test_a_fixture_that_left_the_browser_elsewhere_is_followed_by_the_screens_own_navigation() -> None:
    source = _source({"create-form-open": "docs/features/policy/gui/screens/landing.md"})

    assert source.index('qa.fixture("create-form-open")') < source.index('qa.goto("/")')


SIGN_IN_PATH = "docs/features/app/sign-in.md"
DASHBOARD_PATH = "docs/features/app/dashboard.md"

SIGN_IN_FIXTURE = """---
type: fixture
title: Signed in
---
# Signed in

- lifetime: scenario

## Steps

### sign-in

- kind: seed
- open: [Sign in](../sign-in.md)
- arrange: click("../sign-in.md#submit")
- arrange: click("../dashboard.md#dashboard-title")
"""


def test_a_fixture_whose_last_act_lands_on_another_screen_leaves_the_browser_there(repo: Path) -> None:
    write(repo / SIGN_IN_PATH, screen_md("sign-in", "Sign in", body="\n## Components\n\n### submit\n\n- role: button\n- name: Sign in\n"))
    write(repo / DASHBOARD_PATH, screen_md("dashboard", "Dashboard", body="\n## Components\n\n### dashboard-title\n\n- role: heading\n- name: Dashboard\n"))
    write(repo / "docs/features/app/fixtures/signed-in.md", SIGN_IN_FIXTURE)
    _git(repo, "init")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")

    assert book_context(repo)["fixtureScreens"] == {"signed-in": DASHBOARD_PATH}


def test_a_fixture_that_left_the_browser_on_the_screens_route_walks_on_from_there() -> None:
    landing, sign_in, dashboard = (f"docs/features/policy/gui/screens/{name}.md" for name in ("landing", "sign-in", "dashboard"))
    context = _context({"create-form-open": dashboard})
    context["navigation"]["policy"]["routes"] = {SCREEN: [
        {"node": f"{landing}#sign-in-link", "from": landing, "label": "Sign in link"},
        {"node": f"{sign_in}#submit", "from": sign_in, "label": "Submit sign in"},
        {"node": f"{dashboard}#policies-link", "from": dashboard, "label": "Policies link"},
    ]}
    result = compile_plan_gaps(context, story="demo-story", base_url=BASE_URL)
    assert isinstance(result, Plan)

    assert "qa.goto(" not in result.source
    assert "Submit sign in" not in result.source
    assert result.source.index('qa.fixture("create-form-open")') < result.source.index("Policies link")


def test_a_fixture_that_left_the_browser_off_the_screens_route_reopens_the_last_entry_on_it() -> None:
    landing, sign_in, dashboard, stages = (f"docs/features/policy/gui/screens/{name}.md"
                                           for name in ("landing", "sign-in", "dashboard", "stages"))
    context = _context({"create-form-open": stages})
    context["navigation"]["policy"]["routes"] = {SCREEN: [
        {"node": f"{landing}#sign-in-link", "from": landing, "label": "Sign in link"},
        {"node": f"{sign_in}#submit", "from": sign_in, "label": "Submit sign in"},
        {"node": f"{dashboard}#policies-link", "from": dashboard, "label": "Policies link"},
    ]}
    context["navigation"]["policy"]["doors"] = {sign_in: "/sign-in", dashboard: "/dashboard"}
    result = compile_plan_gaps(context, story="demo-story", base_url=BASE_URL)
    assert isinstance(result, Plan)

    assert 'qa.goto("/")' not in result.source
    assert "Submit sign in" not in result.source
    assert (result.source.index('qa.fixture("create-form-open")') < result.source.index('qa.goto("/dashboard")')
            < result.source.index("Policies link"))
