"""Typed inputs for mapping source repositories onto one documentation graph."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceScope(BaseModel):
    """One OKF surface's source root inside a repository checkout."""

    model_config = ConfigDict(frozen=True)

    surface: str = Field(min_length=1)
    root: str = "."

    @field_validator("root")
    @classmethod
    def _relative_root(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip("/") or "."
        if normalized == ".." or normalized.startswith("../"):
            raise ValueError("source scope roots must be repository-relative")
        return normalized


class SourceRepository(BaseModel):
    """One independently-versioned source checkout participating in a story diff."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    checkout: str = Field(min_length=1)
    base: str = Field(min_length=1)
    head: str = "WORKTREE"
    scopes: tuple[SourceScope, ...]

    @field_validator("scopes")
    @classmethod
    def _has_scopes(cls, value: tuple[SourceScope, ...]) -> tuple[SourceScope, ...]:
        if not value:
            raise ValueError("a source repository must declare at least one scope")
        return value


__all__ = ["SourceRepository", "SourceScope"]
