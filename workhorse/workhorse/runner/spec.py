"""What the agent runner is handed: one turn's prompt, its arguments, and the outputs it is expected to produce."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from workhorse.runner.backends import AgentProfile


class OutputSpec(BaseModel):
    key: str
    required: bool = True


class AgentNode(BaseModel):
    type: Literal["agent"]
    id: str
    prompt: str = ""
    prompt_text: str = ""
    args: dict[str, str] = Field(default_factory=dict)
    outputs: list[OutputSpec] = Field(default_factory=list)
    power: str | None = None
    timeout: float | None = None
    retries: int | None = None
    invoke_retries: int | None = None
    agent: AgentProfile | None = None

    @model_validator(mode="after")
    def _one_source_of_prompt(self) -> "AgentNode":
        """A turn's text comes from a file or from the state's own source, never both and never neither."""
        if bool(self.prompt) == bool(self.prompt_text):
            raise ValueError(
                f"agent node '{self.id}' must set exactly one of prompt (a template "
                "path) and prompt_text (the body written in the state)"
            )
        return self

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
