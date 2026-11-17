"""Why paddock says no. The message is the one it prints, word for word, with
the sandbox written `<sandbox>`. A rule reads the request (`a`) and the root (`s`)."""

from __future__ import annotations

from ostler.book import Actor, Exited, Rule

from ..fixtures import (CONFIGS, ListArgs, ResumeArgs, RunArgs, RunStepArgs, SandboxRunArgs)
from .changes import start
from .rounds import NAMES, PARK, Round, listing, task_named
from .state import Root, data_committed, has_broken_sibling, home_unreadable, root_is_empty, rounds_of

FAILED = Exited(1)
UNREADABLE = Exited(2)

Request = RunArgs | RunStepArgs | ResumeArgs


def _home_unreadable(a: ListArgs | Request, s: Root, by: Actor | None) -> bool:
    return home_unreadable(s)


def _no_such_benchmark(a: Request, s: Root, by: Actor | None) -> bool:
    return a.benchmark != "acme" and not root_is_empty(s) and not has_broken_sibling(s)


def _no_such_benchmark_beside_broken(a: Request, s: Root, by: Actor | None) -> bool:
    return a.benchmark != "acme" and has_broken_sibling(s) and not root_is_empty(s)


def _no_such_benchmark_in_empty_root(a: Request, s: Root, by: Actor | None) -> bool:
    return root_is_empty(s)


def _no_such_task(a: Request, s: Root, by: Actor | None) -> bool:
    return task_named(a.task) is None


def _uncommitted(a: Request, s: Root, by: Actor | None) -> bool:
    return not data_committed(s)


def _step_fails(task: str):
    return lambda a, s, by: a.task == task


def _no_round_starts(a: RunStepArgs, s: Root, by: Actor | None) -> bool:
    return root_is_empty(s) or task_named(a.task) is None or not data_committed(s)


def _stops(a: RunArgs, s: Root, by: Actor | None) -> bool:
    return a.task == "interrupt" and PARK not in s.files


def _open(rounds: list[Round]) -> list[Round]:
    return [r for r in rounds if r.open]


def _no_round(a: ResumeArgs, s: Root, by: Actor | None) -> bool:
    found = rounds_of(s, a.task)
    return a.n is None and not found


def _no_round_numbered(a: ResumeArgs, s: Root, by: Actor | None) -> bool:
    return a.n is not None and not [r for r in rounds_of(s, a.task) if r.n == a.n]


def _finished_at(number: int):
    def broken(a: ResumeArgs, s: Root, by: Actor | None) -> bool:
        found = [r for r in rounds_of(s, a.task) if a.n is None or r.n == a.n]
        return bool(found) and not _open(found) and found[-1].n == number

    return broken


list_home_unreadable = Rule[ListArgs, Root]("<sandbox>/config.toml: Invalid value (at line 1, column 5)", _home_unreadable, UNREADABLE,
                                            why="The home config names the benchmark root, so nothing can be listed or run without it.")
list_beside_a_broken_benchmark = Rule[ListArgs, Root](
    "\n".join(listing()),
    lambda a, s, by: has_broken_sibling(s) and not root_is_empty(s), FAILED,
    why="A benchmark that does not load is reported on stderr and makes the listing exit 1, but the others are still listed.")

run_home_unreadable = Rule[RunArgs, Root]("<sandbox>/config.toml: Invalid value (at line 1, column 5)", _home_unreadable, UNREADABLE)
run_step_home_unreadable = Rule[RunStepArgs, Root]("<sandbox>/config.toml: Invalid value (at line 1, column 5)", _home_unreadable, UNREADABLE)
resume_home_unreadable = Rule[ResumeArgs, Root]("<sandbox>/config.toml: Invalid value (at line 1, column 5)", _home_unreadable, UNREADABLE)

NO_BENCHMARK = "paddock ERROR: no benchmark named '{benchmark}' in <sandbox>/root/gold. Known: acme"
NO_BENCHMARK_BESIDE = "paddock ERROR: no benchmark named '{benchmark}' in <sandbox>/root/gold. Known: acme, broken"
NO_BENCHMARK_EMPTY = "paddock ERROR: no benchmark named '{benchmark}' in <sandbox>/empty/gold. Known: (none)"
NO_TASK = "paddock ERROR: benchmark 'acme' declares no task named '{task}'. Known: " + ", ".join(NAMES)
NOT_COMMITTED = "paddock ERROR: benchmark 'acme': <sandbox>/root/gold/acme/data is not a git repository with a commit"

