from __future__ import annotations

from pathlib import Path

import pytest

from ostler import crud, doctor
from ostler.model import load

from conftest import BAR_ID, present, BAR_STORY, EPIC_A, EPIC_B, FOO_ID, FOO_STORY, epic_md, specs_root, story_md, write, write_prefix, epics_root, milestones_root


def codes(report):
    return {f.code for f in report.findings if f.severity == "error"}


def test_clean_repo_has_no_errors(repo: Path):
    report = doctor.run(load(repo))
    assert report.errors == 0, [f.message for f in report.findings if f.severity == "error"]
    assert report.profile == "full"
    assert {e["dir"] for e in report.epics} == {EPIC_A, EPIC_B}


def test_cross_epic_seed_reference_is_flagged(repo: Path):
    write(epics_root() / EPIC_A / "epic.md", epic_md(
        EPIC_A, "epic-a", slug="epic-a",
        seeds=[("seed-a1", "researched", "first"), ("seed-a2", "resolved", "done")],
        stories=[("01-foo", "Foo", ["seed-b1"], FOO_ID)],
    ))

    report = doctor.run(load(repo))
    assert "cross-epic-seed" in codes(report)
    assert "orphan-seed" in codes(report)
    assert report.errors


def test_blocker_naming_no_story_is_flagged(repo: Path):
    write(epics_root() / FOO_STORY, story_md("01-foo", "Foo", "Not started", eid=FOO_ID, depends=["no-such-story"]))
    assert "dangling-dependency" in codes(doctor.run(load(repo)))


def test_blocker_in_another_epic_is_flagged(repo: Path):
    write(epics_root() / FOO_STORY, story_md("01-foo", "Foo", "Not started", eid=FOO_ID, depends=["01-bar"]))
    assert "cross-epic-dependency" in codes(doctor.run(load(repo)))


def test_story_key_collision_is_flagged_and_lookup_is_ambiguous(repo: Path):
    second = epics_root() / BAR_STORY
    second.write_text(
        second.read_text(encoding="utf-8").replace(f"id: {BAR_ID}", f"id: {FOO_ID}"),
        encoding="utf-8",
    )
    epic_b = epics_root() / EPIC_B / "epic.md"
    epic_b.write_text(
        epic_b.read_text(encoding="utf-8").replace(f"- id: {BAR_ID}", f"- id: {FOO_ID}"),
        encoding="utf-8",
    )
    second.parent.rename(second.parent.with_name(FOO_ID))
    graph = load(repo)
    findings = [
        f for f in doctor.run(graph).findings if f.code == "story-key-collision"
    ]

    assert [finding.ref for finding in findings] == [FOO_ID]
    assert f"{EPIC_A}/stories/{FOO_ID}/story.md" in findings[0].message
    assert f"{EPIC_B}/stories/{FOO_ID}/story.md" in findings[0].message
    with pytest.raises(ValueError, match="ambiguous"):
        graph.find_story(FOO_ID)


def test_story_id_mismatch_between_epic_and_story_is_flagged(tmp_path: Path):
    write(
        epics_root() / "e/epic.md",
        "\n".join(
            [
                "---",
                "type: epic",
                "id: E-1",
                "title: E",
                "---",
                "# Epic: E",
                "",
                "## Stories",
                "",
                "### a",
                "- title: A",
                "- id: STORY-1",
                "- covers: (none)",
                "",
            ]
        )
        + "\n",
    )
    write(
        epics_root() / "e/stories/a/story.md",
        story_md("a", "A", "Not started").replace(
            "type: story", "type: story\nid: STORY-2"
        ),
    )

    findings = [
        finding
        for finding in doctor.run(load(tmp_path)).findings
        if finding.code == "story-id-mismatch"
    ]

    assert len(findings) == 1
    assert "STORY-1" in findings[0].message
    assert "STORY-2" in findings[0].message


def test_a_dependencies_bullet_that_names_no_blocker_is_flagged(repo: Path):
    """The guard against a silent rewrite: story.md is agent-written, and a body turned into prose empties the DAG with nothing else reporting it."""
    text = story_md("01-foo", "Foo", "Not started", eid=FOO_ID, depends=["01-bar"])
    write(epics_root() / FOO_STORY, text.replace("- Blocked by: 01-bar", "- Needs: 01-bar"))

    findings = [f for f in doctor.run(load(repo)).findings
                if f.code == "malformed-dependency-bullet"]

    assert [f.ref for f in findings] == ["01-foo"]
    assert "Needs: 01-bar" in findings[0].message


