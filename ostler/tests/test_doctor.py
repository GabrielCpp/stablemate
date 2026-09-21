from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

from ostler import crud, doctor
from ostler.cli import main
from ostler.model import load
from ostler.qa import compile as compile_mod
from ostler.qa.context import build_context

from conftest import epic_md, screen_md, story_md, write

FOO_STORY = "docs/epics/epic-a/stories/01-foo/story.md"


def codes(report):
    return {f.code for f in report.findings if f.severity == "error"}


def _git_track(root: Path) -> None:
    """Init a repo at *root* and stage everything in it — `git ls-files` reads the index, not a commit, so staging alone is enough for `misplaced-book-page`'s enumeration."""
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)


def test_clean_repo_has_no_errors(repo: Path):
    report = doctor.run(load(repo))
    assert report.errors == 0, [f.message for f in report.findings if f.severity == "error"]
    assert report.profile == "full"
    assert {e["dir"] for e in report.epics} == {"epic-a", "epic-b"}


def test_a_typed_page_outside_every_doc_root_is_flagged_as_misplaced(repo: Path):
    """A real book page (a declared `type:`) that a move -- or a first draft -- leaves outside `docs/features`, `docs/epics`, `docs/milestones`, `docs/roadmaps`, `docs/specs` and `docs/backlog.md` is invisible to every other check: it is not `okf-missing-type` (it has a type), and nothing walks in to find it, since every book-facing check is rooted at `graph.doc_roots`."""
    write(repo / "notes/orphan-concept.md",
          "---\ntype: concept\ntitle: Orphan\n---\n# Orphan\n\nStray content.\n")
    _git_track(repo)

    report = doctor.run(load(repo))
    assert "misplaced-book-page" in codes(report)
    finding = next(f for f in report.findings if f.code == "misplaced-book-page")
    assert finding.path == "notes/orphan-concept.md"
    assert finding.severity == "error"
    assert "concept" in finding.message


def test_typed_pages_under_the_configured_doc_roots_are_not_misplaced(repo: Path):
    """The predicate is "outside every doc root", never "outside `docs/features`" alone -- real `epic`/`story`/`spec.*` pages that sit under one of the *other* doc roots must not be flagged, even once git tracking makes the new check actually run."""
    write(repo / "docs/specs/plan.md",
          "---\ntype: spec.plan\ntitle: Plan\n---\n# Plan\n\nBody.\n")
    _git_track(repo)

    report = doctor.run(load(repo))
    assert "misplaced-book-page" not in codes(report)


def test_typed_pages_inside_a_nested_book_are_not_misplaced(repo: Path):
    """A subtree with its own `docs/` (a paddock app under `paddock/data/apps/<app>/` is exactly this shape) is a book of its own -- `model.find_root` resolves it as its own root, with its own `doc_roots`, the moment ostler is pointed at it directly."""
    write(repo / "vendor/widgets-app/docs/epics/epic-x/epic.md",
          "---\ntype: epic\ntitle: Widgets\n---\n# Widgets\n\nBody.\n")
    _git_track(repo)

    report = doctor.run(load(repo))
    assert "misplaced-book-page" not in codes(report)


def test_misplaced_book_page_emits_nothing_outside_a_git_repository(repo: Path):
    """The corpus's standing core property -- git-tracked -- is undetermined when `graph.root` is not inside a git repository at all, and the rule for an undetermined property is silence, never a filesystem walk that would sweep `.venv`/build output and invent findings."""
    write(repo / "notes/orphan-concept.md",
          "---\ntype: concept\ntitle: Orphan\n---\n# Orphan\n\nStray content.\n")

    report = doctor.run(load(repo))
    assert "misplaced-book-page" not in codes(report)


