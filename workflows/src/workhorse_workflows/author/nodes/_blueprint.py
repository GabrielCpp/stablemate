"""The one `Blueprint` every node module in this package decorates against.

It is its own module rather than `nodes/__init__.py` so the submodules can import it
without importing the package that imports them. `nodes/__init__.py` re-exports it, and
that re-export is the only name `workflow.py` needs.
"""
from __future__ import annotations

from workhorse.pyflow import Blueprint

blueprint = Blueprint("author")

__all__ = ["blueprint"]
