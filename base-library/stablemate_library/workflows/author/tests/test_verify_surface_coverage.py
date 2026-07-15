"""Tests for verify-surface-coverage.py — the site-surface coverage / grounding gate (OKF model).

Two modes. **full** (opt-in, migration/buildout): every feature-set surface must be covered by
some backlog/epic/story/knowledge record. **grounding** (default): every surface the work *claims
to touch* (seed ``legacySurface`` / knowledge ``surface``+``route``) must exist in the feature set,
without flagging untouched screens. The feature set is the set of typed ``feature`` Concepts ostler
reads from ``docs/features`` — with none present the gate is a clean ``skip``. Matching is generous
(area-slug / slug / route tokens). All data comes from the real ostler CLI.
"""
from __future__ import annotations

from conftest import (
    init_repo, requires_ostler, run_script, write_backlog, write_epic, write_feature,
    write_knowledge,
)

pytestmark = requires_ostler


def gate(repo, mode="full"):
    """Full-coverage mode — every feature-set surface must be covered."""
    return run_script("verify-surface-coverage.py", "x", "docs/epics", "docs/backlog.md",
                      "docs/knowledge", mode, repo=repo)


def ground(repo):
    """Grounding mode — every claimed surface must resolve to the feature set."""
    return gate(repo, "grounding")


# ── opt-in by presence ────────────────────────────────────────────────────────

def test_no_feature_concepts_skips(tmp_path):
    init_repo(tmp_path)
    assert gate(tmp_path)["surface_coverage_ok"] == "skip"


# ── full mode: every feature-set surface must be covered ──────────────────────

def test_surface_covered_by_seed_legacy_surface_passes(tmp_path):
    write_epic(tmp_path, "e1",
               seeds=[{"id": "i1", "legacySurface": "/projects/:id/stages"}],
               stories=[{"slug": "s1", "covers": ["i1"]}])
    write_feature(tmp_path, "stages", area="project", route="/projects/:id/stages")
    assert gate(tmp_path)["surface_coverage_ok"] == "yes"


def test_surface_covered_by_open_backlog_bullet_passes(tmp_path):
    init_repo(tmp_path)
    write_backlog(tmp_path, ["project-stages-editor"])
    write_feature(tmp_path, "project-stages-editor", area="area", route="/x")
    assert gate(tmp_path)["surface_coverage_ok"] == "yes"


def test_surface_covered_by_story_slug_passes(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}],
               stories=[{"slug": "project-stages-editor", "covers": ["i1"]}])
    write_feature(tmp_path, "project-stages-editor", area="area")
    assert gate(tmp_path)["surface_coverage_ok"] == "yes"


def test_surface_covered_by_knowledge_record_passes(tmp_path):
    init_repo(tmp_path)
    write_knowledge(tmp_path, "project-stages-editor", gaps=[{"id": "g1"}])
    write_feature(tmp_path, "project-stages-editor", area="area")
    assert gate(tmp_path)["surface_coverage_ok"] == "yes"


def test_uncovered_surface_fails(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "s1", "covers": ["i1"]}])
    write_feature(tmp_path, "totally-unlisted-screen", area="area", route="/ghost")
    out = gate(tmp_path)
    assert out["surface_coverage_ok"] == "no"
    assert "totally-unlisted-screen" in out["surface_coverage_errors"]


# ── grounding mode (the default): claims must resolve to the feature set ───────

def test_default_mode_is_grounding(tmp_path):
    # No mode arg → grounding. An untouched feature surface with no claims must NOT be flagged.
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "s1", "covers": ["i1"]}])
    write_feature(tmp_path, "untouched-screen", area="area", route="/ghost")
    out = run_script("verify-surface-coverage.py", "x", "docs/epics", "docs/backlog.md",
                     "docs/knowledge", repo=tmp_path)  # no 5th arg
    assert out["surface_coverage_ok"] == "yes"


def test_grounding_no_claims_passes(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "s1", "covers": ["i1"]}])
    write_feature(tmp_path, "untouched-screen", area="area", route="/ghost")
    assert ground(tmp_path)["surface_coverage_ok"] == "yes"


def test_grounding_claim_in_feature_set_passes(tmp_path):
    write_epic(tmp_path, "e1",
               seeds=[{"id": "i1", "legacySurface": "/projects/:id/stages"}],
               stories=[{"slug": "s1", "covers": ["i1"]}])
    write_feature(tmp_path, "stages", area="project", route="/projects/:id/stages")
    assert ground(tmp_path)["surface_coverage_ok"] == "yes"


def test_grounding_phantom_seed_surface_fails(tmp_path):
    # A seed claims a surface the feature set never documents → phantom scope → "no".
    write_epic(tmp_path, "e1",
               seeds=[{"id": "i1", "legacySurface": "/totally/made-up-screen"}],
               stories=[{"slug": "s1", "covers": ["i1"]}])
    write_feature(tmp_path, "real-screen", area="area", route="/real")
    out = ground(tmp_path)
    assert out["surface_coverage_ok"] == "no"
    assert "made-up-screen" in out["surface_coverage_errors"]


def test_grounding_phantom_knowledge_surface_fails(tmp_path):
    # A knowledge record describes a surface not in the feature set → "no".
    init_repo(tmp_path)
    write_knowledge(tmp_path, "ghost-surface", gaps=[{"id": "g1"}])  # surface "area/ghost-surface"
    write_feature(tmp_path, "documented-screen", area="real")
    out = ground(tmp_path)
    assert out["surface_coverage_ok"] == "no"
    assert "ghost-surface" in out["surface_coverage_errors"]