def test_resolved_seed_not_required_to_be_covered(repo: Path):
    report = doctor.run(load(repo))
    assert "orphan-seed" not in codes(report)


def test_a_story_covering_a_seed_id_unknown_to_the_whole_book_is_flagged(repo: Path):
    """Unlike `cross-epic-seed` (the id belongs to a sibling epic), `dangling-seed` is what fires when no epic anywhere claims the id at all."""
    write(epics_root() / EPIC_A / "epic.md", epic_md(
        EPIC_A, "epic-a", slug="epic-a",
        seeds=[("seed-a1", "researched", "first"), ("seed-a2", "resolved", "done")],
        stories=[("01-foo", "Foo", ["seed-ghost"], FOO_ID)],
    ))
    report = doctor.run(load(repo))
    assert "dangling-seed" in codes(report)
    finding = next(f for f in report.findings if f.code == "dangling-seed")
    assert finding.ref == "seed-ghost"


def test_a_story_named_in_the_epic_with_no_story_file_on_disk_is_flagged(repo: Path):
    write(epics_root() / EPIC_A / "epic.md", epic_md(
        EPIC_A, "epic-a", slug="epic-a",
        seeds=[("seed-a1", "researched", "first")],
        stories=[("01-foo", "Foo", ["seed-a1"], FOO_ID), ("02-ghost", "Ghost", [], "t-02ghost")],
    ))
    report = doctor.run(load(repo))
    assert "missing-story-file" in codes(report)
    finding = next(f for f in report.findings if f.code == "missing-story-file")
    assert finding.ref == "02-ghost"


def test_seedless_epic_no_covers_warning(repo: Path):
    write(epics_root() / "t-3/epic.md", epic_md(
        "t-3", "epic-c", seeds=[], stories=[("01-x", "X", [], "t-01x")], slug="epic-c"))
    write(epics_root() / "t-3/stories/t-01x/story.md",
          "---\ntype: story\nslug: 01-x\nid: t-01x\nstatus: Not started\n---\n# Story: X\n")
    warns = {f.code for f in doctor.run(load(repo)).findings if f.severity == "warn"}
    assert "story-covers-no-seed" not in warns


def test_a_story_that_covers_no_seed_in_a_seeded_epic_is_flagged(repo: Path):
    write(epics_root() / EPIC_A / "epic.md", epic_md(
        EPIC_A, "epic-a", slug="epic-a",
        seeds=[("seed-a1", "researched", "first")],
        stories=[("01-foo", "Foo", [], FOO_ID)],
    ))
    report = doctor.run(load(repo))
    errors = [f for f in report.findings if f.severity == "error"]
    assert "story-covers-no-seed" in {f.code for f in errors}
    finding = next(f for f in errors if f.code == "story-covers-no-seed")
    assert finding.ref == "01-foo"


def test_an_active_seed_with_no_layers_bullet_is_flagged_unclassified(repo: Path):
    """`epic_md` never writes a `layers:` bullet, so any active (non-inactive-status) seed it builds already satisfies `not s.layers` — seed-a1 ("researched") in the base `repo` fixture is exactly this shape."""
    report = doctor.run(load(repo))
    warns = [f for f in report.findings if f.severity == "warn"]
    assert "unclassified-seed" in {f.code for f in warns}
    finding = next(f for f in warns if f.code == "unclassified-seed" and f.ref == "seed-a1")
    assert finding.suggestion is not None and "seed-a1" in finding.suggestion


def test_epic_filter_scopes_findings(repo: Path):
    report = doctor.run(load(repo), epic_filter="epic-b")
    assert all(f.epic in (EPIC_B,) for f in report.findings)


def test_template_kind_instance_missing_type_is_flagged(repo: Path):
    write(repo / ".agents/templates.yml", """
research:
  title: Research
  kinds:
    - name: program
      doc_root: research
      default_path: specs
      path_template: "{name}/program.md"
      required: [type, title]
""")
    write(repo / "specs/SMCNv3/program.md", "---\ntitle: SMCNv3\n---\n# SMCNv3\n")
    assert "missing-type" in codes(doctor.run(load(repo)))



def _unwritten(root: Path) -> list:
    return [f for f in doctor.run(load(root)).findings if f.code == "unwritten-story"]


def _story_file(root: Path, slug: str) -> Path:
    return present(present(load(root).story_by_slug(slug))[1].story_md)


