from __future__ import annotations

from pathlib import Path

import pytest

from ostler import doctor
from ostler.model import load

from conftest import epic_md, story_md, write

FOO_STORY = "docs/epics/epic-a/stories/01-foo/story.md"


def codes(report):
    return {f.code for f in report.findings if f.severity == "error"}


def test_clean_repo_has_no_errors(repo: Path):
    report = doctor.run(load(repo))
    assert report.errors == 0, [f.message for f in report.findings if f.severity == "error"]
    assert report.profile == "full"
    assert {e["dir"] for e in report.epics} == {"epic-a", "epic-b"}


def test_cross_epic_seed_reference_is_flagged(repo: Path):
    # Point epic-a's story at a seed that belongs to epic-b.
    write(repo / "docs/epics/epic-a/epic.md", epic_md(
        "t-1", "epic-a",
        seeds=[("seed-a1", "researched", "first"), ("seed-a2", "resolved", "done")],
        stories=[("01-foo", "Foo", ["seed-b1"])],
    ))

    report = doctor.run(load(repo))
    assert "cross-epic-seed" in codes(report)
    # seed-a1 is now uncovered -> orphan
    assert "orphan-seed" in codes(report)
    assert report.errors  # non-zero exit


def test_blocker_naming_no_story_is_flagged(repo: Path):
    write(repo / FOO_STORY, story_md("01-foo", "Foo", "Not started", depends=["no-such-story"]))
    assert "dangling-dependency" in codes(doctor.run(load(repo)))


def test_blocker_in_another_epic_is_flagged(repo: Path):
    write(repo / FOO_STORY, story_md("01-foo", "Foo", "Not started", depends=["01-bar"]))
    assert "cross-epic-dependency" in codes(doctor.run(load(repo)))


def test_story_key_collision_is_flagged_and_lookup_is_ambiguous(repo: Path):
    first = repo / FOO_STORY
    second = repo / "docs/epics/epic-b/stories/01-bar/story.md"
    for path in (first, second):
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "slug:", "externalKey: TEAM-123\nslug:"
            ),
            encoding="utf-8",
        )

    graph = load(repo)
    findings = [
        f for f in doctor.run(graph).findings if f.code == "story-key-collision"
    ]

    assert [finding.ref for finding in findings] == ["TEAM-123"]
    assert "01-foo/story.md" in findings[0].message
    assert "01-bar/story.md" in findings[0].message
    with pytest.raises(ValueError, match="ambiguous"):
        graph.find_story("TEAM-123")


