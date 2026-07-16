"""Tests for the spec ↔ surface-registry edge (ungrounded-surface): a knowledge record whose
surface is absent from the feature Concepts (docs/features/**/*.md)."""
from __future__ import annotations

from pathlib import Path

from conftest import feature_md, knowledge_md, write
from ostler import doctor
from ostler.model import load


def _codes(repo: Path) -> set[str]:
    return {f.code for f in doctor.run(load(repo)).findings}


def _knowledge(repo: Path, surface: str, route: str = "") -> None:
    write(repo / "docs/knowledge/area/rec.md", knowledge_md(surface, route=route))


def test_no_features_skips(tmp_path):
    # greenfield with no feature registry yet → no ungrounded-surface noise
    _knowledge(tmp_path, "settings/profile")
    assert "ungrounded-surface" not in _codes(tmp_path)


def test_grounded_surface_passes(tmp_path):
    write(tmp_path / "docs/features/settings/profile.md",
          feature_md("profile", "Profile", area="settings", route="/settings/profile"))
    _knowledge(tmp_path, "settings/profile")
    assert "ungrounded-surface" not in _codes(tmp_path)


def test_ungrounded_surface_flagged(tmp_path):
    write(tmp_path / "docs/features/settings/profile.md",
          feature_md("profile", "Profile", area="settings"))
    _knowledge(tmp_path, "billing/invoices")  # not in features
    assert "ungrounded-surface" in _codes(tmp_path)


def test_grounded_by_route_passes(tmp_path):
    write(tmp_path / "docs/features/billing/invoices.md",
          feature_md("invoices", "Invoices", area="billing", route="/billing/invoices"))
    _knowledge(tmp_path, "some-internal-name", route="/billing/invoices")
    assert "ungrounded-surface" not in _codes(tmp_path)
