from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ostler.qa import context as qa_context
from ostler.qa.context import book_files
from ostler.qa.run import cmd_validate

CLAIMS = ["the export lands in the mailbox", "the audit line names the actor"]

UNMAPPED = {"kind": "unmapped-change", "severity": "error", "path": "app/a.py", "message": "no owner"}

PLAN = '''\
from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-story-1", story="story-1")

api = target("api")


{scenarios}
'''

SCENARIO = '''\
@scenario(target=api, mechanism="live", covers=["{cover}"])
def {name}(qa: Qa) -> None:
    """Prove the claim."""
    qa.check("the claim holds", True, actual=True, expected=True, covers=["{cover}"])
'''


@pytest.fixture
def built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    def fake(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "version": 1,
            "available": True,
            "acceptanceCriteria": [
                {"id": "ac:1", "requirement": "The export is sent."},
                {"id": "ac:2", "requirement": "The audit is written."},
            ],
            "healthFindings": [dict(UNMAPPED)],
            "obligations": [],
            "bookFiles": book_files(tmp_path, "docs/services"),
            "storyFile": None,
            "inputs": {},
        }

    monkeypatch.setattr(qa_context, "build_context", fake)
    monkeypatch.setattr(qa_context, "annotate_deferred_obligations", lambda packet: packet)
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    return spec


def _packet(spec: Path) -> dict[str, Any]:
    return json.loads((spec / "qa-okf-context.json").read_text(encoding="utf-8"))


def _plan(spec: Path, *covers: str) -> Path:
    scenarios = "\n".join(
        SCENARIO.format(cover=cover, name=f"scenario_{index}") for index, cover in enumerate(covers)
    )
    module = spec / "qa_plan.py"
    module.write_text(PLAN.format(scenarios=scenarios), encoding="utf-8")
    return module


def _claims(spec: Path, claims: list[str]) -> None:
    (spec / "qa-unreached.json").write_text(json.dumps(claims), encoding="utf-8")


def test_the_unreached_claims_replace_the_story_criteria_in_the_packet(built: Path, tmp_path: Path) -> None:
    _claims(built, CLAIMS)

    outcome = qa_context.cmd_context(tmp_path, built, base="HEAD")

    assert outcome.ok
    packet = _packet(built)
    assert [row["id"] for row in packet["acceptanceCriteria"]] == ["claim:1", "claim:2"]
    assert [row["requirement"] for row in packet["acceptanceCriteria"]] == CLAIMS
    assert packet["healthFindings"] == []


def test_no_claims_file_leaves_the_story_criteria_and_the_unmapped_change(built: Path, tmp_path: Path) -> None:
    outcome = qa_context.cmd_context(tmp_path, built, base="HEAD")

    assert not outcome.ok
    packet = _packet(built)
    assert [row["id"] for row in packet["acceptanceCriteria"]] == ["ac:1", "ac:2"]
    assert packet["healthFindings"] == [UNMAPPED]


def test_an_empty_claims_file_leaves_the_packet_with_no_criterion(built: Path, tmp_path: Path) -> None:
    _claims(built, [])

    qa_context.cmd_context(tmp_path, built, base="HEAD")

    assert _packet(built)["acceptanceCriteria"] == []


def test_a_plan_whose_covers_are_the_claims_alone_validates(built: Path, tmp_path: Path) -> None:
    _claims(built, CLAIMS)
    qa_context.cmd_context(tmp_path, built, base="HEAD")

    outcome = cmd_validate(_plan(built, "claim:1", "claim:2"), built, root=tmp_path)

    assert outcome.ok, outcome.message


def test_a_plan_that_leaves_a_claim_uncovered_is_refused(built: Path, tmp_path: Path) -> None:
    _claims(built, CLAIMS)
    qa_context.cmd_context(tmp_path, built, base="HEAD")

    outcome = cmd_validate(_plan(built, "claim:1"), built, root=tmp_path)

    assert not outcome.ok
    assert "required acceptance criterion 'claim:2' is not covered" in outcome.message


def test_a_claim_cover_is_unknown_without_a_claims_file(built: Path, tmp_path: Path) -> None:
    qa_context.cmd_context(tmp_path, built, base="HEAD")

    outcome = cmd_validate(_plan(built, "claim:1"), built, root=tmp_path)

    assert not outcome.ok
    assert "covers unknown ID 'claim:1'" in outcome.message
