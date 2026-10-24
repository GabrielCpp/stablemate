"""Where the daemon's Vault token comes from, in order of preference, and the places it is never read from."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import keyring.errors
import platformdirs
from keyring.backend import KeyringBackend

from saddlebag.store import StoreUnavailable

TOKEN_SERVICE = "stablemate-saddlebag-vault"
TOKEN_ACCOUNT = "token"
REFUSED = (
    "refusing to start with VAULT_TOKEN in the environment: a same-user process reads it from "
    "/proc/<pid>/environ. Pipe the token on stdin instead."
)
EMPTY = "stdin gave an empty Vault token: pipe the token to `saddlebag serve`"


class CustodyError(RuntimeError):
    """No usable token, or an unsafe place held one. The message says what the operator does next."""


@dataclass(frozen=True)
class Token:
    """One Vault token and the label doctor prints for where it came from."""

    value: str
    source: str


def filed_path() -> Path:
    """The 0600 file: saddlebag/vault-token under the platformdirs state dir."""
    return Path(platformdirs.user_state_dir("stablemate")) / "saddlebag" / "vault-token"


def refuse_environment(environ: Mapping[str, str] = os.environ) -> None:
    """CustodyError when VAULT_TOKEN is set."""
    if "VAULT_TOKEN" in environ:
        raise CustodyError(REFUSED)


def piped(stdin: TextIO) -> Token | None:
    """The token on stdin when stdin is not a terminal, else None. An empty line is CustodyError(EMPTY)."""
    if stdin.isatty():
        return None
    value = stdin.readline().strip()
    if not value:
        raise CustodyError(EMPTY)
    return Token(value, "stdin")


def kept(door: Callable[[], KeyringBackend]) -> Token | None:
    """The token the operator kept in the OS keyring, or None when there is none or the keyring is unavailable."""
    try:
        value = door().get_password(TOKEN_SERVICE, TOKEN_ACCOUNT)
    except (StoreUnavailable, keyring.errors.KeyringError):
        return None
    return Token(value, "keyring") if value else None


def filed(path: Path) -> Token | None:
    """The token in ``path``, or None when the file does not exist. A mode other than 0600 is CustodyError."""
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        return None
    if mode != 0o600:
        raise CustodyError(f"refusing {path}: its mode is {mode:04o}, make it 0600")
    value = path.read_text().strip()
    if not value:
        raise CustodyError(f"{path} is empty")
    return Token(value, f"file {path}")


def find(stdin: TextIO, door: Callable[[], KeyringBackend], path: Path) -> Token:
    """The first source that has a token: piped, kept, filed. None of them is CustodyError."""
    token = piped(stdin) or kept(door) or filed(path)
    if token is None:
        raise CustodyError(
            "no Vault token: pipe one to saddlebag serve, keep one with saddlebag serve --keep-token, "
            f"or write it to {path} with mode 0600"
        )
    return token


def keep(stdin: TextIO, door: Callable[[], KeyringBackend]) -> None:
    """Read one token on stdin and store it in the OS keyring."""
    value = stdin.readline().strip()
    if not value:
        raise CustodyError(EMPTY)
    try:
        door().set_password(TOKEN_SERVICE, TOKEN_ACCOUNT, value)
    except keyring.errors.KeyringError as exc:
        raise CustodyError(f"the OS keyring refused the token: {exc}") from exc