def test_a_spec_typed_page_under_features_is_flagged_as_misrooted(repo: Path):
    """`spec.*` is registered under `docs/specs`, not `docs/features` -- and unlike a page outside every root, a `spec.qa-okf-context.md` dropped under `docs/features` (the shape `ostler qa context` writing its scratch output to the wrong directory would produce) IS under a doc root, so `misplaced-book-page` never fires."""
    write(repo / "docs/features/area/scratch.md",
          "---\ntype: spec.qa-okf-context\ntitle: Scratch\n---\n# Scratch\n\n"
          "## Changed Code\n\n- `a.py` (modified): foo\n")
    _git_track(repo)

    report = doctor.run(load(repo))
    assert "misrooted-book-page" in codes(report)
    finding = next(f for f in report.findings if f.code == "misrooted-book-page")
    assert finding.path == "docs/features/area/scratch.md"
    assert finding.severity == "error"
    assert "spec.qa-okf-context" in finding.message
    assert "specs" in finding.message


def test_typed_pages_under_their_own_registered_root_are_not_misrooted(repo: Path):
    """The predicate is "inside a doc root that disagrees with the type", never "inside any doc root but `docs/features`" -- a real `spec.*` page under `docs/specs` (its registered home) must not be flagged."""
    write(repo / "docs/specs/plan/plan.md",
          "---\ntype: spec.plan\ntitle: Plan\n---\n# Plan\n\nBody.\n")
    _git_track(repo)

    report = doctor.run(load(repo))
    assert "misrooted-book-page" not in codes(report)


def test_a_ui_typed_page_outside_features_is_flagged_as_misrooted(repo: Path):
    """The reverse direction: a book page whose type belongs under `features`, filed elsewhere."""
    write(repo / "docs/specs/area/stray.md",
          "---\ntype: screen\ntitle: Stray\n---\n# Stray\n\n- route: /stray\n")
    _git_track(repo)

    report = doctor.run(load(repo))
    finding = next(f for f in report.findings if f.code == "misrooted-book-page")
    assert finding.path == "docs/specs/area/stray.md"
    assert "features" in finding.message
    assert "specs" in finding.message


def test_a_ui_typed_page_under_features_is_not_misrooted(repo: Path):
    """Every `UINodeType`'s registered root is `features`, so an ordinary screen is clean."""
    write(repo / "docs/features/web/ok.md",
          "---\ntype: screen\ntitle: Ok\n---\n# Ok\n\n- route: /ok\n")
    _git_track(repo)

    report = doctor.run(load(repo))
    assert "misrooted-book-page" not in codes(report)


def test_cross_epic_seed_reference_is_flagged(repo: Path):
    write(repo / "docs/epics/epic-a/epic.md", epic_md(
        "t-1", "epic-a",
        seeds=[("seed-a1", "researched", "first"), ("seed-a2", "resolved", "done")],
        stories=[("01-foo", "Foo", ["seed-b1"])],
    ))

    report = doctor.run(load(repo))
    assert "cross-epic-seed" in codes(report)
    assert "orphan-seed" in codes(report)
    assert report.errors


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
    """The guard against a silent rewrite: story.md is agent-written, and a body turned into prose empties the DAG with nothing else reporting it."""
    text = story_md("01-foo", "Foo", "Not started", depends=["01-bar"])
    write(repo / FOO_STORY, text.replace("- Blocked by: 01-bar", "- Needs: 01-bar"))

    findings = [f for f in doctor.run(load(repo)).findings
                if f.code == "malformed-dependency-bullet"]

    assert [f.ref for f in findings] == ["01-foo"]
    assert "Needs: 01-bar" in findings[0].message


def test_resolved_seed_not_required_to_be_covered(repo: Path):
    report = doctor.run(load(repo))
    assert "orphan-seed" not in codes(report)


