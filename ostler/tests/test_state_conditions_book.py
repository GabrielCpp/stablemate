"""A `when:` under a component's `states:` child links the data state its claim holds under, and `fixture: none` on a screen that sends a request names no condition."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ostler import doctor, registry
from ostler.model import load
from ostler.qa.context import build_context

from conftest import write

SCREEN = "docs/features/acme/web/screens/widget-list.md"
API = "docs/features/acme/http/api-service.md"

SCREEN_PAGE = """---
type: screen
title: Widget list
---
# Widget list

- route: /
- requires: none
- params: none
{requests}
## Components

### Low stock panel
- role: status
- name: Low stock
- states: shown when widgets are below 5
  - when: [some-low](../../http/api-service.md#some-low)
  - fixture: none, because the seed already holds a low widget
  - verify: visible(locator="#low-stock-panel")
- states: hidden when no widget is below 5
  - when: [none-low](../../http/api-service.md#none-low)
  - fixture: {second_fixture}
  - verify: hidden(locator="#low-stock-panel")

### Widget table
{table_when}- role: table
- name: Widgets

## Screen states

### Loaded
- shows:
  - [Widget table](#widget-table)
{state_when}
"""

API_PAGE = """---
type: server
title: Widget API
---
# Widget API

- entry-url: http://localhost:18101

## Endpoints

### list-widgets
- method: GET
- path: /api/widgets
- arrange: no_body()
- verify: http_status(code=200)

## Data states

### none-low
- of: widget
- observe: [list](#list-widgets)
- verify: count(subject="$.widgets[?(@.quantity<5)]", equals=0)

### some-low
- of: widget
- observe: [list](#list-widgets)
- verify: count(subject="$.widgets[?(@.quantity<5)]", greater_than=0)
"""

REQUESTS = "- requests:\n  - GET /api/widgets\n"
NONE_LOW = "[none-low](../../http/api-service.md#none-low)"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _book(root: Path, *, requests: str = REQUESTS, second_fixture: str = "none, because the seed holds none low",
          table_when: str = "", state_when: str = "") -> None:
    write(root / SCREEN, SCREEN_PAGE.format(requests=requests, second_fixture=second_fixture,
                                            table_when=table_when, state_when=state_when))
    write(root / API, API_PAGE)


def _findings(repo: Path) -> list[doctor.Finding]:
    return [f for f in doctor.run(load(repo)).findings if f.code == "unnamed-condition"]


def _obligations(root: Path) -> dict[str, dict]:
    _git(root, "init")
    _git(root, "config", "user.email", "a@b.c")
    _git(root, "config", "user.name", "x")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    write(root / "app/w.py", "def go():\n    return 1\n")
    packet = build_context(root, base=_git(root, "rev-parse", "HEAD"), source_roots={"acme": ["app"]},
                           whole_book=True)
    return {row["id"]: row for row in packet["obligations"]}


def test_the_held_keys_of_a_component_and_a_state_are_when() -> None:
    assert registry.held_keys("component") == ("when",)
    assert registry.held_keys("state") == ("when",)
    assert registry.held_keys("command") == ()
    assert "when" in registry.attached_keys("component")


def test_a_nested_when_binds_to_its_states_child_alone(repo: Path) -> None:
    _book(repo)
    node = next(n for n in load(repo).ui_nodes_of_type("component") if n.id.endswith("#low-stock-panel"))
    own, per_claim = registry.attributed_held(node.type, node.bullet_order, node.combiners)
    assert own == []
    assert per_claim == {
        ("states", 1): ["[some-low](../../http/api-service.md#some-low)"],
        ("states", 2): [NONE_LOW],
    }


def test_each_states_claim_carries_the_condition_ids_of_its_own_when(tmp_path: Path) -> None:
    _book(tmp_path)
    rows = _obligations(tmp_path)
    api = "docs/features/acme/http/api-service.md"
    assert rows[f"okf:{SCREEN}#low-stock-panel:states:1"]["conditionsDeclared"] == [f"{api}#some-low"]
    assert rows[f"okf:{SCREEN}#low-stock-panel:states:2"]["conditionsDeclared"] == [f"{api}#none-low"]
    assert "conditionsDeclared" not in rows[f"okf:{SCREEN}#low-stock-panel:name:1"]


def test_a_node_level_when_is_inherited_by_every_claim_of_the_node(tmp_path: Path) -> None:
    _book(tmp_path, table_when=f"- when: {NONE_LOW}\n")
    rows = _obligations(tmp_path)
    table = [row for oid, row in rows.items() if oid.startswith(f"okf:{SCREEN}#widget-table:") and row["kind"] != "contract"]
    assert table
    assert all(row["conditionsDeclared"] == ["docs/features/acme/http/api-service.md#none-low"] for row in table)


def test_a_state_node_keeps_a_when_written_after_its_shows(tmp_path: Path) -> None:
    _book(tmp_path, state_when=f"- when: {NONE_LOW}\n")
    rows = _obligations(tmp_path)
    assert rows[f"okf:{SCREEN}#loaded:contract"]["conditionsDeclared"] == [
        "docs/features/acme/http/api-service.md#none-low"]


def test_fixture_none_on_a_component_state_of_a_screen_that_sends_a_request_is_flagged(repo: Path) -> None:
    _book(repo)
    [found] = _findings(repo)
    assert found.severity == "error"
    assert found.path == SCREEN
    assert "the screen sends `GET /api/widgets`" in found.message
    assert "link the data state it holds under with `- when:`" in (found.suggestion or "")


def test_fixture_none_on_a_screen_state_of_a_screen_that_sends_a_request_is_flagged(repo: Path) -> None:
    _book(repo, second_fixture="well-stocked", state_when="- fixture: none, because nothing is arranged\n")
    state = [f for f in _findings(repo) if f.path == SCREEN and "#loaded" in f.message]
    assert len(state) == 1


def test_a_screen_that_sends_no_request_is_never_flagged(repo: Path) -> None:
    _book(repo, requests="")
    assert _findings(repo) == []


def test_a_named_fixture_is_never_flagged(repo: Path) -> None:
    page = SCREEN_PAGE.replace("none, because the seed already holds a low widget", "low-widget")
    write(repo / SCREEN, page.format(requests=REQUESTS, second_fixture="well-stocked", table_when="", state_when=""))
    write(repo / API, API_PAGE)
    assert _findings(repo) == []


def test_a_server_page_is_never_checked(repo: Path) -> None:
    _book(repo, requests="")
    write(repo / API, API_PAGE.replace("### list-widgets", "### list-widgets\n- fixture: none, because it reads no stored data"))
    assert _findings(repo) == []
