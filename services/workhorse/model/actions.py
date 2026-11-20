"""What each command does to the sandbox and what it prints."""

from __future__ import annotations

from ostler.book import Action, Actor, Create, Select, Transaction, Update

from ..fixtures import (ANSWER, ControlArgs, DotArgs, FinishArgs, ParkArgs, InboxReadArgs, InboxReplyArgs, ReplayArgs, RunArgs, VersionArgs)
from . import rules
from .files import (FLOW, FREE, GATE, GRAPH_CHART, GRAPH_LOOP_RUNNER, M1_ANSWERED, M1_OPEN, M2_ANSWERED,
                    M2_YES, REWOUND, RUNS, STALE, TERMINAL, FileRecord, at)
from .graph import graph
from .state import DRY_RUN, Runs, held_params, holds, messages



def put(s: Runs, record: FileRecord) -> Create | Update:
    """The change that leaves this file holding exactly these strings."""
    return Update(s.files, record.path, record) if record.path in s.files else Create(s.files, record)


class DryRun(Action[RunArgs, Runs]):
    accept = RunArgs
    rules = (
        rules.config_missing,
        rules.backend_and_profile,
        rules.resume_missing,
        rules.unknown_backend,
        rules.unknown_profile,
        rules.params_not_json,
        rules.params_not_an_object,
        rules.params_file_missing,
        rules.unknown_workspace,
        rules.context_missing,
    )

    @staticmethod
    def reduce(a: RunArgs, s: Runs, by: Actor | None) -> Transaction:
        root = a.runs_dir or RUNS
        changes = (
            put(s, FileRecord.holding(at(DRY_RUN, "run.json", root), TERMINAL)),
            put(s, FileRecord.holding(at(DRY_RUN, "checkpoint.json", root), FLOW, FREE)),
            put(s, FileRecord.holding(at(DRY_RUN, "events.jsonl", root))),
        )
        says = (
            "[workhorse] starting 'loop-runner' LoopRunner (run: loop-runner-dry-run)",
            f"[workhorse] dry-run ok — every node ran its stand-in — artifacts in <sandbox>/{a.where}/loop-runner-dry-run",
        )
        return Transaction(*changes, says=says)


class DrawGraph(Action[DotArgs, Runs]):
    accept = DotArgs
    rules = (rules.unknown_flow,)

    @staticmethod
    def reduce(a: DotArgs, s: Runs, by: Actor | None) -> Transaction:
        lines = graph(a.graph)
        if a.out is None:
            return Transaction(says=lines)
        held = GRAPH_CHART if a.name == "chart" else GRAPH_LOOP_RUNNER
        return Transaction(put(s, FileRecord.holding(a.out, held)), says=())


class ShowVersion(Action[VersionArgs, Runs]):
    accept = VersionArgs

    @staticmethod
    def reduce(a: VersionArgs, s: Runs, by: Actor | None) -> Transaction:
        return Transaction()


def checkpoint(s: Runs, name: str) -> tuple[str, ...]:
    """The lines `control status --params` prints for the run's checkpoint."""
    params = held_params(s, name)
    waiting = '"gate"' if GATE in holds(s, name, "checkpoint.json") else "null"
    if params:
        body = ('  "params": {', '    "stale": 1', "  },")
    else:
        body = ('  "params": {},',)
    return ("{", '  "flow": "LoopRunner",', *body, '  "state": "start",', f'  "waiting_on": {waiting}', "}")


class SteerRun(Action[ControlArgs, Runs]):
    accept = ControlArgs
    rules = (
        rules.control_no_such_run,
        rules.control_nothing_unfinished,
        rules.rewind_flags_elsewhere,
        rules.params_elsewhere,
        rules.scope_on_offline,
        rules.wait_elsewhere,
        rules.answer_flags_elsewhere,
        rules.rewind_without_target,
        rules.rewind_finished,
        rules.param_malformed,
        rules.turn_unreadable,
        rules.state_unknown,
        rules.param_unknown,
        rules.keep_unheld_with_params,
        rules.keep_unheld_without_params,
        rules.resume_finished,
        rules.resume_unlaunched,
        rules.name_on_verb,
        rules.switch_without_name,
        rules.stop_scope,
    )

    @staticmethod
    def reduce(a: ControlArgs, s: Runs, by: Actor | None) -> Transaction:
        name = a.target
        if a.verb == "status":
            return Transaction(says=checkpoint(s, name))
        dropped = held_params(s, name)
        says = [
            f"rewound <sandbox>/{RUNS}/loop-runner-{name}: start -> start",
            "  params:  {}",
            *([f"  dropped: {', '.join(dropped)}"] if dropped else []),
            "  resume:  control resume [CLI]",
        ]
        changes = (
            put(s, FileRecord.holding(at(name, "checkpoint.json"), FLOW, FREE)),
            put(s, FileRecord.holding(at(name, "events.jsonl"), REWOUND)),
        )
        return Transaction(*changes, says=tuple(says))