def test_a_story_covering_a_seed_id_unknown_to_the_whole_book_is_flagged(repo: Path):
    """Unlike `cross-epic-seed` (the id belongs to a sibling epic), `dangling-seed` is what fires when no epic anywhere claims the id at all."""
    write(repo / "docs/epics/epic-a/epic.md", epic_md(
        "t-1", "epic-a",
        seeds=[("seed-a1", "researched", "first"), ("seed-a2", "resolved", "done")],
        stories=[("01-foo", "Foo", ["seed-ghost"])],
    ))
    report = doctor.run(load(repo))
    assert "dangling-seed" in codes(report)
    finding = next(f for f in report.findings if f.code == "dangling-seed")
    assert finding.ref == "seed-ghost"


def test_a_story_named_in_the_epic_with_no_story_file_on_disk_is_flagged(repo: Path):
    write(repo / "docs/epics/epic-a/epic.md", epic_md(
        "t-1", "epic-a",
        seeds=[("seed-a1", "researched", "first")],
        stories=[("01-foo", "Foo", ["seed-a1"]), ("02-ghost", "Ghost", [])],
    ))
    report = doctor.run(load(repo))
    assert "missing-story-file" in codes(report)
    finding = next(f for f in report.findings if f.code == "missing-story-file")
    assert finding.ref == "02-ghost"


def test_feature_records_parsed(repo: Path):
    graph = load(repo)
    features = {r.key for r in graph.features}
    assert {"area/rec", "area/rec2"} <= features


def test_missing_type_is_flagged(repo: Path):
    write(repo / "docs/features/area/rec.md",
          "---\nslug: rec\ntitle: Rec\n---\n# rec\n\nbody\n")
    assert "okf-missing-type" in codes(doctor.run(load(repo)))


def test_a_concept_inserted_mid_file_reparents_its_neighbours_fields(repo: Path):
    """The failure this catches is invisible in the rendered page: a new `## concept:` written directly above an existing `### Fields` steals that block, and nothing else in the graph objects — the fields are still fields, just hanging off the wrong concept."""
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
    write(repo / "docs/epics/epic-c/epic.md", epic_md(
        "t-3", "epic-c", seeds=[], stories=[("01-x", "X", [])]))
    write(repo / "docs/epics/epic-c/stories/01-x/story.md",
          "---\ntype: story\nslug: 01-x\nstatus: Not started\n---\n# Story: X\n")
    warns = {f.code for f in doctor.run(load(repo)).findings if f.severity == "warn"}
    assert "story-covers-no-seed" not in warns


def test_a_story_that_covers_no_seed_in_a_seeded_epic_is_flagged(repo: Path):
    write(repo / "docs/epics/epic-a/epic.md", epic_md(
        "t-1", "epic-a",
        seeds=[("seed-a1", "researched", "first")],
        stories=[("01-foo", "Foo", [])],
    ))
    report = doctor.run(load(repo))
    warns = [f for f in report.findings if f.severity == "warn"]
    assert "story-covers-no-seed" in {f.code for f in warns}
    finding = next(f for f in warns if f.code == "story-covers-no-seed")
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



def _unwritten(root: Path) -> list:
    return [f for f in doctor.run(load(root)).findings if f.code == "unwritten-story"]


def _scaffolded(root: Path, slugs: list[str]) -> str:
    """Scaffold the stories under a fresh epic; return its numbered directory name."""
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
    assert "Context (empty), Acceptance Criteria (empty)" in found[0].message
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


def test_an_old_story_is_unwritten_for_the_sections_it_never_had(tmp_path: Path):
    """No frontmatter exempts a document from the contract — there is only one, and it is the table."""
    epic_dir = _scaffolded(tmp_path, ["01-a"])
    story_md = tmp_path / f"docs/epics/{epic_dir}/stories/01-a/story.md"
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
    """A story written before a section was required has no heading to write under, and reporting that as "empty" sends the reader looking for prose that has nowhere to go."""
    epic_dir = _scaffolded(tmp_path, ["01-a"])
    story_md = tmp_path / f"docs/epics/{epic_dir}/stories/01-a/story.md"
    body = story_md.read_text(encoding="utf-8")
    start = body.index("## Dependencies")
    story_md.write_text(body[:start] + body[body.index("## Context") :], encoding="utf-8")

    found = _unwritten(tmp_path)

    assert len(found) == 1
    assert "Dependencies (missing)" in found[0].message


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


