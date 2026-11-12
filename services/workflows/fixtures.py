"""What a user types after the command name, as the model reads it. A field is
named as the argument is, and left None where the user leaves the flag out."""

from __future__ import annotations

from dataclasses import dataclass

from ostler.book import Fixture

WORKFLOW = "fix-tests"
CHECK = "pytest -q"
OTHER_CHECK = "make test"


@dataclass
class NewArgs(Fixture):
    name: str | None = None
    check: str | None = None
    into: str | None = None

    @property
    def base(self) -> str:
        """The folder the workflow's distribution lands in, with its trailing slash."""
        return "" if self.into in (None, ".") else f"{str(self.into).strip('/')}/"

    @property
    def target(self) -> str:
        return f"{self.base}{self.name}"

    @property
    def shown(self) -> str:
        return f"./{self.target}"


@dataclass
class DryRunArgs(Fixture):
    pass


def new(name: str | None = WORKFLOW, *, check: str | None = CHECK, into: str | None = None) -> NewArgs:
    return NewArgs(name=name, check=check, into=into)


def dry_run() -> DryRunArgs:
    return DryRunArgs()


__all__ = ["CHECK", "DryRunArgs", "NewArgs", "OTHER_CHECK", "WORKFLOW", "dry_run", "new"]
