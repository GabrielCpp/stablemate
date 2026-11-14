"""What the python book flow's commands and turns say."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BookGate(BaseModel):
    """What one of the book's own commands said: its exit code and the tail of its output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_code: int
    output: str = ""


class MissingList(BookGate):
    """What the book's missing said, with the files no element names."""

    unnamed: tuple[str, ...] = ()


class BookEntries(BaseModel):
    """The entry files of the app that the book does not describe yet."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    entries: list[str] = Field(default_factory=list, description="Each entry file, spelled exactly as the list above spells it.")
    how: str = Field(default="", description="The file of the app that declares its pages.")


class PythonBookReply(BaseModel):
    """What the owner's turn says it did, or what stopped it."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    done: str = ""
    blocked: str = ""


class PythonBookOutcome(BaseModel):
    """The book the run committed, and how many laps it took."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    service: str
    laps: int
