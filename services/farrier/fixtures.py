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


@dataclass
class VersionArgs(Fixture):
    pass


@dataclass
class DoctorArgs(Placed, Fixture):
    repo: str | None = None


@dataclass
class ConfigShowArgs(Fixture):
    key: str | None = None


@dataclass
class ConfigGetArgs(Fixture):
    key: str | None = None


@dataclass
class ConfigSetArgs(Fixture):
    assignment: str | None = None

    @property
    def setting(self) -> str:
        return (self.assignment or "").partition("=")[0]


@dataclass
class ConfigReferenceArgs(Fixture):
    key: str | None = None


@dataclass
class WorktreeDirArgs(Fixture):
    path: str | None = None


@dataclass
class LibraryDirArgs(Fixture):
    path: str | None = None


@dataclass
class BaseDirArgs(Fixture):
    path: str | None = None


@dataclass
class StablemateDirArgs(Fixture):
    path: str | None = None


@dataclass
class LibraryListArgs(Fixture):
    library: str | None = None


@dataclass
class LibraryShowArgs(Fixture):
    skill: str | None = None
    library: str | None = None


@dataclass
class LibraryCheckArgs(Fixture):
    library: str | None = None


@dataclass
class SourceArgs(Fixture):
    file: str | None = None
    library: str | None = None


@dataclass
class EjectArgs(Fixture):
    name: str | None = None
    library: str | None = None


@dataclass
class HooksListArgs(Placed, Fixture):
    repo: str | None = None


@dataclass
class HooksInstallArgs(Fixture):
    dry_run: bool | None = None


@dataclass
class ChecksArgs(Fixture):
    pass


@dataclass
class SyncArgs(Fixture):
    pass


@dataclass
class InstallUserArgs(Fixture):
    library: str | None = None
    home: str | None = None


@dataclass
class WorkflowsArgs(Fixture):
    pass


@dataclass
class WorkflowNamesArgs(Fixture):
    pass


@dataclass
class WorktreesArgs(Fixture):
    pass


LIBRARY = "lib"
SCAFFOLD = "service-gitignore"
SKILL_NAME = "acme-demo"
GENERATED = ".claude/skills/acme-demo/SKILL.md"
HOME = "home"


def init(*, repo: str | None = ".", force: bool | None = None) -> InitArgs:
    return InitArgs(repo=repo, force=force)


def install(*, repo: str | None = ".", library: str | None = LIBRARY) -> InstallArgs:
    return InstallArgs(repo=repo, library=library)


def scaffold(name: str | None = SCAFFOLD, *, dir: str | None = None, repo: str | None = ".",
             library: str | None = LIBRARY) -> ScaffoldArgs:
    return ScaffoldArgs(name=name, dir=dir, repo=repo, library=library)


def version() -> VersionArgs:
    return VersionArgs()


def doctor(*, repo: str | None = None) -> DoctorArgs:
    return DoctorArgs(repo=repo)


def config_show(key: str | None = None) -> ConfigShowArgs:
    return ConfigShowArgs(key=key)


def config_get(key: str | None = "default_cli") -> ConfigGetArgs:
    return ConfigGetArgs(key=key)


def config_set(assignment: str | None = "default_cli=codex") -> ConfigSetArgs:
    return ConfigSetArgs(assignment=assignment)


def config_reference(key: str | None = "default_cli") -> ConfigReferenceArgs:
    return ConfigReferenceArgs(key=key)


def set_worktree(path: str | None = "wt") -> WorktreeDirArgs:
    return WorktreeDirArgs(path=path)


def set_library(path: str | None = LIBRARY) -> LibraryDirArgs:
    return LibraryDirArgs(path=path)


def set_base(path: str | None = LIBRARY) -> BaseDirArgs:
    return BaseDirArgs(path=path)


def set_stablemate(path: str | None = "st") -> StablemateDirArgs:
    return StablemateDirArgs(path=path)


def library_list(*, library: str | None = LIBRARY) -> LibraryListArgs:
    return LibraryListArgs(library=library)


def library_show(skill: str | None = "demo", *, library: str | None = LIBRARY) -> LibraryShowArgs:
    return LibraryShowArgs(skill=skill, library=library)


def library_check(*, library: str | None = LIBRARY) -> LibraryCheckArgs:
    return LibraryCheckArgs(library=library)


def source(file: str | None = GENERATED, *, library: str | None = LIBRARY) -> SourceArgs:
    return SourceArgs(file=file, library=library)


def eject(name: str | None = SKILL_NAME, *, library: str | None = LIBRARY) -> EjectArgs:
    return EjectArgs(name=name, library=library)


def hooks_list(*, repo: str | None = None) -> HooksListArgs:
    return HooksListArgs(repo=repo)


def hooks_install(*, dry_run: bool | None = None) -> HooksInstallArgs:
    return HooksInstallArgs(dry_run=dry_run)


def install_user(*, library: str | None = LIBRARY, home: str | None = HOME) -> InstallUserArgs:
    return InstallUserArgs(library=library, home=home)