def test_grounding_knowledge_surface_in_feature_set_passes(tmp_path):
    init_repo(tmp_path)
    write_knowledge(tmp_path, "documented-screen", gaps=[{"id": "g1"}])  # "area/documented-screen"
    write_feature(tmp_path, "documented-screen", area="area")
    assert ground(tmp_path)["surface_coverage_ok"] == "yes"


# ── survey-produced unit manifest (the surveyor workflow's other producer) ──────

MANIFEST = "docs/survey/unit-manifest.json"


def write_unit_manifest(repo, units):
    """A surveyor-style manifest: entries carry the bullet ids that cover them."""
    import json
    p = repo / MANIFEST
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": 1, "generatedBy": "surveyor", "units": units}),
                 encoding="utf-8")


def gate_manifest(repo, mode="full"):
    return run_script("verify-surface-coverage.py", MANIFEST, "docs/epics",
                      "docs/backlog.md", "docs/knowledge", mode, repo=repo)


def test_manifest_only_repo_does_not_skip_and_flags_uncovered_units(tmp_path):
    # No feature Concepts at all — the manifest alone activates the gate (opt-in by
    # presence, same contract, different producer).
    init_repo(tmp_path)
    write_unit_manifest(tmp_path, [
        {"id": "src/editor", "path": "src/editor", "kind": "folder",
         "status": "assessed", "bullets": ["survey-fix-frob"]},
    ])
    out = gate_manifest(tmp_path)
    assert out["surface_coverage_ok"] == "no"
    assert "unit src/editor" in out["surface_coverage_errors"]


def test_unit_covered_by_its_generated_backlog_bullet_passes(tmp_path):
    init_repo(tmp_path)
    write_backlog(tmp_path, ["survey-fix-frob"])
    write_unit_manifest(tmp_path, [
        {"id": "src/editor", "path": "src/editor", "kind": "folder",
         "status": "assessed", "bullets": ["survey-fix-frob"]},
    ])
    assert gate_manifest(tmp_path)["surface_coverage_ok"] == "yes"


def test_unit_covered_by_seed_source_bullet_after_prune_passes(tmp_path):
    # Author consumed the generated bullet (pruned from the backlog) — the same id
    # survives as the seed's sourceBullet, so the unit stays covered.
    write_epic(tmp_path, "e1",
               seeds=[{"id": "i1", "sourceBullet": "survey-fix-frob"}],
               stories=[{"slug": "s1", "covers": ["i1"]}])
    write_unit_manifest(tmp_path, [
        {"id": "src/editor", "path": "src/editor", "kind": "folder",
         "status": "assessed", "bullets": ["survey-fix-frob"]},
    ])
    assert gate_manifest(tmp_path)["surface_coverage_ok"] == "yes"


def test_workless_unit_demands_no_coverage(tmp_path):
    # A clean / accepted-blocked unit has empty `bullets` — nothing to cover.
    init_repo(tmp_path)
    write_unit_manifest(tmp_path, [
        {"id": "src/clean", "path": "src/clean", "kind": "folder",
         "status": "clean", "bullets": []},
    ])
    assert gate_manifest(tmp_path)["surface_coverage_ok"] == "yes"


def test_features_and_units_gate_together(tmp_path):
    # Both producers present: an uncovered feature still fails even when every unit
    # is covered.
    init_repo(tmp_path)
    write_backlog(tmp_path, ["survey-fix-frob"])
    write_feature(tmp_path, "totally-unlisted-screen", area="area", route="/ghost")
    write_unit_manifest(tmp_path, [
        {"id": "src/editor", "path": "src/editor", "kind": "folder",
         "status": "assessed", "bullets": ["survey-fix-frob"]},
    ])
    out = gate_manifest(tmp_path)
    assert out["surface_coverage_ok"] == "no"
    assert "totally-unlisted-screen" in out["surface_coverage_errors"]


def test_grounding_claim_grounded_in_unit_manifest_passes(tmp_path):
    # On a survey-driven repo (no feature Concepts) a knowledge record about a surveyed
    # unit is grounded scope, not phantom scope.
    init_repo(tmp_path)
    write_knowledge(tmp_path, "editor", area="src", gaps=[{"id": "g1"}])  # surface "src/editor"
    write_unit_manifest(tmp_path, [
        {"id": "src/editor", "path": "src/editor", "kind": "folder",
         "status": "assessed", "bullets": ["survey-fix-frob"]},
    ])
    assert gate_manifest(tmp_path, "grounding")["surface_coverage_ok"] == "yes"


def test_grounding_phantom_claim_still_fails_with_manifest(tmp_path):
    init_repo(tmp_path)
    write_knowledge(tmp_path, "ghost-surface", gaps=[{"id": "g1"}])  # "area/ghost-surface"
    write_unit_manifest(tmp_path, [
        {"id": "src/editor", "path": "src/editor", "kind": "folder",
         "status": "assessed", "bullets": ["survey-fix-frob"]},
    ])
    out = gate_manifest(tmp_path, "grounding")
    assert out["surface_coverage_ok"] == "no"
    assert "ghost-surface" in out["surface_coverage_errors"]
