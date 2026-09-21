"""`main` — the flat stage dispatcher a bare `workhorse-author run` starts."""
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
