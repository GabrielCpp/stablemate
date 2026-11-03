"""The PreToolUse guard: refuses an agent action that would read a dotenv, key or credentials file, and names the way to get the same thing."""

from __future__ import annotations

import json
import posixpath
import re
import shlex
import sys

TYPE_CHECKING = False
if TYPE_CHECKING:
    from pathlib import Path
    from typing import IO

_SUFFIX_EXAMPLES = (".example", ".sample", ".template", ".dist")
_KEY_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
_KEY_NAMES = frozenset({"id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"})
_CREDENTIAL_NAMES = frozenset({".netrc", "_netrc", ".npmrc", ".pypirc", ".git-credentials", ".vault-token"})

_READERS = frozenset(
    "cat tac less more head tail grep egrep fgrep rg ag sed awk cut sort uniq strings xxd od hexdump base64 bat nl wc tee source . "
    "python python3 node ruby perl php jq yq".split()
)
_WRAPPERS = frozenset({"sudo", "time", "nice", "command", "builtin", "exec", "nohup", "xargs"})
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_REDIRECT = re.compile(r"^\d*[<>]+")
_SUBSHELL = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")

DOTENV_MESSAGE = "`{path}` holds secrets. Read it masked: `saddlebag env show {path}`; list its keys: `saddlebag env keys {path}`."
FILE_MESSAGE = "`{path}` holds secrets. Store it: `saddlebag secret set NAME < {path}`, then run the consumer under `saddlebag exec --env VAR=NAME -- <command>`."

HOOK_SUFFIX = "guard --hook"

_HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)(\w+)\1")


class Verdict:
    """Allow or deny, with the redirect when denied."""

    __slots__ = ("allowed", "reason")

    def __init__(self, allowed: bool, reason: str = "") -> None:
        self.allowed = allowed
        self.reason = reason

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Verdict) and (self.allowed, self.reason) == (other.allowed, other.reason)

    def __hash__(self) -> int:
        return hash((self.allowed, self.reason))

    def __repr__(self) -> str:
        return f"Verdict({self.allowed!r}, {self.reason!r})"


ALLOW = Verdict(True)


def _deny(reason: str) -> Verdict:
    return Verdict(False, reason)


def protected_kind(path: str) -> str | None:
    """``dotenv`` or ``file`` when *path* names a file whose contents are secret, else None."""
    name = posixpath.basename(path.rstrip("/"))
    parent = posixpath.basename(posixpath.dirname(path.rstrip("/")))
    if name == ".env" or name.startswith(".env.") or name.endswith(".env"):
        return None if name.endswith(_SUFFIX_EXAMPLES) else "dotenv"
    if name.endswith(_KEY_SUFFIXES) or name in _KEY_NAMES or name in _CREDENTIAL_NAMES:
        return "file"
    if (name == "credentials" and parent == ".aws") or (name == "config.json" and parent == ".docker"):
        return "file"
    return None


def _file_reason(path: str) -> str | None:
    kind = protected_kind(path)
    if kind is None:
        return None
    return (DOTENV_MESSAGE if kind == "dotenv" else FILE_MESSAGE).format(path=path)


def _split(command: str) -> list[str]:
    """The stages of *command* outside quotes."""
    stages: list[str] = []
    current: list[str] = []
    quote = ""
    i, n = 0, len(command)

    def close() -> None:
        text = "".join(current).strip()
        if text:
            stages.append(text)
        current.clear()

    while i < n:
        char = command[i]
        if quote:
            current.append(char)
            if char == "\\" and quote == '"' and i + 1 < n:
                i += 1
                current.append(command[i])
            elif char == quote:
                quote = ""
        elif char == "\\" and i + 1 < n:
            current.append(char)
            i += 1
            current.append(command[i])
        elif char in "'\"":
            quote = char
            current.append(char)
        elif char == "&" and (command[i - 1 : i] in (">", "<") or command[i + 1 : i + 2] == ">"):
            current.append(char)
        elif char in "|&;\n":
            double = command[i + 1 : i + 2] == char and char in "|&"
            close()
            i += 1 if double else 0
        else:
            current.append(char)
        i += 1
    close()
    return stages


def _without_heredocs(command: str) -> str:
    """*command* with the body of every heredoc removed; the line that opens it stays."""
    kept: list[str] = []
    pending: list[str] = []
    for line in command.split("\n"):
        if pending:
            if line.strip() == pending[0]:
                pending.pop(0)
            continue
        kept.append(line)
        pending.extend(match.group(2) for match in _HEREDOC.finditer(line))
    return "\n".join(kept)


