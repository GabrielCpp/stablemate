"""The base every agent reply and node return in this workflow derives from.

Its two rules come from how workhorse *fails*, not from how it succeeds, and they are
the same two `research/schemas.py` documents at length:

* **Every field has a default.** After the resilience ladder's last rung a node that
  could not be answered emits its declared output keys as `null` and the run advances
  (`workhorse/docs/GUARDRAILS.md`, "Default to the next node"). A required field would
  turn that soft failure into a hard one.
* **Unknown keys are ignored, nulls are dropped**, so a missing answer falls back to the
  field's own default instead of raising.

A defaulted `status` is `""`, which matches no branch — so a state that cannot get an
answer takes its else arm, and every else arm here is the conservative one.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class AuthorResult(BaseModel):
    """Base for every agent reply and node return in the author workflow."""

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


__all__ = ["AuthorResult"]
