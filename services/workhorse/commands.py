"""The workhorse loop runner commands the book plays: what a person types, and every way each one can end."""

from __future__ import annotations

from ostler.book import STDERR, Bool, Command, Exit, Field, Files, Flag, Lines, Object, Positional, Str, Switch

from .model.actions import AnswerInbox, DrawGraph, DryRun, ListFiles, ReadInbox, RefuseEnvironment, RefuseReplay, ShowVersion, SteerRun
from .model.files import MARKS

DIGITS = tuple("0123456789")


def _app(*paths: str) -> tuple[str, ...]:
    return tuple(f"workhorse/workhorse/{path}" for path in paths)


LOOP = _app(
    "artifacts.py",
    "cli/__init__.py",
    "cli/params.py",
    "cli/parser.py",
    "config_run.py",
    "context.py",
    "control.py",
    "gates.py",
    "gitstate.py",
    "job.py",
    "logsetup.py",
    "manifest.py",
    "otel.py",
    "packaged.py",
    "profile.py",
    "records.py",
    "references.py",
    "reload.py",
    "rundir.py",
    "scratch.py",
    "sessions.py",
    "templates.py",
    "turnkey.py",
    "worklist.py",
    "pyflow/activity.py",
    "pyflow/blueprint.py",
    "pyflow/driver.py",
    "pyflow/engine.py",
    "pyflow/errors.py",
    "pyflow/graph.py",
    "pyflow/names.py",
    "pyflow/park.py",
    "pyflow/preflight.py",
    "pyflow/prompts.py",
    "pyflow/registry.py",
    "pyflow/replies.py",
    "pyflow/run.py",
    "pyflow/transitions.py",
    "pyflow/workflow.py",
    "pyflow/workspace_worktrees.py",
    "pyflow/worktree.py",
    "runner/acp.py",
    "runner/caps.py",
    "runner/extract.py",
    "runner/failure.py",
    "runner/ladder.py",
    "runner/process.py",
    "runner/redact.py",
    "runner/reframe.py",
    "runner/spec.py",
    "runner/transcript.py",
    "runner/turn_record.py",
    "runner/usage.py",
    "runner/waits.py",
    "runner/worktree_guard.py",
    "runner/backends/__init__.py",
    "runner/backends/claude.py",
    "runner/backends/cline.py",
    "runner/backends/codex.py",
    "runner/backends/copilot.py",
    "runner/backends/delegates.py",
    "runner/backends/guard.py",
    "runner/backends/guard_shell.py",
    "runner/backends/jsonl.py",
    "runner/backends/model_guard.py",
    "runner/backends/null.py",
    "runner/backends/opencode.py",
    "runner/backends/policy.py",
    "runner/backends/registry.py",
    "runner/backends/turn.py",
)

RUN = Field(Str(classes={"the parked run": "parked", "the finished run": "finished"}), required=False, does="the run to act on, by name or directory; the newest unfinished run when left out")


class Run(Command):
    does = "Start the loop runner against the agent backend and the configuration the flags name."
    program = "workhorse-loop-runner"
    argv = (
        "run",
        "--dry-run",
        Flag("--runs-dir", "runs_dir"),
        Flag("--params", "params"),
        Flag("--params-file", "params_file"),
        Flag("--cli", "cli"),
        Flag("--profile", "profile"),
        Flag("--config", "config"),
        Flag("--workspace", "workspace"),
        Flag("--context-file", "context_file"),
        Flag("--resume-run", "resume_run"),
    )
    args = Object(
        "RunArgs",
        runs_dir=Field(Str(classes={"a folder": "elsewhere", "the default folder": ".agents/runs"}), required=False, does="where the run directory is written; .agents/runs when left out"),
        params=Field(
            Str(classes={"text that is not JSON": "nope", "JSON that is not an object": "[1]"}),
            required=False,
            does="the run's parameters as a JSON object",
        ),
        params_file=Field(Str(classes={"a file that does not exist": "nope"}), required=False,
                          does="a file holding the run's parameters"),
        cli=Field(Str(classes={"a backend the runner does not know": "nope"}), required=False,
                  does="the agent backend to drive"),
        profile=Field(Str(classes={"a profile the home config does not define": "nope"}), required=False,
                      does="the home config profile that picks the backend"),
        config=Field(Str(classes={"a config file that does not exist": "nope"}), required=False,
                     does="the home config file"),
        workspace=Field(Str(classes={"a workspace the home config does not name": "nope"}), required=False,
                        does="the workspace to enter before the run starts"),
        context_file=Field(Str(classes={"a file that does not exist": "nope"}), required=False,
                           does="a file whose text is handed to the run as context"),
        resume_run=Field(Str(classes={"a run that does not exist": "nope"}), required=False,
                         does="an earlier run to continue instead of starting a new one"),
    )
    answers = (
        Exit(0, Lines(), "the dry run walks the loop to its end, prints where its artifacts went, and finishes the run"),
        Exit(1, STDERR, "the flags name something the runner cannot find or read"),
        Exit(2, STDERR, "two flags that cannot be given together were given together"),
    )
    carries = DryRun
    source = ("workhorse/workhorse/cli/run.py::run", "workhorse/workhorse/cli/run.py::invocation", *LOOP)


