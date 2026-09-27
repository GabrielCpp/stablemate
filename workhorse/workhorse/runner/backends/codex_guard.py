"""The PreToolUse hook that holds a confined codex turn to its profile.

Codex runs outside its sandbox here, because a profile's commands bring up the app the
turn documents. So every shell call and every patch passes this hook first. A patch
writes only under the turn's cwd. A shell call passes the judge in `codex_shell`.
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

from workhorse.runner.backends.codex_shell import READ_ONLY_PROGRAMS, shell_denial

HOOK_MODULE = "workhorse.runner.backends.codex_guard"
PATCH_PATH = re.compile(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$", re.MULTILINE)


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
        read_roots = _string_list_or_none(data.get("read_roots"))
        commands = _string_list_or_none(data.get("commands"))
        if not isinstance(cwd, str) or read_roots is None or commands is None:
            raise ValueError("the policy needs a string cwd and string lists for read_roots and commands")
        return cls(cwd=Path(cwd), read_roots=tuple(Path(root) for root in read_roots), commands=commands)

    def reads(self, path: Path) -> bool:
        """Whether the turn may read the absolute path."""
        return _within(path, self.read_roots)


def _string_list_or_none(value: object) -> tuple[str, ...] | None:
    """The list's strings, or None when it is no list of strings."""
    if not isinstance(value, list):
        return None
    items: list[object] = list(value)
    strings = tuple(item for item in items if isinstance(item, str))
    return strings if len(strings) == len(items) else None


@dataclass(frozen=True, slots=True)
class ToolCall:
    """The part of one hook payload the guard judges: the tool codex calls, and the text it passes, a shell command or a patch."""

    tool: str
    input_text: str | None

    @classmethod
    def from_json(cls, text: str) -> ToolCall:
        """The call codex sends the hook, refusing a payload that is not an object."""
        data: object = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("the call is not an object")
        tool = data.get("tool_name")
        tool_input = data.get("tool_input")
        command_text = tool_input.get("command") if isinstance(tool_input, dict) else None
        return cls(tool=tool if isinstance(tool, str) else "", input_text=command_text if isinstance(command_text, str) else None)


def _within(path: Path, roots: Sequence[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


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
    if call.input_text is None:
        return _refusal_message("the call carries no command", policy)
    denial = shell_denial(call.input_text, policy) if call.tool == "Bash" else patch_denial(call.input_text, policy)
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