def outstanding_lines(rows: tuple[tuple[str, str, str, str], ...]) -> tuple[str, ...]:
    lines: list[str] = []
    for _ident, body, reply, _when in rows:
        lines.append(f"  {body}")
        if reply:
            lines.append(f"  -> {reply}")
    return tuple(lines)


class ReadInbox(Action[InboxReadArgs, Runs]):
    accept = InboxReadArgs
    rules = (rules.read_no_such_run, rules.read_nothing_unfinished)

    @staticmethod
    def reduce(a: InboxReadArgs, s: Runs, by: Actor | None) -> Transaction:
        rows = messages(s, a.target)
        if not a.all:
            rows = tuple(r for r in rows if not r[2])
        if not rows:
            what = "messages" if a.all else "outstanding messages"
            return Transaction(says=(f"no {what} in <sandbox>/{RUNS}/loop-runner-{a.target}",))
        return Transaction(says=outstanding_lines(rows))


class AnswerInbox(Action[InboxReplyArgs, Runs]):
    accept = InboxReplyArgs
    rules = (rules.reply_no_such_run, rules.reply_nothing_unfinished, rules.reply_incomplete, rules.reply_unknown)

    @staticmethod
    def reduce(a: InboxReplyArgs, s: Runs, by: Actor | None) -> Transaction:
        path = at(a.target, "inbox.jsonl")
        held = holds(s, a.target, "inbox.jsonl")
        if a.message == "m1":
            kept = [h for h in held if h in (M2_YES, M2_ANSWERED)]
            now = {ANSWER: M1_ANSWERED, "": M1_OPEN}.get(a.text or "")
        else:
            kept = [h for h in held if h in (M1_OPEN, M1_ANSWERED)]
            now = {ANSWER: M2_ANSWERED, "yes": M2_YES}.get(a.text or "")
        record = FileRecord.holding(path, *kept, *([now] if now else []))
        return Transaction(put(s, record), says=(f"replied to [{a.message}] in <sandbox>/{RUNS}/loop-runner-{a.target}",))


class RefuseReplay(Action[ReplayArgs, Runs]):
    accept = ReplayArgs
    rules = (rules.replay_no_such_run, rules.turn_missing)

    @staticmethod
    def reduce(a: ReplayArgs, s: Runs, by: Actor | None) -> Transaction:
        return Transaction()


class ParkByHand(Action[ParkArgs, Runs]):
    accept = ParkArgs

    @staticmethod
    def reduce(a: ParkArgs, s: Runs, by: Actor | None) -> Transaction:
        return Transaction(
            put(s, FileRecord.holding(at("parked", "run.json"))),
            put(s, FileRecord.holding(at("parked", "checkpoint.json"), FLOW, GATE, STALE)),
            put(s, FileRecord.holding(at("parked", "inbox.jsonl"), M1_OPEN, M2_YES)),
        )


class FinishByHand(Action[FinishArgs, Runs]):
    accept = FinishArgs

    @staticmethod
    def reduce(a: FinishArgs, s: Runs, by: Actor | None) -> Transaction:
        return Transaction(
            put(s, FileRecord.holding(at("finished", "run.json"), TERMINAL)),
            put(s, FileRecord.holding(at("finished", "checkpoint.json"), FLOW, FREE)),
        )


class ListFiles(Action[object, Runs]):
    @staticmethod
    def reduce(a: object, s: Runs, by: Actor | None) -> Select[FileRecord]:
        return Select(s.files, order=lambda f: f.path)