class Dot(Command):
    does = "Print the loop runner's flow as a Graphviz graph, or write it to a file."
    program = "workhorse-loop-runner"
    argv = ("dot", Flag("-o", "out"), Flag("--name", "name"), Flag("--flow", "flow"))
    args = Object(
        "DotArgs",
        name=Field(Str(classes={"a graph name": "flow", "a graph name with an underscore": "my_flow"}), required=False, does="the graph's name; loop_runner when left out"),
        out=Field(Str(classes={"a file name": "flow.dot", "another file name": "graph.dot"}), required=False, does="a file to write instead of printing to the terminal"),
        flow=Field(Str(classes={"the runner's one flow": "default", "a flow the runner does not have": "nope"}), required=False, does="the one flow to draw; every flow when left out"),
    )
    answers = (
        Exit(0, Lines(), "the graph is printed, or written to the named file"),
        Exit(1, STDERR, "the runner has no flow of that name"),
    )
    carries = DrawGraph
    source = ("workhorse/workhorse/cli/dot.py::run", *_app("pyflow/dot.py", "pyflow/graph.py", "packaged.py"))


class Version(Command):
    does = "Print the version of the installed workhorse package."
    program = "workhorse-loop-runner"
    argv = ("version",)
    args = Object("VersionArgs")
    answers = (Exit(0, Lines(opaque=DIGITS), "the version number is printed"),)
    carries = ShowVersion
    source = ("workhorse/workhorse/cli/version.py::run",)


class Control(Command):
    does = "Steer one run of the loop runner: read its checkpoint, rewind it to an earlier state, or switch its backend."
    program = "workhorse-loop-runner"
    argv = (
        "control",
        Positional("verb"),
        Positional("name"),
        Flag("--run", "run"),
        Flag("--to", "to"),
        Flag("--keep", "keep"),
        Flag("--param", "param"),
        Flag("--param-from-turn", "param_from_turn"),
        Switch("--params", "params"),
        Switch("--core", "core"),
        Switch("--at-boundary", "at_boundary"),
        Switch("--wait", "wait"),
        Flag("--text", "text"),
    )
    args = Object(
        "ControlArgs",
        verb=Field(
            Str(classes={"a switch with no backend named": "switch-cli", "a resume of a run that never launched": "resume"}),
            required=False,
            does="what to do to the run: status, rewind, resume, switch-cli",
        ),
        name=Field(Str(classes={"a backend": "claude", "another backend": "codex"}), required=False, does="the backend a switch moves the run onto"),
        run=RUN,
        to=Field(Str(classes={"a state the flow does not have": "nowhere"}), required=False,
                 does="the state a rewind moves the run back to"),
        keep=Field(Str(classes={"a param the run holds": "stale", "a param the run does not hold": "zzz"}), required=False, does="the params a rewind keeps"),
        param=Field(Str(classes={"a param written without a value": "bad", "a param the flow does not declare": "n=3"}),
                    required=False, does="a param a rewind sets, written NAME=VALUE"),
        param_from_turn=Field(Str(classes={"a turn file that cannot be read": "x=nofile"}), required=False,
                              does="a param a rewind takes from a turn's output, written NAME=FILE"),
        params=Field(Bool(), required=False, does="read the run's params from its checkpoint on disk"),
        core=Field(Bool(), required=False, does="reload the core of a live run"),
        at_boundary=Field(Bool(), required=False, does="apply a switch at the next turn boundary"),
        wait=Field(Bool(), required=False, does="wait for a stopping run to end"),
        text=Field(Str(classes={"a short answer": "go ahead", "an answer of several words": "yes, go ahead and ship it"}), required=False, does="the answer a live run is given"),
    )
    answers = (
        Exit(0, Lines(opaque=("  backup:",)), "the checkpoint is printed, or the rewind is applied and described"),
        Exit(1, STDERR, "the run, the verb or the arguments cannot be acted on, and the checkpoint is left as it was"),
    )
    carries = SteerRun
    source = (
        "workhorse/workhorse/cli/control.py::run",
        "workhorse/workhorse/cli/offline.py::run_rewind",
        "workhorse/workhorse/cli/offline.py::print_params",
        "workhorse/workhorse/cli/target.py::resolve_target",
        *_app("control.py", "reload.py", "rewind.py", "rundir.py", "records.py"),
    )


