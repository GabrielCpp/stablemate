"""Time-based one-time passwords (RFC 6238), computed inside the vault.

A second factor is the other half of a machine identity's login, and it has the
same problem the password does: the thing worth protecting is the *seed*, and any
arrangement where something outside saddlebag turns the seed into a code has, by
construction, handed out the seed. A seed is not a password — it is a password
generator, valid until the account is re-enrolled — so it is the one credential
value that must never leave the store.

So saddlebag computes the code itself. The seed goes in under its own store key
and comes back out only as a six-digit number with a thirty-second lifetime, which
``fill`` types into the browser. Thirty implementations of this exist; the reason
this is thirty lines of :mod:`hmac` rather than a dependency or a shell-out to
``oathtool`` is that a subprocess takes the seed on its argv, where the process
table publishes it to every user on the box.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import struct
import time

#: The RFC 6238 defaults, which is what every authenticator app enrols with.
PERIOD_SECONDS = 30
DIGITS = 6


class SeedError(ValueError):
    """The stored seed is not usable base32."""


def decode_seed(seed: str) -> bytes:
    """Decode an enrolment seed as an authenticator app would.

    Providers print the seed in space-separated groups and in either case, and a
    seed whose length is not a multiple of 8 is normally shown without its padding.
    Accepting all three spellings is the difference between "the code is wrong" and
    "the value was pasted the way the screen showed it".
    """
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
    """How long the current code stays valid.

    Reported by ``fill`` so a caller that is about to submit a form knows whether it
    is racing the window — a code typed with two seconds left fails a verification
    that has nothing wrong with it.
    """
    moment = time.time() if now is None else now
    return int(period - (moment % period))
