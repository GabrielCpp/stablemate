"""The shapes that make a dotenv line secret without consulting any stored value. Pure and stdlib only."""

from __future__ import annotations

import re
from collections.abc import Callable

from saddlebag.redact import MIN_LENGTH

_KEY_WORDS = frozenset({"PASSWORD", "PASSWD", "PASS", "SECRET", "TOKEN", "APIKEY", "PRIVATE", "CREDENTIAL", "CREDENTIALS", "AUTH", "DSN"})
_KEY_PHRASES = ("API_KEY", "PRIVATE_KEY", "CLIENT_SECRET", "ACCESS_KEY", "SECRET_KEY")
_TOKEN_PREFIXES = ("sk-", "ghp_", "github_pat_", "hvs.", "AKIA")
_TOKEN_PATTERN = re.compile(r"xox[abprs]-|glpat-|-----BEGIN ")
_USERINFO = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/@\s:]+:[^/@\s]+@")


def key_name(key: str) -> bool:
    """Whether the variable name says it holds a secret."""
    upper = key.upper()
    parts = upper.split("_")
    if "PUBLIC" in upper or upper.endswith("_PUBLIC_KEY"):
        return False
    if any(part in _KEY_WORDS for part in parts):
        return True
    joined = f"_{upper}_"
    return any(f"_{phrase}_" in joined for phrase in _KEY_PHRASES)


def token_shape(value: str) -> bool:
    """Whether the value looks like a vendor token or a PEM block."""
    if len(value) < MIN_LENGTH:
        return False
    return value.startswith(_TOKEN_PREFIXES) or _TOKEN_PATTERN.match(value) is not None


def url_userinfo(value: str) -> bool:
    """Whether the value is a URL carrying ``user:password@``."""
    return _USERINFO.match(value) is not None


RULES: tuple[tuple[str, Callable[[str, str], bool]], ...] = (
    ("key-name", lambda key, value: key_name(key)),
    ("token-shape", lambda key, value: token_shape(value)),
    ("url-userinfo", lambda key, value: url_userinfo(value)),
)
