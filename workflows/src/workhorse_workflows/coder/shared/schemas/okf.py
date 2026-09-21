"""The diff-to-OKF context packet's two gate results, shared by `docs` and `qa`."""
from __future__ import annotations

from typing import Any, Literal

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class OkfContextResult(CoderResult):
    """`ostler qa context` / `ostler qa context-validate` — the packet, and whether it holds."""

    status: Literal["passed", "invalid"] = "invalid"
    notes: str = ""
    ostler: dict[str, Any] = {}


__all__ = ["OkfContextResult"]