run_no_benchmark = Rule[RunArgs, Root](NO_BENCHMARK, _no_such_benchmark, FAILED)
run_no_benchmark_beside_broken = Rule[RunArgs, Root](NO_BENCHMARK_BESIDE, _no_such_benchmark_beside_broken, FAILED)
run_no_benchmark_in_empty_root = Rule[RunArgs, Root](NO_BENCHMARK_EMPTY, _no_such_benchmark_in_empty_root, FAILED)
run_no_task = Rule[RunArgs, Root](NO_TASK, _no_such_task, FAILED)
run_uncommitted = Rule[RunArgs, Root](
    NOT_COMMITTED, _uncommitted, FAILED,
    why="A round is named by the commit of the data it copies, so data with no commit cannot be run.")

resume_no_benchmark = Rule[ResumeArgs, Root](NO_BENCHMARK, _no_such_benchmark, FAILED)
resume_no_benchmark_beside_broken = Rule[ResumeArgs, Root](NO_BENCHMARK_BESIDE, _no_such_benchmark_beside_broken, FAILED)
resume_no_benchmark_in_empty_root = Rule[ResumeArgs, Root](NO_BENCHMARK_EMPTY, _no_such_benchmark_in_empty_root, FAILED)
resume_no_task = Rule[ResumeArgs, Root](NO_TASK, _no_such_task, FAILED)
no_round_to_resume = Rule[ResumeArgs, Root](
    "paddock ERROR: no workspace holds an interrupted round of acme/{task} to resume", _no_round, FAILED)
no_such_round_to_resume = Rule[ResumeArgs, Root](
    "paddock ERROR: no workspace holds round {n} of acme/{task} to resume", _no_round_numbered, FAILED)
round_already_finished = Rule[ResumeArgs, Root](
    "paddock ERROR: round 1 of acme/{task} already finished: its result exists", _finished_at(1), FAILED,
    why="A result folder is the round's end. Resume continues a round that has none.")
second_round_already_finished = Rule[ResumeArgs, Root](
    "paddock ERROR: round 2 of acme/{task} already finished: its result exists", _finished_at(2), FAILED,
    why="The message names the highest round the task has, which a second run of the task makes the second.")

step_no_round_starts = Rule[RunStepArgs, Root](
    "", _no_round_starts, FAILED,
    why="A run that is refused before its first step prints its error on stderr and nothing on stdout.")

no_command = Rule[SandboxRunArgs, Root](
    "paddock ERROR: no command to run. Put it after `--`, as in `paddock sandbox run ... -- workhorse-okf-book run`",
    lambda a, s, by: a.command is None, FAILED)
unreadable_config = Rule[SandboxRunArgs, Root](
    "paddock ERROR: {config} cannot be read (No such file or directory). Name a stablemate config with --config",
    lambda a, s, by: a.config not in CONFIGS, FAILED)
no_login_for = Rule[SandboxRunArgs, Root](
    "paddock ERROR: {config} runs gemini, which the sandbox has no login for. Point the config's profiles at one of claude, opencode",
    lambda a, s, by: "gemini" in a.logins, FAILED)
not_isolated = Rule[SandboxRunArgs, Root](
    "paddock ERROR: the sandbox would not be isolated:\n{refusals}", lambda a, s, by: bool(a.refusals), FAILED,
    why="The sandbox hides the stablemate checkout, so a mount that is missing or that contains it is refused before docker starts.")
needs_a_workdir = Rule[SandboxRunArgs, Root](
    "paddock ERROR: the sandbox mounts {count} apps ({listed}) and needs --workdir to say which one the command starts in",
    lambda a, s, by: len(a.apps) > 1 and a.workdir is None, FAILED)
workdir_names_no_app = Rule[SandboxRunArgs, Root](
    "paddock ERROR: --workdir '{workdir}' names no --app. The apps are {listed}",
    lambda a, s, by: a.workdir is not None and a.workdir not in a.names, FAILED)

round_stopped = Rule[RunArgs, Root](
    "", _stops, Exited(130), does=lambda a, s, by: start(s, a),
    why="A step that raises the runner's interruption leaves its workspace and writes no result, so a later resume can continue it.")


def _a_step_failed(task: str, message: str) -> Rule[RunStepArgs, Root]:
    return Rule[RunStepArgs, Root](message, lambda a, s, by: a.task == task, FAILED, does=lambda a, s, by: start(s, a),
                                   why="A failed step ends the round's steps and is still written down, so the result says what failed.")


step_raised = _a_step_failed("failing", "ok   first  0.0s\nFAIL boom  0.0s  RuntimeError: boom\nskip later  0.0s")
step_misread_an_input = _a_step_failed(
    "inputs", "ok   read  0.0s\nFAIL misread  0.0s  TypeError: input 'strict' is bool, expected a number")
step_ran_a_missing_command = _a_step_failed(
    "tools", "ok   exit_code  0.0s\nFAIL missing_tool  0.0s  RunError: no-such-program-xyz: not on PATH")
