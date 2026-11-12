#!/usr/bin/env python3
"""Refuse a commit that would put a private project name into a public repo.

The names come from ``$STABLEMATE_PRIVATE_NAMES`` or ``$GIT_DIR/private-names``. Neither is
tracked, and with neither set the check passes. It scans the staged paths and their index
content, limited to the pathspecs given as arguments, then the commit command the agent
ran, from ``$AGENT_COMMIT_COMMAND``, and the file a ``-F`` names.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ENV_VAR = "STABLEMATE_PRIVATE_NAMES"
GIT_FILE = "private-names"
COMMAND_ENV = "AGENT_COMMIT_COMMAND"
CWD_ENV = "AGENT_COMMIT_CWD"
BINARY_SNIFF_BYTES = 8000
PLACEHOLDERS = "acme, globex, api-service, web-app, mobile-app, example.com"


def _git(*args: str, stdin: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *args], input=stdin, capture_output=True, check=True
    ).stdout


def load_names() -> list[str]:
    """The configured private names, lowercased and deduplicated."""
    raw = os.environ.get(ENV_VAR, "")
    if not raw.strip():
        try:
            common = _git("rev-parse", "--path-format=absolute", "--git-common-dir")
        except (OSError, subprocess.CalledProcessError):
            common = b""
        path = Path(common.decode().strip()) / GIT_FILE if common.strip() else None
        if path is not None and path.is_file():
            raw = path.read_text(encoding="utf-8")
    names: list[str] = []
    for line in raw.splitlines():
        for token in re.split(r"[,\s]+", line.split("#", 1)[0]):
            name = token.strip().lower()
            if name and name not in names:
                names.append(name)
    return names


def staged_paths(pathspecs: list[str]) -> list[str]:
    """Paths the index adds, copies, modifies or renames against HEAD, within *pathspecs*."""
    out = _git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR", "--", *pathspecs)
    return [path for path in out.decode("utf-8", errors="replace").split("\0") if path]


def staged_blobs(paths: list[str]) -> dict[str, bytes]:
    """The index content of each path that is a blob."""
    if not paths:
        return {}
    request = "".join(f":{path}\n" for path in paths).encode()
    out = _git("cat-file", "--batch", stdin=request)
    blobs: dict[str, bytes] = {}
    offset = 0
    for path in paths:
        end = out.index(b"\n", offset)
        header = out[offset:end].split()
        offset = end + 1
        if len(header) != 3:
            continue
        size = int(header[2])
        if header[1] == b"blob":
            blobs[path] = out[offset:offset + size]
        offset += size + 1
    return blobs


def _hits(pattern: re.Pattern[str], where: str, text: str) -> list[str]:
    return [
        f"{where}:{number}: {line.strip()}"
        for number, line in enumerate(text.splitlines(), start=1)
        if pattern.search(line)
    ]


def check_staged(pattern: re.Pattern[str], pathspecs: list[str]) -> list[str]:
    paths = staged_paths(pathspecs)
    offenders = [f"{path}: (in the path)" for path in paths if pattern.search(path)]
    for path, body in staged_blobs(paths).items():
        if b"\0" in body[:BINARY_SNIFF_BYTES]:
            continue
        offenders.extend(_hits(pattern, path, body.decode("utf-8", errors="replace")))
    return offenders


def message_files(command: str) -> list[str]:
    """The files a ``git commit`` command reads its message from."""
    try:
        words = shlex.split(command, comments=False)
    except ValueError:
        return []
    files: list[str] = []
    for index, word in enumerate(words):
        if word in ("-F", "--file") and index + 1 < len(words):
            files.append(words[index + 1])
        elif word.startswith("--file="):
            files.append(word.split("=", 1)[1])
        elif word.startswith("-F") and len(word) > 2 and not word.startswith("--"):
            files.append(word[2:])
    return [name for name in files if name != "-"]


def check_message(pattern: re.Pattern[str]) -> list[str]:
    command = os.environ.get(COMMAND_ENV, "")
    if not command.strip():
        return []
    offenders = _hits(pattern, "commit command", command)
    base = Path(os.environ.get(CWD_ENV) or os.getcwd())
    for name in message_files(command):
        path = base / name
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        offenders.extend(_hits(pattern, str(path), text))
    return offenders


def main(argv: list[str]) -> int:
    names = load_names()
    if not names:
        return 0
    pattern = re.compile("|".join(re.escape(name) for name in names), re.IGNORECASE)
    offenders = check_staged(pattern, argv) + check_message(pattern)
    if not offenders:
        return 0
    print("A private project name is about to enter this public repo:", file=sys.stderr)
    for offender in offenders:
        print(f"  {offender}", file=sys.stderr)
    print(
        f"Replace each with a neutral placeholder ({PLACEHOLDERS}), restage, and commit again.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