def _scaffolded(root: Path, slugs: list[str]) -> str:
    """Scaffold the stories under a fresh epic; return its directory name, which is its id."""
    write_prefix(root)
    epic_dir = crud.create_epic(load(root), "billing", "Billing").entity_name
    for slug in slugs:
        crud.create_story(load(root), "billing", slug, slug.title())
    return epic_dir


def test_every_unwritten_story_is_named_with_its_empty_sections(tmp_path: Path):
    epic_dir = _scaffolded(tmp_path, ["01-a", "02-b", "03-c"])

    found = _unwritten(tmp_path)

    assert [f.ref for f in found] == ["01-a", "02-b", "03-c"], "one finding per story, not one summary"
    assert all(f.severity == "error" for f in found)
    assert all(f.epic == epic_dir for f in found)
    assert "Context (empty), Acceptance Criteria (empty)" in found[0].message
    assert found[0].path == str(_story_file(tmp_path, "01-a"))


def test_an_old_story_is_unwritten_for_the_sections_it_never_had(tmp_path: Path):
    """No frontmatter exempts a document from the contract — there is only one, and it is the table."""
    _scaffolded(tmp_path, ["01-a"])
    story_md = _story_file(tmp_path, "01-a")
    text = story_md.read_text(encoding="utf-8")
    start = text.index("## Non-Functional Acceptance Criteria")
    end = text.index("## Implementation Status")
    text = text[:start] + text[end:]
    text = text.replace("## Context\n", "## Context\n\nLegacy context.\n")
    text = text.replace("## Acceptance Criteria\n", "## Acceptance Criteria\n\n- It works.\n")
    story_md.write_text(text, encoding="utf-8")

    found = _unwritten(tmp_path)
    assert len(found) == 1
    assert "Non-Functional Acceptance Criteria (missing)" in found[0].message
    assert "Technical Notes (missing)" in found[0].message


def test_a_partially_written_story_names_only_the_empty_section(tmp_path: Path):
    _scaffolded(tmp_path, ["01-a"])
    story_md = _story_file(tmp_path, "01-a")
    story_md.write_text(
        story_md.read_text(encoding="utf-8").replace(
            "## Context\n", "## Context\n\n- the operator needs a daily total\n"),
        encoding="utf-8",
    )

    found = _unwritten(tmp_path)
    assert len(found) == 1
    assert "Acceptance Criteria (empty)" in found[0].message
    assert "Context" not in found[0].message


def test_a_section_the_story_predates_is_reported_missing_not_empty(tmp_path: Path):
    """A story written before a section was required has no heading to write under, and reporting that as "empty" sends the reader looking for prose that has nowhere to go."""
    _scaffolded(tmp_path, ["01-a"])
    story_md = _story_file(tmp_path, "01-a")
    body = story_md.read_text(encoding="utf-8")
    start = body.index("## Dependencies")
    story_md.write_text(body[:start] + body[body.index("## Context") :], encoding="utf-8")

    found = _unwritten(tmp_path)

    assert len(found) == 1
    assert "Dependencies (missing)" in found[0].message


def test_story_status_mismatch_is_flagged(repo: Path):
    story = epics_root() / FOO_STORY
    story.write_text(
        story.read_text(encoding="utf-8").replace(
            "- **Status**: Not started", "- **Status**: QA passed"),
        encoding="utf-8",
    )

    report = doctor.run(load(repo))

    assert "story-status-mismatch" in codes(report)


def test_missing_milestones_directory_does_not_fail(repo: Path):
    report = doctor.run(load(repo))

    assert not any(f.code.startswith("milestone") for f in report.findings)
    assert "epic-without-milestone" not in codes(report)


def test_an_epic_assigned_to_no_milestone_is_flagged(repo: Path):
    write(milestones_root(repo) / "foundation/milestone.md", """---
type: milestone
id: m0
title: Foundation
status: proposed
dependsOn: []
epics:
  - epic-a
---
# Foundation
""")

    report = doctor.run(load(repo))

    assert "epic-without-milestone" in codes(report)
    finding = next(f for f in report.findings if f.code == "epic-without-milestone")
    assert finding.ref == EPIC_B


