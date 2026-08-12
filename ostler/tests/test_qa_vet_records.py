"""A `vet` record becomes ordinary assertions in the ledger.

The defect this closes reached a green run: the screenshot showing a page crushed into a
column against the right margin was the one artifact nothing downstream read. Translating
the record here — rather than reporting it as a signal somebody may act on — is what makes
a misplaced component fail the story it was built in.
"""

from __future__ import annotations

import json
from pathlib import Path

from ostler.qa.drivers import PythonDriver
from ostler.qa.session import QaSession

from conftest import write

SCREEN = "docs/features/groom/gui/screens/s.md"


def _book(repo: Path) -> None:
    write(
        repo / SCREEN,
        "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
        "## Components\n\n"
        "### body\n- role: article\n- selector: `article.prose`\n"
        "- placement: width 60-100%, x 0-20%\n\n"
        "### toc\n- role: navigation\n- selector: `nav.toc`\n- placement: width 10-25%\n",
    )


def _shot(repo: Path, regions: list[dict]) -> Path:
    shot = repo / "docs/specs/story-1/qa/artifacts/loaded.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(b"\x89PNG")
    shot.with_suffix(".layout.json").write_text(
        json.dumps({"viewport": {"width": 1440, "height": 900}}), encoding="utf-8"
    )
    shot.with_suffix(".regions.json").write_text(json.dumps(regions), encoding="utf-8")
    return shot


def _region(role: str, selector: str, box: tuple[float, float, float, float]) -> dict:
    x, y, width, height = box
    return {
        "bbox": {"x": x, "y": y, "width": width, "height": height},
        "role": role,
        "selectors": [selector],
    }


def _driver(repo: Path) -> PythonDriver:
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    session = QaSession.create(spec, "qa-vet-1", "story-1", {})
    return PythonDriver(
        session, "web", {"driver": "playwright"}, root=repo, variables={}
    )


def _records(shot: Path, screen: str = SCREEN) -> list[dict]:
    return [
        {
            "type": "vet",
            "screen": screen,
            "state": "loaded",
            "screenshot": str(shot),
            "regions": str(shot.with_suffix(".regions.json")),
        },
        {"type": "scenario", "id": "s-1", "status": "passed", "assertions": 0, "failures": 0},
    ]


def _asserts(driver: PythonDriver) -> list[dict]:
    log = driver.session.qa_dir / "qa-run.ndjson"
    if not log.is_file():
        return []
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return [entry for entry in entries if entry.get("kind") == "assert"]


def test_a_misplaced_component_is_a_failed_assertion_carrying_its_numbers(repo: Path) -> None:
    """`by_role("article")` is true whether the page lays the article across the window or
    crushes it into a sliver, so the geometry has to arrive as its own assertion — and it
    has to quote the measured share, because the fix loop reads the ledger and nothing else."""
    _book(repo)
    shot = _shot(
        repo,
        [
            # The scan mints the `:nth(i)` suffix for an element with no id; the book
            # cannot know an index taken from one render and must not have to.
            _region("article", "article.prose:nth(41)", (1180, 88, 250, 760)),
            _region("navigation", "nav.toc", (0, 88, 240, 760)),
        ],
    )
    driver = _driver(repo)

    result = driver._grade("s-1", ["ac:1"], _records(shot), "", 0, timed_out=False)

    assert result.status == "failed"
    assert (result.assertions, result.failures) == (2, 1)
    records = _asserts(driver)
    assert [r["result"] for r in records] == ["FAIL", "PASS"]
    assert "is placed wrong" in records[0]["label"]
    assert "width is 17.4% of the viewport, documented as 60-100%" in records[0]["label"]
    # The obligations the scenario declared, not a separate coverage vocabulary: a vet
    # failure has to make the same acceptance criterion go red that a check does.
    assert records[0]["covers"] == ["ac:1"]


def test_the_verdicts_are_filed_beside_the_screenshot(repo: Path) -> None:
    """The independent audit reads a report rather than re-deriving one from the pixels."""
    _book(repo)
    shot = _shot(
        repo,
        [
            _region("article", "article.prose", (0, 88, 1400, 760)),
            _region("navigation", "nav.toc", (0, 88, 240, 760)),
        ],
    )
    driver = _driver(repo)

    result = driver._grade("s-1", [], _records(shot), "", 0, timed_out=False)

    assert result.status == "passed" and result.failures == 0
    report = json.loads(shot.with_suffix(".vet.json").read_text(encoding="utf-8"))
    assert report["schema"] == "vet-placement/1"
    assert report["viewport"] == {"width": 1440.0, "height": 900.0}
    assert [v["status"] for v in report["verdicts"]] == ["matched", "matched"]
    assert report["verdicts"][0]["bbox"]["width"] == 1400


def test_a_vet_of_a_screen_the_book_does_not_document_fails_the_scenario(repo: Path) -> None:
    """The failure mode that would quietly undo the whole change: a vet naming nothing
    registers nothing, reports no disagreement, and is indistinguishable from a correct
    screen. It is a problem, not an empty verdict list."""
    _book(repo)
    shot = _shot(repo, [_region("article", "article.prose", (0, 88, 1400, 760))])
    driver = _driver(repo)

    result = driver._grade(
        "s-1", [], _records(shot, "docs/features/groom/gui/screens/ghost.md"), "", 0,
        timed_out=False,
    )

    assert result.status == "failed"
    assert "does not document" in result.message
    assert _asserts(driver) == []


def test_a_screen_that_was_gone_by_the_time_it_was_measured_fails(repo: Path) -> None:
    _book(repo)
    shot = _shot(repo, [])
    shot.with_suffix(".regions.json").unlink()
    driver = _driver(repo)

    result = driver._grade("s-1", [], _records(shot), "", 0, timed_out=False)

    assert result.status == "failed"
    assert "produced no scan" in result.message
