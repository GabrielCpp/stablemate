"""A `vet` record becomes ordinary assertions in the ledger."""

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
        "- route: /dashboard\n\n"
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


def _driver(repo: Path, obligation_documents: dict[str, list[str]] | None = None) -> PythonDriver:
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "qa-okf-context.json").write_text(
        json.dumps({"featuresRoot": "docs/features"}), encoding="utf-8"
    )
    session = QaSession.create(spec, "qa-vet-1", "story-1", {})
    return PythonDriver(
        session,
        "web",
        {"driver": "playwright"},
        root=repo,
        variables={},
        obligation_documents=obligation_documents,
    )


def _records(
    shot: Path,
    screen: str = SCREEN,
    components: list[str] | None = None,
    url: str = "",
) -> list[dict]:
    return [
        {
            "type": "vet",
            "screen": screen,
            "state": "loaded",
            "screenshot": str(shot),
            "regions": str(shot.with_suffix(".regions.json")),
            "components": components or [],
            "url": url,
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
    """`by_role("article")` is true whether the page lays the article across the window or crushes it into a sliver, so the geometry has to arrive as its own assertion — and it has to quote the measured share, because the fix loop reads the ledger and nothing else."""
    _book(repo)
    shot = _shot(
        repo,
        [
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
    """The failure mode that would quietly undo the whole change: a vet naming nothing registers nothing, reports no disagreement, and is indistinguishable from a correct screen."""
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


def test_a_vet_spelled_in_the_packet_s_frame_resolves_against_a_book_rooted_elsewhere(
    repo: Path,
) -> None:
    """The defect this closes: a compiled plan spells `qa.vet(...)` relative to the packet's `featuresRoot`, not to the checkout's own default `docs/features`."""
    nested_screen = "shed/docs/features/groom/gui/screens/s.md"
    write(
        repo / nested_screen,
        "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
        "## Components\n\n"
        "### body\n- role: article\n- selector: `article.prose`\n"
        "- placement: width 60-100%\n",
    )
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "qa-okf-context.json").write_text(
        json.dumps({"featuresRoot": "shed/docs/features"}), encoding="utf-8"
    )
    session = QaSession.create(spec, "qa-vet-1", "story-1", {})
    driver = PythonDriver(
        session, "web", {"driver": "playwright"}, root=repo, variables={}
    )
    shot = _shot(repo, [_region("article", "article.prose", (0, 88, 1400, 760))])

    result = driver._grade("s-1", [], _records(shot, nested_screen), "", 0, timed_out=False)

    assert result.status == "passed" and result.failures == 0
    assert _asserts(driver)[0]["result"] == "PASS"


def test_with_no_qa_context_packet_a_vet_reports_the_missing_frame_as_a_problem(
    repo: Path,
) -> None:
    """No packet means no stated frame to resolve `qa.vet`'s argument against."""
    _book(repo)
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    session = QaSession.create(spec, "qa-vet-1", "story-1", {})
    driver = PythonDriver(
        session, "web", {"driver": "playwright"}, root=repo, variables={}
    )
    shot = _shot(repo, [_region("article", "article.prose", (0, 88, 1400, 760))])

    result = driver._grade("s-1", [], _records(shot), "", 0, timed_out=False)

    assert result.status == "failed"
    assert "qa-okf-context.json" in result.message
    assert _asserts(driver) == []


def test_a_scoped_vet_registers_only_the_components_it_names(repo: Path) -> None:
    """A photograph taken mid-journey establishes some of a screen, not all of it."""
    _book(repo)
    shot = _shot(
        repo,
        [
            _region("article", "article.prose", (0, 88, 1400, 760)),
            _region("navigation", "nav.toc", (0, 88, 1400, 760)),
        ],
    )
    driver = _driver(repo)

    result = driver._grade("s-1", [], _records(shot, components=["body"]), "", 0, timed_out=False)

    assert result.status == "passed"
    assert (result.assertions, result.failures) == (1, 0)
    assert [r["label"].split(" ")[0].rsplit("#", 1)[-1] for r in _asserts(driver)] == ["body"]


def test_a_scoped_vet_naming_a_component_the_book_does_not_have_fails(repo: Path) -> None:
    """Scoping narrows what a photograph answers for, so a typo in the list would narrow it to nothing and report a pass."""
    _book(repo)
    shot = _shot(repo, [_region("article", "article.prose", (0, 88, 1400, 760))])
    driver = _driver(repo)

    result = driver._grade("s-1", [], _records(shot, components=["ghost"]), "", 0, timed_out=False)

    assert result.status == "failed"
    assert "undocumented component" in result.message
    assert _asserts(driver) == []


def test_a_screen_that_was_gone_by_the_time_it_was_measured_fails(repo: Path) -> None:
    _book(repo)
    shot = _shot(repo, [])
    shot.with_suffix(".regions.json").unlink()
    driver = _driver(repo)

    result = driver._grade("s-1", [], _records(shot), "", 0, timed_out=False)

    assert result.status == "failed"
    assert "produced no scan" in result.message


def test_a_vet_speaks_only_for_the_document_it_photographed(repo: Path) -> None:
    """The fan-out that made an abort-shaped verdict out of a placement one: a vet was filed against the scenario's whole `covers`, so one misplaced component disproved every API obligation the same scenario happened to claim."""
    _book(repo)
    shot = _shot(
        repo,
        [
            _region("article", "article.prose", (1180, 88, 250, 760)),
            _region("navigation", "nav.toc", (0, 88, 240, 760)),
        ],
    )
    driver = _driver(
        repo,
        obligation_documents={
            f"okf:{SCREEN}#loads:does:1": [SCREEN],
            "okf:docs/features/groom/http/groom.md#get-runs:does:2": [
                "docs/features/groom/http/groom.md"
            ],
        },
    )
    covers = [
        f"okf:{SCREEN}#loads:does:1",
        "okf:docs/features/groom/http/groom.md#get-runs:does:2",
        "ac:1",
    ]

    result = driver._grade("s-1", covers, _records(shot), "", 0, timed_out=False)

    assert result.status == "failed"
    failed = [record for record in _asserts(driver) if record["result"] == "FAIL"]
    assert len(failed) == 1
    assert failed[0]["covers"] == [f"okf:{SCREEN}#loads:does:1", "ac:1"]


def test_a_vet_credits_a_same_as_family_s_obligation_though_the_id_names_another_screen(
    repo: Path,
) -> None:
    """A `same-as:` family collapses onto one id minted for its lexicographic-min member (`context.py::_obligations`), so the id this scenario covers can name a screen other than the one a given vet photographs — `docs/features/groom/gui/screens/other.md` below, never `SCREEN` — while still being the very obligation `SCREEN` states, because the family occupies both documents."""
    _book(repo)
    shot = _shot(
        repo,
        [
            _region("article", "article.prose", (1180, 88, 250, 760)),
            _region("navigation", "nav.toc", (0, 88, 240, 760)),
        ],
    )
    family_id = "okf:docs/features/groom/gui/screens/other.md#body:contract"
    other_document_id = "okf:docs/features/groom/http/groom.md#get-runs:does:2"
    driver = _driver(
        repo,
        obligation_documents={
            family_id: [SCREEN, "docs/features/groom/gui/screens/other.md"],
            other_document_id: ["docs/features/groom/http/groom.md"],
        },
    )
    covers = [family_id, other_document_id, "ac:1"]

    result = driver._grade("s-1", covers, _records(shot), "", 0, timed_out=False)

    assert result.status == "failed"
    failed = [record for record in _asserts(driver) if record["result"] == "FAIL"]
    assert len(failed) == 1
    assert failed[0]["covers"] == [family_id, "ac:1"]


def test_a_failed_verdict_puts_what_the_page_showed_on_the_ledger(repo: Path) -> None:
    """A reader of `qa-run.ndjson` has the vet JSON beside it and no reason to open it."""
    _book(repo)
    shot = _shot(repo, [_region("navigation", "nav.toc", (0, 88, 240, 760))])
    driver = _driver(repo)

    result = driver._grade("s-1", [], _records(shot), "", 0, timed_out=False)

    assert result.status == "failed"
    records = {r["result"]: r for r in _asserts(driver)}
    assert "missing" in records["FAIL"]["params"]["actual"]
    assert "as documented" not in records["FAIL"]["params"]["actual"]
    assert "matched at x=0, y=88, 240x760" == records["PASS"]["params"]["actual"]


def test_a_vet_of_a_screen_the_walk_never_reached_is_a_hard_stop(repo: Path) -> None:
    """The screen is an argument and the pixels are an observation; nothing else related them."""
    _book(repo)
    shot = _shot(repo, [_region("navigation", "nav.toc", (0, 88, 240, 760))])
    driver = _driver(repo)

    result = driver._grade(
        "s-1", [], _records(shot, url="http://localhost:18102/settings"), "", 0, timed_out=False
    )

    assert result.status == "failed"
    assert "did not arrive" in result.message
    assert _asserts(driver) == []
    assert not shot.with_suffix(".vet.json").exists()


def test_a_vet_on_the_documented_route_registers_and_says_it_confirmed_the_screen(
    repo: Path,
) -> None:
    """A query string is state within a screen, not a different screen."""
    _book(repo)
    shot = _shot(
        repo,
        [
            _region("article", "article.prose", (0, 88, 1400, 760)),
            _region("navigation", "nav.toc", (0, 88, 240, 760)),
        ],
    )
    driver = _driver(repo)

    result = driver._grade(
        "s-1",
        [],
        _records(shot, url="http://localhost:18102/dashboard?page=2"),
        "",
        0,
        timed_out=False,
    )

    assert result.status == "passed"
    report = json.loads(shot.with_suffix(".vet.json").read_text(encoding="utf-8"))
    assert report["arrival"] == "confirmed"
    assert report["url"] == "http://localhost:18102/dashboard?page=2"


def test_a_photograph_with_no_url_says_the_screen_was_never_established(repo: Path) -> None:
    """A device has no URL, so its vet cannot claim it photographed the screen it names."""
    _book(repo)
    shot = _shot(
        repo,
        [
            _region("article", "article.prose", (0, 88, 1400, 760)),
            _region("navigation", "nav.toc", (0, 88, 240, 760)),
        ],
    )
    driver = _driver(repo)

    driver._grade("s-1", [], _records(shot), "", 0, timed_out=False)

    report = json.loads(shot.with_suffix(".vet.json").read_text(encoding="utf-8"))
    assert report["arrival"] == "unobserved"
