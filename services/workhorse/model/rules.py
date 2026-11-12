"""Why workhorse's loop runner says no. The message is the one it prints, word
for word, with the sandbox written `<sandbox>`. A rule reads the request (`a`)
and the sandbox (`s`)."""

from __future__ import annotations

from ostler.book import Actor, Exited, Rule

from ..fixtures import (BACKENDS, HELD_PARAM, STATE, ControlArgs, InboxReadArgs,
                        InboxReplyArgs, ReplayArgs, RunArgs)
from .state import Runs, exists, finished, held_params, messages, unfinished

FAILED = Exited(1)
USAGE = Exited(2)
RUNS = "<sandbox>/.agents/runs"


def _no_such_run(a: ControlArgs | InboxReadArgs | InboxReplyArgs | ReplayArgs, s: Runs, by: Actor | None) -> bool:
    return a.run is not None and not exists(s, a.run)


def _nothing_unfinished(a: ControlArgs | InboxReadArgs | InboxReplyArgs, s: Runs, by: Actor | None) -> bool:
    return a.run is None and unfinished(s) is None


LOOKUP = (
    "error: no run dir for '{run}' (looked under " + RUNS + ")\n  groom at http://127.0.0.1:9 not reachable"
)
NONE_LEFT = "error: no unfinished run found under " + RUNS + " — name one with --run"
LOOKUP_WHY = "A name groom does not know either leaves the operator with the directory the lookup searched."

control_no_such_run = Rule[ControlArgs, Runs](LOOKUP, _no_such_run, FAILED, why=LOOKUP_WHY)
control_nothing_unfinished = Rule[ControlArgs, Runs](NONE_LEFT, _nothing_unfinished, FAILED)
read_no_such_run = Rule[InboxReadArgs, Runs](LOOKUP, _no_such_run, FAILED, why=LOOKUP_WHY)
read_nothing_unfinished = Rule[InboxReadArgs, Runs](NONE_LEFT, _nothing_unfinished, FAILED)
reply_no_such_run = Rule[InboxReplyArgs, Runs](LOOKUP, _no_such_run, FAILED, why=LOOKUP_WHY)
reply_nothing_unfinished = Rule[InboxReplyArgs, Runs](NONE_LEFT, _nothing_unfinished, FAILED)
replay_no_such_run = Rule[ReplayArgs, Runs](
    "error: no run dir for '{run}' under " + RUNS + "; pass the run's directory path", _no_such_run, FAILED)


def _config_missing(a: RunArgs, s: Runs, by: Actor | None) -> bool:
    return a.config is not None


def _backend_and_profile(a: RunArgs, s: Runs, by: Actor | None) -> bool:
    return a.cli is not None and a.profile is not None


def _resume_missing(a: RunArgs, s: Runs, by: Actor | None) -> bool:
    return a.resume_run is not None


def _unknown_backend(a: RunArgs, s: Runs, by: Actor | None) -> bool:
    return a.cli is not None and a.cli not in BACKENDS


def _unknown_profile(a: RunArgs, s: Runs, by: Actor | None) -> bool:
    return a.profile is not None


def _params_not_json(a: RunArgs, s: Runs, by: Actor | None) -> bool:
    return a.params is not None and bool(a.json_problem)


def _params_not_an_object(a: RunArgs, s: Runs, by: Actor | None) -> bool:
    return a.params is not None and not a.json_problem and not isinstance(a.parsed_params, dict)


def _params_file_missing(a: RunArgs, s: Runs, by: Actor | None) -> bool:
    return a.params_file is not None


def _unknown_workspace(a: RunArgs, s: Runs, by: Actor | None) -> bool:
    return a.workspace is not None


def _context_missing(a: RunArgs, s: Runs, by: Actor | None) -> bool:
    return a.context_file is not None


config_missing = Rule[RunArgs, Runs]("error: --config {config}: no such file", _config_missing, FAILED)
backend_and_profile = Rule[RunArgs, Runs](
    "error: --cli and --profile are mutually exclusive — a profile carries its own `cli` field. Drop one of them.",
    _backend_and_profile, USAGE,
    why="A profile names its own backend, so a second one on the command line would have two answers.")
