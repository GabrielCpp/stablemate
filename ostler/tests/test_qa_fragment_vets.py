"""A scenario ending on a fragment page is vetted against the route of the screen the fragment is shown on."""

from __future__ import annotations

import json
from pathlib import Path

from ostler.qa.compile_support import vet_calls
from ostler.qa.drivers import PythonDriver
from ostler.qa.plan_source import Gap
from ostler.qa.session import QaSession

from conftest import write

SCREEN = "docs/features/groom/gui/screens/s.md"
FRAGMENT = "docs/features/groom/gui/screens/s-interactions.md"
NESTED = "docs/features/groom/gui/screens/s-interactions-export.md"


def test_a_fragment_s_vet_waits_for_the_route_of_the_screen_its_host_chain_ends_on() -> None:
    gaps: list[Gap] = []

    lines = vet_calls([NESTED], {SCREEN: "/:locale/editor/:pageId"}, ["okf:1"], gaps,
                      {NESTED: FRAGMENT, FRAGMENT: SCREEN})

    assert gaps == []
    assert lines == [f'    qa.vet("{NESTED}", arrives="[^/]+//[^/]+/[^/]+/editor/[^/]+/?(?:[?#].*)?")']


def test_a_fragment_whose_host_chain_reaches_no_screen_is_still_unidentifiable() -> None:
    gaps: list[Gap] = []

    lines = vet_calls([FRAGMENT], {SCREEN: "/dashboard"}, ["okf:1"], gaps,
                      {FRAGMENT: NESTED, NESTED: FRAGMENT})

    assert lines == []
    assert [(gap.obligation_id, gap.kind) for gap in gaps] == [("okf:1", "unidentifiable-screen")]


def _book(repo: Path) -> None:
    write(repo / SCREEN, "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n- route: /dashboard\n\n"
                         "See [its interactions](s-interactions.md).\n")
    write(repo / FRAGMENT, "---\ntype: fragment\nslug: s-interactions\ntitle: S interactions\n---\n"
                           "# S interactions\n\n- host: [S](s.md)\n")


def _driver(repo: Path) -> PythonDriver:
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "qa-okf-context.json").write_text(json.dumps({"featuresRoot": "docs/features"}), encoding="utf-8")
    session = QaSession.create(spec, "qa-vet-1", "story-1", {})
    return PythonDriver(session, "web", {"driver": "playwright"}, root=repo, variables={})


def _records(repo: Path, url: str) -> list[dict]:
    shot = repo / "docs/specs/story-1/qa/artifacts/loaded.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(b"\x89PNG")
    shot.with_suffix(".layout.json").write_text(json.dumps({"viewport": {"width": 1440, "height": 900}}),
                                                encoding="utf-8")
    shot.with_suffix(".regions.json").write_text("[]", encoding="utf-8")
    return [
        {"type": "vet", "screen": FRAGMENT, "state": "loaded", "screenshot": str(shot),
         "regions": str(shot.with_suffix(".regions.json")), "components": [], "url": url},
        {"type": "scenario", "id": "s-1", "status": "passed", "assertions": 0, "failures": 0},
    ]


def test_a_vet_of_a_fragment_is_checked_against_its_host_screen_s_arrival(repo: Path) -> None:
    _book(repo)
    driver = _driver(repo)

    arrived = driver._grade("s-1", [], _records(repo, "http://localhost:18102/dashboard"), "", 0, timed_out=False)
    assert arrived.status == "passed" and arrived.failures == 0

    elsewhere = driver._grade("s-1", [], _records(repo, "http://localhost:18102/settings"), "", 0, timed_out=False)
    assert elsewhere.status == "failed"
    assert "did not arrive" in elsewhere.message
