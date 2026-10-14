"""A screen declares passages between its states: doctor refuses the joints, stops and elements a walk could not follow."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ostler import registry
from ostler.cli import main

from conftest import report_of, write

RESULTS = "docs/features/acme/gui/screens/results.md"
DETAILS = "docs/features/acme/gui/screens/details.md"
FLOW = "docs/features/acme/flows/see.md"

CODES = {"passage-shape", "broken-joint", "unarranged-stop", "stateless-screen", "unsettled-act", "unperceivable-element", "unresolved-relation"}

RESULTS_PAGE = """---
type: screen
title: Results
---
# Results

- route: /
- requires: none
- params: none
- requests:
  - GET /api/results

## Components

### Results table
- role: table
- name: Results

### Load error
- role: alert
- name: Could not load results

### Open details button
- role: button
- name: Open details
- code: app/r.py::go

## Interactions

### open-details-click
- on: [Open details button](#open-details-button)
- trigger: click
- does:
  - request: opens
- code: app/r.py::go

## Screen states

### Loaded
- shows:
  - [Results table](#results-table)
  - [Load error](#load-error) absent

### Error
- fixture: [Results fail](../../fixtures/results-fail.md)
- shows:
  - [Load error](#load-error)

## Passages

### Open details

- from: [Loaded](#loaded)
- steps:
  - [Open details](#open-details-click)
- to: [Shown](details.md#shown)
- requests:
  - GET /api/results/{id}
"""

DETAILS_PAGE = """---
type: screen
title: Details
---
# Details

- route: /details
- requires: none
- params: none
- requests:
  - GET /api/details/{id}

## Components

### Details heading
- role: heading
- name: Details

## Screen states

### Shown
- shows:
  - [Details heading](#details-heading)
"""

FIXTURE = """---
type: fixture
title: Results fail
---
# Results fail

## Steps

### fail

- kind: seed
- run: true
"""


def flow_page(*steps: str) -> str:
    listed = "\n".join(f"  - [{label}]({href})" for label, href in (step.split("|") for step in steps))
    return f"""---
type: flow
title: See
---
# See

- start: [results](../gui/screens/results.md)
- steps:
{listed}
- end: [details](../gui/screens/details.md)
"""


LOADED = "Loaded|../gui/screens/results.md#loaded"
ERROR = "Error|../gui/screens/results.md#error"
OPEN = "Open details|../gui/screens/results.md#open-details"
SHOWN = "Shown|../gui/screens/details.md#shown"
CLICK = "Open details|../gui/screens/results.md#open-details-click"
FILL = "Search|../gui/screens/results.md#search-fill"
ARRIVE = "Arrive|../gui/screens/results.md#arrive-load"

EXTRA_INTERACTIONS = """### search-fill
- on: [Open details button](#open-details-button)
- trigger: fill(text="acme")
- does:
  - request: types
- code: app/r.py::go

### arrive-load
- on: [Results table](#results-table)
- trigger: load
- does:
  - request: arrives
- code: app/r.py::go

## Screen states
"""


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


@pytest.fixture
def book(tmp_path: Path) -> Path:
    write(tmp_path / RESULTS, RESULTS_PAGE)
    write(tmp_path / DETAILS, DETAILS_PAGE)
    write(tmp_path / FLOW, flow_page(LOADED, OPEN, SHOWN))
    write(tmp_path / "docs/features/acme/fixtures/results-fail.md", FIXTURE)
    write(tmp_path / "app/r.py", "def go():\n    return 1\n")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "x")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    return tmp_path


def _findings(book: Path, capsys: pytest.CaptureFixture[str]) -> list[dict]:
    main(["-C", str(book), "doctor", "--json"])
    return [f for f in report_of(capsys)["findings"] if f["code"] in CODES]


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new, 1))


def test_the_registry_hosts_passages_on_screen_pages_and_links_their_ends() -> None:
    assert registry.UI_HEADING_TO_TYPE["Passages"] == "passage"
    assert registry.UI_TYPES_BY_NAME["passage"].host_page_types == ("screen",)
    assert {"from", "to", "steps"} <= set(registry.RELATION_KEYS)


def test_a_flow_through_a_passage_is_clean(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _findings(book, capsys) == []


def test_a_renamed_state_fails_the_flow_and_the_passage_that_link_it(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _edit(book / DETAILS, "### Shown", "### Displayed")
    found = [f for f in _findings(book, capsys) if f["code"] == "unresolved-relation"]

    assert {f["path"] for f in found} == {RESULTS, FLOW}
    assert any("`to:`" in f["message"] for f in found)
    assert any("`steps:`" in f["message"] for f in found)


def test_a_passage_that_leaves_another_state_than_the_flow_is_at_breaks_the_joint(
    book: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    write(book / FLOW, flow_page(ERROR, OPEN, SHOWN))
    found = _findings(book, capsys)

    joints = [f for f in found if f["code"] == "broken-joint"]
    assert len(joints) == 1
    assert "#error`" in joints[0]["message"] and "#loaded`" in joints[0]["message"]
    assert joints[0]["path"] == FLOW


def test_a_stop_after_a_passage_must_be_where_the_passage_lands(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(book / FLOW, flow_page(LOADED, OPEN, LOADED))
    joints = [f for f in _findings(book, capsys) if f["code"] == "broken-joint"]

    assert len(joints) == 1
    assert "#shown`" in joints[0]["message"]


def test_a_stop_whose_fixture_the_flow_does_not_arrange_is_refused(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(book / FLOW, flow_page(ERROR))
    found = [f for f in _findings(book, capsys) if f["code"] == "unarranged-stop"]

    assert len(found) == 1
    assert "results-fail" in found[0]["message"] and "#error`" in found[0]["message"]


def test_a_stop_whose_fixture_the_flow_arranges_is_clean(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(book / FLOW, flow_page(ERROR))
    _edit(book / FLOW, "- steps:", "- fixture: [Results fail](../fixtures/results-fail.md)\n- steps:")

    assert [f for f in _findings(book, capsys) if f["code"] == "unarranged-stop"] == []


def test_a_stop_after_a_step_of_the_flow_is_reached_by_acts_and_arranges_nothing(
    book: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    write(book / FLOW, flow_page(LOADED, "Open details|../gui/screens/results.md#open-details-click", ERROR))

    assert [f for f in _findings(book, capsys) if f["code"] == "unarranged-stop"] == []


def test_a_state_a_passage_lands_on_is_reached_by_acts_and_arranges_nothing(
    book: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    _edit(book / DETAILS, "### Shown\n", "### Shown\n- fixture: [Results fail](../../fixtures/results-fail.md)\n")

    assert [f for f in _findings(book, capsys) if f["code"] == "unarranged-stop"] == []


def test_a_button_a_passage_clicks_must_be_found_by_role_and_label(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _edit(book / RESULTS, "### Open details button\n- role: button\n- name: Open details\n",
          "### Open details button\n- selector: testID=open\n")
    found = [f for f in _findings(book, capsys) if f["code"] == "unperceivable-element"]

    assert [f["ref"] for f in found] == [f"{RESULTS}#open-details-button"]
    message = found[0]["message"]
    assert "role and its label" in message and "test id" in message and "accessibility finding" in message

    _edit(book / RESULTS, "- selector: testID=open\n", "- role: button\n- name: Open details\n")
    assert [f for f in _findings(book, capsys) if f["code"] == "unperceivable-element"] == []


def test_a_component_no_state_busy_sign_or_passage_uses_is_not_checked(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _edit(book / RESULTS, "### Load error\n- role: alert\n- name: Could not load results\n\n", "")
    _edit(book / RESULTS, "  - [Load error](#load-error) absent\n", "")
    _edit(book / RESULTS, "- shows:\n  - [Load error](#load-error)\n", "- shows:\n  - [Results table](#results-table)\n")
    _edit(book / RESULTS, "### Open details button\n", "### Stray\n- selector: .stray\n\n### Open details button\n")

    assert [f for f in _findings(book, capsys) if f["code"] == "unperceivable-element"] == []


def test_a_passage_from_that_links_a_component_is_refused(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _edit(book / RESULTS, "- from: [Loaded](#loaded)", "- from: [Results table](#results-table)")
    found = [f for f in _findings(book, capsys) if f["code"] == "passage-shape"]

    assert len(found) == 1
    assert "`from:`" in found[0]["message"] and found[0]["path"] == RESULTS


def test_a_passage_whose_request_is_not_a_method_and_path_is_refused(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _edit(book / RESULTS, "  - GET /api/results/{id}", "  - results/{id}")
    found = [f for f in _findings(book, capsys) if f["code"] == "passage-shape"]

    assert len(found) == 1
    assert "METHOD /path" in found[0]["message"]


def test_a_passage_step_that_links_a_component_is_refused(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _edit(book / RESULTS, "  - [Open details](#open-details-click)", "  - [Open details](#open-details-button)")
    found = [f for f in _findings(book, capsys) if f["code"] == "passage-shape"]

    assert len(found) == 1
    assert "`steps:`" in found[0]["message"]


def _with_extra_interactions(book: Path) -> None:
    _edit(book / RESULTS, "## Screen states\n", EXTRA_INTERACTIONS)


def _unsettled(book: Path, capsys: pytest.CaptureFixture[str]) -> list[dict]:
    return [f for f in _findings(book, capsys) if f["code"] == "unsettled-act"]


def test_a_screen_with_no_state_is_one_finding_until_it_declares_one(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _edit(book / DETAILS, "## Screen states\n\n### Shown\n- shows:\n  - [Details heading](#details-heading)\n", "")
    found = [f for f in _findings(book, capsys) if f["code"] == "stateless-screen"]

    assert len(found) == 1
    assert found[0]["path"] == DETAILS
    assert "Under `## Screen states`" in found[0]["message"] and "`shows:`" in found[0]["message"]

    _edit(book / DETAILS, "## Components", "## Screen states\n\n### Shown\n\n## Components")
    assert [f for f in _findings(book, capsys) if f["code"] == "stateless-screen"] == []


def test_a_screen_whose_states_section_is_empty_is_stateless(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _edit(book / DETAILS, "### Shown\n- shows:\n  - [Details heading](#details-heading)\n", "")
    found = [f for f in _findings(book, capsys) if f["code"] == "stateless-screen"]

    assert [f["path"] for f in found] == [DETAILS]


def test_an_act_followed_by_a_stop_is_settled(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(book / FLOW, flow_page(LOADED, CLICK, ERROR))

    assert _unsettled(book, capsys) == []


def test_an_act_followed_by_an_act_is_unsettled(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(book / FLOW, flow_page(LOADED, CLICK, CLICK, ERROR))
    found = _unsettled(book, capsys)

    assert len(found) == 1
    assert found[0]["path"] == FLOW
    assert f"`{RESULTS}#open-details-click`" in found[0]["message"] and f"`{RESULTS}`" in found[0]["message"]
    assert "no stop follows it" in found[0]["message"]


def test_an_act_as_the_last_step_is_unsettled(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(book / FLOW, flow_page(LOADED, CLICK))

    assert len(_unsettled(book, capsys)) == 1


def test_a_fill_needs_no_stop_after_it(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _with_extra_interactions(book)
    write(book / FLOW, flow_page(LOADED, FILL, CLICK, ERROR))

    assert _unsettled(book, capsys) == []


def test_a_flow_opening_on_a_click_with_no_stop_is_unsettled(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(book / FLOW, flow_page(CLICK, ERROR))
    found = _unsettled(book, capsys)

    assert len(found) == 1
    assert "before it stopped there" in found[0]["message"]


def test_a_flow_opening_on_an_arrival_followed_by_a_stop_is_settled(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _with_extra_interactions(book)
    write(book / FLOW, flow_page(ARRIVE, LOADED))

    assert _unsettled(book, capsys) == []


def test_a_flow_opening_on_a_passage_is_settled(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(book / FLOW, flow_page(OPEN, SHOWN))

    assert _unsettled(book, capsys) == []
