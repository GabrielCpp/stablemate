from __future__ import annotations

from pathlib import Path

import pytest

from ostler import Ostler, crud, doctor
from ostler.milestones import MilestoneSelectionError, approved_milestone, journey_slug
from ostler.model import load

from conftest import write

SECTIONS = ("Outcome", "Release Boundary", "User Journeys", "Architecture Decisions",
            "Constraints", "Acceptance", "Non-Goals")
READINESS = {
    "milestone-missing-section", "milestone-open-decisions", "milestone-dangling-link",
    "milestone-journey-services",
}
JOURNEY = "### Sign in with a code\n\n- services: area\n\nThe user signs in.\n"
UI_JOURNEY = "### Sign in with a code\n\n- services: mobile-app\n\nThe user signs in.\n"


def milestone_md(status: str = "approved", *, journeys: str = JOURNEY, omit: tuple[str, ...] = (),
                 extra: str = "", epics: str = "[]") -> str:
    out = ["---", "type: milestone", "title: Sign in", f"status: {status}", f"epics: {epics}",
           "---", "# Sign in", ""]
    for heading in SECTIONS:
        if heading in omit:
            continue
        body = journeys if heading == "User Journeys" else "Prose.\n"
        out += [f"## {heading}", "", body]
    return "\n".join(out) + extra


def put(repo: Path, slug: str = "sign-in", **kwargs) -> Path:
    path = repo / f"docs/milestones/{slug}/milestone.md"
    write(path, milestone_md(**kwargs))
    return path


def add_mobile_book(repo: Path) -> None:
    screens = "docs/services/mobile-app/gui/screens"
    write(repo / screens / "widget-list.md", (
        "---\ntype: screen\nslug: widget-list\ntitle: Widgets\n---\n# Widgets\n\n"
        "- route: `WidgetList`\n- requires: none\n- params: none\n"
    ))
    write(repo / "docs/services/mobile-app/ops/stack.md", (
        "---\ntype: runbook\nslug: stack\ntitle: Stack\n---\n# Stack\n\n"
        "- driver: mobile\n- surfaces: [widget-list](../gui/screens/widget-list.md)\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `metro`\n"
    ))


def findings(repo: Path, code: str | None = None) -> list:
    found = [f for f in doctor.run(load(repo)).findings if f.code in READINESS | {
        "legacy-milestone-file", "multiple-approved-milestones"}]
    return [f for f in found if code is None or f.code == code]


def test_a_milestone_is_loaded_from_its_folder(repo: Path):
    put(repo, "sign-in")

    [milestone] = load(repo).milestones

    assert milestone.name == "sign-in"
    assert milestone.eid == "sign-in"
    assert milestone.path == repo / "docs/milestones/sign-in/milestone.md"
    assert milestone.status == "approved"


def test_a_frontmatter_id_overrides_the_folder_name_as_the_eid(repo: Path):
    write(repo / "docs/milestones/sign-in/milestone.md",
          milestone_md().replace("title: Sign in", "id: m-1\ntitle: Sign in"))

    [milestone] = load(repo).milestones

    assert (milestone.name, milestone.eid) == ("sign-in", "m-1")


def test_a_flat_milestone_file_is_flagged_and_not_loaded(repo: Path):
    write(repo / "docs/milestones/sign-in.md", milestone_md())

    [finding] = findings(repo, "legacy-milestone-file")

    assert finding.severity == "error"
    assert finding.path == "docs/milestones/sign-in.md"
    assert "docs/milestones/sign-in/milestone.md" in finding.message
    assert load(repo).milestones == []


def test_a_flat_page_that_is_not_a_milestone_is_not_flagged(repo: Path):
    write(repo / "docs/milestones/notes.md", "# Notes\n")
    write(repo / "docs/milestones/other.md", "---\ntype: concept\ntitle: Other\n---\n# Other\n")

    assert findings(repo, "legacy-milestone-file") == []


def test_two_approved_milestones_are_an_error(repo: Path):
    put(repo, "first")
    put(repo, "second")

    [finding] = findings(repo, "multiple-approved-milestones")

    assert finding.severity == "error"
    assert "first" in finding.message and "second" in finding.message


def test_one_approved_milestone_among_others_is_fine(repo: Path):
    put(repo, "first")
    put(repo, "second", status="proposed")
    put(repo, "third", status="authored")

    assert findings(repo, "multiple-approved-milestones") == []


def test_the_approved_milestone_of_a_graph_is_returned(repo: Path):
    put(repo, "first", status="proposed")
    put(repo, "second")

    assert approved_milestone(load(repo)).name == "second"
    assert Ostler(repo, use_index=False).approved_milestone().name == "second"


def test_selection_with_no_approved_milestone_names_the_candidates(repo: Path):
    put(repo, "first", status="proposed")
    put(repo, "second", status="authored")

    with pytest.raises(MilestoneSelectionError, match=r"no milestone is approved.*first.*second"):
        approved_milestone(load(repo))


def test_selection_with_two_approved_milestones_names_both(repo: Path):
    put(repo, "first")
    put(repo, "second")

    with pytest.raises(MilestoneSelectionError, match=r"2 milestones are approved.*first.*second"):
        approved_milestone(load(repo))


def test_a_complete_milestone_has_no_readiness_finding(repo: Path):
    put(repo)

    assert findings(repo) == []


def test_a_missing_or_empty_section_fires_once_per_section(repo: Path):
    write(repo / "docs/milestones/sign-in/milestone.md",
          milestone_md(omit=("Constraints",)).replace("## Acceptance\n\nProse.\n", "## Acceptance\n"))

    found = findings(repo, "milestone-missing-section")

    assert len(found) == 2
    assert {"Constraints", "Acceptance"} == {
        h for h in SECTIONS if any(f"## {h}" in f.message for f in found)}


