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

from conftest import epic_md, story_md, write

FOO_STORY = "docs/epics/epic-a/stories/01-foo/story.md"


def codes(report):
    return {f.code for f in report.findings if f.severity == "error"}


def _git_track(root: Path) -> None:
    """Init a repo at *root* and stage everything in it — `git ls-files` reads the index,
    not a commit, so staging alone is enough for `misplaced-book-page`'s enumeration."""
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)


def test_clean_repo_has_no_errors(repo: Path):
    report = doctor.run(load(repo))
    assert report.errors == 0, [f.message for f in report.findings if f.severity == "error"]
    assert report.profile == "full"
    assert {e["dir"] for e in report.epics} == {"epic-a", "epic-b"}


def test_a_typed_page_outside_every_doc_root_is_flagged_as_misplaced(repo: Path):
    """A real book page (a declared `type:`) that a move -- or a first draft -- leaves outside
    `docs/features`, `docs/epics`, `docs/milestones`, `docs/roadmaps`, `docs/specs` and
    `docs/backlog.md` is invisible to every other check: it is not `okf-missing-type` (it has
    a type), and nothing walks in to find it, since every book-facing check is rooted at
    `graph.doc_roots`. `misplaced-book-page` is the one check that walks the tracked tree
    independently of those roots.
    """
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
    """The predicate is "outside every doc root", never "outside `docs/features`" alone --
    real `epic`/`story`/`spec.*` pages that sit under one of the *other* doc roots must not be
    flagged, even once git tracking makes the new check actually run.
    """
    write(repo / "docs/specs/plan.md",
          "---\ntype: spec.plan\ntitle: Plan\n---\n# Plan\n\nBody.\n")
    _git_track(repo)

    report = doctor.run(load(repo))
    assert "misplaced-book-page" not in codes(report)


def test_typed_pages_inside_a_nested_book_are_not_misplaced(repo: Path):
    """A subtree with its own `docs/` (a paddock app under `paddock/data/apps/<app>/` is
    exactly this shape) is a book of its own -- `model.find_root` resolves it as its own
    root, with its own `doc_roots`, the moment ostler is pointed at it directly. A typed
    page under that subtree's own `docs/` belongs to *that* book, not to the outer one, and
    must not be flagged just because it also sits outside the outer book's doc roots.
    """
    write(repo / "vendor/widgets-app/docs/epics/epic-x/epic.md",
          "---\ntype: epic\ntitle: Widgets\n---\n# Widgets\n\nBody.\n")
    _git_track(repo)

    report = doctor.run(load(repo))
    assert "misplaced-book-page" not in codes(report)


def test_misplaced_book_page_emits_nothing_outside_a_git_repository(repo: Path):
    """The corpus's standing core property -- git-tracked -- is undetermined when `graph.root`
    is not inside a git repository at all, and the rule for an undetermined property is
    silence, never a filesystem walk that would sweep `.venv`/build output and invent
    findings.
    """
    write(repo / "notes/orphan-concept.md",
          "---\ntype: concept\ntitle: Orphan\n---\n# Orphan\n\nStray content.\n")
    # deliberately no `_git_track(repo)` -- repo is a plain directory, not a git repository

    report = doctor.run(load(repo))
    assert "misplaced-book-page" not in codes(report)


def test_a_spec_typed_page_under_features_is_flagged_as_misrooted(repo: Path):
    """`spec.*` is registered under `docs/specs`, not `docs/features` -- and unlike a page
    outside every root, a `spec.qa-okf-context.md` dropped under `docs/features` (the shape
    `ostler qa context` writing its scratch output to the wrong directory would produce) IS
    under a doc root, so `misplaced-book-page` never fires. Its file node is suppressed
    (`spec` is not a `UINodeType`) but `_parse_ui_nodes` still recurses into its `##`
    sections, seeding `untyped` nodes into the book with nothing else catching the mismatch
    between the declared type's registered root and the root the file actually sits under.
    """
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
    """The predicate is "inside a doc root that disagrees with the type", never "inside any
    doc root but `docs/features`" -- a real `spec.*` page under `docs/specs` (its registered
    home) must not be flagged.
    """
    write(repo / "docs/specs/plan/plan.md",
          "---\ntype: spec.plan\ntitle: Plan\n---\n# Plan\n\nBody.\n")
    _git_track(repo)

    report = doctor.run(load(repo))
    assert "misrooted-book-page" not in codes(report)


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
# empty, gone the moment they are written.

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


