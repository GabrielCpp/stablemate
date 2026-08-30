from __future__ import annotations

import logging
from pathlib import Path

import pytest
import workhorse_workflows
from ostler import Ostler
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.main.nodes.config import load_config
from workhorse_workflows.author.main.nodes.intake import (
    mark_roadmap_authored,
    validate_roadmap_milestone,
)


ROADMAP = "docs/roadmaps/account-access.md"


def _roadmap(status: str = "approved", *, doc_type: str = "roadmap") -> str:
    return f"""---
type: {doc_type}
title: Account Access
status: {status}
---

# Account Access

## Outcome

Account holders can access and recover their account.

## Release Boundary

One account-access milestone is complete when both journeys pass.

## User Journeys

### Sign in

An account holder signs in.

## Architecture Decisions

Firebase owns authentication.

## Constraints

Existing account data remains readable.

## Acceptance

Sign-in and recovery pass end to end.

## Non-Goals

Profile editing is excluded.
"""


def test_author_config_never_invents_a_surface_inventory(tmp_path: Path) -> None:
    roadmap = tmp_path / ROADMAP
    roadmap.parent.mkdir(parents=True)
    roadmap.write_text(_roadmap(), encoding="utf-8")
    survey_manifest = tmp_path / "docs/survey/unit-manifest.json"
    survey_manifest.parent.mkdir(parents=True)
    survey_manifest.write_text("{}\n", encoding="utf-8")
    (tmp_path / "agents.yml").write_text(
        "template:\n  surface_manifest: docs/features/inventory.json\n",
        encoding="utf-8",
    )

    config = load_config(
        logging.getLogger("test.author"), roadmap=ROADMAP, repo_dir=str(tmp_path)
    )

    assert "surface_manifest" not in config.model_dump()
    assert config.roadmap_path == ROADMAP
    assert not (tmp_path / "docs/features/inventory.json").exists()


@pytest.mark.parametrize(
    ("status", "doc_type"),
    [("proposed", "roadmap"), ("authored", "roadmap"), ("approved", "feature")],
)
def test_epic_authoring_requires_an_approved_roadmap(
    tmp_path: Path, status: str, doc_type: str
) -> None:
    roadmap = tmp_path / ROADMAP
    roadmap.parent.mkdir(parents=True)
    roadmap.write_text(_roadmap(status, doc_type=doc_type), encoding="utf-8")

    with pytest.raises(WorkflowFailed, match="approved roadmap"):
        load_config(
            logging.getLogger("test.author"), roadmap=ROADMAP, repo_dir=str(tmp_path)
        )


def test_epic_authoring_does_not_fall_back_to_a_backlog(tmp_path: Path) -> None:
    backlog = tmp_path / "docs/backlog.md"
    backlog.parent.mkdir(parents=True)
    backlog.write_text("# Backlog\n\n- A legacy item\n", encoding="utf-8")

    with pytest.raises(WorkflowFailed, match="roadmap file is required"):
        load_config(logging.getLogger("test.author"), repo_dir=str(tmp_path))


def test_roadmap_must_source_exactly_one_nonempty_milestone(tmp_path: Path) -> None:
    logger = logging.getLogger("test.author")
    missing = validate_roadmap_milestone(logger, ROADMAP, repo_dir=str(tmp_path))
    assert not missing.ok
    assert "found 0" in missing.errors

    okf = Ostler(tmp_path)
    assert okf.create_epic("account-access", "Account access").ok
    milestones = tmp_path / "docs/milestones"
    milestones.mkdir(parents=True)
    (milestones / "account-access.md").write_text(
        "---\ntype: milestone\nid: ACME-1\ntitle: Account access\nstatus: planned\n"
        f"sourceItems:\n  - {ROADMAP}\nepics:\n  - account-access\n---\n",
        encoding="utf-8",
    )

    valid = validate_roadmap_milestone(logger, ROADMAP, repo_dir=str(tmp_path))
    assert valid.ok, valid.errors

    (milestones / "duplicate.md").write_text(
        "---\ntype: milestone\nid: ACME-2\ntitle: Duplicate\nstatus: planned\n"
        f"sourceItems:\n  - {ROADMAP}\nepics:\n  - account-access\n---\n",
        encoding="utf-8",
    )
    duplicate = validate_roadmap_milestone(logger, ROADMAP, repo_dir=str(tmp_path))
    assert not duplicate.ok
    assert "found 2" in duplicate.errors


def test_mark_roadmap_authored_preserves_the_contract_body(tmp_path: Path) -> None:
    roadmap = tmp_path / ROADMAP
    roadmap.parent.mkdir(parents=True)
    roadmap.write_text(_roadmap(), encoding="utf-8")
    before_body = roadmap.read_text(encoding="utf-8").partition("\n---\n")[2]

    result = mark_roadmap_authored(
        logging.getLogger("test.author"), ROADMAP, repo_dir=str(tmp_path)
    )

    after = roadmap.read_text(encoding="utf-8")
    assert result.status == "authored"
    assert "status: authored" in after
    assert after.partition("\n---\n")[2] == before_body


def test_design_prompt_has_no_inventory_write_contract() -> None:
    # Both flows that design a mockup ship their own copy of the envelope, and a write
    # contract reintroduced in either one is the defect this guards.
    author = Path(workhorse_workflows.__file__).parent / "author"
    copies = sorted(author.glob("*/prompts/design-mockup.md"))
    assert copies, "no flow ships design-mockup.md"

    for path in copies:
        prompt = path.read_text(encoding="utf-8")

        assert "surface_manifest" not in prompt, path
        assert "inventory.json" not in prompt, path
        assert "manifest entry" not in prompt, path
