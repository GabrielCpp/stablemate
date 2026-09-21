"""The one name index shared by states and nodes."""
from __future__ import annotations

from typing import Generic, TypeVar

from workhorse.pyflow.errors import WorkflowDefinitionError

T = TypeVar("T")


class NameIndex(Generic[T]):
    """Live names → targets, plus retired names → live names."""

    def __init__(self, kind: str, owner: str = "") -> None:
        self.kind = kind
        self.owner = owner
        self._live: dict[str, T] = {}
        self._aliases: dict[str, str] = {}


    def register(self, name: str, target: T, aliases: tuple[str, ...] = ()) -> None:
        where = f" on {self.owner}" if self.owner else ""
        if name in self._live:
            raise WorkflowDefinitionError(
                f"duplicate {self.kind} name {name!r}{where}"
            )
        if name in self._aliases:
            raise WorkflowDefinitionError(
                f"{self.kind} {name!r}{where} collides with an alias of "
                f"{self._aliases[name]!r} — an alias may not shadow a live "
                f"{self.kind}; drop the alias or rename the {self.kind}"
            )
        self._live[name] = target
        for alias in aliases:
            self._alias(alias, name)

    def _alias(self, alias: str, name: str) -> None:
        where = f" on {self.owner}" if self.owner else ""
        if alias == name:
            raise WorkflowDefinitionError(
                f"{self.kind} {name!r}{where} declares itself as an alias"
            )
        if alias in self._live:
            raise WorkflowDefinitionError(
                f"alias {alias!r} of {self.kind} {name!r}{where} shadows the live "
                f"{self.kind} {alias!r} — aliases share the namespace with live names"
            )
        claimed = self._aliases.get(alias)
        if claimed is not None and claimed != name:
            raise WorkflowDefinitionError(
                f"alias {alias!r}{where} is claimed by both {self.kind} "
                f"{claimed!r} and {name!r}"
            )
        self._aliases[alias] = name

    def merge(self, other: "NameIndex[T]") -> None:
        """Fold another index in, re-raising the same collisions across owners."""
        for name, target in other._live.items():
            self.register(name, target)
        for alias, name in other._aliases.items():
            self._alias(alias, name)

    def replacing(self, targets: dict[str, T]) -> "NameIndex[T]":
        """A copy of this index with `targets` swapped in — the substitution primitive."""
        copy: NameIndex[T] = NameIndex(self.kind, owner=self.owner)
        copy._live = dict(self._live)
        copy._aliases = dict(self._aliases)
        for name, target in targets.items():
            live = self.canonical(name)
            if live is None:
                known = ", ".join(sorted(self._live)) or "(none)"
                raise WorkflowDefinitionError(
                    f"cannot replace {self.kind} {name!r}: this index has no such "
                    f"{self.kind}. Known {self.kind}s: {known}."
                )
            copy._live[live] = target
        return copy


    def live_names(self) -> list[str]:
        """The names `dot` and `--dry-run` render."""
        return list(self._live)

    def items(self) -> list[tuple[str, T]]:
        """Live name → target pairs, for callers that transform the whole index."""
        return list(self._live.items())

    def get(self, name: str) -> T | None:
        if name in self._live:
            return self._live[name]
        live = self._aliases.get(name)
        return self._live[live] if live is not None else None

    def canonical(self, name: str) -> str | None:
        """The live name `name` refers to, whether it is live or retired."""
        if name in self._live:
            return name
        return self._aliases.get(name)

    def aliases_of(self, name: str) -> list[str]:
        return [alias for alias, live in self._aliases.items() if live == name]

    def __contains__(self, name: str) -> bool:
        return self.canonical(name) is not None
