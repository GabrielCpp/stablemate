"""The author nodes two or more machines call."""
from __future__ import annotations

from workhorse_workflows.author.shared.nodes.blueprint import blueprint
from workhorse_workflows.author.shared.nodes.commit import commit_author
from workhorse_workflows.author.shared.nodes.config import load_config
from workhorse_workflows.author.shared.nodes.coverage import validate_coverage
from workhorse_workflows.author.shared.nodes.integrity import verify_integrity
from workhorse_workflows.author.shared.nodes.stories import (
    check_story_grounding,
    record_attempt,
    validate_story,
)
from workhorse_workflows.author.shared.nodes.story_mode import (
    adopt_backlog,
    prune_bullet,
    resolve_bullet,
    seed_story,
)

__all__ = [
    "blueprint",
    "adopt_backlog",
    "check_story_grounding",
    "commit_author",
    "load_config",
    "prune_bullet",
    "record_attempt",
    "resolve_bullet",
    "seed_story",
    "validate_coverage",
    "validate_story",
    "verify_integrity",
]
