"""The PreToolUse guard: refuses an agent action that would put a secret in front of it, and names the way to get the same thing."""

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
_PROC_ENVIRON = re.compile(r"^/proc/(?:\d+|self)/environ$")

_READERS = frozenset(
    "cat tac less more head tail grep egrep fgrep rg ag sed awk cut sort uniq strings xxd od hexdump base64 bat nl wc tee source . "
    "python python3 node ruby perl php jq yq".split()
)
_WRAPPERS = frozenset({"sudo", "time", "nice", "command", "builtin", "exec", "nohup", "xargs"})
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_REDIRECT = re.compile(r"^\d*[<>]+")
_SUBSHELL = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
_PASS_SUBCOMMANDS = frozenset("ls insert git rm mv cp edit generate init grep find".split())

DOTENV_MESSAGE = "`{path}` holds secrets. Read it masked: `saddlebag env show {path}`; list its keys: `saddlebag env keys {path}`."
FILE_MESSAGE = "`{path}` holds secrets. Store it: `saddlebag secret set NAME < {path}`, then run the consumer under `saddlebag exec --env VAR=NAME -- <command>`."
ENVIRONMENT_MESSAGE = "`{word}` would print every secret in the environment. Print one variable by name: `printenv HOME`; list a dotenv's keys: `saddlebag env keys .env`."
MANAGER_MESSAGE = "`{stage}` prints a secret. Store it instead: `{stage} | saddlebag secret set NAME`, then run the consumer under `saddlebag exec --env VAR=NAME -- <command>`."

PASTED_MESSAGE = "the command carries the value of secret {names}. Refer to it instead: run the consumer under `saddlebag exec --env VAR={name} -- <command>` and use $VAR."
UNREACHABLE_NOTE = "saddlebag guard: no daemon answers, so the command was not checked for pasted secret values; start one with `saddlebag serve`."

HOOK_SUFFIX = "guard --hook"

_MIN_CANDIDATE = 8
_TOKEN_SPLIT = re.compile(r"[^\s'\"`;|&()<>]+")
_TOKEN_PREFIXES = ("sk-", "ghp_", "github_pat_", "hvs.", "AKIA", "xoxa-", "xoxb-", "xoxp-", "xoxr-", "xoxs-", "glpat-", "-----BEGIN")
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
    if path.startswith("~"):
        path = posixpath.expanduser(path)
    name = posixpath.basename(path.rstrip("/"))
    parent = posixpath.basename(posixpath.dirname(path.rstrip("/")))
    if name == ".env" or name.startswith(".env.") or name.endswith(".env"):
        return None if name.endswith(_SUFFIX_EXAMPLES) else "dotenv"
    if name.endswith(_KEY_SUFFIXES) or name in _KEY_NAMES or name in _CREDENTIAL_NAMES:
        return "file"
    if (name == "credentials" and parent == ".aws") or (name == "config.json" and parent == ".docker"):
        return "file"
    if _PROC_ENVIRON.match(path):
        return "file"
    return None


def _file_reason(path: str) -> str | None:
    kind = protected_kind(path)
    if kind is None:
        return None
    return (DOTENV_MESSAGE if kind == "dotenv" else FILE_MESSAGE).format(path=path)


def _split(command: str) -> list[tuple[str, bool]]:
    """The stages of *command* outside quotes, each with whether a pipe feeds the next one."""
    stages: list[tuple[str, bool]] = []
    current: list[str] = []
    quote = ""
    i, n = 0, len(command)

    def close(piped: bool) -> None:
        text = "".join(current).strip()
        if text:
            stages.append((text, piped))
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
            close(char == "|" and not double)
            i += 1 if double else 0
        else:
            current.append(char)
        i += 1
    close(False)
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


def _stages(command: str) -> list[tuple[str, bool]]:
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


def _strip_wrappers(tokens: list[str]) -> tuple[list[str], str]:
    """The tokens from the command word on, and the last wrapper removed."""
    last = ""
    while tokens:
        word = posixpath.basename(tokens[0])
        if _ASSIGNMENT.match(tokens[0]):
            tokens = tokens[1:]
        elif word in _WRAPPERS:
            last, tokens = word, tokens[1:]
            while tokens and tokens[0].startswith("-"):
                tokens = tokens[1:]
        elif word == "timeout":
            last, tokens = word, tokens[1:]
            while tokens and tokens[0].startswith("-"):
                tokens = tokens[1:]
            if tokens and tokens[0][:1].isdigit():
                tokens = tokens[1:]
        elif word == "env":
            last, tokens = word, tokens[1:]
            while tokens and (tokens[0].startswith("-") or _ASSIGNMENT.match(tokens[0])):
                tokens = tokens[1:]
        elif word == "stdbuf":
            last, tokens = word, tokens[1:]
            while tokens and tokens[0].startswith("-"):
                tokens = tokens[1:]
        else:
            break
    return tokens, last


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


