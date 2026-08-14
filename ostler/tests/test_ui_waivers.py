"""`ostler doctor` waivers — an accepted defect downgrades to a warning; it is never hidden.

The contract these lock down: a waived `ambiguous-locator` stays in the report (so `doctor --json`
and a human still see it), carries its reason and backlog id, and stops counting as an error — but a
finding with no waiver is untouched, and an empty/absent register can never silence a real error.
"""
from __future__ import annotations

from pathlib import Path

from ostler import doctor, waivers
from ostler.model import load

from conftest import write
from test_ui_locators import DASH, DUPLICATE_SAVE, SAVE, _screen


def _amb(repo: Path) -> list:
    return [f for f in doctor.run(load(repo)).findings if f.code == "ambiguous-locator"]


def test_no_waiver_file_leaves_the_error_standing(repo: Path):
    write(repo / DASH, _screen(SAVE, DUPLICATE_SAVE))
    amb = _amb(repo)
    assert len(amb) == 2
    assert all(f.severity == "error" and not f.waived for f in amb)
    assert doctor.run(load(repo)).errors >= 2


def test_waiver_downgrades_to_warn_but_keeps_the_finding_visible(repo: Path):
    write(repo / DASH, _screen(SAVE, DUPLICATE_SAVE))
    # Read the real node refs off the first run rather than hardcoding the node-id format.
    for f in _amb(repo):
        waivers.add(load(repo), f.code, f.ref,
                    "known: both Save controls co-render; needs distinct aria-labels in source",
                    "fix-ambiguous-locator-dashboard-save")

    amb = _amb(repo)
    assert len(amb) == 2                                   # still reported, NOT dropped
    assert all(f.severity == "warn" and f.waived for f in amb)   # downgraded
    assert all(not f.fixable for f in amb)
    assert "fix-ambiguous-locator-dashboard-save" in amb[0].message   # backlog id surfaced
    rep = doctor.run(load(repo))
    assert rep.errors == 0                                 # no longer gates
    assert rep.warnings >= 2                               # accounted as warnings instead


def test_a_waiver_for_a_different_ref_does_not_silence_this_one(repo: Path):
    write(repo / DASH, _screen(SAVE, DUPLICATE_SAVE))
    waivers.add(load(repo), "ambiguous-locator",
                "docs/features/web/gui/screens/other.md#screen/ghost", "stale", "x")
    amb = _amb(repo)
    assert len(amb) == 2
    assert all(f.severity == "error" for f in amb)         # untouched — exact (code, ref) match only


def test_add_is_idempotent_on_code_and_ref(repo: Path):
    write(repo / DASH, _screen(SAVE, DUPLICATE_SAVE))
    ref = _amb(repo)[0].ref
    waivers.add(load(repo), "ambiguous-locator", ref, "first", "b1")
    waivers.add(load(repo), "ambiguous-locator", ref, "second", "b2")   # update, not append
    table = waivers.load(load(repo))
    from ostler.coverage import normalize_ref
    entry = table[("ambiguous-locator", normalize_ref(ref))]
    assert entry["reason"] == "second" and entry["backlog"] == "b2"
    assert len(table) == 1


def test_a_warn_level_finding_is_waivable_too(repo: Path):
    """The register is okf-builder's only exit from a warn, so it has to reach one.

    Nothing about the exit code changes — it counted errors before and after. What changes is
    the `waived` flag on a finding that was never an error: the convergence gate drains every
    finding that does not carry one, so an obligation on prose nobody will run would otherwise
    be re-queued every round until the stall bound failed the run, with no diffable way to say
    "accepted". Restricting the waiver to errors left that class with no exit at all.
    """
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n- returns: the published revision\n")

    def undeclared() -> list:
        return [f for f in doctor.run(load(repo)).findings if f.code == "undeclared-obligation"]

    standing = undeclared()
    assert standing and all(f.severity == "warn" and not f.waived for f in standing)

    waivers.add(load(repo), standing[0].code, standing[0].ref,
                "legacy surface, documented but never exercised", "backfill-legacy-obligations")

    waived = undeclared()
    assert len(waived) == len(standing)          # still reported, NOT dropped
    assert waived[0].waived and waived[0].severity == "warn"
    assert not waived[0].fixable
    assert "backfill-legacy-obligations" in waived[0].message
