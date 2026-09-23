"""What a run is told about a service it has never documented: one declaration per surface."""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class SurfaceKind(StrEnum):
    """How a user reaches a service, which decides what its entry points are."""

    CLI = "cli"
    HTTP = "http"
    WEB = "web"
    MOBILE = "mobile"


class Surface(BaseModel):
    """One surface of one service, as the operator declares it on a cold start."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    service: str = Field(pattern=SLUG_PATTERN)
    kind: SurfaceKind
    entry: str = Field(min_length=1)


class EntryPoint(BaseModel):
    """One place a user starts: a command, an endpoint, or a home screen."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str = Field(pattern=SLUG_PATTERN)
    title: str = Field(min_length=1)


class EntryPointListing(BaseModel):
    """The reply of the turn that lists a surface's entry points."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_points: tuple[EntryPoint, ...] = Field(min_length=1)