resume_missing = Rule[RunArgs, Runs](
    "error: resume run dir not found for '{resume_run}' (looked under <sandbox>/{where})", _resume_missing, FAILED)
unknown_backend = Rule[RunArgs, Runs](
    "error: unknown CLI backend '{cli}' (set AGENT_CLI, --cli or the config's default_cli to one of: "
    "claude, cline, codex, copilot, opencode)", _unknown_backend, FAILED)
unknown_profile = Rule[RunArgs, Runs](
    "error: unknown profile '{profile}' in <sandbox>/config.toml (known: none defined)", _unknown_profile, FAILED)
params_not_json = Rule[RunArgs, Runs](
    "error: --params is not valid JSON: {json_problem}", _params_not_json, FAILED)
params_not_an_object = Rule[RunArgs, Runs](
    "error: --params must be a JSON object (key→value map)", _params_not_an_object, FAILED)
params_file_missing = Rule[RunArgs, Runs](
    "error: cannot read --params-file {params_file}: [Errno 2] No such file or directory: '{params_file}'",
    _params_file_missing, FAILED)
unknown_workspace = Rule[RunArgs, Runs](
    "error: --workspace {workspace}: unknown workspace '{workspace}'; known workspaces: (none)",
    _unknown_workspace, FAILED)
context_missing = Rule[RunArgs, Runs](
    "error: --context-file not found: {context_file}\nRun `make agent-install` to generate .agents/agents-context.json.",
    _context_missing, FAILED)


