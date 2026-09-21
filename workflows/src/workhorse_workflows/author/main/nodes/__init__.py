"""The non-agent work the **main** author machine sequences, grouped by subject."""
from __future__ import annotations

from workhorse_workflows.author.main.nodes._blueprint import blueprint
from workhorse_workflows.author.main.nodes.artifacts import (
    commit_author,
    validate_artifacts,
    verify_integrity,
    verify_reconcile,
)
from workhorse_workflows.author.main.nodes.config import load_config
from workhorse_workflows.author.main.nodes.coverage import validate_coverage
from workhorse_workflows.author.main.nodes.epics import select_epic, select_epic_document
from workhorse_workflows.author.main.nodes.intake import (
    adopt_backlog,
    mark_roadmap_authored,
    validate_roadmap_milestone,
)
from workhorse_workflows.author.main.nodes.planner import plan_author_step
from workhorse_workflows.author.main.nodes.stories import (
    check_mockup_needed,
    check_story_feedback,
    check_story_grounding,
    prune_bullet,
    record_attempt,
    remove_story,
    seed_story,
    select_story,
    validate_story,
)

__all__ = [
    "blueprint",
    "adopt_backlog",
    "check_mockup_needed",
    "check_story_feedback",
    "check_story_grounding",
    "commit_author",
    "load_config",
    "mark_roadmap_authored",
    "plan_author_step",
    "prune_bullet",
    "record_attempt",
    "remove_story",
    "seed_story",
    "select_epic",
    "select_epic_document",
    "select_story",
    "validate_artifacts",
    "validate_coverage",
    "validate_roadmap_milestone",
    "validate_story",
    "verify_integrity",
    "verify_reconcile",
]
