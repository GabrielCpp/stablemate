"""Tests for validate-epic-coverage.py — seed coverage + graph validity + deferral ownership.

The structural checks (every active seed covered, no dangling seed/dependency references, etc.)
are computed by ``ostler doctor --epic <epic>`` and surfaced when the finding code is one of the
coverage codes. On top of that the gate enforces the deferral-ownership invariant: every knowledge
gap marked ``disposition: deferred`` must name an owner that resolves to a real story slug, seed
id, or open backlog item. Only ``argv[1]`` (the epic dir) is read; backlog/knowledge come from
ostler.
"""
from __future__ import annotations

from conftest import requires_ostler, run_script, write_epic

pytestmark = requires_ostler


def cov(repo, epic_dir="docs/epics/e1"):
    return run_script("validate-epic-coverage.py", epic_dir, repo=repo)


def test_fully_covered_epic_passes(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}, {"id": "i2"}], stories=[
        {"slug": "s1", "covers": ["i1"]},
        {"slug": "s2", "deps": ["s1"], "covers": ["i2"]},
    ])
    out = cov(tmp_path)
    assert out["coverage_ok"] == "yes", out["coverage_errors"]


def test_uncovered_seed_item_fails(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}, {"id": "i2"}], stories=[
        {"slug": "s1", "covers": ["i1"]},  # i2 uncovered → orphan-seed
    ])
    out = cov(tmp_path)
    assert out["coverage_ok"] == "no"
    assert "i2" in out["coverage_errors"]


def test_unknown_seed_reference_fails(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[
        {"slug": "s1", "covers": ["i1", "ghost"]},  # ghost is not a seed → dangling-seed
    ])
    out = cov(tmp_path)
    assert out["coverage_ok"] == "no"
    assert "ghost" in out["coverage_errors"]


def test_dangling_dependency_fails(tmp_path):
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[
        {"slug": "s1", "covers": ["i1"], "deps": ["nope"]},  # depends on a missing story
    ])
    out = cov(tmp_path)
    assert out["coverage_ok"] == "no"
    assert "nope" in out["coverage_errors"]


# ── deferral ownership ────────────────────────────────────────────────────────


# ── C.3 probe: is there a real vacuity window on a greenfield repo? ────────────
# `doctor.run` short-circuits on a non-`full` ostler profile, and profile is inferred from
# whether `docs/epics/` is a directory. The worry was that a fresh repo could reach this gate
# on an `exploration` profile, produce no findings, and report `coverage_ok: "yes"` for an epic
# that covers nothing. These pin the actual behaviour rather than a fix applied on speculation.

def test_zero_story_epic_fails_on_a_fresh_repo(tmp_path):
    """An epic with seeds and no stories at all must fail, not pass vacuously."""
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}, {"id": "i2"}], stories=[])
    out = cov(tmp_path)
    assert out["coverage_ok"] == "no", (
        "a zero-story epic passed — doctor short-circuited on a non-full profile, so this "
        "gate asserted nothing"
    )
    assert "i1" in out["coverage_errors"] and "i2" in out["coverage_errors"]


def test_profile_is_full_whenever_this_gate_can_run(tmp_path):
    """Why the window above is closed structurally, not just by genesis: this gate is handed an
    epic dir under `docs/epics/`, and that dir existing is exactly what flips the profile to
    `full`. There is no reachable state where the gate has an epic to check but doctor
    short-circuits."""
    from ostler.model import load
    write_epic(tmp_path, "e1", seeds=[{"id": "i1"}], stories=[{"slug": "s1", "covers": ["i1"]}])
    assert load(tmp_path).profile == "full"