def test_an_epic_another_repo_minted_is_left_to_that_repo(repo: Path):
    write(milestones_root(repo) / "foundation/milestone.md", _foundation_owning(EPIC_A))
    write_prefix(repo, "t")
    assert "epic-without-milestone" in codes(doctor.run(load(repo)))

    write_prefix(repo, "u")
    report = doctor.run(load(repo))
    scoped = doctor.run(load(repo), epic_filter=EPIC_B)

    assert "epic-without-milestone" not in codes(report)
    assert not any(f.epic in {EPIC_A, EPIC_B} for f in report.findings)
    assert [(f.severity, f.code) for f in scoped.findings] == [("warn", "foreign-epic")]
    assert "`t`" in scoped.findings[0].message and "`u`" in scoped.findings[0].message


def _foundation_owning(*epics: str) -> str:
    listed = "".join(f"  - {epic}\n" for epic in epics)
    return (
        "---\ntype: milestone\nid: m0\ntitle: Foundation\nstatus: proposed\n"
        f"dependsOn: []\nepics:\n{listed}---\n\n# Foundation\n"
    )


def test_an_epic_of_filed_follow_ups_needs_no_milestone(repo: Path):
    write_prefix(repo)
    write(milestones_root(repo) / "foundation/milestone.md", _foundation_owning("epic-a", "epic-b"))
    assert crud.create_epic(load(repo), "fixes", "Filed fixes", followups=True).ok
    loose = crud.create_epic(load(repo), "loose", "Loose")
    assert loose.ok

    report = doctor.run(load(repo))

    unowned = [f.ref for f in report.findings if f.code == "epic-without-milestone"]
    assert unowned == [loose.entity_id], unowned


def test_a_milestone_listing_the_epic_of_filed_follow_ups_is_flagged(repo: Path):
    write_prefix(repo)
    fixes = crud.create_epic(load(repo), "fixes", "Filed fixes", followups=True)
    assert fixes.ok
    write(milestones_root(repo) / "foundation/milestone.md",
          _foundation_owning("epic-a", "epic-b", "fixes"))

    report = doctor.run(load(repo))

    finding = next(f for f in report.findings if f.code == "followups-epic-in-milestone")
    assert finding.severity == "error"
    assert finding.ref == fixes.entity_id


def test_a_milestone_depending_on_an_unknown_milestone_is_flagged(repo: Path):
    write(milestones_root(repo) / "foundation/milestone.md", """---
type: milestone
id: m0
title: Foundation
status: proposed
dependsOn:
  - no-such-milestone
epics:
  - epic-a
  - epic-b
---
# Foundation
""")

    report = doctor.run(load(repo))

    assert "dangling-milestone-dependency" in codes(report)
    finding = next(f for f in report.findings if f.code == "dangling-milestone-dependency")
    assert finding.ref == "no-such-milestone"


def test_a_milestone_listing_an_unknown_epic_is_flagged(repo: Path):
    write(milestones_root(repo) / "foundation/milestone.md", """---
type: milestone
id: m0
title: Foundation
status: proposed
dependsOn: []
epics:
  - epic-a
  - epic-b
  - epic-ghost
---
# Foundation
""")

    report = doctor.run(load(repo))

    assert "dangling-milestone-epic" in codes(report)
    finding = next(f for f in report.findings if f.code == "dangling-milestone-epic")
    assert finding.ref == "epic-ghost"


def test_backlog_item_cannot_belong_to_multiple_milestones(repo: Path):
    source_item = "ACME-01JBXR7K9QZ4M2T8VNF3HD6PWC"
    for name in ("first", "second"):
        write(milestones_root(repo) / f"{name}/milestone.md", f"""---
type: milestone
id: {name}
title: {name.title()}
status: proposed
dependsOn: []
sourceItems:
  - {source_item}
epics: []
---
# {name.title()}
""")

    report = doctor.run(load(repo))

    assert "backlog-item-in-multiple-milestones" in codes(report)



def test_a_recorded_conflict_is_an_error_on_the_story_until_cleared(repo: Path):
    def conflicts() -> list:
        return [f for f in doctor.run(load(repo)).findings if f.code == "story-conflict"]

    assert conflicts() == []
    crud.set_conflict(load(repo), FOO_ID, "AC2 wants a modal, AC4 forbids one")
    found = conflicts()
    assert len(found) == 1 and found[0].severity == "error"
    assert found[0].epic == EPIC_A and found[0].ref == "01-foo"
    assert "AC2 wants a modal" in found[0].message
    assert f"ostler conflict {FOO_ID} --clear" in found[0].suggestion
    crud.set_conflict(load(repo), FOO_ID, "")
    assert conflicts() == []