def test_the_compatibility_sources_section_is_optional(repo: Path):
    put(repo, extra="\n## Compatibility Sources\n\nLegacy.\n")

    assert findings(repo) == []


def test_an_open_decisions_section_fires(repo: Path):
    put(repo, extra="\n## Open Decisions\n\n- which provider\n")

    [finding] = findings(repo, "milestone-open-decisions")

    assert "Open Decisions" in finding.message


def test_a_dangling_link_fires_and_a_resolving_one_does_not(repo: Path):
    write(repo / "docs/design/real.md", "# Real\n")
    put(repo, extra=("\nSee [real](../../design/real.md), [anchor](#outcome), "
                     "[web](https://example.com/x), [mail](mailto:a@example.com) and "
                     "[gone](../../design/gone.md).\n"))

    [finding] = findings(repo, "milestone-dangling-link")

    assert finding.ref == "../../design/gone.md"


def test_a_link_inside_a_code_span_is_not_checked(repo: Path):
    put(repo, extra="\nWrite `[x](gone.md)` as a link.\n")

    assert findings(repo, "milestone-dangling-link") == []


def test_a_journey_with_no_services_bullet_fires(repo: Path):
    put(repo, journeys="### Sign in with a code\n\nThe user signs in.\n")

    [finding] = findings(repo, "milestone-journey-services")

    assert "no `- services:" in finding.message


def test_a_journey_naming_a_book_that_does_not_exist_fires(repo: Path):
    put(repo, journeys="### Sign in with a code\n\n- services: area, nowhere\n")

    [finding] = findings(repo, "milestone-journey-services")

    assert "nowhere" in finding.message


def test_a_journey_through_known_books_does_not_fire_the_services_check(repo: Path):
    put(repo, journeys="### One\n\n- services: area\n\n### Two\n\n- services: area, area\n")

    assert findings(repo, "milestone-journey-services") == []


def test_a_ui_journey_without_a_mockup_produces_no_finding(repo: Path):
    add_mobile_book(repo)
    put(repo, journeys=UI_JOURNEY)

    assert findings(repo) == []


@pytest.mark.parametrize(("title", "slug"), [
    ("Sign in with a code", "sign-in-with-a-code"),
    ("  Pay -- then / refund!  ", "pay-then-refund"),
    ("J1: Checkout", "j1-checkout"),
])
def test_a_journey_slug_lowercases_and_collapses_non_alphanumerics(title: str, slug: str):
    assert journey_slug(title) == slug


@pytest.mark.parametrize(("status", "severity"), [
    ("approved", "error"), ("authored", "error"), ("delivered", "error"), ("proposed", "warn"),
])
def test_readiness_is_an_error_once_approved_and_a_warning_while_proposed(
    repo: Path, status: str, severity: str,
):
    put(repo, status=status, omit=("Outcome",), extra="\n## Open Decisions\n\n- x\n")

    found = findings(repo)

    assert {f.code for f in found} == {"milestone-missing-section", "milestone-open-decisions"}
    assert {f.severity for f in found} == {severity}


def test_a_superseded_milestone_is_not_checked(repo: Path):
    put(repo, status="superseded", omit=("Outcome",), extra="\n## Open Decisions\n\n- x\n")

    assert findings(repo) == []


def test_the_api_returns_the_readiness_findings_of_one_milestone(repo: Path):
    put(repo, omit=("Outcome",))
    okf = Ostler(repo, use_index=False)

    [finding] = okf.milestone_readiness("sign-in")

    assert (finding.severity, finding.code) == ("error", "milestone-missing-section")
    with pytest.raises(KeyError):
        okf.milestone_readiness("nope")


def test_grills_and_artifacts_and_html_mockups_produce_no_finding(repo: Path):
    add_mobile_book(repo)
    put(repo, journeys=UI_JOURNEY)
    write(repo / "docs/milestones/sign-in/mockups/sign-in-with-a-code.html", "<html></html>")
    write(repo / "docs/milestones/sign-in/grills/auth.md", "# Auth grill\n\n1. Which provider?\n")
    write(repo / "docs/milestones/sign-in/grills/typed.md",
          "---\ntype: concept\ntitle: Typed\n---\n# Typed\n")
    write(repo / "docs/milestones/sign-in/artifacts/notes.md", "no frontmatter\n")
    write(repo / "docs/milestones/sign-in/artifacts/data.json", "{}\n")

    report = doctor.run(load(repo))

    noise = [f for f in report.findings
             if "docs/milestones/sign-in/" in f.path and f.path != "docs/milestones/sign-in/milestone.md"]
    assert noise == []
    assert "okf-missing-type" not in {f.code for f in report.findings}
    assert findings(repo) == []


def test_readiness_runs_when_the_profile_is_exploration(repo: Path):
    write(repo / "ostler.yml", "organization:\n  profile: exploration\n")
    put(repo, omit=("Outcome",))

    assert load(repo).profile == "exploration"
    assert [f.code for f in findings(repo)] == ["milestone-missing-section"]


def test_create_milestone_writes_the_folder_with_every_section_as_a_stub(tmp_path: Path):
    result = crud.create_milestone(load(tmp_path), "sign-in", "Sign in", prefix="t")

    path = tmp_path / "docs/milestones/sign-in/milestone.md"
    assert result.ok and result.paths == [path]
    text = path.read_text(encoding="utf-8")
    assert "status: proposed" in text
    assert all(f"## {heading}\n" in text for heading in SECTIONS)
    assert "## Open Decisions" not in text
    assert crud.create_milestone(load(tmp_path), "sign-in", "Again").ok is False
    [milestone] = load(tmp_path).milestones
    assert (milestone.name, milestone.status) == ("sign-in", "proposed")
