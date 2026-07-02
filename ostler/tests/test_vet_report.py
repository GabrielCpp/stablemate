from __future__ import annotations

import json

from ostler import markdown
from ostler.vet.geometry import BBox
from ostler.vet.manifest import DomElement
from ostler.vet.regions import RegionBox
from ostler.vet.register import MatchResult, match
from ostler.vet.report import VetReport, build_report, build_vet_concept


def _dom(selector, x, y, w, h, visible=True, role="") -> DomElement:
    return DomElement(selector=selector, role=role, visible=visible,
                      bbox=BBox(x=x, y=y, width=w, height=h))


def _region(x, y, w, h, role=None, selectors=None) -> RegionBox:
    return RegionBox(bbox=BBox(x=x, y=y, width=w, height=h), role=role,
                     selectors=selectors or ["#r"])


def _clean_match_result() -> MatchResult:
    elements = [_dom("#nav", 0, 0, 10, 10, role="navigation")]
    regions = [_region(0, 0, 10, 10, role="navigation")]
    return match(elements, regions)


def _dirty_match_result() -> MatchResult:
    elements = [_dom("#gone", 0, 0, 10, 10)]
    regions = [_region(50, 50, 10, 10, role="dialog")]
    return match(elements, regions)


def _build(match_result: MatchResult, state="default") -> VetReport:
    return build_report(
        slug="01-foo", state=state, screenshot="vet/default.png", manifest="vet/manifest.json",
        regions="vet/default-regions.json", cdp_url=None, manifest_errors=[],
        iou_threshold=0.5, match_result=match_result,
    )


def test_build_report_clean_status():
    report = _build(_clean_match_result())
    assert report.summary.status == "clean"
    assert report.summary.matchedCount == 1
    assert report.summary.missingCount == 0


def test_build_report_disagreements_status():
    report = _build(_dirty_match_result())
    assert report.summary.status == "disagreements"
    assert report.summary.missingCount == 1
    assert report.summary.unexpectedCount == 1


def test_report_round_trips_through_json():
    report = _build(_dirty_match_result())
    dumped = json.loads(report.model_dump_json(by_alias=True))
    restored = VetReport.model_validate(dumped)
    assert restored == report
    assert dumped["cdpUrl"] is None
    assert "manifestErrors" in dumped


def test_build_vet_concept_creates_fresh():
    report = _build(_clean_match_result())
    raw = build_vet_concept(None, report)
    doc = markdown.split(raw)
    assert doc.frontmatter["type"] == "spec.vet"
    assert doc.frontmatter["slug"] == "01-foo"
    assert doc.frontmatter["status"] == "clean"
    assert doc.find_section("State: default") is not None


def test_build_vet_concept_rerun_same_state_replaces_in_place():
    report1 = _build(_clean_match_result())
    raw = build_vet_concept(None, report1)
    report2 = _build(_dirty_match_result())
    raw2 = build_vet_concept(raw, report2)
    doc = markdown.split(raw2)
    assert doc.frontmatter["states"]["default"]["status"] == "disagreements"
    # only one "State: default" section, not two
    assert raw2.count("## State: default") == 1


def test_build_vet_concept_different_state_appends_section():
    report1 = _build(_clean_match_result(), state="default")
    raw = build_vet_concept(None, report1)
    report2 = _build(_dirty_match_result(), state="expanded")
    raw2 = build_vet_concept(raw, report2)
    doc = markdown.split(raw2)
    assert doc.find_section("State: default") is not None
    assert doc.find_section("State: expanded") is not None


def test_build_vet_concept_top_level_status_is_disagreements_if_any_state_is():
    report1 = _build(_clean_match_result(), state="default")
    raw = build_vet_concept(None, report1)
    report2 = _build(_dirty_match_result(), state="expanded")
    raw2 = build_vet_concept(raw, report2)
    assert markdown.split(raw2).frontmatter["status"] == "disagreements"

    # once the disagreeing state goes clean again, overall status follows
    report2_clean = _build(_clean_match_result(), state="expanded")
    raw3 = build_vet_concept(raw2, report2_clean)
    assert markdown.split(raw3).frontmatter["status"] == "clean"