@pytest.mark.parametrize("name", ["ostler.yml", "agents.yml"])
def test_a_doc_roots_key_in_the_organization_config_is_flagged_as_removed(repo: Path, name: str):
    write(repo / name, "organization:\n  docRoots:\n    epics: docs/plans\n")

    report = doctor.run(load(repo))
    finding = next(f for f in report.findings if f.code == "removed-doc-roots")
    assert finding.severity == "error"
    assert "docRoots" in finding.message
    assert not (repo / "docs/plans").exists()
    assert load(repo).doc_roots["epics"] == epics_root()


def test_no_doc_roots_key_means_no_removed_doc_roots_finding(repo: Path):
    write(repo / "ostler.yml", "organization:\n  name: demo\n")

    assert "removed-doc-roots" not in codes(doctor.run(load(repo)))


def test_missing_type_is_flagged(repo: Path):
    write(specs_root() / "01-x/plan.md", "# Plan\n")
    assert "missing-type" in codes(doctor.run(load(repo)))


def test_writing_the_sections_clears_the_finding(tmp_path: Path):
    _scaffolded(tmp_path, ["01-a"])
    story_md = _story_file(tmp_path, "01-a")
    story_md.write_text(
        story_md.read_text(encoding="utf-8")
        .replace("## Context\n", "## Context\n\n- the operator needs a daily total\n")
        .replace("## Acceptance Criteria\n",
                 "## Acceptance Criteria\n\n- The page shows one row per day.\n")
        .replace("## Non-Functional Acceptance Criteria\n",
                 "## Non-Functional Acceptance Criteria\n\n- Existing exports remain unchanged.\n")
        .replace("## Technical Notes\n",
                 "## Technical Notes\n\n- `legacy/report.py::daily_rows` defines the prior mechanic.\n"),
        encoding="utf-8",
    )

    assert _unwritten(tmp_path) == []


def test_milestone_files_assign_epics(repo: Path):
    write(milestones_root(repo) / "foundation/milestone.md", """---
type: milestone
id: m0
title: Foundation
status: proposed
dependsOn: []
epics:
  - epic-a
---
# Foundation
""")
    write(milestones_root(repo) / "feature/milestone.md", """---
type: milestone
id: m1
title: Feature
status: proposed
dependsOn:
  - m0
epics:
  - epic-b
---
# Feature
""")

    graph = load(repo)
    report = doctor.run(graph)

    assert {m.eid for m in graph.milestones} == {"m0", "m1"}
    assert "epic-without-milestone" not in codes(report)


def test_an_epic_assigned_to_two_milestones_at_once_is_flagged(repo: Path):
    write(milestones_root(repo) / "foundation/milestone.md", """---
type: milestone
id: m0
title: Foundation
status: proposed
dependsOn: []
epics:
  - epic-a
---
# Foundation
""")
    write(milestones_root(repo) / "feature/milestone.md", """---
type: milestone
id: m1
title: Feature
status: proposed
dependsOn: []
epics:
  - epic-a
  - epic-b
---
# Feature
""")

    report = doctor.run(load(repo))

    assert "epic-in-multiple-milestones" in codes(report)
    finding = next(f for f in report.findings if f.code == "epic-in-multiple-milestones")
    assert finding.ref == EPIC_A
    assert "foundation" in finding.message and "feature" in finding.message


def test_path_scope_keeps_only_that_files_findings():
    one = doctor.Finding("error", "missing-type", "m", path="docs/specs/a/rec.md")
    two = doctor.Finding("error", "missing-type", "m", path="docs/specs/a/rec2.md")
    report = doctor.Report(org="acme", profile="full", findings=[one, two])

    root = Path("/repo")
    assert doctor.scope_to_paths(report, root, [root / "docs/specs/a/rec.md"]).findings == [one]
    assert doctor.scope_to_paths(report, root, [root / "docs/specs/a"]).findings == [one, two]


def test_path_scope_keeps_a_group_finding_through_its_related_member():
    member = doctor.Finding("warn", "schema", "m", path="docs/specs/a.md", related=["docs/specs/b.md#node-b"])
    other = doctor.Finding("warn", "schema", "m", path="docs/specs/c.md")
    report = doctor.Report(org="acme", profile="full", findings=[member, other])

    root = Path("/repo")
    assert doctor.scope_to_paths(report, root, [root / "docs/specs/b.md"]).findings == [member]
