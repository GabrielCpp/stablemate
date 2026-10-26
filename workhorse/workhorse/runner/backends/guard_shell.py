"""The judge of one shell call a confined codex or claude turn makes.

A call runs one of the profile's commands or a read-only command, joined by pipes, and
names no path outside the directories the turn reads. A call may join whole commands with
`;`, `&&` and `||`. A `cd` may move only into a directory the turn reads, and `xargs` runs
only what the turn could run itself. The hook sees the command but not the directory it
runs in, so a relative path is judged by its spelling: it may not climb with `..` or start
at `~`.
"""
from __future__ import annotations

import os
import re
import shlex
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from workhorse.runner.backends.guard import Policy

READ_ONLY_PROGRAMS = (
    *("cat", "cut", "diff", "find", "grep", "head", "ls", "nl", "pwd", "rg", "sed", "sort", "tail", "true", "uniq", "wc"),
)
FORBIDDEN_OPTIONS = {
    "find": ("-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls"),
    "rg": ("--pre", "--pre-glob"),
    "sort": ("-o", "--output", "--compress-program"),
}
SORT_FORBIDDEN_LONG_OPTIONS = ("output", "compress-program")
UNIQ_VALUE_OPTIONS = ("-f", "-s", "-w", "--skip-fields", "--skip-chars", "--check-chars")
XARGS_PROGRAM = "xargs"
XARGS_FLAGS = ("-0", "--null", "-r", "--no-run-if-empty", "-t", "--verbose")
XARGS_SHORT_VALUE_OPTIONS = ("-n", "-L", "-P", "-d", "-I")
XARGS_LONG_VALUE_OPTIONS = ("--max-args", "--max-lines", "--max-procs", "--delimiter", "--replace")
CD_PROGRAM = "cd"
SEARCH_PATTERN_OPTIONS = ("-e", "--regexp")
SEARCH_VALUE_OPTIONS = (
    *SEARCH_PATTERN_OPTIONS,
    *("-f", "--file"),
    *("-g", "--glob", "-t", "--type", "-T", "--type-not", "-A", "-B", "-C", "-m", "--max-count", "-M"),
)
ALLOWED_SED_OPTIONS = ("-n", "-E", "-r", "-u", "--quiet", "--silent")
SED_PRINT = re.compile(r"(?:\d+|\$)(?:,(?:\d+|\$))?p(?:;(?:\d+|\$)(?:,(?:\d+|\$))?p)*")
HARMLESS_REDIRECT = re.compile(r"(?<=\s)2>(?:&1|/dev/null)(?=\s|\||$)")
TIMEOUT_PROGRAM = "timeout"
DURATION = re.compile(r"\d+(?:\.\d+)?[smhd]?")
PIPE = "|"
LIST_OPERATORS = (";", "&&", "||")
SHELL_OPERATOR_CHARS = frozenset("();<>|&")


def _unquoted_hazard(command: str) -> str | None:
    """The first character outside single quotes that makes the shell run more than the command says."""
    quote = ""
    escaped = False
    for char in command:
        if escaped:
            escaped = False
        elif quote == "'":
            quote = "" if char == "'" else quote
        elif char == "\\":
            escaped = True
        elif char in "$`":
            return f"`{char}`"
        elif quote == '"':
            quote = "" if char == '"' else quote
        elif char in "'\"":
            quote = char
        elif char == "\n":
            return "newline"
    return None