def test_story_id_mismatch_between_epic_and_story_is_flagged(tmp_path: Path):
    write(
        tmp_path / "docs/epics/e/epic.md",
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
        tmp_path / "docs/epics/e/stories/a/story.md",
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
    """The guard against a silent rewrite: story.md is agent-written, and a body turned into
    prose empties the DAG with nothing else reporting it."""
    text = story_md("01-foo", "Foo", "Not started", depends=["01-bar"])
    write(repo / FOO_STORY, text.replace("- Blocked by: 01-bar", "- Needs: 01-bar"))

    findings = [f for f in doctor.run(load(repo)).findings
                if f.code == "malformed-dependency-bullet"]

    assert [f.ref for f in findings] == ["01-foo"]
    assert "Needs: 01-bar" in findings[0].message


def test_resolved_seed_not_required_to_be_covered(repo: Path):
    # seed-a2 is resolved and covered by nobody -> must NOT be an orphan error.
    report = doctor.run(load(repo))
    assert "orphan-seed" not in codes(report)


def test_feature_records_parsed(repo: Path):
    graph = load(repo)
    features = {r.key for r in graph.features}
    assert {"area/rec", "area/rec2"} <= features


def test_missing_type_is_flagged(repo: Path):
    # a feature Concept without `type` violates OKF conformance
    write(repo / "docs/features/area/rec.md",
          "---\nslug: rec\ntitle: Rec\n---\n# rec\n\nbody\n")
    assert "okf-missing-type" in codes(doctor.run(load(repo)))


def test_a_concept_inserted_mid_file_reparents_its_neighbours_fields(repo: Path):
    """The failure this catches is invisible in the rendered page: a new `## concept:` written
    directly above an existing `### Fields` steals that block, and nothing else in the graph
    objects — the fields are still fields, just hanging off the wrong concept."""
    write(repo / "docs/features/area/rec.md", """---
type: concept
slug: rec
title: Rec
---
# rec

## concept: ManifestPage

## concept: SlugCollisionError

### Fields

- **code**: the collision code

### Fields

- **slug**: the page slug
""")

    findings = [f for f in doctor.run(load(repo)).findings
                if f.code == "duplicate-container-heading"]

    assert [f.ref for f in findings] == ["Fields"]
    assert findings[0].severity == "error"
    assert "concept: SlugCollisionError" in findings[0].message
    assert findings[0].path == "docs/features/area/rec.md"


def test_the_same_container_under_two_different_concepts_is_fine(repo: Path):
    write(repo / "docs/features/area/rec.md", """---
type: concept
slug: rec
title: Rec
---
# rec

## concept: ManifestPage

### Fields

- **slug**: the page slug

## concept: SlugCollisionError

### Fields

- **code**: the collision code
""")

    assert "duplicate-container-heading" not in codes(doctor.run(load(repo)))


def test_seedless_epic_no_covers_warning(repo: Path):
    # a wholly-seedless epic (globex-style) must not raise story-covers-no-seed
    write(repo / "docs/epics/epic-c/epic.md", epic_md(
        "t-3", "epic-c", seeds=[], stories=[("01-x", "X", [])]))
    write(repo / "docs/epics/epic-c/stories/01-x/story.md",
          "---\ntype: story\nslug: 01-x\nstatus: Not started\n---\n# Story: X\n")
    warns = {f.code for f in doctor.run(load(repo)).findings if f.severity == "warn"}
    assert "story-covers-no-seed" not in warns


def test_epic_filter_scopes_findings(repo: Path):
    report = doctor.run(load(repo), epic_filter="epic-b")
    assert all(f.epic in ("epic-b",) for f in report.findings)


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
    assert "okf-missing-type" in codes(doctor.run(load(repo)))


# --------------------------------------------------------------------------- #
# unwritten-story                                                             #
# --------------------------------------------------------------------------- #
#
# The surface that makes a half-authored book visible. Before it existed, a repo whose stories
# were all `ostler create story` scaffolds reported itself perfectly healthy — 0 errors on a
# book that said nothing — because every check the graph ran was satisfied by the file merely
# existing. These pin the finding down: one per unwritten story, naming which sections are
# empty, gone the moment they are written, and waivable when a stub is deliberate.

def _unwritten(root: Path) -> list:
    return [f for f in doctor.run(load(root)).findings if f.code == "unwritten-story"]


def _scaffolded(root: Path, slugs: list[str]) -> str:
    """Scaffold the stories under a fresh epic; return its numbered directory name."""
    from ostler import crud

    epic_dir = crud.create_epic(load(root), "billing", "Billing", prefix="acme").entity_name
    for slug in slugs:
        crud.create_story(load(root), "billing", slug, slug.title())
    return epic_dir


def test_every_unwritten_story_is_named_with_its_empty_sections(tmp_path: Path):
    epic_dir = _scaffolded(tmp_path, ["01-a", "02-b", "03-c"])

    found = _unwritten(tmp_path)

    assert [f.ref for f in found] == ["01-a", "02-b", "03-c"], "one finding per story, not one summary"
    assert all(f.severity == "error" for f in found)
    assert all(f.epic == epic_dir for f in found)
    # Which sections are empty is the actionable part — "unwritten" alone does not say what to write.
    assert "Context (empty), Acceptance Criteria (empty)" in found[0].message
    # And it is located: a finding without a path cannot be opened from a report.
    assert found[0].path == f"docs/epics/{epic_dir}/stories/01-a/story.md"


def test_writing_the_sections_clears_the_finding(tmp_path: Path):
    epic_dir = _scaffolded(tmp_path, ["01-a"])
    story_md = tmp_path / f"docs/epics/{epic_dir}/stories/01-a/story.md"
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


def test_legacy_story_without_shape_version_keeps_the_original_contract(tmp_path: Path):
    epic_dir = _scaffolded(tmp_path, ["01-a"])
    story_md = tmp_path / f"docs/epics/{epic_dir}/stories/01-a/story.md"
    text = story_md.read_text(encoding="utf-8")
    text = text.replace("storyShape: 2\n", "")
    start = text.index("## Non-Functional Acceptance Criteria")
    end = text.index("## Implementation Status")
    text = text[:start] + text[end:]
    text = text.replace("## Context\n", "## Context\n\nLegacy context.\n")
    text = text.replace("## Acceptance Criteria\n", "## Acceptance Criteria\n\n- It works.\n")
    story_md.write_text(text, encoding="utf-8")

    assert _unwritten(tmp_path) == []


def test_a_partially_written_story_names_only_the_empty_section(tmp_path: Path):
    # Half-written is the state a rerun resumes into, so it must be reported as precisely as
    # a fresh scaffold — otherwise an author run that stopped mid-story looks finished.
    epic_dir = _scaffolded(tmp_path, ["01-a"])
    story_md = tmp_path / f"docs/epics/{epic_dir}/stories/01-a/story.md"
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
    """A story written before a section was required has no heading to write under, and
    reporting that as "empty" sends the reader looking for prose that has nowhere to go.
    The two states need different repairs, so the finding has to tell them apart."""
    epic_dir = _scaffolded(tmp_path, ["01-a"])
    story_md = tmp_path / f"docs/epics/{epic_dir}/stories/01-a/story.md"
    body = story_md.read_text(encoding="utf-8")
    start = body.index("## Dependencies")
    story_md.write_text(body[:start] + body[body.index("## Context") :], encoding="utf-8")

    found = _unwritten(tmp_path)

    assert len(found) == 1
    assert "Dependencies (missing)" in found[0].message


def test_a_waiver_downgrades_an_unwritten_story_without_hiding_it(tmp_path: Path):
    """A deliberately-stubbed story is waivable — explicitly, with a reason, and still visible.

    That is the difference from the old behaviour: the stub was accepted *silently*, by
    accident, with nothing recorded anywhere that a human could review.
    """
    from ostler import waivers

    _scaffolded(tmp_path, ["01-a", "02-b"])
    waivers.add(load(tmp_path), "unwritten-story", "01-a",
                "placeholder for scope agreed with the operator; body lands next run",
                "fill-01-a")

    found = _unwritten(tmp_path)
    waived = {f.ref: f for f in found}
    assert set(waived) == {"01-a", "02-b"}, "a waived finding stays in the report"
    assert waived["01-a"].severity == "warn" and waived["01-a"].waived
    assert "fill-01-a" in waived["01-a"].message
    assert waived["02-b"].severity == "error", "the waiver is scoped to the ref it names"


def test_story_status_mismatch_is_flagged(repo: Path):
    story = repo / "docs/epics/epic-a/stories/01-foo/story.md"
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


def test_milestone_files_assign_epics(repo: Path):
    write(repo / "docs/milestones/foundation.md", """---
type: milestone
id: m0
title: Foundation
status: planned
dependsOn: []
epics:
  - epic-a
---
# Foundation
""")
    write(repo / "docs/milestones/feature.md", """---
type: milestone
id: m1
title: Feature
status: planned
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


def test_backlog_item_cannot_belong_to_multiple_milestones(repo: Path):
    source_item = "ACME-01JBXR7K9QZ4M2T8VNF3HD6PWC"
    for name in ("first", "second"):
        write(repo / f"docs/milestones/{name}.md", f"""---
type: milestone
id: {name}
title: {name.title()}
status: planned
dependsOn: []
sourceItems:
  - {source_item}
epics: []
---
# {name.title()}
""")

    report = doctor.run(load(repo))

    assert "backlog-item-in-multiple-milestones" in codes(report)
