"""What a user types after the command name, as the model reads it. A field is
named as the argument is, and left None where the user leaves the flag out."""

from __future__ import annotations

from dataclasses import dataclass

from ostler.book import Fixture

WORKFLOW = "fix-tests"
CHECK = "pytest -q"
OTHER_CHECK = "make test"
PROGRAM_DIR = "specs/demo"
CODE_ROOT = "src/demo"
OTHER_GATE = "G1"


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
class NewProgramArgs(Fixture):
    dir: str | None = None
    code_root: str | None = None
    gate: str | None = None
    set_default: bool | None = None
    force: bool | None = None

    @property
    def program_dir(self) -> str:
        """The program folder as the scaffolder trims it, without the slashes around it."""
        return str(self.dir).strip("/")

    @property
    def first_gate(self) -> str:
        return self.gate or "G0"


@dataclass
class DryRunArgs(Fixture):
    pass


@dataclass
class CoderTurnArgs(Fixture):
    turn_minutes: int | None = None


def new(name: str | None = WORKFLOW, *, check: str | None = CHECK, into: str | None = None) -> NewArgs:
    return NewArgs(name=name, check=check, into=into)


def program(dir: str | None = PROGRAM_DIR, *, code_root: str | None = CODE_ROOT, gate: str | None = None,
            set_default: bool | None = None, force: bool | None = None) -> NewProgramArgs:
    return NewProgramArgs(dir=dir, code_root=code_root, gate=gate, set_default=set_default, force=force)


def dry_run() -> DryRunArgs:
    return DryRunArgs()


def coder_turn(turn_minutes: int | None = 0) -> CoderTurnArgs:
    return CoderTurnArgs(turn_minutes=turn_minutes)


__all__ = ["CHECK", "CODE_ROOT", "CoderTurnArgs", "DryRunArgs", "NewArgs", "NewProgramArgs", "OTHER_CHECK", "OTHER_GATE", "PROGRAM_DIR",
           "WORKFLOW", "coder_turn", "dry_run", "new", "program"]
