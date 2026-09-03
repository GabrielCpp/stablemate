"""Where a defect the book cannot repair actually goes (`main/nodes/waivers.py`).

The waiver half of this node was never the interesting half: downgrading a finding
error→warn is what lets the loop converge, and it was already honest about it. What
was wrong is where the *fix* was filed. A backlog bullet is a dead end — nothing
selects work out of the backlog — so a real a11y code defect settled into the same
undifferentiated pile as grammar debt and stayed there. It is filed as a seed in a
queued epic now, which is the one shape the author lane reads.

`doctor` is scripted rather than provoked. Making a real book emit `ambiguous-locator`
takes a fixture larger than the finding dict it would stand in for, and doctor is not
what is under test — everything downstream of it (the epic, the queue, the seed, the
waiver, the ids) runs for real against the repo the test stands in.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from ostler import Ostler
from workhorse_workflows.okf_builder.main.nodes.waivers import SEED_EPIC, auto_waive

BOOK = "docs/features/acme"


def _finding(code: str, ref: str) -> dict:
    return {
        "severity": "error", "code": code, "path": f"{BOOK}/concepts/charge.md",
        "ref": ref, "line": 1, "waived": False,
        "message": "two controls render with the same accessible name",
        "suggestion": "give the second control a distinct name",
    }


def _scripted_doctor(monkeypatch: pytest.MonkeyPatch, *findings: dict) -> None:
    """Pin `Ostler.doctor` to a fixed report. Everything else stays real."""

    class _Outcome:
        data = {"findings": list(findings)}

    monkeypatch.setattr(Ostler, "doctor", lambda self, **_: _Outcome())


def _epic_md(repo: Path) -> Path:
    matches = sorted((repo / "docs/epics").glob(f"*{SEED_EPIC}/epic.md"))
    assert matches, sorted(p.name for p in (repo / "docs/epics").glob("*"))
    return matches[0]


def test_a_code_fix_only_defect_becomes_a_seed_in_a_queued_epic(
    booked: Path, logger: logging.Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of the split, in one drive.

    The defect must be reachable by the lane that can actually fix it, and the epic
    must be *queued* — epic selection reads the todo index and nothing else, so a seed
    in an unqueued epic is exactly as invisible as the waiver file it came from.
    """
    _scripted_doctor(monkeypatch, _finding("ambiguous-locator", f"{BOOK}/concepts/charge.md#save"))

    result = auto_waive(logger, str(booked), f"{booked}/{BOOK}", "acme")

    assert (result.waived_count, result.has_unwaivable) == (1, False), result
    assert result.seed_epic == SEED_EPIC, result

    epic = _epic_md(booked).read_text(encoding="utf-8")
    assert "## Seeds" in epic, epic
    assert "BUG(a11y/ambiguous-locator)" in epic, epic
    # The seed names the source fix and the un-waive step, not just the symptom.
    assert "give the second control a distinct name" in epic, epic
    assert "docs/doctor-waivers.json" in epic, epic
    assert "- layers: frontend" in epic, epic
    assert "- services: acme" in epic, epic

    index = (booked / "docs/epics/index.md")
    assert index.exists(), sorted(p.name for p in (booked / "docs/epics").glob("*"))
    assert SEED_EPIC in index.read_text(encoding="utf-8"), index.read_text(encoding="utf-8")


def test_the_waiver_points_at_the_seed_that_owns_the_fix(
    booked: Path, logger: logging.Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One id, two records. The waiver is the IOU's receipt, so it must carry its number.

    Without it the waiver file says a defect was accepted and gives no way to find the
    work that accepts it, which is the state this phase exists to end.
    """
    _scripted_doctor(monkeypatch, _finding("unnamed-interactive", f"{BOOK}/concepts/charge.md#row"))

    auto_waive(logger, str(booked), f"{booked}/{BOOK}", "acme")

    waivers = json.loads((booked / "docs/doctor-waivers.json").read_text(encoding="utf-8"))
    entries = waivers if isinstance(waivers, list) else waivers.get("waivers", [])
    assert len(entries) == 1, waivers
    (entry,) = entries
    assert entry.get("code") == "unnamed-interactive", entry
    sid = entry.get("backlog") or ""
    assert sid, entry
    assert f"### {sid}" in _epic_md(booked).read_text(encoding="utf-8")


def test_a_defect_a_doc_edit_could_fix_is_never_seeded(
    booked: Path, logger: logging.Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The narrow list is the safety property: an unwaivable finding writes nothing.

    Seeding a code fix for something the book itself could repair would both hide the
    real remedy and spend a work id on it.
    """
    _scripted_doctor(monkeypatch, _finding("missing-code-ref", f"{BOOK}/concepts/charge.md"))

    result = auto_waive(logger, str(booked), f"{booked}/{BOOK}", "acme")

    assert result.has_unwaivable is True, result
    assert (result.waived_count, result.seed_epic) == (0, ""), result
    assert not (booked / "docs/epics").exists() or not list(
        (booked / "docs/epics").glob(f"*{SEED_EPIC}"))
    assert not (booked / "docs/doctor-waivers.json").exists()


def test_a_second_stalled_round_reuses_the_epic_it_already_made(
    booked: Path, logger: logging.Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`create_epic` reporting "already exists" is the normal answer, not a failure.

    A run that treated it as one would either crash on the second stall or file the
    defects into a second epic nobody queued.
    """
    _scripted_doctor(monkeypatch, _finding("ambiguous-locator", f"{BOOK}/concepts/charge.md#save"))
    auto_waive(logger, str(booked), f"{booked}/{BOOK}", "acme")

    _scripted_doctor(monkeypatch, _finding("ambiguous-locator", f"{BOOK}/concepts/charge.md#next"))
    second = auto_waive(logger, str(booked), f"{booked}/{BOOK}", "acme")

    assert second.waived_count == 1, second
    assert len(sorted((booked / "docs/epics").glob(f"*{SEED_EPIC}"))) == 1
    epic = _epic_md(booked).read_text(encoding="utf-8")
    assert epic.count("BUG(a11y/ambiguous-locator)") == 2, epic
