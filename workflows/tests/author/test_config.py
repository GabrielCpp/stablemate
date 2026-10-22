from __future__ import annotations

import logging
from pathlib import Path

import pytest
import workhorse_workflows
from ostler import Ostler
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.finalize.nodes.milestone import (
    mark_milestone_authored,
    validate_milestone_epics,
)
from workhorse_workflows.author.shared.nodes.config import load_config

MILESTONE = "docs/milestones/account-access/milestone.md"
LOGGER = logging.getLogger("test.author")


def _milestone(status: str = "approved", *, epics: str = "[]", extra: str = "") -> str:
    return f"""---
type: milestone
title: Account Access
status: {status}
epics: {epics}
---

# Account Access

## Outcome

Account holders can access and recover their account.

## Release Boundary

One account-access milestone is complete when both journeys pass.

## User Journeys

### Sign in

- services: account

An account holder signs in.

## Architecture Decisions

Firebase owns authentication.

## Constraints

Existing account data remains readable.

## Acceptance

Sign-in and recovery pass end to end.

## Non-Goals

Profile editing is excluded.
{extra}"""


def _write(root: Path, slug: str = "account-access", **kwargs: str) -> Path:
    path = root / "docs/milestones" / slug / "milestone.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_milestone(**kwargs), encoding="utf-8")
    (root / "docs/services/account").mkdir(parents=True, exist_ok=True)
    return path


def test_author_config_never_invents_a_surface_inventory(tmp_path: Path) -> None:
    _write(tmp_path)
    survey_manifest = tmp_path / "docs/survey/unit-manifest.json"
    survey_manifest.parent.mkdir(parents=True)
    survey_manifest.write_text("{}\n", encoding="utf-8")
    (tmp_path / "agents.yml").write_text(
        "template:\n  surface_manifest: docs/services/inventory.json\n",
        encoding="utf-8",
    )

    config = load_config(LOGGER, repo_dir=str(tmp_path))

    assert "surface_manifest" not in config.model_dump()
    assert config.milestone_path == MILESTONE
    assert not (tmp_path / "docs/services/inventory.json").exists()


def test_epic_authoring_selects_the_approved_milestone_folder(tmp_path: Path) -> None:
    _write(tmp_path, "first", status="authored")
    _write(tmp_path, "second")
    _write(tmp_path, "third", status="proposed")

    config = load_config(LOGGER, repo_dir=str(tmp_path))

    assert config.milestone_path == "docs/milestones/second/milestone.md"


@pytest.mark.parametrize("status", ["proposed", "authored", "delivered", "superseded"])
def test_epic_authoring_fails_when_no_milestone_is_approved(tmp_path: Path, status: str) -> None:
    _write(tmp_path, status=status)

    with pytest.raises(WorkflowFailed, match="no milestone is approved.*account-access"):
        load_config(LOGGER, repo_dir=str(tmp_path))


def test_epic_authoring_fails_when_two_milestones_are_approved(tmp_path: Path) -> None:
    _write(tmp_path, "first")
    _write(tmp_path, "second")

    with pytest.raises(WorkflowFailed, match=r"2 milestones are approved.*first.*second"):
        load_config(LOGGER, repo_dir=str(tmp_path))


def test_epic_authoring_does_not_fall_back_to_a_backlog(tmp_path: Path) -> None:
    backlog = tmp_path / "docs/backlog.md"
    backlog.parent.mkdir(parents=True)
    backlog.write_text("# Backlog\n\n- A legacy item\n", encoding="utf-8")

    with pytest.raises(WorkflowFailed, match="no milestone is approved"):
        load_config(LOGGER, repo_dir=str(tmp_path))


def test_epic_authoring_fails_on_a_readiness_error_and_lists_it(tmp_path: Path) -> None:
    _write(tmp_path, extra="\n## Open Decisions\n\n- which provider\n")

    with pytest.raises(WorkflowFailed, match="milestone-open-decisions"):
        load_config(LOGGER, repo_dir=str(tmp_path))


def test_a_flat_milestone_file_is_not_an_approved_milestone(tmp_path: Path) -> None:
    flat = tmp_path / "docs/milestones/account-access.md"
    flat.parent.mkdir(parents=True)
    flat.write_text(_milestone(), encoding="utf-8")

    with pytest.raises(WorkflowFailed, match="no milestone is approved"):
        load_config(LOGGER, repo_dir=str(tmp_path))


def test_a_milestone_must_list_at_least_one_epic(tmp_path: Path) -> None:
    missing = validate_milestone_epics(LOGGER, MILESTONE, repo_dir=str(tmp_path))
    assert not missing.ok
    assert "was not found" in missing.errors

    _write(tmp_path)
    empty = validate_milestone_epics(LOGGER, MILESTONE, repo_dir=str(tmp_path))
    assert not empty.ok
    assert "lists no epics" in empty.errors

    assert Ostler(tmp_path).create_epic("account-access", "Account access").ok
    _write(tmp_path, epics="[account-access]")
    valid = validate_milestone_epics(LOGGER, MILESTONE, repo_dir=str(tmp_path))
    assert valid.ok, valid.errors


def test_epic_validation_ignores_other_milestones(tmp_path: Path) -> None:
    _write(tmp_path, epics="[account-access]")
    _write(tmp_path, "unrelated", status="proposed", epics="[missing-epic]")

    result = validate_milestone_epics(LOGGER, MILESTONE, repo_dir=str(tmp_path))

    assert result.ok, result.errors


def test_mark_milestone_authored_preserves_the_contract_body(tmp_path: Path) -> None:
    milestone = _write(tmp_path)
    before_body = milestone.read_text(encoding="utf-8").partition("\n---\n")[2]

    result = mark_milestone_authored(LOGGER, MILESTONE, repo_dir=str(tmp_path))

    after = milestone.read_text(encoding="utf-8")
    assert result.status == "authored"
    assert "status: authored" in after
    assert after.partition("\n---\n")[2] == before_body


def test_marking_an_authored_milestone_is_a_no_op(tmp_path: Path) -> None:
    milestone = _write(tmp_path, status="authored")
    before = milestone.read_text(encoding="utf-8")

    result = mark_milestone_authored(LOGGER, MILESTONE, repo_dir=str(tmp_path))

    assert result.status == "authored"
    assert milestone.read_text(encoding="utf-8") == before


@pytest.mark.parametrize("status", ["proposed", "delivered"])
def test_marking_any_other_status_raises(tmp_path: Path, status: str) -> None:
    _write(tmp_path, status=status)

    with pytest.raises(WorkflowFailed, match="must still be approved"):
        mark_milestone_authored(LOGGER, MILESTONE, repo_dir=str(tmp_path))


def test_design_prompt_has_no_inventory_write_contract() -> None:
    author = Path(workhorse_workflows.__file__).parent / "author"
    copies = sorted(author.glob("*/prompts/design-mockup.md"))
    assert copies, "no flow ships design-mockup.md"

    for path in copies:
        prompt = path.read_text(encoding="utf-8")

        assert "surface_manifest" not in prompt, path
        assert "inventory.json" not in prompt, path
        assert "manifest entry" not in prompt, path
