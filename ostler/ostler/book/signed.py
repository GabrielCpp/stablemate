"""A credential that keeps an account signed in for a play of any length.

A surface holds every account as a `Signed`, never a bare token. A play outlasts
a token's life, and a `Signed` signs the account in again whenever it is read
with less than `margin` seconds of life left.
"""

from __future__ import annotations

import base64
import binascii
import json
import threading
import time
from typing import Callable


def expiry(token: str) -> float | None:
    """The `exp` of a JWT, or None when the token is not one."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        middle = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(middle))
    except (binascii.Error, ValueError):
        return None
    exp = claims.get("exp") if isinstance(claims, dict) else None
    if isinstance(exp, bool) or not isinstance(exp, (int, float)):
        return None
    return float(exp)


class Signed:
    """An account's token, signed in on first read and again when it nears its end."""

    def __init__(self, sign_in: Callable[[], str], *, lasts: float | None = None, margin: float = 300.0,
                 clock: Callable[[], float] = time.time):
        self.sign_in = sign_in
        self.lasts = lasts
        self.margin = margin
        self.clock = clock
        self.held: str | None = None
        self.ends: float | None = None
        self.lock = threading.Lock()

    @property
    def token(self) -> str:
        with self.lock:
            if self.held is None or self.nearing():
                self.held = self.sign_in()
                self.ends = self.end_of(self.held)
            return self.held

    def nearing(self) -> bool:
        return self.ends is not None and self.ends - self.clock() < self.margin

    def end_of(self, token: str) -> float | None:
        exp = expiry(token)
        if exp is not None:
            return exp
        return None if self.lasts is None else self.clock() + self.lasts

    def __str__(self) -> str:
        return self.token

    def __repr__(self) -> str:
        return f"Signed({'signed in' if self.held is not None else 'not yet signed in'})"
