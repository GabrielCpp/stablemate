"""The base every agent reply and node return in this workflow derives from."""
from __future__ import annotations

from workhorse_workflows.kit.result import Result


class AuthorResult(Result):
    """Base for every agent reply and node return in the author workflow."""


__all__ = ["AuthorResult"]
