"""Tests for build-inventory.py — surface-count reporter over ostler features + survey units.

Under the OKF model every feature is a typed ``feature`` Concept and ostler reads the feature set
directly (``ostler list --type feature``); there is no derived feature ``inventory.json`` to
build. The node never writes a file — it reports how many surfaces the coverage gate will see:
feature Concepts, plus (opt-in by presence) the units of a survey-produced manifest at the
``cfg.surface_manifest`` path.
"""
from __future__ import annotations

import json

from conftest import init_repo, requires_ostler, run_script, write_feature

pytestmark = requires_ostler


def build(repo):
    return run_script("build-inventory.py", "docs/features", "docs/features/inventory.json",
                      repo=repo)


def test_no_features_skips_with_zero_count(tmp_path):
    init_repo(tmp_path)
    out = build(tmp_path)
    assert out["inventory_built"] == "skip"
    assert out["surface_count"] == 0
    # the retired manifest is never written
    assert not (tmp_path / "docs/features/inventory.json").exists()


def test_counts_feature_concepts(tmp_path):
    init_repo(tmp_path)
    write_feature(tmp_path, "login", area="auth", route="/login")
    write_feature(tmp_path, "projects", area="project", route="/projects")
    out = build(tmp_path)
    assert out["inventory_built"] == "skip"
    assert out["surface_count"] == 2
    # still no inventory.json — the source Concepts ARE the manifest
    assert not (tmp_path / "docs/features/inventory.json").exists()


def test_reports_features_dir_path(tmp_path):
    init_repo(tmp_path)
    out = build(tmp_path)
    assert out["inventory_path"] == "docs/features"
    assert "inventory.json" in out["inventory_note"]


def test_counts_survey_units_when_manifest_present(tmp_path):
    init_repo(tmp_path)
    write_feature(tmp_path, "login", area="auth", route="/login")
    manifest = tmp_path / "docs" / "survey" / "unit-manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"generatedBy": "surveyor", "units": [
        {"id": "src/a"}, {"id": "src/b"}, {"id": "src/c"},
    ]}), encoding="utf-8")

    out = run_script("build-inventory.py", "docs/features",
                     "docs/survey/unit-manifest.json", repo=tmp_path)
    assert out["inventory_built"] == "manifest"
    assert out["surface_count"] == 4  # 1 feature Concept + 3 surveyed units
    assert out["inventory_path"] == "docs/survey/unit-manifest.json"
    assert "surveyor" in out["inventory_note"]