def _dumps_environment(tokens: list[str], last: str) -> str | None:
    if not tokens:
        return ENVIRONMENT_MESSAGE.format(word="env") if last == "env" else None
    word, rest = posixpath.basename(tokens[0]), tokens[1:]
    positional = [token for token in rest if not token.startswith("-")]
    dump = (
        (word == "printenv" and not positional)
        or (word == "export" and all(token == "-p" for token in rest))
        or (word in ("declare", "typeset") and not positional and all(re.fullmatch(r"-[px]+", token) for token in rest))
        or (word == "set" and not rest)
    )
    return ENVIRONMENT_MESSAGE.format(word=word) if dump else None


def _fetches_secret(tokens: list[str]) -> bool:
    head = [posixpath.basename(tokens[0]), *tokens[1:]]
    flags = set(tokens)
    positional = [token for token in tokens[1:] if not token.startswith("-")]
    return (
        head[:3] == ["aws", "secretsmanager", "get-secret-value"]
        or (head[:2] == ["aws", "ssm"] and head[2:3] in (["get-parameter"], ["get-parameters"]) and "--with-decryption" in flags)
        or head[:3] == ["vault", "kv", "get"]
        or head[:2] == ["vault", "read"]
        or head[:4] == ["gcloud", "secrets", "versions", "access"]
        or head[:4] == ["az", "keyvault", "secret", "show"]
        or (head[:2] == ["kubectl", "get"] and head[2:3] in (["secret"], ["secrets"]))
        or head[:2] == ["op", "read"]
        or head[:3] == ["op", "item", "get"]
        or head[:3] == ["gh", "auth", "token"]
        or (head[:2] in (["security", "find-generic-password"], ["security", "find-internet-password"]) and "-w" in flags)
        or head[:2] == ["secret-tool", "lookup"]
        or head[:2] == ["pass", "show"]
        or (head[0] == "pass" and len(positional) == 1 and positional[0] not in _PASS_SUBCOMMANDS)
        or head[:2] == ["docker", "inspect"]
        or (head[:2] == ["docker", "compose"] and "config" in head[2:])
        or (head[0] == "docker-compose" and "config" in head[1:])
    )


def _is_saddlebag(tokens: list[str], *words: str) -> bool:
    return bool(tokens) and posixpath.basename(tokens[0]) == "saddlebag" and tokens[1 : 1 + len(words)] == list(words)


def _candidates(text: str) -> bool:
    """Whether *text* holds a token that could be a secret value: long enough, and mixed letters and digits or a vendor prefix."""
    for token in _TOKEN_SPLIT.findall(text):
        if len(token) < _MIN_CANDIDATE:
            continue
        if token.startswith(_TOKEN_PREFIXES):
            return True
        if any(char.isalpha() for char in token) and any(char.isdigit() for char in token):
            return True
    return False


def _ask_custody(text: str) -> tuple[bool, list[str]] | None:
    """Whether the daemon holds a value that appears in *text*, with the names, or None when no daemon answers."""
    from saddlebag.sockets import socket_path

    if not socket_path().exists():
        return None
    from saddlebag import protocol

    try:
        reply = protocol.send(protocol.Request("holds", {"text": text}), timeout=0.5)
    except (protocol.DaemonNotRunning, protocol.ProtocolError, OSError):
        return None
    if not reply.ok:
        return None
    names = reply.result.get("names")
    return bool(reply.result.get("held")), [name for name in names if isinstance(name, str)] if isinstance(names, list) else []


def _decide_command(command: str) -> Verdict:
    stages = _stages(command)
    parsed = [_strip_wrappers(_tokens(text)) for text, _ in stages]
    if parsed and _is_saddlebag(parsed[0][0], "exec"):
        return ALLOW
    for index, (text, piped) in enumerate(stages):
        tokens, last = parsed[index]
        if tokens and posixpath.basename(tokens[0]) == "saddlebag":
            continue
        if tokens and (reason := _reads_protected(tokens)):
            return _deny(reason)
        if reason := _dumps_environment(tokens, last):
            return _deny(reason)
        if tokens and _fetches_secret(tokens):
            if piped and index + 1 < len(parsed) and _is_saddlebag(parsed[index + 1][0], "secret", "set"):
                continue
            return _deny(MANAGER_MESSAGE.format(stage=text))
    if any(_is_saddlebag(tokens, "secret", "set") for tokens, _ in parsed) or not _candidates(command):
        return ALLOW
    answer = _ask_custody(command)
    if answer is None:
        sys.stderr.write(UNREACHABLE_NOTE + "\n")
        return ALLOW
    held, names = answer
    if held and names:
        return _deny(PASTED_MESSAGE.format(names=", ".join(names), name=names[0]))
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