def _single_quoted(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    double = False
    start = -1
    for i, char in enumerate(text):
        if start >= 0:
            if char == "'":
                spans.append((start, i))
                start = -1
        elif char == '"':
            double = not double
        elif char == "'" and not double:
            start = i
    return spans


def _stages(command: str) -> list[str]:
    command = _without_heredocs(command)
    found = _split(command)
    spans = _single_quoted(command)
    for match in _SUBSHELL.finditer(command):
        if any(start < match.start() < end for start, end in spans):
            continue
        found.extend(_stages(match.group(1) or match.group(2) or ""))
    return found


def _tokens(stage: str) -> list[str]:
    try:
        return shlex.split(stage, posix=True)
    except ValueError:
        return stage.split()


def _strip_wrappers(tokens: list[str]) -> list[str]:
    """The tokens from the command word on."""
    while tokens:
        word = posixpath.basename(tokens[0])
        if _ASSIGNMENT.match(tokens[0]):
            tokens = tokens[1:]
        elif word in _WRAPPERS:
            tokens = tokens[1:]
            while tokens and tokens[0].startswith("-"):
                tokens = tokens[1:]
        elif word == "timeout":
            tokens = tokens[1:]
            while tokens and tokens[0].startswith("-"):
                tokens = tokens[1:]
            if tokens and tokens[0][:1].isdigit():
                tokens = tokens[1:]
        elif word == "env":
            tokens = tokens[1:]
            while tokens and (tokens[0].startswith("-") or _ASSIGNMENT.match(tokens[0])):
                tokens = tokens[1:]
        elif word == "stdbuf":
            tokens = tokens[1:]
            while tokens and tokens[0].startswith("-"):
                tokens = tokens[1:]
        else:
            break
    return tokens


def _operands(tokens: list[str]) -> list[str]:
    return [stripped for token in tokens if (stripped := _REDIRECT.sub("", token))]


def _reads_protected(tokens: list[str]) -> str | None:
    word = posixpath.basename(tokens[0])
    allexport = tokens[:2] == ["set", "-a"] or tokens[:3] == ["set", "-o", "allexport"]
    if word not in _READERS and not allexport:
        return None
    for operand in _operands(tokens[1:]):
        if reason := _file_reason(operand):
            return reason
    return None


def _decide_command(command: str) -> Verdict:
    parsed = [_strip_wrappers(_tokens(stage)) for stage in _stages(command)]
    if parsed and parsed[0] and posixpath.basename(parsed[0][0]) == "saddlebag" and parsed[0][1:2] == ["exec"]:
        return ALLOW
    for tokens in parsed:
        if tokens and (reason := _reads_protected(tokens)):
            return _deny(reason)
    return ALLOW


def decide(payload: object) -> Verdict:
    """The verdict for a PreToolUse *payload*. Never raises: anything unreadable is allowed."""
    try:
        if not isinstance(payload, dict):
            return ALLOW
        tool, tool_input = payload.get("tool_name"), payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return ALLOW
        if tool in ("Read", "Write", "Edit", "MultiEdit", "Grep"):
            raw = tool_input.get("path" if tool == "Grep" else "file_path")
            reason = _file_reason(raw) if isinstance(raw, str) else None
            return _deny(reason) if reason else ALLOW
        if tool == "Bash":
            command = tool_input.get("command")
            return _decide_command(command) if isinstance(command, str) else ALLOW
    except Exception:
        return ALLOW
    return ALLOW


def hook(stdin: IO[str] | None = None, stdout: IO[str] | None = None) -> int:
    """Read a PreToolUse payload from *stdin* and print a deny decision when the guard refuses. Always returns 0."""
    source = sys.stdin if stdin is None else stdin
    sink = sys.stdout if stdout is None else stdout
    try:
        payload = json.load(source)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    verdict = decide(payload)
    if not verdict.allowed:
        sink.write(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": verdict.reason,
                    }
                }
            )
            + "\n"
        )
        sink.flush()
    return 0


def _default_command() -> str:
    import shutil
    from pathlib import Path

    executable = shutil.which("saddlebag") or str(Path(sys.argv[0]).resolve())
    return f"{executable} {HOOK_SUFFIX}"


def install(scope: str, settings_path: Path | None = None, command: str | None = None) -> Path:
    """Register the guard as a PreToolUse hook in Claude Code's settings and return the file written."""
    from pathlib import Path

    if settings_path is None:
        base = Path.home() if scope == "user" else Path.cwd()
        settings_path = base / ".claude" / "settings.json"
    entry = {
        "matcher": "Read|Grep|Bash",
        "hooks": [{"type": "command", "command": command or _default_command(), "timeout": 5, "statusMessage": "saddlebag guard"}],
    }
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    entries = settings.setdefault("hooks", {}).setdefault("PreToolUse", [])
    ours = [
        i
        for i, existing in enumerate(entries)
        if isinstance(existing, dict)
        and any(isinstance(h, dict) and str(h.get("command", "")).endswith(HOOK_SUFFIX) for h in existing.get("hooks", []))
    ]
    if ours:
        entries[ours[0]] = entry
        for i in reversed(ours[1:]):
            del entries[i]
    else:
        entries.append(entry)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    return settings_path
