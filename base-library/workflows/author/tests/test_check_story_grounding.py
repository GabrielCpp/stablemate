"""Tests for check-story-grounding.py — the thin grounding pre-gate before the story auditor.

Presence/structure only (no semantic judgment): the story's covered seed items exist in the
epic's seeds; a knowledge Concept grounds the story (matched generously by slug / seed-id /
legacy-surface tokens); and — iff ``features_dir`` is configured — that record recorded a journey
(non-empty ``journeys[]`` or ``provenance.sourcesRead`` under the features dir). Degrades to
presence-only when ``features_dir`` is empty **or when the graph holds no feature Concepts** —
the greenfield case, since ``load-config.py`` defaults ``features_dir`` unconditionally so it is
never falsy on its own. All data comes from the real ostler CLI.
"""
from __future__ import annotations

from conftest import requires_ostler, run_script, write_epic, write_feature, write_knowledge

pytestmark = requires_ostler

KN = "docs/knowledge"


def _epic_with_story(repo, *, seed_ids, slug, covers):
    write_epic(repo, "e1", seeds=[{"id": s} for s in seed_ids],
               stories=[{"slug": slug, "covers": covers}])
    return f"docs/epics/e1/stories/{slug}", "docs/epics/e1"


def gate(repo, story_dir, epic_dir, features_dir="docs/features"):
    return run_script("check-story-grounding.py", story_dir, epic_dir, KN, features_dir, repo=repo)


def test_grounded_with_journey_passes(tmp_path):
    sd, ed = _epic_with_story(tmp_path, seed_ids=["form-editor"], slug="form-editor",
                              covers=["form-editor"])
    write_knowledge(tmp_path, "form-editor",
                    journeys=[{"id": "edit", "name": "Edit and save"}])
    assert gate(tmp_path, sd, ed)["story_grounding_ok"] == "yes"


def test_grounded_via_sources_read_under_features_passes(tmp_path):
    sd, ed = _epic_with_story(tmp_path, seed_ids=["form-editor"], slug="form-editor",
                              covers=["form-editor"])
    write_knowledge(tmp_path, "form-editor", journeys=[],
                    sources=["docs/features/area/form-editor.md", "app/routes/form.tsx"])
    assert gate(tmp_path, sd, ed)["story_grounding_ok"] == "yes"


def test_missing_record_downgrades(tmp_path):
    sd, ed = _epic_with_story(tmp_path, seed_ids=["form-editor"], slug="form-editor",
                              covers=["form-editor"])
    out = gate(tmp_path, sd, ed)
    assert out["story_grounding_ok"] == "no"
    assert "knowledge record" in out["story_grounding_errors"]


def test_features_set_but_no_journey_downgrades(tmp_path):
    """Brownfield: feature Concepts exist, so the journey requirement is armed."""
    sd, ed = _epic_with_story(tmp_path, seed_ids=["form-editor"], slug="form-editor",
                              covers=["form-editor"])
    write_feature(tmp_path, "form-editor", area="area")
    write_knowledge(tmp_path, "form-editor", journeys=[], sources=["app/routes/form.tsx"])
    out = gate(tmp_path, sd, ed)
    assert out["story_grounding_ok"] == "no"
    assert "journey" in out["story_grounding_errors"].lower()


def test_no_feature_concepts_disarms_journey_check(tmp_path):
    """Greenfield: ``features_dir`` is defaulted by load-config.py and so is always set, but
    with no feature Concepts in the graph there is no journey to have read. The journey check
    must stay disarmed rather than hard-failing every story on a repo with no feature docs yet."""
    sd, ed = _epic_with_story(tmp_path, seed_ids=["form-editor"], slug="form-editor",
                              covers=["form-editor"])
    write_knowledge(tmp_path, "form-editor", journeys=[], sources=["app/routes/form.tsx"])
    assert gate(tmp_path, sd, ed)["story_grounding_ok"] == "yes"


def test_no_feature_concepts_still_requires_a_knowledge_record(tmp_path):
    """Disarming the journey check must not disarm the record-presence check with it —
    gather_knowledge still has to have run."""
    sd, ed = _epic_with_story(tmp_path, seed_ids=["form-editor"], slug="form-editor",
                              covers=["form-editor"])
    out = gate(tmp_path, sd, ed)
    assert out["story_grounding_ok"] == "no"
    assert "knowledge record" in out["story_grounding_errors"]


def test_unknown_seed_id_downgrades(tmp_path):
    # story covers 'ghost', which is not one of the epic's seeds → phantom scope.
    sd, ed = _epic_with_story(tmp_path, seed_ids=["i1"], slug="form-editor", covers=["ghost"])
    write_knowledge(tmp_path, "form-editor", journeys=[{"id": "j", "name": "x"}])
    out = gate(tmp_path, sd, ed)
    assert out["story_grounding_ok"] == "no"
    assert "ghost" in out["story_grounding_errors"]


def test_features_empty_presence_only_passes(tmp_path):
    sd, ed = _epic_with_story(tmp_path, seed_ids=["form-editor"], slug="form-editor",
                              covers=["form-editor"])
    write_knowledge(tmp_path, "form-editor")  # record present, no journeys
    # features_dir empty ⇒ journey requirement is skipped; record presence + valid seed is enough.
    assert gate(tmp_path, sd, ed, features_dir="")["story_grounding_ok"] == "yes"
