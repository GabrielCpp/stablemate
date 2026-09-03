"""`known-defect:` — a record of a code-side fault, with two mechanical exits.

A waiver silenced a finding for as long as nobody deleted it. A `known-defect:` bullet names
the seed that fixes the code and the finding it excuses, and doctor takes it back the moment
the seed closes or the finding stops firing. Both exits fire without a human noticing.
"""
from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.model import load
from ostler.registry import declared_keys

from conftest import write
from test_ui_locators import DASH, DUPLICATE_SAVE, SAVE, _screen


def _findings(repo: Path, code: str) -> list[doctor.Finding]:
    return [f for f in doctor.run(load(repo)).findings if f.code == code]


def _excused_save(seed: str = "seed-a1", code: str = "ambiguous-locator") -> str:
    return SAVE + f"- known-defect: {seed} {code} — source renders both as `Save`\n"


def test_known_defect_is_a_declared_advisory_key():
    assert "known-defect" in declared_keys("component")
    assert "known-defect" in declared_keys("interaction")
    assert doctor.parse_known_defect("`seed-a1` ambiguous-locator — prose") == (
        "seed-a1", "ambiguous-locator")
    assert doctor.parse_known_defect("ambiguous-locator") is None


def test_an_open_seed_suppresses_exactly_that_code_on_that_node(repo: Path):
    write(repo / DASH, _screen(_excused_save(), DUPLICATE_SAVE))
    ambiguous = _findings(repo, "ambiguous-locator")
    # The other half of the pair is still ambiguous: the record is per node, not per pair.
    assert [f.ref for f in ambiguous] == [f"{DASH}#footer-save-button"]
    assert _findings(repo, "stale-defect") == []
    assert _findings(repo, "unknown-bullet") == []


def test_a_resolved_seed_makes_the_record_stale_and_the_finding_returns(repo: Path):
    write(repo / DASH, _screen(_excused_save(seed="seed-a2"), DUPLICATE_SAVE))
    assert {f.ref for f in _findings(repo, "ambiguous-locator")} == {
        f"{DASH}#save-button", f"{DASH}#footer-save-button"}
    stale = _findings(repo, "stale-defect")
    assert len(stale) == 1 and stale[0].severity == "error"
    assert "seed-a2 is resolved" in stale[0].message
    assert stale[0].ref == f"{DASH}#save-button#known-defect"


def test_an_unknown_seed_is_stale_too(repo: Path):
    write(repo / DASH, _screen(_excused_save(seed="seed-nope"), DUPLICATE_SAVE))
    stale = _findings(repo, "stale-defect")
    assert len(stale) == 1
    assert "no epic carries a seed seed-nope" in stale[0].message
    assert len(_findings(repo, "ambiguous-locator")) == 2


def test_a_finding_that_no_longer_fires_makes_the_record_stale(repo: Path):
    # No duplicate sibling: the excused collision is gone, so the bullet pre-excuses the next.
    write(repo / DASH, _screen(_excused_save()))
    stale = _findings(repo, "stale-defect")
    assert len(stale) == 1
    assert "no longer fires" in stale[0].message
    assert stale[0].suggestion == "delete the `known-defect:` bullet"


def test_the_record_excuses_one_code_not_the_node(repo: Path):
    write(repo / DASH, _screen(_excused_save(code="unnamed-interactive"), DUPLICATE_SAVE))
    # The collision still fires on both nodes; the bullet names a code that does not.
    assert len(_findings(repo, "ambiguous-locator")) == 2
    assert len(_findings(repo, "stale-defect")) == 1


def test_a_value_naming_no_seed_and_code_is_malformed(repo: Path):
    write(repo / DASH, _screen(SAVE + "- known-defect: ambiguous-locator\n", DUPLICATE_SAVE))
    bad = _findings(repo, "malformed-defect")
    assert len(bad) == 1 and bad[0].ref == f"{DASH}#save-button#known-defect"
    assert len(_findings(repo, "ambiguous-locator")) == 2


def test_exploration_profile_keeps_the_suppression_and_the_second_exit(tmp_path: Path):
    write(tmp_path / DASH, _screen(_excused_save(), DUPLICATE_SAVE))
    assert load(tmp_path).profile == "exploration"
    assert [f.ref for f in _findings(tmp_path, "ambiguous-locator")] == [
        f"{DASH}#footer-save-button"]
    assert _findings(tmp_path, "stale-defect") == []
    write(tmp_path / DASH, _screen(_excused_save()))
    assert len(_findings(tmp_path, "stale-defect")) == 1
