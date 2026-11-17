"""What the PreToolUse guard decides about an agent action, as far as the book plays it."""

from __future__ import annotations

import json
import posixpath
import re
import shlex

EXAMPLES = (".example", ".sample", ".template", ".dist")
KEY_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
KEY_NAMES = frozenset({"id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"})
CREDENTIAL_NAMES = frozenset({".netrc", "_netrc", ".npmrc", ".pypirc", ".git-credentials", ".vault-token"})
EXPORT_SUFFIX = ".saddlebag.json"
READERS = frozenset(
    "cat tac less more head tail grep egrep fgrep rg ag sed awk cut sort uniq strings xxd od hexdump base64 bat nl wc tee source . "
    "python python3 node ruby perl php jq yq".split())

DOTENV = "`{path}` holds secrets. Read it masked: `saddlebag env show {path}`; list its keys: `saddlebag env keys {path}`; change a literal: `saddlebag env set {path} KEY VALUE`."
FILE = "`{path}` holds secrets. Store it: `saddlebag secret set NAME < {path}`, then run the consumer under `saddlebag exec --env VAR=NAME -- <command>`."
EXPORT = "`{path}` is a saddlebag export with every secret in plaintext. Load it: `saddlebag import {path}`; see what the store holds: `saddlebag list`."


def kind(path: str) -> str | None:
    name = posixpath.basename(path.rstrip("/"))
    parent = posixpath.basename(posixpath.dirname(path.rstrip("/")))
    if name == ".env" or name.startswith(".env.") or name.endswith(".env"):
        return None if name.endswith(EXAMPLES) else "dotenv"
    if name.endswith(EXPORT_SUFFIX):
        return "export"
    if name.endswith(KEY_SUFFIXES) or name in KEY_NAMES or name in CREDENTIAL_NAMES:
        return "file"
    if (name == "credentials" and parent == ".aws") or (name == "config.json" and parent == ".docker"):
        return "file"
    return None


def reason(path: str) -> str | None:
    found = kind(path)
    if found is None:
        return None
    return {"dotenv": DOTENV, "export": EXPORT}.get(found, FILE).format(path=path)


def bash(command: str) -> str | None:
    stages = [s.strip() for s in re.split(r"[|;&\n]", command) if s.strip()]
    parsed = []
    for stage in stages:
        try:
            tokens = shlex.split(stage)
        except ValueError:
            tokens = stage.split()
        while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
            tokens = tokens[1:]
        parsed.append(tokens)
    if parsed and parsed[0] and posixpath.basename(parsed[0][0]) == "saddlebag" and parsed[0][1:2] == ["exec"]:
        return None
    for tokens in parsed:
        if tokens and posixpath.basename(tokens[0]) in READERS:
            for operand in tokens[1:]:
                found = reason(re.sub(r"^\d*[<>]+", "", operand))
                if found:
                    return found
    return None


def decide(text: str) -> str | None:
    """The reason the guard refuses the action the payload describes, or None when it allows it."""
    try:
        payload = json.loads(text)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    tool, tool_input = payload.get("tool_name"), payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    if tool in ("Read", "Write", "Edit", "MultiEdit", "Grep"):
        raw = tool_input.get("path" if tool == "Grep" else "file_path")
        return reason(raw) if isinstance(raw, str) else None
    if tool == "Bash":
        command = tool_input.get("command")
        return bash(command) if isinstance(command, str) else None
    return None