def test_an_old_story_is_unwritten_for_the_sections_it_never_had(tmp_path: Path):
    """No frontmatter exempts a document from the contract — there is only one, and it is the table.

    Before, dropping the shape key bought this story a weaker section list and a clean report; the
    sections it is missing are real work, and saying so is the point.
    """
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


# --------------------------------------------------------------------------- #
# story-conflict                                                              #
# --------------------------------------------------------------------------- #
#
# The adjudicator's `story` verdict: two criteria that cannot both hold. It may not rewrite
# intent, and no undetermined fault may stay open, so the story carries the finding until an
# operator edits the criteria and clears the key.

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
    """`gap_findings` names every kind `compile_plan` mints — no kind reaches the catch-all.

    The catch-all `else` is a runtime safety net, not the thing that decides whether a kind is
    handled: it turns a missing case into a `Finding` carrying `uncompilable-claim`, which is a
    valid finding with the wrong code, and a wrong answer is not observable as a missing case.
    That is how `undeclared-check-locator` and `unstated-claim-combiner` — both real doctor
    codes, both with their own repair fragment under `okf_builder/main/prompts/repair/` — came
    to be reported to the builders under a third code whose fragment says something else.

    Two relations, because each catches a different drift: a kind minted in `compile.py` and
    never declared, and a kind declared and never translated.
    """
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

    # `warn`, the severity doctor already grades `undeclared-obligation` at when it raises the
    # same fact from the book alone. One rule graded two ways by which component noticed it is
    # the drift this bridge exists to avoid.
    assert (finding.severity, finding.code) == ("warn", "undeclared-obligation")


def test_undeclared_obligation_fires_per_bullet_even_when_the_node_declares_a_check(repo: Path):
    """SITE-GAP is per-obligation; SITE-BOOK's `declared` flag is node-wide.

    An `endpoint` with two normative bullets (`does`, `status`) and exactly one `verify:` —
    bound by document order to `does`, the nearer bullet above it — has *something* declared,
    so SITE-BOOK's `if check_keys and normative and not declared` never fires: `declared` is a
    node-wide flag, true the moment any bullet on the node carries a check.

    But `status` itself declares nothing, and `registry.attributed_checks` binds a check to the
    *nearest* normative bullet above it, not to every normative bullet on the node — so the
    compiler's per-obligation partition (`qa/compile.py`'s `declared`/`undeclared` split, fed by
    `checksDeclared` from `qa/context.py`) puts the `status` obligation in `undeclared` while
    `does` sits in `declared`. Only the full context -> compile -> `gap_findings` path sees
    this: the discriminator between the two raise sites is the finding's `ref` shape — a bare
    bullet key when SITE-BOOK fires on a node that declares nothing at all, an indexed
    obligation id when SITE-GAP fires on one bullet of a node that declares plenty.
    """
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
    _source, gaps = compile_mod.compile_plan_gaps(packet, story="demo-story")

    no_verify = {g.obligation_id: g for g in gaps if g.kind == "no-verify-declared"}
    assert not any(":does:" in oid for oid in no_verify)
    status_id = next(oid for oid in no_verify if ":status:" in oid)
    gap = no_verify[status_id]

    [finding] = doctor.gap_findings([gap])
    assert (finding.severity, finding.code) == ("warn", "undeclared-obligation")
    assert re.match(r"^okf:.+:[a-z-]+:\d+$", finding.ref), finding.ref
    assert finding.ref == gap.obligation_id


def test_an_unparsed_fixture_gap_keeps_the_code_doctor_already_raises_for_that_bullet():
    """`_check_book_fixtures` raises `qa-fixture-bullet` on this bullet from the book alone.

    The compiler's kind names the *consequence* — which obligations went uncompiled because of
    it — not a second defect, so it bridges to that same code at that same severity. A code of
    its own would grade one rule two ways depending on which component noticed it, which is
    the drift this bridge exists to avoid; `no-verify-declared` is translated for the same
    reason.
    """
    oid = "okf:docs/features/demo/flows/add-a-thing.md:end-state"
    gap = compile_mod.Gap(oid, "unparsed-fixture", "this claim's arrangement could not be read")

    [finding] = doctor.gap_findings([gap])

    assert (finding.severity, finding.code) == ("error", "qa-fixture-bullet")
    assert finding.ref == oid


