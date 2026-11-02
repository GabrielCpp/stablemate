from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler
from workhorse_workflows.author.epic_edit.nodes.edit import snapshot_epic, validate_edit_plan
from workhorse_workflows.author.shared.schemas import (
    EditIntent,
    EpicEditPlan,
    EpicSnapshot,
    SeedChange,
    StoryChange,
)


def _snapshot(repo: Path) -> EpicSnapshot:
    return snapshot_epic(logging.getLogger("test.epic-edit"), "accounts", repo_dir=str(repo))


def test_plan_requires_force_for_removals_beyond_requested_story(tmp_path: Path) -> None:
    (tmp_path / "agents.yml").write_text("repo:\n  id_prefix: X\n", encoding="utf-8")
    okf = Ostler(tmp_path)
    assert okf.create_epic("accounts", "Accounts").ok
    assert okf.add_seed("accounts", "requested", status="researched").ok
    assert okf.add_seed("accounts", "collateral", status="researched").ok
    assert okf.create_story("accounts", "requested", "Requested", covers=["requested"]).ok
    assert okf.create_story("accounts", "collateral", "Collateral", covers=["collateral"]).ok
    snapshot = _snapshot(tmp_path)
    plan = EpicEditPlan(
        status="complete",
        epic="accounts",
        delete_epic=True,
        seed_changes=[
            SeedChange(action="remove", id="requested", disposition="drop"),
            SeedChange(action="remove", id="collateral", disposition="drop"),
        ],
        story_changes=[
            StoryChange(action="remove", slug="requested"),
            StoryChange(action="remove", slug="collateral"),
        ],
    )

    report = validate_edit_plan(
        logging.getLogger("test.epic-edit"),
        EditIntent(kind="remove-story", epic="accounts", story="requested"),
        snapshot,
        plan,
        repo_dir=str(tmp_path),
    )

    assert "[E_FORCE_REQUIRED] collateral story 'collateral'" in report.errors
    assert "[E_FORCE_REQUIRED] collateral seed 'collateral'" in report.errors
    forced = validate_edit_plan(
        logging.getLogger("test.epic-edit"),
        EditIntent(kind="remove-story", epic="accounts", story="requested", force=True),
        snapshot,
        plan,
        repo_dir=str(tmp_path),
    )
    assert forced.ok, forced.errors
