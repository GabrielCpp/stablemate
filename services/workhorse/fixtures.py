"""What a user types after the command name, as the model reads it. A field is
named as the argument is, and left None where the user leaves the flag out."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, TypedDict, Unpack

from ostler.book import Actor, Fixture


class Aimed:
    """A command aimed at one run of the loop runner. No `--run` means the newest
    run that has not finished, and the book only ever leaves one unfinished."""

    run: str | None

    @property
    def target(self) -> str:
        return self.run or PARKED

    @property
    def named(self) -> str:
        return self.run if self.run is not None else "the newest unfinished run"


@dataclass
class RunArgs(Fixture):
    runs_dir: str | None = None
    params: str | None = None
    params_file: str | None = None
    cli: str | None = None
    profile: str | None = None
    config: str | None = None
    workspace: str | None = None
    context_file: str | None = None
    resume_run: str | None = None

    @property
    def where(self) -> str:
        return self.runs_dir or ".agents/runs"

    @property
    def json_problem(self) -> str:
        try:
            json.loads(self.params or "")
        except ValueError as exc:
            return str(exc)
        return ""

    @property
    def parsed_params(self) -> object:
        return json.loads(self.params) if self.params is not None and not self.json_problem else {}

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[RunArgs]:
        return (
            run(),
            run(runs_dir="elsewhere"),
            run(cli="claude"),
            run(cli=MISSING),
            run(cli="claude", profile=MISSING),
            run(profile=MISSING),
            run(config=MISSING),
            run(params=NOT_JSON),
            run(params=NOT_AN_OBJECT),
            run(params_file=MISSING),
            run(workspace=MISSING),
            run(context_file=MISSING),
            run(resume_run=MISSING),
        )


@dataclass
class VersionArgs(Fixture):
    pass


@dataclass
class DotArgs(Fixture):
    name: str | None = None
    out: str | None = None

    @property
    def graph(self) -> str:
        return self.name or "loop_runner"


@dataclass
class ControlArgs(Aimed, Fixture):
    verb: str | None = None
    name: str | None = None
    run: str | None = None
    to: str | None = None
    keep: str | None = None
    param: str | None = None
    param_from_turn: str | None = None
    params: bool | None = None
    core: bool | None = None
    at_boundary: bool | None = None
    wait: bool | None = None
    text: str | None = None

    @property
    def param_name(self) -> str:
        return (self.param or "").partition("=")[0]

    @property
    def turn_file(self) -> str:
        return (self.param_from_turn or "").partition("=")[2]

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[ControlArgs]:
        return (
            status(),
            status(run=PARKED),
            status(run=FINISHED),
            status(run=MISSING),
            control("status", name="x"),
            control("status", to=STATE),
            control("status", wait=True),
            control("status", text=ANSWER),
            rewind(),
            rewind(run=PARKED),
            rewind(run=FINISHED),
            rewind(run=MISSING),
            rewind(to=None),
            rewind(to=UNKNOWN_STATE),
            rewind(param=MALFORMED_PARAM),
            rewind(param=UNKNOWN_PARAM),
            rewind(param_from_turn=UNREADABLE_TURN),
            rewind(keep=HELD_PARAM),
            rewind(keep=UNHELD_PARAM),
            rewind(core=True),
            rewind(params=True),
            control("resume"),
            control("resume", run=FINISHED),
            control("switch-cli"),
            control("stop", core=True),
        )


@dataclass
class InboxReadArgs(Aimed, Fixture):
    run: str | None = None
    all: bool | None = None


@dataclass
class InboxReplyArgs(Aimed, Fixture):
    message: str | None = None
    text: str | None = None
    run: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[InboxReplyArgs]:
        return (reply(), reply("m2"), reply("m9"), reply(text=None), reply(run=MISSING))


@dataclass
class ReplayArgs(Aimed, Fixture):
    turn: str | None = None
    run: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[ReplayArgs]:
        return (replay(), replay(run=MISSING))


@dataclass
class ParkArgs(Fixture):
    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[ParkArgs]:
        return () if f".agents/runs/loop-runner-{PARKED}/run.json" in state.files else (park(),)


@dataclass
class FinishArgs(Fixture):
    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[FinishArgs]:
        return () if f".agents/runs/loop-runner-{FINISHED}/run.json" in state.files else (finish(),)


PARKED = "parked"
FINISHED = "finished"
MISSING = "nope"
ANSWER = "go ahead"
NOT_JSON = "nope"
NOT_AN_OBJECT = "[1]"
BACKENDS = ("claude", "cline", "codex", "copilot", "opencode")
STATE = "start"
UNKNOWN_STATE = "nowhere"
UNKNOWN_PARAM = "n=3"
MALFORMED_PARAM = "bad"
UNREADABLE_TURN = "x=nofile"
HELD_PARAM = "stale"
UNHELD_PARAM = "zzz"


def run(**given: str | None) -> RunArgs:
    return RunArgs(**given)


def park() -> ParkArgs:
    return ParkArgs()


def finish() -> FinishArgs:
    return FinishArgs()


def version() -> VersionArgs:
    return VersionArgs()


def dot(name: str | None = None, out: str | None = None) -> DotArgs:
    return DotArgs(name=name, out=out)


class RewindFlags(TypedDict, total=False):
    name: str | None
    keep: str | None
    param: str | None
    param_from_turn: str | None
    params: bool | None
    core: bool | None
    at_boundary: bool | None
    wait: bool | None
    text: str | None


class Flags(RewindFlags, total=False):
    run: str | None
    to: str | None


def control(verb: str, **given: Unpack[Flags]) -> ControlArgs:
    return ControlArgs(verb=verb, **given)


def rewind(*, run: str | None = None, to: str | None = "start", **given: Unpack[RewindFlags]) -> ControlArgs:
    return ControlArgs(verb="rewind", run=run, to=to, **given)


def status(*, run: str | None = None) -> ControlArgs:
    return ControlArgs(verb="status", run=run, params=True)


def read_inbox(*, run: str | None = None, all: bool | None = None) -> InboxReadArgs:
    return InboxReadArgs(run=run, all=all)


def reply(message: str | None = "m1", text: str | None = ANSWER, *, run: str | None = None) -> InboxReplyArgs:
    return InboxReplyArgs(message=message, text=text, run=run)


def replay(turn: str | None = MISSING, *, run: str | None = PARKED) -> ReplayArgs:
    return ReplayArgs(turn=turn, run=run)


__all__ = [
    "ANSWER", "BACKENDS", "ControlArgs", "DotArgs", "FINISHED", "FinishArgs", "HELD_PARAM", "InboxReadArgs", "InboxReplyArgs",
    "MALFORMED_PARAM", "MISSING", "NOT_AN_OBJECT", "NOT_JSON", "PARKED", "ParkArgs", "ReplayArgs", "RunArgs", "STATE",
    "UNHELD_PARAM", "UNKNOWN_PARAM", "UNKNOWN_STATE", "UNREADABLE_TURN", "VersionArgs", "control", "dot", "finish", "park", "read_inbox", "replay", "reply", "rewind", "run", "status", "version",
]
