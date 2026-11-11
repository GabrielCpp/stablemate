"""What a user types after the command name, as the model reads it. A field is
named as the argument is, and left None where the user leaves the flag out."""

from __future__ import annotations

from dataclasses import dataclass

from ostler.book import Fixture


class Placed:
    """The repository a command is aimed at. No `--repo` and `.` both mean the
    directory the command runs in."""

    repo: str | None

    @property
    def here(self) -> bool:
        return self.repo in (None, ".")

    @property
    def at(self) -> str:
        return "" if self.here else f"{self.repo}/"

    @property
    def root(self) -> str:
        return "<sandbox>" if self.here else f"<sandbox>/{self.repo}"

    @property
    def typed(self) -> str:
        return "<sandbox>" if self.repo is None else str(self.repo)


@dataclass
class InitArgs(Placed, Fixture):
    repo: str | None = None
    force: bool | None = None


@dataclass
class InstallArgs(Placed, Fixture):
    repo: str | None = None
    library: str | None = None


@dataclass
class ScaffoldArgs(Placed, Fixture):
    name: str | None = None
    dir: str | None = None
    repo: str | None = None
    library: str | None = None


LIBRARY = "lib"
SCAFFOLD = "service-gitignore"


def init(*, repo: str | None = ".", force: bool | None = None) -> InitArgs:
    return InitArgs(repo=repo, force=force)


def install(*, repo: str | None = ".", library: str | None = LIBRARY) -> InstallArgs:
    return InstallArgs(repo=repo, library=library)


def scaffold(name: str | None = SCAFFOLD, *, dir: str | None = None, repo: str | None = ".",
             library: str | None = LIBRARY) -> ScaffoldArgs:
    return ScaffoldArgs(name=name, dir=dir, repo=repo, library=library)


__all__ = ["InitArgs", "InstallArgs", "LIBRARY", "SCAFFOLD", "ScaffoldArgs", "init", "install", "scaffold"]
