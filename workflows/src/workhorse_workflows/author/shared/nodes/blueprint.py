"""The one `Blueprint` the author nodes several machines share decorate against."""
from __future__ import annotations

from workhorse.pyflow import Blueprint

blueprint = Blueprint("author-shared")

__all__ = ["blueprint"]
