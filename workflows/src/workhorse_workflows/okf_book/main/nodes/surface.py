"""What a run is told about a service it has never documented: one declaration per surface."""
from __future__ import annotations

from enum import StrEnum

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class SurfaceKind(StrEnum):
    """How a user reaches a service, which decides what its entry points are."""

    CLI = "cli"
    HTTP = "http"
    WEB = "web"
    MOBILE = "mobile"
    GRPC = "grpc"


class Surface(BaseModel):
    """One surface of one service, as the operator declares it on a cold start."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    service: str = Field(pattern=SLUG_PATTERN)
    kind: SurfaceKind
    entry: str = Field(min_length=1)
    repo: str = ""
    contract: str = ""

    @model_validator(mode="after")
    def _contract_matches_kind(self) -> Self:
        if self.kind is SurfaceKind.GRPC and not self.contract:
            raise ValueError("`contract` is required for kind `grpc`: name the folder of the repository that holds its `.proto` files")
        if self.contract and self.kind not in (SurfaceKind.GRPC, SurfaceKind.HTTP):
            raise ValueError(f"`contract` is refused for kind `{self.kind.value}`: only `grpc` and `http` surfaces carry a contract folder")
        return self