def _tokens(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def _commands(tokens: list[str]) -> list[list[str]]:
    commands: list[list[str]] = [[]]
    for token in tokens:
        if token in LIST_OPERATORS:
            commands.append([])
        else:
            commands[-1].append(token)
    if tokens[-1:] == [";"]:
        commands.pop()
    return commands


def _stages(tokens: list[str]) -> list[list[str]]:
    stages: list[list[str]] = [[]]
    for token in tokens:
        if token == PIPE:
            stages.append([])
        else:
            stages[-1].append(token)
    return stages


def _path_in_argument(token: str) -> str:
    """The path an argument names: the whole token, the value after an option's `=`, or an option's text from its first `/`."""
    if not token.startswith("-"):
        return token
    if "=" in token:
        return token.partition("=")[2]
    return token[token.find("/") :] if "/" in token else ""


def _path_denial(tokens: Sequence[str], policy: Policy) -> str | None:
    """Why one of the arguments names a path the turn may not read, or None."""
    for token in tokens:
        named_path = _path_in_argument(token)
        if named_path.startswith("~"):
            return f"`{token}` starts at the home directory"
        if ".." in Path(named_path).parts:
            return f"`{token}` climbs out of its directory with `..`"
        if named_path.startswith("/") and not policy.may_read(Path(os.path.normpath(named_path))):
            return f"`{token}` is outside the directories this turn reads"
    return None


def _sed_denial(arguments: Sequence[str]) -> str | None:
    options = [argument for argument in arguments if argument.startswith("-")]
    scripts = [argument for argument in arguments if not argument.startswith("-")][:1]
    if any(option not in ALLOWED_SED_OPTIONS for option in options):
        return f"`sed` runs here with {', '.join(ALLOWED_SED_OPTIONS)} only"
    if not scripts or not SED_PRINT.fullmatch(scripts[0]):
        return "`sed` runs here only to print lines, as in `sed -n '1,200p' FILE`"
    return None


def _names_patterns(argument: str) -> bool:
    """Whether the option gives the search its patterns, so no positional argument is one."""
    if argument.startswith("--"):
        return argument.startswith(("--regexp", "--file"))
    return argument.startswith("-") and bool(set(argument[1:]) & {"e", "f"})


def _arguments_without_patterns(arguments: Sequence[str]) -> list[str]:
    """A search's arguments without the patterns it matches, which name no file it reads."""
    kept: list[str] = []
    pattern_left = not any(_names_patterns(argument) for argument in arguments)
    option_awaiting_value = ""
    for argument in arguments:
        if option_awaiting_value:
            if option_awaiting_value not in SEARCH_PATTERN_OPTIONS:
                kept.append(argument)
            option_awaiting_value = ""
        elif argument in SEARCH_VALUE_OPTIONS:
            option_awaiting_value = argument
        elif pattern_left and not argument.startswith("-"):
            pattern_left = False
        else:
            kept.append(argument)
    return kept


def _abbreviates_forbidden_sort_option(name: str) -> bool:
    return bool(name) and any(option.startswith(name) for option in SORT_FORBIDDEN_LONG_OPTIONS)


def _sort_denial(arguments: Sequence[str]) -> str | None:
    for argument in arguments:
        if argument.startswith("--") and _abbreviates_forbidden_sort_option(argument[2:].partition("=")[0]):
            return f"`sort {argument.partition('=')[0]}` does more than read"
        if argument.startswith("-") and not argument.startswith("--") and "o" in argument:
            return "`sort -o` does more than read"
    return None


def _uniq_denial(arguments: Sequence[str]) -> str | None:
    positionals = 0
    option_awaiting_value = False
    for argument in arguments:
        if option_awaiting_value:
            option_awaiting_value = False
        elif argument in UNIQ_VALUE_OPTIONS:
            option_awaiting_value = True
        elif not argument.startswith("-"):
            positionals += 1
    if positionals > 1:
        return "`uniq` writes its output to a second file argument"
    return None


def _xargs_denial(arguments: Sequence[str], policy: Policy) -> str | None:
    """Why `xargs` would run more than the turn could run itself, or None."""
    index = 0
    while index < len(arguments) and arguments[index].startswith("-"):
        option = arguments[index]
        index += 1
        if option in XARGS_FLAGS:
            continue
        if option in XARGS_SHORT_VALUE_OPTIONS:
            index += 1
        elif option[:2] in XARGS_SHORT_VALUE_OPTIONS and not option.startswith("--"):
            continue
        elif option.partition("=")[0] in XARGS_LONG_VALUE_OPTIONS and "=" in option:
            continue
        else:
            return f"`xargs {option}` is not allowed here"
    if index >= len(arguments):
        return "`xargs` needs a program to run, and a bare one runs `echo`, which is not allowed"
    return _stage_denial(arguments[index:], policy)


def _cd_denial(arguments: Sequence[str], policy: Policy) -> str | None:
    if len(arguments) != 1 or arguments[0].startswith("-"):
        return "`cd` runs here with exactly one directory"
    return _path_denial(arguments, policy)


def _without_timeout(stage: Sequence[str]) -> Sequence[str]:
    """The stage without a leading `timeout DURATION`, which only bounds the command it runs."""
    if len(stage) > 2 and stage[0] == TIMEOUT_PROGRAM and DURATION.fullmatch(stage[1]):
        return stage[2:]
    return stage


def _stage_denial(stage: Sequence[str], policy: Policy) -> str | None:
    stage = _without_timeout(stage)
    if not stage:
        return "a pipe has an empty side"
    for command in policy.commands:
        command_tokens = shlex.split(command)
        if list(stage[: len(command_tokens)]) == command_tokens:
            return _path_denial(stage[len(command_tokens) :], policy)
    program, arguments = stage[0], stage[1:]
    if program == CD_PROGRAM:
        return "`cd` runs only as a whole command, not in a pipeline"
    if program == XARGS_PROGRAM:
        return _xargs_denial(arguments, policy)
    if program not in READ_ONLY_PROGRAMS:
        return f"`{program}` is neither one of this turn's commands nor a read-only command"
    for option in FORBIDDEN_OPTIONS.get(program, ()):
        if any(argument == option or argument.startswith(f"{option}=") for argument in arguments):
            return f"`{program} {option}` does more than read"
    for check, checked_program in ((_sed_denial, "sed"), (_sort_denial, "sort"), (_uniq_denial, "uniq")):
        if program == checked_program:
            denial = check(arguments)
            if denial is not None:
                return denial
    return _path_denial(_arguments_without_patterns(arguments) if program in ("rg", "grep") else arguments, policy)


def _command_denial(command: list[str], policy: Policy) -> str | None:
    if not command:
        return "a command list has an empty command"
    stages = _stages(command)
    if len(stages) == 1 and stages[0][0] == CD_PROGRAM:
        return _cd_denial(stages[0][1:], policy)
    for stage in stages:
        denial = _stage_denial(stage, policy)
        if denial is not None:
            return denial
    return None


def shell_denial(command: str, policy: Policy) -> str | None:
    """Why the shell call may not run under the policy, or None when it may."""
    command = HARMLESS_REDIRECT.sub("", command)
    hazard = _unquoted_hazard(command)
    if hazard is not None:
        return f"the command has a {hazard} outside single quotes"
    try:
        tokens = _tokens(command)
    except ValueError as error:
        return f"the command does not parse: {error}"
    chaining_tokens = [
        token for token in tokens if token not in (PIPE, *LIST_OPERATORS) and set(token) <= SHELL_OPERATOR_CHARS
    ]
    if chaining_tokens:
        return f"the command joins or redirects with `{chaining_tokens[0]}`"
    for part in _commands(tokens):
        denial = _command_denial(part, policy)
        if denial is not None:
            return denial
    return None
