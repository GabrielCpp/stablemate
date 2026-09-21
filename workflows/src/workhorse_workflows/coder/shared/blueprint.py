"""The one `Blueprint` every node module in this package decorates against."""
from __future__ import annotations

from workhorse.pyflow import Blueprint

blueprint = Blueprint("coder")

__all__ = ["blueprint"]
