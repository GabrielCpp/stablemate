"""Time-based one-time passwords (RFC 6238), computed inside the vault."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import struct
import time

PERIOD_SECONDS = 30
DIGITS = 6


class SeedError(ValueError):
    """The stored seed is not usable base32."""


def decode_seed(seed: str) -> bytes:
    """Decode an enrolment seed as an authenticator app would."""
    normalised = seed.strip().replace(" ", "").replace("-", "").upper()
    if not normalised:
        raise SeedError("the stored seed is empty")
    padded = normalised + "=" * (-len(normalised) % 8)
    try:
        return base64.b32decode(padded, casefold=True)
    except (binascii.Error, ValueError) as exc:
        raise SeedError(f"the stored seed is not valid base32: {exc}") from exc


def code(seed: str, *, now: float | None = None, period: int = PERIOD_SECONDS, digits: int = DIGITS) -> str:
    """The current TOTP for ``seed``, zero-padded to ``digits``."""
    counter = int((time.time() if now is None else now) // period)
    digest = hmac.new(decode_seed(seed), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    (truncated,) = struct.unpack(">I", digest[offset : offset + 4])
    return str((truncated & 0x7FFF_FFFF) % (10**digits)).zfill(digits)


def seconds_remaining(*, now: float | None = None, period: int = PERIOD_SECONDS) -> int:
    """How long the current code stays valid."""
    moment = time.time() if now is None else now
    return int(period - (moment % period))
