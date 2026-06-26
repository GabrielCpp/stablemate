"""Tests for the freeze/provenance trust-layer: an approved entity is pinned, and `doctor`
flags later mutation or removal (the greenfield anchor)."""
from __future__ import annotations

import json
from pathlib import Path

from conftest import epic_md, write, write_json
from ostler import doctor, freeze
from ostler.model import load


def _ids(repo: Path) -> None:
    write_json(repo / ".agents/ids.json", {"prefix": "t", "counter": 1})


def _codes(repo: Path) -> set[str]:
    return {f.code for f in doctor.run(load(repo)).findings}


def test_freeze_then_clean(repo):
    _ids(repo)
    plan = freeze.freeze(load(repo), "01-foo", by="alice")
    assert not plan.error
    plan.apply()
    # registry now records the approval with a fingerprint + provenance
    ids = json.loads((repo / ".agents/ids.json").read_text())
    assert ids["frozen"]["01-foo"]["kind"] == "story"
    assert ids["frozen"]["01-foo"]["approvedBy"] == "alice"
    assert "hash" in ids["frozen"]["01-foo"]
    # unchanged → no frozen findings
    assert "frozen-mutated" not in _codes(repo)
    assert "frozen-removed" not in _codes(repo)


def test_frozen_mutation_is_flagged(repo):
    _ids(repo)
    freeze.freeze(load(repo), "01-foo").apply()
    story = repo / "docs/epics/epic-a/stories/01-foo/story.md"
    story.write_text(story.read_text() + "\n- A new, unapproved acceptance criterion.\n")
    codes = _codes(repo)
    assert "frozen-mutated" in codes
    assert "frozen-removed" not in codes


def test_frozen_removal_is_flagged(repo):
    _ids(repo)
    freeze.freeze(load(repo), "01-foo").apply()
    # remove the story from the graph entirely (epic.md stories entry gone + story.md gone)
    write(repo / "docs/epics/epic-a/epic.md", epic_md(
        "t-1", "epic-a",
        seeds=[("seed-a1", "resolved", "first"), ("seed-a2", "resolved", "done")],
        stories=[],
    ))
    (repo / "docs/epics/epic-a/stories/01-foo/story.md").unlink()
    assert "frozen-removed" in _codes(repo)


def test_unfreeze_lifts_the_guard(repo):
    _ids(repo)
    freeze.freeze(load(repo), "01-foo").apply()
    story = repo / "docs/epics/epic-a/stories/01-foo/story.md"
    story.write_text(story.read_text() + "\nchanged\n")
    assert "frozen-mutated" in _codes(repo)
    freeze.unfreeze(load(repo), "01-foo").apply()
    assert "frozen-mutated" not in _codes(repo)


def test_freeze_unknown_entity_errors(repo):
    _ids(repo)
    plan = freeze.freeze(load(repo), "no-such-thing")
    assert plan.error and "no story slug or seed id" in plan.error


def test_freeze_without_registry_errors(repo):
    # no .agents/ids.json → freezing cannot synthesize the required registry
    plan = freeze.freeze(load(repo), "01-foo")
    assert plan.error and "registry" in plan.error


def test_freeze_a_seed(repo):
    _ids(repo)
    plan = freeze.freeze(load(repo), "seed-a1")
    assert not plan.error and plan.entry["kind"] == "seed"
    plan.apply()
    # change the seed's summary in epic.md → mutation flagged
    write(repo / "docs/epics/epic-a/epic.md", epic_md(
        "t-1", "epic-a",
        seeds=[("seed-a1", "researched", "rewritten"), ("seed-a2", "resolved", "done")],
        stories=[("01-foo", "Foo", ["seed-a1"], [])],
    ))
    assert "frozen-mutated" in _codes(repo)
