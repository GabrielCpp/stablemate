"""`main` — the flat stage dispatcher a bare `workhorse-author run` starts.

`flow.py` owns setup and one artifact-derived dispatch state; [`nodes/`](nodes) holds
the deterministic planner plus shared artifact operations. Those nodes are also imported by `epic-edit` and
`story-edit`, which are the two flows that edit the same artifacts this machine writes;
what is genuinely common to *every* flow, survey included, lives in
[`../shared/`](../shared) instead.

`main` is not registered in `add_flows` — it is the entry point, which is how it was
always reached, and naming it twice would give one machine two names. The registry that
composes the distribution stays at [`../workflow.py`](../workflow.py), because the package
root is what every flow's prompt paths and the repo's `.agents/flavors/author/` resolve
against.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from workhorse_workflows.author.main.flow import Author


def __getattr__(name: str) -> Any:
    """Keep node imports from eagerly importing the composition flow."""
    if name == "Author":
        from workhorse_workflows.author.main.flow import Author

        return Author
    raise AttributeError(name)

__all__ = ["Author"]
