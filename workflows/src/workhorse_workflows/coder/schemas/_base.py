"""The base every agent reply and node return in this workflow derives from.

Identical in force to `author`'s and `research`'s, and here for the same two reasons,
both about how workhorse *fails*:

* **Every field has a default.** After the resilience ladder's last rung a node that
  could not be answered emits its declared output keys as `null` and the run advances
  (`workhorse/docs/GUARDRAILS.md`, "Default to the next node"). A required field would
  turn that soft failure into a hard one.
* **Unknown keys are ignored, nulls are dropped**, so a missing answer falls back to the
  field's own default instead of raising.

A defaulted `status` is `""`, which matched no YAML `cases:` entry and so took the
node's `default:` arm. Every `if` ported from such a branch keeps that arm as its `else`,
which is in every case the conservative one — an unanswered gate does not pass.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class CoderResult(BaseModel):
    """Base for every agent reply and node return in the coder workflow."""

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


__all__ = ["CoderResult"]
