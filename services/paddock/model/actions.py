"""What each command does to the root and what it prints."""

from __future__ import annotations

from ostler.book import Action, Actor, Create, Select, Transaction, Update

from ..fixtures import ListArgs, ResumeArgs, RunArgs, RunStepArgs, SandboxRunArgs
from . import rules
from .files import BROKEN_BENCHMARK, BROKEN_HOME, BROKEN_TASKS, CONFIG, DATA_COMMITTED, DATA_HEAD, EMPTY_ROOT, FileRecord
from .changes import settle, start, write
from .rounds import TASKS, listing, play, task_named
from .state import Root, root_is_empty, rounds_of


class ListBenchmarks(Action[ListArgs, Root]):
    accept = ListArgs
    rules = (rules.list_home_unreadable, rules.list_beside_a_broken_benchmark)

    @staticmethod
    def reduce(a: ListArgs, s: Root, by: Actor | None) -> Transaction:
        if root_is_empty(s):
            return Transaction(says=("no benchmarks in <sandbox>/empty/gold",))
        return Transaction(says=listing())


class RunTask(Action[RunArgs, Root]):
    accept = RunArgs
    rules = (rules.run_home_unreadable, rules.run_no_benchmark, rules.run_no_benchmark_beside_broken,
             rules.run_no_benchmark_in_empty_root, rules.run_no_task, rules.run_uncommitted, rules.round_stopped)

    @staticmethod
    def reduce(a: RunArgs, s: Root, by: Actor | None) -> Transaction:
        return start(s, a)


class RunTaskThatFails(Action[RunStepArgs, Root]):
    accept = RunStepArgs
    rules = (rules.run_step_home_unreadable, rules.step_no_round_starts, rules.step_raised, rules.step_misread_an_input,
             rules.step_ran_a_missing_command)

    @staticmethod
    def reduce(a: RunStepArgs, s: Root, by: Actor | None) -> Transaction:
        return start(s, a)


class ResumeTask(Action[ResumeArgs, Root]):
    accept = ResumeArgs
    rules = (rules.resume_home_unreadable, rules.resume_no_benchmark, rules.resume_no_benchmark_beside_broken,
             rules.resume_no_benchmark_in_empty_root, rules.resume_no_task, rules.no_round_to_resume,
             rules.no_such_round_to_resume, rules.round_already_finished,
             rules.second_round_already_finished)

    @staticmethod
    def reduce(a: ResumeArgs, s: Root, by: Actor | None) -> Transaction:
        task = task_named(a.task)
        assert task is not None
        round_ = [r for r in rounds_of(s, a.task) if r.open and (a.n is None or r.n == a.n)][-1]
        played = play(s, task, round_.pinned, round_.finished)
        return settle(s, task, played, round_.pinned, round_.n, round_.segments)


class SandboxRun(Action[SandboxRunArgs, Root]):
    accept = SandboxRunArgs
    rules = (rules.no_command, rules.unreadable_config, rules.no_login_for, rules.not_isolated, rules.needs_a_workdir,
             rules.workdir_names_no_app)

    @staticmethod
    def reduce(a: SandboxRunArgs, s: Root, by: Actor | None) -> Transaction:
        return Transaction()


class StopRound(Action[object, Root]):
    @staticmethod
    def reduce(a: object, s: Root, by: Actor | None) -> Transaction:
        return start(s, RunArgs(task="interrupt"))


class ListFiles(Action[object, Root]):
    @staticmethod
    def reduce(a: object, s: Root, by: Actor | None) -> Select[FileRecord]:
        return Select(s.files, order=lambda f: f.path)


class CommitData(Action[object, Root]):
    @staticmethod
    def reduce(a: object, s: Root, by: Actor | None) -> Transaction:
        return Transaction(write(s, DATA_HEAD, DATA_COMMITTED))


class AddBrokenBenchmark(Action[object, Root]):
    @staticmethod
    def reduce(a: object, s: Root, by: Actor | None) -> Transaction:
        return Transaction(write(s, BROKEN_BENCHMARK, BROKEN_TASKS))


class BreakHomeConfig(Action[object, Root]):
    @staticmethod
    def reduce(a: object, s: Root, by: Actor | None) -> Transaction:
        return Transaction(write(s, CONFIG, BROKEN_HOME))


class EmptyRoot(Action[object, Root]):
    @staticmethod
    def reduce(a: object, s: Root, by: Actor | None) -> Transaction:
        return Transaction(write(s, CONFIG, EMPTY_ROOT))


class KeepResults(Action[object, Root]):
    @staticmethod
    def reduce(a: object, s: Root, by: Actor | None) -> Transaction:
        changes: list[Create | Update] = []
        for task in TASKS:
            done = [r for r in rounds_of(s, task.name) if not r.open]
            if done:
                changes.append(write(s, f"kept/{task.name}.ledger.json", *done[-1].ledger))
                changes.append(write(s, f"kept/{task.name}.score.json", *done[-1].score))
        return Transaction(*changes)
