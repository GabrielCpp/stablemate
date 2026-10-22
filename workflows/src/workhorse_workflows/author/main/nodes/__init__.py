"""The non-agent work only the **main** author machine sequences."""
from __future__ import annotations

from workhorse_workflows.author.main.nodes._blueprint import blueprint
from workhorse_workflows.author.main.nodes.completion import (
    answer_below,
    check_completion,
    contract_digest,
)
from workhorse_workflows.author.main.nodes.fill import check_epic_split, fill_work

__all__ = [
    "answer_below",
    "blueprint",
    "check_completion",
    "check_epic_split",
    "contract_digest",
    "fill_work",
]
