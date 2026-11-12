"""The lifecycle matrix of a working directory: which runs it holds and what
each command does to them there."""

from __future__ import annotations

from datetime import date
from typing import Callable

from ostler.book import Axes, Scene

from ..commands import Control, Dot, InboxRead, InboxReply, Look, Replay, Run, Version
from ..events import FinishARun, ParkARun
from ..fixtures import (ANSWER, FINISHED, HELD_PARAM, MALFORMED_PARAM, MISSING, NOT_AN_OBJECT, NOT_JSON, UNHELD_PARAM,
                        UNKNOWN_PARAM, UNKNOWN_STATE, UNREADABLE_TURN, control, dot, finish, park, read_inbox, replay, reply, rewind,
                        run, status, version)
from .state import Runs, stage

TODAY = date(2026, 11, 4)

SCENES = (
    Scene("empty", "the working directory holds no run", lambda today: ()),
    Scene("parked", "a run stopped at a gate with two messages, one answered", lambda today: (ParkARun(park()),)),
    Scene("replied", "the open message of the parked run was answered",
          lambda today: (ParkARun(park()), InboxReply(reply()))),
    Scene("rewound", "the parked run was moved back to its start",
          lambda today: (ParkARun(park()), Control(rewind()))),
    Scene("finished", "the parked run is joined by a run that ended",
          lambda today: (ParkARun(park()), FinishARun(finish()))),
    Scene("dry-run", "a dry run walked the loop to its end", lambda today: (Run(run()),)),
)

ACTIONS: dict[str, Callable[[Runs], object]] = {
    "run": lambda m: Run(run()),
    "run elsewhere": lambda m: Run(run(runs_dir="elsewhere")),
    "run on a known backend": lambda m: Run(run(cli="claude")),
    "run on an unknown backend": lambda m: Run(run(cli=MISSING)),
    "run on a backend and a profile": lambda m: Run(run(cli="claude", profile=MISSING)),
    "run on an unknown profile": lambda m: Run(run(profile=MISSING)),
    "run with a missing config": lambda m: Run(run(config=MISSING)),
    "run with params that are not json": lambda m: Run(run(params=NOT_JSON)),
    "run with params that are not an object": lambda m: Run(run(params=NOT_AN_OBJECT)),
    "run with a missing params file": lambda m: Run(run(params_file=MISSING)),
    "run in an unknown workspace": lambda m: Run(run(workspace=MISSING)),
    "run with a missing context file": lambda m: Run(run(context_file=MISSING)),
    "run resuming a missing run": lambda m: Run(run(resume_run=MISSING)),
    "dot": lambda m: Dot(dot()),
    "dot named": lambda m: Dot(dot("chart")),
    "dot to a file": lambda m: Dot(dot(out="out.dot")),
    "dot named to a file": lambda m: Dot(dot("chart", "out.dot")),
    "version": lambda m: Version(version()),
    "status": lambda m: Control(status()),
    "status of the parked run": lambda m: Control(status(run="parked")),
    "status of the finished run": lambda m: Control(status(run=FINISHED)),
    "status of a missing run": lambda m: Control(status(run=MISSING)),
    "status with a name": lambda m: Control(control("status", name="x")),
    "status with rewind flags": lambda m: Control(control("status", to="start")),
    "status with a wait": lambda m: Control(control("status", wait=True)),
    "status with an answer": lambda m: Control(control("status", text=ANSWER)),
    "rewind": lambda m: Control(rewind()),
    "rewind the parked run": lambda m: Control(rewind(run="parked")),
    "rewind a finished run": lambda m: Control(rewind(run=FINISHED)),
    "rewind a missing run": lambda m: Control(rewind(run=MISSING)),
    "rewind to no state": lambda m: Control(rewind(to=None)),
    "rewind to an unknown state": lambda m: Control(rewind(to=UNKNOWN_STATE)),
    "rewind with a malformed param": lambda m: Control(rewind(param=MALFORMED_PARAM)),
    "rewind with an unknown param": lambda m: Control(rewind(param=UNKNOWN_PARAM)),
    "rewind with an unreadable turn": lambda m: Control(rewind(param_from_turn=UNREADABLE_TURN)),
    "rewind keeping a held param": lambda m: Control(rewind(keep=HELD_PARAM)),
    "rewind keeping a param not held": lambda m: Control(rewind(keep=UNHELD_PARAM)),
    "rewind with a core scope": lambda m: Control(rewind(core=True)),
    "rewind with params": lambda m: Control(rewind(params=True)),
    "resume": lambda m: Control(control("resume")),
    "resume a finished run": lambda m: Control(control("resume", run=FINISHED)),
    "switch with no backend": lambda m: Control(control("switch-cli")),
    "stop with a scope": lambda m: Control(control("stop", core=True)),
    "read the inbox": lambda m: InboxRead(read_inbox()),
    "read the whole inbox": lambda m: InboxRead(read_inbox(all=True)),
    "read the inbox of the parked run": lambda m: InboxRead(read_inbox(run="parked")),
    "read the inbox of a missing run": lambda m: InboxRead(read_inbox(run=MISSING)),
    "reply to the open message": lambda m: InboxReply(reply()),
    "reply to the answered message": lambda m: InboxReply(reply("m2")),
    "reply to a missing message": lambda m: InboxReply(reply("m9")),
    "reply without text": lambda m: InboxReply(reply(text=None)),
    "reply in a missing run": lambda m: InboxReply(reply(run=MISSING)),
    "replay": lambda m: Replay(replay()),
    "replay in a missing run": lambda m: Replay(replay(run=MISSING)),
    "look": lambda m: Look(),
}

MATRICES = (Axes[Runs]("runs", TODAY, SCENES, ACTIONS, stage, state_of=lambda m, _: stage(m)),)