def _rewind_flags_elsewhere(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    given = a.to is not None or a.param is not None or a.param_from_turn is not None or a.keep is not None
    return given and a.verb != "rewind"


def _params_elsewhere(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    return bool(a.params) and a.verb != "status"


def _scope_on_offline(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    return bool(a.core or a.at_boundary) and a.verb in ("rewind", "resume")


def _wait_elsewhere(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    return bool(a.wait) and a.verb != "stop"


def _answer_flags_elsewhere(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    return a.text is not None and a.verb != "answer"


rewind_flags_elsewhere = Rule[ControlArgs, Runs](
    "error: {verb} takes no --to, --param, --param-from-turn or --keep", _rewind_flags_elsewhere, FAILED,
    why="A flag typed after the wrong verb is an error, because silence would read as a request that worked.")
params_elsewhere = Rule[ControlArgs, Runs](
    "error: {verb} takes no --params (it is `status --params`)", _params_elsewhere, FAILED)
scope_on_offline = Rule[ControlArgs, Runs](
    "error: {verb} takes no --core or --at-boundary", _scope_on_offline, FAILED)
wait_elsewhere = Rule[ControlArgs, Runs](
    "error: {verb} takes no --wait (it is `stop --wait`)", _wait_elsewhere, FAILED)
answer_flags_elsewhere = Rule[ControlArgs, Runs](
    "error: {verb} takes no --gate or --text", _answer_flags_elsewhere, FAILED)


def _rewind_without_target(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    return a.verb == "rewind" and a.to is None


def _rewind_finished(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    return a.verb == "rewind" and a.to is not None and finished(s, a.target)


def _param_malformed(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    return a.verb == "rewind" and a.to is not None and a.param is not None and "=" not in a.param


def _turn_unreadable(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    return a.verb == "rewind" and a.to is not None and a.param_from_turn is not None


def _state_unknown(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    return a.verb == "rewind" and a.to is not None and a.to != STATE


def _param_unknown(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    return a.verb == "rewind" and a.param is not None and "=" in a.param


def _keep_unheld(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    return a.verb == "rewind" and a.keep is not None and a.keep not in held_params(s, a.target)


def _keep_unheld_with_params(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    return _keep_unheld(a, s, by) and HELD_PARAM in held_params(s, a.target)


def _keep_unheld_without_params(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    return _keep_unheld(a, s, by) and not held_params(s, a.target)


REFUSED = "error: rewind refused, checkpoint unchanged: "

rewind_without_target = Rule[ControlArgs, Runs](
    "error: rewind needs the state to move to: `control rewind --to STATE`", _rewind_without_target, FAILED)
rewind_finished = Rule[ControlArgs, Runs](
    "error: rewind: " + RUNS + "/loop-runner-{target} already finished (terminal)", _rewind_finished, FAILED,
    why="A run that finished has no checkpoint left to move; only a stopped or failed run can be rewound.")
param_malformed = Rule[ControlArgs, Runs]("error: --param wants NAME=VALUE, got '{param}'", _param_malformed, FAILED)
turn_unreadable = Rule[ControlArgs, Runs](
    "error: --param-from-turn: cannot read " + RUNS + "/loop-runner-{target}/{turn_file}: "
    "[Errno 2] No such file or directory: '" + RUNS + "/loop-runner-{target}/{turn_file}'", _turn_unreadable, FAILED)
state_unknown = Rule[ControlArgs, Runs](
    REFUSED + "LoopRunner has no state '{to}'. Known states: start. If it was renamed, declare @state(aliases=['{to}']) "
    "on the state that replaced it so runs checkpointed under the old name can resume.", _state_unknown, FAILED,
    why="A checkpoint that names a state the flow no longer has could never be resumed, so the move is refused before it is written.")
param_unknown = Rule[ControlArgs, Runs](
    REFUSED + "checkpoint gives state 'start' the parameter(s) {param_name}, which it does not have. "
    "Its parameters are: (none).", _param_unknown, FAILED)
keep_unheld_with_params = Rule[ControlArgs, Runs](
    REFUSED + "--keep names {keep}, which the checkpoint does not hold. It holds: stale", _keep_unheld_with_params, FAILED)
keep_unheld_without_params = Rule[ControlArgs, Runs](
    REFUSED + "--keep names {keep}, which the checkpoint does not hold. It holds: (none)", _keep_unheld_without_params, FAILED)


def _resume_finished(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    return a.verb == "resume" and finished(s, a.target)


def _resume_unlaunched(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    return a.verb == "resume"


resume_finished = Rule[ControlArgs, Runs](
    "error: resume: " + RUNS + "/loop-runner-{target} already finished (terminal)", _resume_finished, FAILED)
resume_unlaunched = Rule[ControlArgs, Runs](
    "error: resume: no usable launch.json in " + RUNS + "/loop-runner-{target} ([Errno 2] No such file or directory: '"
    + RUNS + "/loop-runner-{target}/launch.json') — run `<workflow> run --resume-run " + RUNS + "/loop-runner-{target}` by hand",
    _resume_unlaunched, FAILED,
    why="Only a run that was started with a recorded launch can be relaunched from its directory.")


def _name_on_verb(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    plain = a.verb in ("reload", "stop", "status", "questions", "answer")
    return bool(a.name) and plain and not (a.verb == "status" and a.params)


def _switch_without_name(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    return a.verb == "switch-cli" and not a.name


def _stop_scope(a: ControlArgs, s: Runs, by: Actor | None) -> bool:
    return a.verb == "stop" and bool(a.core or a.at_boundary)


name_on_verb = Rule[ControlArgs, Runs]("error: {verb} takes no name (got '{name}')", _name_on_verb, FAILED)
switch_without_name = Rule[ControlArgs, Runs](
    "error: switch-cli needs the name to switch to, e.g. `control switch-cli claude`", _switch_without_name, FAILED)
stop_scope = Rule[ControlArgs, Runs]("error: stop takes no --core or --at-boundary", _stop_scope, FAILED)


def _reply_incomplete(a: InboxReplyArgs, s: Runs, by: Actor | None) -> bool:
    return not a.message or a.text is None


def _reply_unknown(a: InboxReplyArgs, s: Runs, by: Actor | None) -> bool:
    return a.message not in {m[0] for m in messages(s, a.target)}


reply_incomplete = Rule[InboxReplyArgs, Runs](
    'error: reply needs an id and text, e.g. `inbox reply m1 "go ahead"`', _reply_incomplete, FAILED)
reply_unknown = Rule[InboxReplyArgs, Runs](
    "error: \"no inbox message with id '{message}' in " + RUNS + "/loop-runner-{target}/inbox.jsonl\"", _reply_unknown, FAILED)


def _turn_missing(a: ReplayArgs, s: Runs, by: Actor | None) -> bool:
    return True


turn_missing = Rule[ReplayArgs, Runs](
    "error: " + RUNS + "/loop-runner-{target}/turns/{turn}/turn.json does not exist; name a directory under the run's "
    "turns/ that holds a turn.json", _turn_missing, FAILED)
