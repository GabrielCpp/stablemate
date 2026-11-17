"""What saddlebag accepts as a name, a tag, a metadata pair or a value, written as the app checks it."""

from __future__ import annotations

import base64
import binascii
import json
import re
from urllib.parse import quote, quote_plus

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
VAR = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
META_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")

Pair = tuple[str, str]


def split(text: str) -> tuple[bool, str, str]:
    """Whether the text is `key=value`, and the key and value with their spaces trimmed."""
    key, sep, value = text.partition("=")
    key, value = key.strip(), value.strip()
    return bool(sep and key and value), key, value


def tag_of(text: str) -> Pair | None:
    ok, key, value = split(text)
    return (key, value) if ok else None


def meta_of(text: str) -> Pair | None:
    ok, key, value = split(text)
    return (key, value) if ok and META_KEY.fullmatch(key) else None


def first_bad_tag(texts: list[str] | None) -> str | None:
    return next((t for t in texts or () if tag_of(t) is None), None)


def first_bad_meta(texts: list[str] | None) -> str | None:
    return next((t for t in texts or () if meta_of(t) is None), None)


def repeated_meta(texts: list[str] | None) -> str | None:
    seen: set[str] = set()
    for text in texts or ():
        pair = meta_of(text)
        if pair is None:
            continue
        if pair[0] in seen:
            return pair[0]
        seen.add(pair[0])
    return None


def seed_fault(value: str) -> str | None:
    """Why a text is no TOTP seed, as the app words it, or None when it is one."""
    normalised = value.strip().replace(" ", "").replace("-", "").upper()
    if not normalised:
        return "the stored seed is empty"
    padded = normalised + "=" * (-len(normalised) % 8)
    try:
        base64.b32decode(padded, casefold=True)
    except (binascii.Error, ValueError) as exc:
        return f"the stored seed is not valid base32: {exc}"
    return None


def sorted_pairs(pairs: set[Pair] | frozenset[Pair]) -> tuple[Pair, ...]:
    return tuple(sorted(pairs))


KEY_WORDS = frozenset({"PASSWORD", "PASSWD", "PASS", "SECRET", "TOKEN", "APIKEY", "PRIVATE", "CREDENTIAL", "CREDENTIALS", "AUTH", "DSN"})
KEY_PHRASES = ("API_KEY", "PRIVATE_KEY", "CLIENT_SECRET", "ACCESS_KEY", "SECRET_KEY")
TOKEN_PREFIXES = ("sk-", "ghp_", "github_pat_", "hvs.", "AKIA")
TOKEN_PATTERN = re.compile(r"xox[abprs]-|glpat-|-----BEGIN ")
USERINFO = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/@\s:]+:[^/@\s]+@")
MIN_LENGTH = 8


def key_name(key: str) -> bool:
    upper = key.upper()
    parts = upper.split("_")
    if "PUBLIC" in upper or upper.endswith("_PUBLIC_KEY"):
        return False
    if any(part in KEY_WORDS for part in parts):
        return True
    joined = f"_{upper}_"
    return any(f"_{phrase}_" in joined for phrase in KEY_PHRASES)


def token_shape(value: str) -> bool:
    if len(value) < MIN_LENGTH:
        return False
    return value.startswith(TOKEN_PREFIXES) or TOKEN_PATTERN.match(value) is not None


def url_userinfo(value: str) -> bool:
    return USERINFO.match(value) is not None


def shape_rule(key: str, value: str) -> str | None:
    """The first rule of the shapes that makes a dotenv line secret, by name."""
    if key_name(key):
        return "key-name"
    if token_shape(value):
        return "token-shape"
    if url_userinfo(value):
        return "url-userinfo"
    return None


FORMS = (
    ("as written", lambda value: value),
    ("compose", lambda value: value.replace("$", "$$")),
    ("url path", lambda value: quote(value, safe="")),
    ("url query", lambda value: quote_plus(value, safe="")),
    ("json ascii", lambda value: json.dumps(value)[1:-1]),
    ("json unicode", lambda value: json.dumps(value, ensure_ascii=False)[1:-1]),
)


def forms(value: str) -> frozenset[str]:
    """The value as written, and as compose, a URL and a JSON string escape it."""
    return frozenset(derive(value) for _, derive in FORMS)


BARE = re.compile(r"[^\s#'\"\\$`]*")


def quoted(value: str) -> str | None:
    """The value written so a dotenv reader gives it back, or None when no quoting can."""
    if "\n" in value or "\r" in value:
        return None
    if BARE.fullmatch(value):
        return value
    if "'" not in value:
        return f"'{value}'"
    if not any(char in value for char in "\"\\$`"):
        return f'"{value}"'
    return None


def binding_of(text: str) -> tuple[str, str, str] | None:
    """The variable, the secret and the field an `--env VAR=NAME[.field]` names."""
    var, sep, source = text.partition("=")
    name, _, field = source.partition(".")
    if not sep or not var or not name:
        return None
    return var, name, field or "password"


def key_of(line: str) -> tuple[str, str] | None:
    """The key and value of a plain `KEY=value` dotenv line."""
    if line.startswith("#") or "=" not in line:
        return None
    key, _, value = line.partition("=")
    return key, value
