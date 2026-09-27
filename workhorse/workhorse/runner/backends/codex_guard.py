"""The PreToolUse hook that holds a confined codex turn to its profile.

Codex runs outside its sandbox here, because a profile's commands bring up the app the
turn documents. So every shell call and every patch passes this hook first. A patch
writes only under the turn's cwd. A shell call runs one of the profile's commands or a
read-only command, joined by pipes at most, and names no path outside the turn's cwd,
its added directories and the project skills.

The hook sees a shell call's command but not the directory the call asks to run in, so a
relative path is judged by its spelling: it may not climb with `..` or start at `~`.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

HOOK_MODULE = "workhorse.runner.backends.codex_guard"
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
PATCH_PATH = re.compile(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$", re.MULTILINE)
HARMLESS_REDIRECT = re.compile(r"(?<=\s)2>(?:&1|/dev/null)(?=\s|\||$)")
TIMEOUT = "timeout"
DURATION = re.compile(r"\d+(?:\.\d+)?[smhd]?")
PIPE = "|"
PUNCTUATION = frozenset("();<>|&")


@dataclass(frozen=True, slots=True)
class Policy:
    """What one confined turn may do: where it writes, where it reads, and the commands it runs."""

    cwd: Path
    read_roots: tuple[Path, ...]
    commands: tuple[str, ...]

    def to_json(self) -> str:
        """The policy as the hook reads it back."""
        return json.dumps(
            {"cwd": str(self.cwd), "read_roots": [str(root) for root in self.read_roots], "commands": list(self.commands)}
        )

    @classmethod
    def from_json(cls, text: str) -> Policy:
        """The policy written by `to_json`, refusing one whose fields are not the strings it writes."""
        data: object = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("the policy is not an object")
        cwd = data.get("cwd")
        read_roots = _strings(data.get("read_roots"))
        commands = _strings(data.get("commands"))
        if not isinstance(cwd, str) or read_roots is None or commands is None:
            raise ValueError("the policy needs a string cwd and string lists for read_roots and commands")
        return cls(cwd=Path(cwd), read_roots=tuple(Path(root) for root in read_roots), commands=commands)


def _strings(value: object) -> tuple[str, ...] | None:
    """The list's strings, or None when it is no list of strings."""
    if not isinstance(value, list):
        return None
    items: list[object] = list(value)
    strings = tuple(item for item in items if isinstance(item, str))
    return strings if len(strings) == len(items) else None


@dataclass(frozen=True, slots=True)
class ToolCall:
    """The part of one hook payload the guard judges: the tool codex calls, and the command it passes."""

    tool: str
    command: str | None

    @classmethod
    def from_json(cls, text: str) -> ToolCall:
        """The call codex sends the hook, refusing a payload that is not an object."""
        data: object = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("the call is not an object")
        tool = data.get("tool_name")
        tool_input = data.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        return cls(tool=tool if isinstance(tool, str) else "", command=command if isinstance(command, str) else None)


def _within(path: Path, roots: Sequence[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


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
        if value.startswith("/") and not _within(Path(os.path.normpath(value)), policy.read_roots):
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


def _search_path_arguments(arguments: Sequence[str]) -> list[str]:
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
    if len(stage) > 2 and stage[0] == TIMEOUT and DURATION.fullmatch(stage[1]):
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
    return _path_denial(_search_path_arguments(arguments) if program in ("rg", "grep") else arguments, policy)


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


def patch_denial(patch: str, policy: Policy) -> str | None:
    """Why the patch may not apply under the policy, or None when every file it touches is under the turn's cwd."""
    for match in PATCH_PATH.finditer(patch):
        target = Path(os.path.normpath(policy.cwd / match.group(1).strip()))
        if not _within(target, (policy.cwd,)):
            return f"the patch writes {match.group(1).strip()}, outside {policy.cwd}"
    return None


def _refusal_message(denial: str, policy: Policy) -> str:
    roots = ", ".join(str(root) for root in policy.read_roots)
    return (
        f"Refused: {denial}. This turn runs its own commands and the read-only commands "
        + f"{', '.join(READ_ONLY_PROGRAMS)}, joined by `|` at most, on paths under {roots}. "
        + f"It writes only with a patch, under {policy.cwd}."
    )


def call_refusal(call: ToolCall, policy: Policy) -> str | None:
    """The reason to refuse the tool call, or None to let it run."""
    if call.tool not in ("Bash", "apply_patch"):
        return None
    if call.command is None:
        return _refusal_message("the call carries no command", policy)
    denial = shell_denial(call.command, policy) if call.tool == "Bash" else patch_denial(call.command, policy)
    return None if denial is None else _refusal_message(denial, policy)


def denial_output(reason: str) -> str:
    """The hook output that refuses the call."""
    output = {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}
    return json.dumps({"hookSpecificOutput": output})


def hook_command(policy_path: Path) -> str:
    """The command codex runs as the hook, reading the policy at `policy_path`."""
    return shlex.join([sys.executable, "-m", HOOK_MODULE, str(policy_path)])


def main(argv: Sequence[str] | None = None) -> int:
    """Read one tool call on stdin, and print a refusal when the policy forbids it."""
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        policy = Policy.from_json(Path(args[0]).read_text(encoding="utf-8"))
        call = ToolCall.from_json(sys.stdin.read())
    except (IndexError, OSError, ValueError, KeyError) as error:
        print(denial_output(f"Refused: the guard could not read the call or its policy: {error}"))
        return 0
    reason = call_refusal(call, policy)
    if reason is not None:
        print(denial_output(reason))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
