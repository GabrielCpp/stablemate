"""Node registry for the standalone story-split flow."""
from __future__ import annotations

from workhorse.pyflow import Blueprint

blueprint = Blueprint("author-story-split")

__all__ = ["blueprint"]
