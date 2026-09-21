"""The base every agent reply and node return in this workflow derives from."""
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