def test_an_epic_assigned_to_no_milestone_is_flagged(repo: Path):
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

    report = doctor.run(load(repo))

    assert "epic-without-milestone" in codes(report)
    finding = next(f for f in report.findings if f.code == "epic-without-milestone")
    assert finding.ref == "epic-b"


def test_a_milestone_depending_on_an_unknown_milestone_is_flagged(repo: Path):
    write(repo / "docs/milestones/foundation.md", """---
type: milestone
id: m0
title: Foundation
status: planned
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
    write(repo / "docs/milestones/foundation.md", """---
type: milestone
id: m0
title: Foundation
status: planned
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


def test_an_epic_assigned_to_two_milestones_at_once_is_flagged(repo: Path):
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
    assert finding.ref == "epic-a"
    assert "foundation" in finding.message and "feature" in finding.message


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



def test_a_recorded_conflict_is_an_error_on_the_story_until_cleared(repo: Path):
    def conflicts() -> list:
        return [f for f in doctor.run(load(repo)).findings if f.code == "story-conflict"]

    assert conflicts() == []
    crud.set_conflict(load(repo), "01-foo", "AC2 wants a modal, AC4 forbids one")
    found = conflicts()
    assert len(found) == 1 and found[0].severity == "error"
    assert found[0].epic == "epic-a" and found[0].ref == "01-foo"
    assert "AC2 wants a modal" in found[0].message
    assert "ostler conflict 01-foo --clear" in found[0].suggestion
    crud.set_conflict(load(repo), "01-foo", "")
    assert conflicts() == []


def test_path_scope_keeps_only_that_files_findings(repo: Path):
    write(repo / "docs/features/area/rec.md", "---\nslug: rec\ntitle: Rec\n---\n# rec\n\nbody\n")
    write(repo / "docs/features/area/rec2.md", "---\nslug: rec2\ntitle: Rec2\n---\n# rec2\n\nbody\n")
    report = doctor.run(load(repo))
    assert {f.path for f in report.findings if f.code == "okf-missing-type"} >= {
        "docs/features/area/rec.md", "docs/features/area/rec2.md"}

    scoped = doctor.scope_to_paths(report, ["docs/features/area/rec.md"])

    assert scoped.findings
    assert {f.path for f in scoped.findings} == {"docs/features/area/rec.md"}
    assert {f.path for f in doctor.scope_to_paths(report, ["docs/features/area/"]).findings} >= {
        "docs/features/area/rec.md", "docs/features/area/rec2.md"}


def test_path_scope_keeps_a_group_finding_through_its_related_member():
    member = doctor.Finding("warn", "same-as-disagreement", "m",
                            path="docs/features/a.md", related=["docs/features/b.md#node-b"])
    other = doctor.Finding("warn", "unparsed-check", "m", path="docs/features/c.md")
    report = doctor.Report(org="acme", profile="full", findings=[member, other])

    assert doctor.scope_to_paths(report, ["docs/features/b.md"]).findings == [member]


def test_path_scoped_doctor_leads_with_its_verdict_about_that_file(repo: Path, capsys):
    write(repo / "docs/features/area/rec.md", "---\nslug: rec\ntitle: Rec\n---\n# rec\n\nbody\n")

    main(["-C", str(repo), "doctor", "--no-index", "--path", "docs/features/area/rec.md"])

    out = capsys.readouterr().out
    first = out.splitlines()[0]
    assert first.endswith("in docs/features/area/rec.md") and "error(s)" in first
    assert "epic " not in out and "org:" not in out


def test_path_outside_the_book_is_refused_rather_than_reported_clean(repo: Path, capsys):
    write(repo / "notes/copy.md", "---\nslug: copy\ntitle: Copy\n---\n# copy\n\nbody\n")

    for path in ("notes/copy.md", "docs/features/area/missing.md"):
        assert main(["-C", str(repo), "doctor", "--no-index", "--path", path]) == 2
        captured = capsys.readouterr()
        assert "not a file of this book" in captured.err and not captured.out


def test_every_gap_kind_has_its_own_branch_in_the_doctor_bridge():
    """`gap_findings` names every kind `compile_plan` mints — no kind reaches the catch-all."""
    tree = ast.parse((Path(compile_mod.__file__)).read_text())
    minted = {
        node.args[1].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Gap"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
    }
    assert minted <= compile_mod.GAP_KINDS, minted - compile_mod.GAP_KINDS

    bridge = next(
        node for node in ast.walk(ast.parse(Path(doctor.__file__).read_text()))
        if isinstance(node, ast.FunctionDef) and node.name == "gap_findings"
    )
    branched = {
        node.comparators[0].value
        for node in ast.walk(bridge)
        if isinstance(node, ast.Compare) and isinstance(node.comparators[0], ast.Constant)
    }
    assert compile_mod.GAP_KINDS - branched == {"uncompilable-claim"}, (
        compile_mod.GAP_KINDS - branched
    )


def test_a_gap_kind_that_is_not_a_doctor_code_is_translated_not_passed_through():
    """`no-verify-declared` is the compiler's spelling; doctor's is `undeclared-obligation`."""
    oid = "okf:docs/features/demo/api.md#post-things:does:1"
    gap = compile_mod.Gap(oid, "no-verify-declared", "the book declares no check")

    [finding] = doctor.gap_findings([gap])

    assert (finding.severity, finding.code) == ("warn", "undeclared-obligation")


def test_a_when_guarded_gap_keeps_its_own_code_rather_than_undeclared_obligation():
    """`precondition-discharged-by-arrangement` is its own doctor code, not a second spelling of `undeclared-obligation`: the two name different defects."""
    oid = "okf:docs/features/demo/api.md#submit-widget:when:1"
    gap = compile_mod.Gap(
        oid, "precondition-discharged-by-arrangement",
        "this `when:` states a condition under which the node's claims hold, not an "
        "observable claim, so no check is expected to prove it",
    )

    [finding] = doctor.gap_findings([gap])

    assert (finding.severity, finding.code) == ("warn", "precondition-discharged-by-arrangement")


def test_undeclared_obligation_fires_per_bullet_even_when_the_node_declares_a_check(repo: Path):
    """SITE-GAP is per-obligation; SITE-BOOK's `declared` flag is node-wide."""
    write(repo / "docs/features/demo/publisher.md",
          "---\ntype: concept\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n- returns: the published revision\n"
          "- raises: `ManifestConflict` when the revision moved\n")
    book_only = doctor.run(load(repo))
    zero_check = next(f for f in book_only.findings if f.code == "undeclared-obligation")
    assert zero_check.ref == "docs/features/demo/publisher.md#publish#verify"

    (repo / "app").mkdir()
    source = repo / "app/service.py"
    source.write_text("def create_thing():\n    return 'old'\n", encoding="utf-8")
    write(repo / "docs/features/demo/api.md",
          "---\ntype: server\ntitle: Demo API\n---\n# Demo API\n\n"
          "- entry-url: http://localhost:8080\n\n"
          "## Endpoints\n\n### post-things\n"
          "- method: POST\n"
          "- path: /api/things\n"
          "- does:\n"
          "  - conflict: rejects a duplicate\n"
          '- verify: http_status(201, title="Created")\n'
          "- status: 201 on creation\n"
          "- code: app/service.py::create_thing\n")

    api_findings = [f for f in doctor.run(load(repo)).findings if f.path == "docs/features/demo/api.md"]
    assert "undeclared-obligation" not in {f.code for f in api_findings}

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "qa@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "QA"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    source.write_text("def create_thing():\n    return 'new'\n", encoding="utf-8")

    packet = build_context(repo, base=base, source_roots={"demo": ["app"]})
    result = compile_mod.compile_plan_gaps(packet, story="demo-story")

    no_verify = {g.obligation_id: g for g in result.gaps if g.kind == "no-verify-declared"}
    assert not any(":does:" in oid for oid in no_verify)
    status_id = next(oid for oid in no_verify if ":status:" in oid)
    gap = no_verify[status_id]

    [finding] = doctor.gap_findings([gap])
    assert (finding.severity, finding.code) == ("warn", "undeclared-obligation")
    assert re.match(r"^okf:.+:[a-z-]+:\d+$", finding.ref), finding.ref
    assert finding.ref == gap.obligation_id


def test_an_unparsed_fixture_gap_keeps_the_code_doctor_already_raises_for_that_bullet():
    """`_check_book_fixtures` raises `qa-fixture-bullet` on this bullet from the book alone."""
    oid = "okf:docs/features/demo/flows/add-a-thing.md:end-state"
    gap = compile_mod.Gap(oid, "unparsed-fixture", "this claim's arrangement could not be read")

    [finding] = doctor.gap_findings([gap])

    assert (finding.severity, finding.code) == ("error", "qa-fixture-bullet")
    assert finding.ref == oid


def test_an_unparsed_check_gap_keeps_the_code_doctor_already_raises_for_that_bullet():
    """`_check_ui` raises `unparsed-check` on this bullet from the book alone."""
    oid = "okf:docs/features/policy/gui/screens/policy-list.md#policy-table:contract"
    gap = compile_mod.Gap(oid, "unparsed-check-bullet", "this claim's check could not be read")

    [finding] = doctor.gap_findings([gap])

    assert (finding.severity, finding.code) == ("error", "unparsed-check")
    assert finding.ref == oid


def test_a_misfiled_test_ref_on_a_type_with_no_tests_key_does_not_suggest_one(repo: Path):
    """`screen` declares `verify:` and never `tests:` — the message must not send the author to a key the type cannot hold, and the suggestion beside it must offer the check vocabulary rather than either `- tests: …` or the offending value restated under its own key."""
    write(repo / "docs/features/ui/dash.md", screen_md(
        "dash", "Dash", entry=True,
        body="\n- verify: `e2e/dash_test.go::TestDash`\n"))

    report = doctor.run(load(repo))

    finding = next(f for f in report.findings if f.code == "misfiled-test-ref")
    assert "tests:" not in finding.message
    assert finding.suggestion.startswith("- verify: ")
    assert "e2e/dash_test.go" not in finding.suggestion
    assert "http_status(" in finding.suggestion
    assert finding.fixable is False


def test_a_misfiled_test_ref_on_a_type_that_declares_tests_still_offers_it(repo: Path):
    """`concept` declares both `verify:` and `tests:`, so the same finding on a `concept` page keeps proposing the move — unaffected by the fallback the `screen` case above exercises."""
    write(repo / "docs/features/concepts/widget.md", (
        "---\ntype: concept\nslug: widget\ntitle: Widget\n---\n\n# Widget\n\n"
        "- verify: `e2e/dash_test.go::TestDash`\n"))

    report = doctor.run(load(repo))

    finding = next(f for f in report.findings if f.code == "misfiled-test-ref")
    assert finding.suggestion == "- tests: e2e/dash_test.go::TestDash"
    assert finding.fixable is True


def test_gap_findings_reports_a_compile_plan_gap_as_a_doctor_finding():
    oid = "okf:docs/features/demo/api.md#post-things:does:1"
    gap = compile_mod.Gap(oid, "unresolved-precondition", "the book carries no request body")

    [finding] = doctor.gap_findings([gap])

    assert finding == doctor.Finding(
        "error", "unresolved-precondition",
        f"{oid}: the book carries no request body", ref=oid,
    )


def test_an_unresolved_extends_gap_is_reported_as_a_doctor_finding():
    """`unresolved-extends` is minted by `qa.compile.compile_plan_gaps`, not by any check `doctor.run` performs on its own walk — `census.py`'s own bridge note says so ("gap_findings has no product caller; gaps surface via qa compile-plan only"), so the only way to exercise the code -> Finding translation is to build the `Gap` directly, the same way every other Gap-based code above is tested."""
    oid = "okf:docs/features/demo/api.md#refuse-act:does:1"
    gap = compile_mod.Gap(
        oid, "unresolved-extends",
        "this arm's `extends:` target is missing or not the same node type, so its control "
        "identity could not be inherited from the base case")

    [finding] = doctor.gap_findings([gap])

    assert finding == doctor.Finding(
        "error", "unresolved-extends",
        f"{oid}: this arm's `extends:` target is missing or not the same node type, so its "
        "control identity could not be inherited from the base case", ref=oid,
    )


def test_an_unparsed_capture_gap_keeps_the_code_doctor_already_raises_for_that_bullet():
    """`_check_book_captures` raises `unparsed-capture` on this bullet from the book alone."""
    oid = "okf:docs/features/demo/http/api.md#submit:does:1"
    gap = compile_mod.Gap(oid, "unparsed-capture-bullet", "this claim's capture could not be read")

    [finding] = doctor.gap_findings([gap])

    assert (finding.severity, finding.code) == ("error", "unparsed-capture")
    assert finding.ref == oid


def _emitted_codes() -> dict[str, str]:
    """Every `(code, severity)` pair `doctor.py` can construct, read out of its source."""
    tree = ast.parse(Path(doctor.__file__).read_text())
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "Finding"
    ]
    computed = [
        node.lineno for node in calls
        if len(node.args) < 2
        or not isinstance(node.args[0], ast.Constant)
        or not isinstance(node.args[1], ast.Constant)
    ]
    assert not computed, f"Finding(...) with a computed severity or code at lines {computed}"
    emitted: dict[str, set[str]] = {}
    for node in calls:
        severity, code = node.args[0], node.args[1]
        if isinstance(severity, ast.Constant) and isinstance(code, ast.Constant):
            if isinstance(severity.value, str) and isinstance(code.value, str):
                emitted.setdefault(code.value, set()).add(severity.value)
    split = {code: sorted(sevs) for code, sevs in emitted.items() if len(sevs) > 1}
    assert not split, f"one code raised at two severities, so no row can state one: {split}"
    return {code: next(iter(sevs)) for code, sevs in emitted.items()}


