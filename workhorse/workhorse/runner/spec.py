"""What the agent runner is handed: one turn's prompt, its arguments, and the outputs it is expected to produce."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class OutputSpec(BaseModel):
    key: str
    required: bool = True


class AgentNode(BaseModel):
    type: Literal["agent"]
    id: str
    prompt: str
    args: dict[str, str] = Field(default_factory=dict)
    outputs: list[OutputSpec] = Field(default_factory=list)
    power: str | None = None
    timeout: float | None = None
    retries: int | None = None
    invoke_retries: int | None = None

    @field_validator("timeout", mode="before")
    @classmethod
    def _coerce_timeout(cls, v: Any) -> Any:
        """Accept seconds as a number, or a word for 'no limit'."""
        if isinstance(v, str):
            s = v.strip().lower()
            if s in {"infinity", "inf", "infinite", "unbounded", "never"}:
                return float("inf")
            return float(s)
        return v

    cwd: str | None = None
    add_dirs: list[str] | str = Field(default_factory=list)
    activity: str | None = None
    next: str | None = None


__all__ = ["AgentNode", "OutputSpec"]
