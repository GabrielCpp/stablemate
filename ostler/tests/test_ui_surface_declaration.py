"""``exercised: false`` on a surface index — a whole surface's obligations declared out of scope.

A legacy surface kept documented while nothing drives it still carries every normative bullet it
ever had. The declaration on ``features/<surface>/index.md`` drops the obligation-class findings
under that surface and nothing else; it is malformed when not a boolean and stale when the
surface has no node left to cover.
"""
from __future__ import annotations

import re
from pathlib import Path

from ostler import doctor
from ostler.model import load

from conftest import write

UNDECLARED = (
    "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
    "## Methods\n\n### Publish\n- returns: the published revision\n"
    "- raises: `ManifestConflict` when the revision moved\n"
)
DANGLING = (
    "---\ntype: concept\nslug: broken\ntitle: Broken\n---\n# Broken\n\n"
    "See [gone](./gone.md).\n"
)


def _codes(repo: Path) -> set[str]:
    return {f.code for f in doctor.run(load(repo)).findings}


def _finding(repo: Path, code: str):
    return next(f for f in doctor.run(load(repo)).findings if f.code == code)


def test_the_index_frontmatter_is_loaded_per_surface(repo: Path):
    write(repo / "docs/features/legacy/index.md", "---\nexercised: false\n---\n# Legacy\n")
    write(repo / "docs/features/legacy/concepts/publisher.md", UNDECLARED)
    assert load(repo).surfaces == {"legacy": {"exercised": False}}


def test_not_exercised_drops_the_obligation_findings_under_that_surface(repo: Path):
    write(repo / "docs/features/legacy/concepts/publisher.md", UNDECLARED)
    assert "undeclared-obligation" in _codes(repo)
    write(repo / "docs/features/legacy/index.md", "---\nexercised: false\n---\n")
    assert "undeclared-obligation" not in _codes(repo)


def test_the_declaration_stops_at_the_surface_boundary(repo: Path):
    write(repo / "docs/features/legacy/index.md", "---\nexercised: false\n---\n")
    write(repo / "docs/features/legacy/concepts/publisher.md", UNDECLARED)
    write(repo / "docs/features/web/concepts/publisher.md", UNDECLARED)
    kept = [f for f in doctor.run(load(repo)).findings if f.code == "undeclared-obligation"]
    assert [f.path for f in kept] == ["docs/features/web/concepts/publisher.md"]


def test_mechanical_findings_still_fire_on_a_surface_not_exercised(repo: Path):
    write(repo / "docs/features/legacy/index.md", "---\nexercised: false\n---\n")
    write(repo / "docs/features/legacy/concepts/broken.md", DANGLING)
    assert "dangling-link" in _codes(repo)


def test_exercised_true_changes_nothing(repo: Path):
    write(repo / "docs/features/legacy/index.md", "---\nexercised: true\n---\n")
    write(repo / "docs/features/legacy/concepts/publisher.md", UNDECLARED)
    codes = _codes(repo)
    assert "undeclared-obligation" in codes
    assert not codes & {"malformed-declaration", "stale-declaration"}


def test_a_non_boolean_value_is_malformed(repo: Path):
    write(repo / "docs/features/legacy/index.md", "---\nexercised: nope\n---\n")
    write(repo / "docs/features/legacy/concepts/publisher.md", UNDECLARED)
    finding = _finding(repo, "malformed-declaration")
    assert finding.severity == "error"
    assert finding.path == "docs/features/legacy/index.md"
    assert finding.ref == "legacy#exercised"
    assert "undeclared-obligation" in _codes(repo)   # a malformed declaration excuses nothing


def test_a_declaration_on_a_surface_with_no_node_is_stale(repo: Path):
    write(repo / "docs/features/legacy/index.md", "---\nexercised: false\n---\n")
    finding = _finding(repo, "stale-declaration")
    assert finding.severity == "error"
    assert finding.path == "docs/features/legacy/index.md"
    assert "delete" in finding.suggestion


def test_the_documented_obligation_class_is_the_one_the_gate_applies():
    """The class is spelled twice — a frozenset here, a sentence in `doctor-codes.md`.

    It has already drifted once: the commit that added `insensitive-check` put it in the
    documented list and in doctor's emitters and not in the frozenset, so the suppression
    the reference promised was never implemented, and nothing said so. A reader checking
    whether a code is dropped reads the prose; only the literal decides.
    """
    ref = Path(__file__).resolve().parents[2] / (
        "base-library/library/skills/ostler/okf/references/doctor-codes.md")
    # The sentence naming the class, from `exercised: false` to the period that ends it.
    sentence = re.search(r"`exercised: false`.*?obligation-class findings under that "
                         r"surface\s*—(.*?)\.\s", ref.read_text(), re.S)
    assert sentence is not None, "doctor-codes.md no longer describes the class in prose"
    assert set(re.findall(r"`([a-z0-9-]+)`", sentence.group(1))) == doctor.OBLIGATION_CODES


def test_an_unwitnessed_check_is_not_an_obligation_anyone_owes():
    """It states the harness could not build a witness, not that a claim wants a proof.

    Listing it here would suppress it under `exercised: false` for the one reason it never
    claims — and the absence has to be asserted, or the next reader adds it as a sibling of
    `insensitive-check` on the strength of the name.
    """
    assert "unwitnessed-check" not in doctor.OBLIGATION_CODES
