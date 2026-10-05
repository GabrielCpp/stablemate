"""The reply a schema declares for `--dry-run`, so the happy path lives beside the fields it fills."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from workhorse.pyflow.errors import WorkflowDefinitionError

REPLY_ATTR = "__workhorse_dry_run__"

M = TypeVar("M", bound=type[BaseModel])

_DECLARING_MODULES: set[str] = set()


def dry_run(**reply: Any) -> Callable[[M], M]:
    """Declare the reply a dry run gives for every agent turn that returns this model."""

    def declare(cls: M) -> M:
        try:
            cls.model_validate(reply)
        except ValidationError as exc:
            raise WorkflowDefinitionError(
                f"@dry_run on {cls.__qualname__} declares a reply the model rejects: {exc}"
            ) from exc
        setattr(cls, REPLY_ATTR, dict(reply))
        _DECLARING_MODULES.add(cls.__module__)
        return cls

    return declare


def declared_reply(returns: Any) -> dict[str, Any] | None:
    """The reply `returns` itself declared, never one inherited from a base model."""
    if not isinstance(returns, type):
        return None
    return returns.__dict__.get(REPLY_ATTR)


def declares_under(package: str) -> bool:
    """Whether any model in `package`, or a module beneath it, declared a dry-run reply."""
    return bool(package) and any(
        module == package or module.startswith(f"{package}.") for module in _DECLARING_MODULES
    )


__all__ = ["dry_run", "declared_reply", "declares_under"]