class InboxRead(Command):
    does = "List the messages a run has put to its operator."
    program = "workhorse-loop-runner"
    argv = ("inbox", "read", Flag("--run", "run"), Switch("--all", "all"))
    args = Object(
        "InboxReadArgs",
        run=RUN,
        all=Field(Bool(), required=False, does="list answered messages too; only the open ones when left out"),
    )
    answers = (
        Exit(0, Lines(opaque=("[m",)), "the messages are listed, or the inbox is said to be empty"),
        Exit(1, STDERR, "no run matches"),
    )
    carries = ReadInbox
    source = ("workhorse/workhorse/cli/inbox.py::run", "workhorse/workhorse/cli/target.py::resolve_target")


class InboxReply(Command):
    does = "Answer one message in a run's inbox."
    program = "workhorse-loop-runner"
    argv = ("inbox", "reply", Positional("message"), Positional("text"), Flag("--run", "run"))
    args = Object(
        "InboxReplyArgs",
        message=Field(Str(classes={"a message the inbox does not hold": "m9"}), required=False,
                      does="the message to answer"),
        text=Field(Str(classes={"a short answer": "go ahead", "an answer of several words": "yes, go ahead and ship it"}), required=False, does="the answer"),
        run=RUN,
    )
    answers = (
        Exit(0, Lines(), "the answer is stored on the message and acknowledged"),
        Exit(1, STDERR, "the run, the message or the answer is missing"),
    )
    carries = AnswerInbox
    source = ("workhorse/workhorse/cli/inbox.py::run", "workhorse/workhorse/inbox.py::reply")


class Replay(Command):
    does = "Re-run one turn of a run from its recorded input."
    program = "workhorse-loop-runner"
    argv = ("replay", Positional("turn"), Flag("--run", "run"))
    args = Object(
        "ReplayArgs",
        turn=Field(Str(classes={"a turn directory that does not exist": "nope", "a turn directory with a number": "t1"}), does="the turn directory to replay"),
        run=Field(Str(classes={"the parked run": "parked", "the finished run": "finished"}), does="the run to act on, by name or directory"),
    )
    answers = (Exit(1, STDERR, "the run or the turn cannot be found"),)
    carries = RefuseReplay
    source = ("workhorse/workhorse/cli/replay.py::run", *_app("rundir.py", "runner/turn_record.py"))


class CheckEnvironment(Command):
    does = "Compare what an agent turn loads with what a plain session of the same CLI loads."
    program = "workhorse-loop-runner"
    argv = ("environment", Flag("--profile", "profile"), Flag("--config", "config"))
    args = Object(
        "EnvironmentArgs",
        profile=Field(Str(classes={"a profile the home config does not define": "nope"}), required=False,
                      does="the home config profile whose backend and models the turn runs under"),
        config=Field(Str(classes={"a config file that does not exist": "nope"}), required=False,
                     does="the home config file"),
    )
    answers = (
        Exit(1, STDERR, "the flags name a config or a profile the runner cannot find or read"),
    )
    carries = RefuseEnvironment
    source = ("workhorse/workhorse/cli/environment.py::run", "workhorse/workhorse/cli/environment.py::compare", *_app("profile.py", "runner/backends/claude.py"))


class Look(Files):
    does = "List the watched files of the sandbox with the strings each holds."
    marks = MARKS
    carries = ListFiles
    source = ("workhorse/workhorse/rewind.py::rewind", "workhorse/workhorse/inbox.py::reply")


ALL = (Run, Dot, Version, Control, InboxRead, InboxReply, Replay, CheckEnvironment, Look)