def test_an_unparsed_check_gap_keeps_the_code_doctor_already_raises_for_that_bullet():
    """`_check_ui` raises `unparsed-check` on this bullet from the book alone.

    Same bridge as the fixture kind above, for the same reason: the compiler's kind names which
    obligations went unproven because the bullet could not be read, which is the consequence of
    one defect and not a second one. Left unbridged it would be a second code for a rule doctor
    already states — and before the bridge existed at all, the obligation fell through to
    `no-verify-declared`, which contradicted doctor about the same bullet.
    """
    oid = "okf:docs/features/policy/gui/screens/policy-list.md#policy-table:contract"
    gap = compile_mod.Gap(oid, "unparsed-check-bullet", "this claim's check could not be read")

    [finding] = doctor.gap_findings([gap])

    assert (finding.severity, finding.code) == ("error", "unparsed-check")
    assert finding.ref == oid


def test_gap_findings_reports_a_compile_plan_gap_as_a_doctor_finding():
    oid = "okf:docs/features/demo/api.md#post-things:does:1"
    gap = compile_mod.Gap(oid, "unresolved-precondition", "the book carries no request body")

    [finding] = doctor.gap_findings([gap])

    assert finding == doctor.Finding(
        "error", "unresolved-precondition",
        f"{oid}: the book carries no request body", ref=oid,
    )


def test_an_unparsed_capture_gap_keeps_the_code_doctor_already_raises_for_that_bullet():
    """`_check_book_captures` raises `unparsed-capture` on this bullet from the book alone.

    The third of the same bridge: the compiler's kind names what the unreadable bullet cost —
    a fact no later `$name` can resolve against — which is the consequence of one defect and
    not a second one.
    """
    oid = "okf:docs/features/demo/http/api.md#submit:does:1"
    gap = compile_mod.Gap(oid, "unparsed-capture-bullet", "this claim's capture could not be read")

    [finding] = doctor.gap_findings([gap])

    assert (finding.severity, finding.code) == ("error", "unparsed-capture")
    assert finding.ref == oid


def _emitted_codes() -> dict[str, str]:
    """Every `(code, severity)` pair `doctor.py` can construct, read out of its source.

    A `Finding(...)` whose severity or code is not a literal is unreadable here, so the
    extraction asserts there are none rather than skipping them — a code a static reader has to
    execute a ternary to learn is a code no enumeration can see, and an enumeration with a hole
    in it reports "documented" about a code nobody looked at.
    """
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
    """`doctor-codes.md` calls itself the list of every finding, and until now nothing joined it
    to the findings.

    The drift is silent in both directions and it had already happened twice. Five codes —
    `unarranged-journey`, `unarranged-state`, `uneven-claim-coverage`, `unidentifiable-screen`,
    `unparsed-capture` — were raised with no row at all, so a builder handed one of them had
    nowhere to look, which is the same defect as a missing repair fragment seen one artifact
    over. And the page's own header claimed a code count twenty-one short of its own table,
    which is why there is no count here to keep in step: the table is the list.

    okf-builder's `test_drift_tripwire.py` is this test's sibling and covers the other Gate A
    artifact — that every code has a repair fragment or a reasoned exemption. Neither implies
    the other: a code can have a fragment the builders read and no row a person can.
    """
    emitted, documented = _emitted_codes(), _documented_codes()
    assert set(emitted) == set(documented), {
        "raised with no row": sorted(set(emitted) - set(documented)),
        "documented and never raised": sorted(set(documented) - set(emitted)),
    }


def test_the_reference_page_states_the_severity_each_code_is_raised_at():
    """The severity is the half of a row a reader acts on — an error gates a story and a warn
    does not — and it was wrong for `malformed-variants` and `runbook-missing` in opposite
    directions, each for as long as nobody re-read the code beside the row.
    """
    emitted, documented = _emitted_codes(), _documented_codes()
    mismatched = {
        code: {"doctor.py": emitted[code], "doctor-codes.md": documented[code]}
        for code in set(emitted) & set(documented) if emitted[code] != documented[code]
    }
    assert not mismatched, mismatched
