"""The judge of one shell call a confined codex turn makes.

A call runs one of the profile's commands or a read-only command, joined by pipes at
most, and names no path outside the directories the turn reads. The hook sees the
command but not the directory it runs in, so a relative path is judged by its spelling:
it may not climb with `..` or start at `~`.
"""
from __future__ import annotations

import os
import re
import shlex
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from workhorse.runner.backends.codex_guard import Policy

READ_ONLY_PROGRAMS = ("cat", "cut", "diff", "find", "grep", "head", "ls", "nl", "pwd", "rg", "sed", "tail", "wc")
FORBIDDEN_OPTIONS = {
    "find": ("-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls"),
    "rg": ("--pre", "--pre-glob"),
}
SEARCH_PATTERN_OPTIONS = ("-e", "--regexp")
SEARCH_VALUE_OPTIONS = (
    *SEARCH_PATTERN_OPTIONS,
    *("-f", "--file"),
    *("-g", "--glob", "-t", "--type", "-T", "--type-not", "-A", "-B", "-C", "-m", "--max-count", "-M"),
)
SED_OPTIONS = ("-n", "-E", "-r", "-u", "--quiet", "--silent")
SED_PRINT = re.compile(r"(?:\d+|\$)(?:,(?:\d+|\$))?p(?:;(?:\d+|\$)(?:,(?:\d+|\$))?p)*")
HARMLESS_REDIRECT = re.compile(r"(?<=\s)2>(?:&1|/dev/null)(?=\s|\||$)")
TIMEOUT_PROGRAM = "timeout"
DURATION = re.compile(r"\d+(?:\.\d+)?[smhd]?")
PIPE = "|"
PUNCTUATION = frozenset("();<>|&")


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


def _stages(tokens: list[str]) -> list[list[str]]:
    stages: list[list[str]] = [[]]
    for token in tokens:
        if token == PIPE:
            stages.append([])
        else:
            stages[-1].append(token)
    return stages


def _path_denial(tokens: Sequence[str], policy: Policy) -> str | None:
    """Why one of the arguments names a path the turn may not read, or None."""
    for token in tokens:
        value = token
        if token.startswith("-"):
            value = token.partition("=")[2] if "=" in token else token[token.find("/") :] if "/" in token else ""
        if value.startswith("~"):
            return f"`{token}` starts at the home directory"
        if ".." in Path(value).parts:
            return f"`{token}` climbs out of its directory with `..`"
        if value.startswith("/") and not policy.reads(Path(os.path.normpath(value))):
            return f"`{token}` is outside the directories this turn reads"
    return None


def _sed_denial(arguments: Sequence[str]) -> str | None:
    options = [argument for argument in arguments if argument.startswith("-")]
    scripts = [argument for argument in arguments if not argument.startswith("-")][:1]
    if any(option not in SED_OPTIONS for option in options):
        return f"`sed` runs here with {', '.join(SED_OPTIONS)} only"
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
        head = shlex.split(command)
        if list(stage[: len(head)]) == head:
            return _path_denial(stage[len(head) :], policy)
    program, arguments = stage[0], stage[1:]
    if program not in READ_ONLY_PROGRAMS:
        return f"`{program}` is neither one of this turn's commands nor a read-only command"
    for option in FORBIDDEN_OPTIONS.get(program, ()):
        if any(argument == option or argument.startswith(f"{option}=") for argument in arguments):
            return f"`{program} {option}` does more than read"
    if program == "sed":
        denial = _sed_denial(arguments)
        if denial is not None:
            return denial
    return _path_denial(_arguments_without_patterns(arguments) if program in ("rg", "grep") else arguments, policy)


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
    chaining_tokens = [token for token in tokens if token != PIPE and set(token) <= PUNCTUATION]
    if chaining_tokens:
        return f"the command joins or redirects with `{chaining_tokens[0]}`"
    for stage in _stages(tokens):
        denial = _stage_denial(stage, policy)
        if denial is not None:
            return denial
    return None
