"""The lifecycle matrix of a benchmark root: how far it has come, and what each command does to it there."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from ostler.book import Axes, Impossible, Scene

from .. import commands as c
from .. import fixtures as f
from ..events import AddABrokenBenchmark, BreakTheHomeConfig, CommitTheData, EmptyTheRoot, StopARound
from .state import Root, stage

TODAY = date(2026, 11, 16)

COMMITTED = ("ready", "ran", "interrupted", "a-broken-benchmark")

SCENES = (
    Scene("uncommitted", "the benchmark's data folder holds files and is not a git repository", lambda today: ()),
    Scene("ready", "the data folder is a git repository with a commit and no round has run",
          lambda today: (CommitTheData(),)),
    Scene("ran", "the plain task ran once and left a result",
          lambda today: (CommitTheData(), c.RunTask(f.run("plain")))),
    Scene("interrupted", "the interrupt task stopped after its first step and left a round to resume",
          lambda today: (CommitTheData(), StopARound())),
    Scene("a-broken-benchmark", "a second benchmark whose tasks.py raises sits beside acme",
          lambda today: (CommitTheData(), AddABrokenBenchmark())),
    Scene("empty-root", "paddock_dir names a folder with no gold/", lambda today: (EmptyTheRoot(),)),
    Scene("home-config-broken", "the home config is not TOML", lambda today: (BreakTheHomeConfig(),)),
)


def in_scenes(*scenes: str, call: Callable[[Root], object]) -> Callable[[Root], object]:
    def column(m: Root) -> object:
        here = stage(m)
        if here not in scenes:
            return Impossible(f"the book does not play this command in the {here} scene")
        return call(m)

    return column


ALL = tuple(s.name for s in SCENES)

ACTIONS: dict[str, Callable[[Root], object]] = {
    "list": in_scenes(*ALL, call=lambda m: c.ListBenchmarks(f.ListArgs())),
    "run plain": in_scenes(*ALL, call=lambda m: c.RunTask(f.run("plain"))),
    "run plain pinned": in_scenes("ready", call=lambda m: c.RunTask(f.run("plain", pinned=True))),
    "run override": in_scenes("ready", call=lambda m: c.RunTask(f.run("override"))),
    "run scored": in_scenes("ready", call=lambda m: c.RunTask(f.run("scored"))),
    "run library": in_scenes("ready", call=lambda m: c.RunTask(f.run("library"))),
    "run interrupt": in_scenes("ready", "interrupted", call=lambda m: c.RunTask(f.run("interrupt"))),
    "run unknown benchmark": in_scenes("ready", "a-broken-benchmark", "empty-root",
                                       call=lambda m: c.RunTask(f.run(benchmark="nope"))),
    "run unknown task": in_scenes("ready", call=lambda m: c.RunTask(f.run("nope"))),
    "run a task that does not fail": in_scenes("ready", call=lambda m: c.RunTaskThatFails(f.run_step("override"))),
    "run a step fails": in_scenes("ready", call=lambda m: c.RunTaskThatFails(f.run_step("failing"))),
    "run a step reads a boolean as a number": in_scenes("ready", call=lambda m: c.RunTaskThatFails(f.run_step("inputs"))),
    "run a command that is not installed": in_scenes("ready", call=lambda m: c.RunTaskThatFails(f.run_step("tools"))),
    "resume interrupted": in_scenes("interrupted", call=lambda m: c.ResumeTask(f.resume("interrupt"))),
    "resume round 1": in_scenes("interrupted", call=lambda m: c.ResumeTask(f.resume("interrupt", n=1))),
    "resume a task never run": in_scenes("ready", "interrupted", call=lambda m: c.ResumeTask(f.resume("plain"))),
    "resume round 7": in_scenes("interrupted", call=lambda m: c.ResumeTask(f.resume("interrupt", n=7))),
    "resume a finished round": in_scenes("ran", call=lambda m: c.ResumeTask(f.resume("plain"))),
    "resume unknown benchmark": in_scenes("ready", "a-broken-benchmark", "empty-root",
                                          call=lambda m: c.ResumeTask(f.resume(benchmark="nope"))),
    "resume unknown task": in_scenes("ready", call=lambda m: c.ResumeTask(f.resume("nope"))),
    "sandbox no command": in_scenes("ready", call=lambda m: c.SandboxRun(f.sandbox_run(command=None))),
    "sandbox unreadable config": in_scenes("ready", call=lambda m: c.SandboxRun(f.sandbox_run(config="sbx/none.toml"))),
    "sandbox config with a login it lacks": in_scenes("ready", call=lambda m: c.SandboxRun(f.sandbox_run(config=f.GEMINI))),
    "sandbox app missing": in_scenes("ready", call=lambda m: c.SandboxRun(f.sandbox_run("sbx/apps/nodir"))),
    "sandbox two apps of one name": in_scenes("ready", call=lambda m: c.SandboxRun(f.sandbox_run(f"{f.APPS}/api", f"{f.OTHER}/api"))),
    "sandbox claude login missing": in_scenes("ready", call=lambda m: c.SandboxRun(f.sandbox_run(config=f.CLAUDE))),
    "sandbox opencode login missing": in_scenes("ready", call=lambda m: c.SandboxRun(f.sandbox_run(config=f.OPENCODE))),
    "sandbox several apps no workdir": in_scenes("ready", call=lambda m: c.SandboxRun(f.sandbox_run(f"{f.APPS}/api", f"{f.APPS}/web"))),
    "sandbox workdir names no app": in_scenes("ready", call=lambda m: c.SandboxRun(f.sandbox_run(workdir="zzz"))),
    "look": lambda m: c.Look(),
}

MATRICES = (Axes[Root]("root", TODAY, SCENES, ACTIONS, stage, state_of=lambda m, _: stage(m)),)
