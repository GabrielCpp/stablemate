"""The non-agent work only the **main** coder machine calls."""
from __future__ import annotations

from workhorse_workflows.coder.main.nodes.pr import (
    flag_ci_failure,
    flag_merge_failure,
    merge_pr,
    open_pr,
    open_story_pr,
)

__all__ = [
    "flag_ci_failure",
    "flag_merge_failure",
    "merge_pr",
    "open_pr",
    "open_story_pr",
]
