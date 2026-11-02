"""A hold keeps a request open from before the trigger until the claim it follows has been read."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ostler import checks, registry
from ostler.qa.context import build_context
from ostler.qa.harness_host import load_harness_module
from ostler.qa.obligation_frame import BookNode, obligation_frame

browser_module = load_harness_module("ostler_qa_browser")

_HOLD = 'hold(event="PUT /api/items/{id}")'

_SCREEN = f"""---
type: screen
slug: items
title: Items
---
# Items

- route: /items
- requires: none
- params: none

## Interactions

### save-item
- on: [save-button](#save-button)
- trigger: click
- code: app/items.py::save
- does: disables the save button until the server has answered
- intercept: {_HOLD}
- verify: inert(locator="#save-button")
- does: shows the saved notice
- verify: visible(locator="#save-button")

## Components

### save-button
- role: button
- name: Save
- selector: button.save
- states: shown while an item is open
- code: app/items.py::save
"""


class _Context:
    def __init__(self) -> None:
        self.routes: list[tuple[Any, Any]] = []

    def route(self, predicate: Any, handler: Any) -> None:
        self.routes.append((predicate, handler))


class _Route:
    def __init__(self, method: str = "PUT") -> None:
        self.request = SimpleNamespace(
            url="http://127.0.0.1:8099/api/items/7", method=method, resource_type="fetch", headers={},
            post_data=None, failure=None, timing={"responseEnd": -1}, response=lambda: None)
        self.fell_back = 0

    def fallback(self) -> None:
        self.fell_back += 1


def _holding(tmp_path: Path) -> tuple[Any, Any]:
    browser = browser_module.Browser(
        SimpleNamespace(browser=None, permissions=None, recording=None, viewport=None),
        qa_dir=tmp_path, scenario_id="scenario", clock=lambda: 0, emit=lambda record: None,
    )
    browser._context = _Context()
    browser.intercept("hold", event="PUT /api/items/{id}")
    return browser, browser._context.routes[0][1]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def test_a_hold_takes_only_the_request_it_keeps_open() -> None:
    call = checks.parse_intercept(_HOLD)

    assert isinstance(call, checks.CheckCall)
    assert (call.name, call.args) == ("hold", {"event": "PUT /api/items/{id}"})
    assert isinstance(checks.parse_intercept('hold(event="PUT /a", find="b")'), checks.Refusal)
    assert isinstance(checks.parse_intercept('hold(event="/a")'), checks.Refusal)


def test_an_interaction_hands_its_intercepts_to_the_frame() -> None:
    node = BookNode(id="items.md#save-item", type="interaction", page_type="", surface="acme",
                    bullets={"intercept": (_HOLD,)}, edges=())

    assert [call.name for call in obligation_frame(node, None, {}).intercepts] == ["hold"]


def test_a_hold_binds_to_the_claim_above_it_and_not_to_the_next_one() -> None:
    keys = [("does", "first"), ("intercept", _HOLD), ("verify", "a"), ("does", "second"), ("verify", "b")]
    order = [(key, value, index) for index, (key, value) in enumerate(keys)]

    contract, per_claim = registry.attributed_intercepts("interaction", order, {})

    assert contract == []
    assert per_claim[("does", 1)] == [_HOLD]
    assert per_claim.get(("does", 2), []) == []


def test_the_packet_says_which_claim_ends_the_hold(tmp_path: Path) -> None:
    screens = tmp_path / "docs/services/acme/gui/screens"
    screens.mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (screens / "items.md").write_text(_SCREEN, encoding="utf-8")
    (tmp_path / "app/items.py").write_text("def save():\n    return 1\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "app/items.py").write_text("def save():\n    return 2\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})

    by_tail = {row["id"].rsplit("#", 1)[-1]: row for row in packet["obligations"]}
    assert by_tail["save-item:does:1"]["releases"] == ["PUT /api/items/{id}"]
    assert "releases" not in by_tail["save-item:does:2"]
    assert by_tail["save-item:does:1"]["intercepts"] == [{"effect": "hold", "args": {"event": "PUT /api/items/{id}"}}]
    assert by_tail["save-item:does:2"]["intercepts"] == by_tail["save-item:does:1"]["intercepts"]


def test_the_route_stays_unanswered_until_release(tmp_path: Path) -> None:
    browser, handler = _holding(tmp_path)
    route = _Route()

    handler(route)
    assert route.fell_back == 0

    browser.release("PUT /api/items/{id}")
    assert route.fell_back == 1


def test_a_request_after_the_release_goes_straight_through(tmp_path: Path) -> None:
    browser, handler = _holding(tmp_path)
    browser.release("PUT /api/items/{id}")
    route = _Route()

    handler(route)

    assert route.fell_back == 1


def test_another_method_on_the_same_path_is_not_held(tmp_path: Path) -> None:
    _, handler = _holding(tmp_path)
    route = _Route("GET")

    handler(route)

    assert route.fell_back == 1


def test_a_held_request_does_not_count_as_in_flight_for_the_settling_checks(tmp_path: Path) -> None:
    browser, handler = _holding(tmp_path)
    route = _Route()
    key = id(route.request)
    browser._open[key] = "PUT"

    handler(route)
    assert browser._open.keys() - browser._kept_back == set()

    browser.release("PUT /api/items/{id}")
    assert browser._open.keys() - browser._kept_back == {key}


def test_a_hold_nothing_reached_or_never_released_is_reported(tmp_path: Path) -> None:
    untouched, _ = _holding(tmp_path)
    assert any("no exchange reached the rule" in problem for problem in untouched.unclean())

    stuck, handler = _holding(tmp_path)
    handler(_Route())
    assert any("never let them go" in problem for problem in stuck.unclean())

    clean, handler = _holding(tmp_path)
    handler(_Route())
    clean.release("PUT /api/items/{id}")
    assert not any("intercept" in problem for problem in clean.unclean())