def _documented_codes() -> dict[str, str]:
    page = Path(__file__).resolve().parents[2] / (
        "base-library/library/skills/ostler/okf/references/doctor-codes.md")
    rows = re.findall(r"^\| `([a-z0-9-]+)` \| (error|warn) \|", page.read_text(), re.M)
    documented = dict(rows)
    assert len(rows) == len(documented), "doctor-codes.md documents one code twice"
    return documented


def test_the_reference_page_lists_every_code_doctor_can_raise():
    """`doctor-codes.md` calls itself the list of every finding, and until now nothing joined it to the findings."""
    emitted, documented = _emitted_codes(), _documented_codes()
    assert set(emitted) == set(documented), {
        "raised with no row": sorted(set(emitted) - set(documented)),
        "documented and never raised": sorted(set(documented) - set(emitted)),
    }


def test_the_reference_page_states_the_severity_each_code_is_raised_at():
    """The severity is the half of a row a reader acts on — an error gates a story and a warn does not — and it was wrong for `malformed-variants` and `runbook-missing` in opposite directions, each for as long as nobody re-read the code beside the row."""
    emitted, documented = _emitted_codes(), _documented_codes()
    mismatched = {
        code: {"doctor.py": emitted[code], "doctor-codes.md": documented[code]}
        for code in set(emitted) & set(documented) if emitted[code] != documented[code]
    }
    assert not mismatched, mismatched
