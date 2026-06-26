from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.model import load

from conftest import epic_md, knowledge_md, write


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
        stories=[("01-foo", "Foo", ["seed-b1"], [])],
    ))

    report = doctor.run(load(repo))
    assert "cross-epic-seed" in codes(report)
    # seed-a1 is now uncovered -> orphan
    assert "orphan-seed" in codes(report)
    assert report.errors  # non-zero exit


def test_dangling_owner_is_flagged(repo: Path):
    write(repo / "docs/knowledge/area/rec.md", knowledge_md("area/rec", [("gap-x", "99-ghost")]))

    report = doctor.run(load(repo))
    assert "dangling-owner" in codes(report)


def test_resolved_seed_not_required_to_be_covered(repo: Path):
    # seed-a2 is resolved and covered by nobody -> must NOT be an orphan error.
    report = doctor.run(load(repo))
    assert "orphan-seed" not in codes(report)


def test_markdown_records_parsed(repo: Path):
    graph = load(repo)
    surfaces = {r.surface for r in graph.knowledge}
    assert {"area/rec", "area/rec2"} <= surfaces
    # gap-y owner came from YAML frontmatter
    md = next(r for r in graph.knowledge if r.surface == "area/rec2")
    assert md.fmt == "md"
    assert md.gaps[0].id == "gap-y" and md.gaps[0].owner == "01-bar"


def test_missing_type_is_flagged(repo: Path):
    # a knowledge Concept without `type` violates OKF conformance
    write(repo / "docs/knowledge/area/rec.md",
          "---\nsurface: area/rec\ngaps: []\n---\n# rec\n\nbody\n")
    assert "okf-missing-type" in codes(doctor.run(load(repo)))


def test_seedless_epic_no_covers_warning(repo: Path):
    # a wholly-seedless epic (yenta-style) must not raise story-covers-no-seed
    write(repo / "docs/epics/epic-c/epic.md", epic_md(
        "t-3", "epic-c", seeds=[], stories=[("01-x", "X", [], [])]))
    write(repo / "docs/epics/epic-c/stories/01-x/story.md",
          "---\ntype: story\nslug: 01-x\nstatus: Not started\n---\n# Story: X\n")
    warns = {f.code for f in doctor.run(load(repo)).findings if f.severity == "warn"}
    assert "story-covers-no-seed" not in warns


def test_epic_filter_scopes_findings(repo: Path):
    write(repo / "docs/knowledge/area/rec.md", knowledge_md("area/rec", [("gap-x", "99-ghost")]))
    report = doctor.run(load(repo), epic_filter="epic-b")
    assert all(f.epic in ("epic-b",) for f in report.findings)
