"""Dataclasses for the credential pool.

The split is deliberate and load-bearing:

* the **secret store** (OS keyring, or Vault) holds only the password, keyed by
  credential id;
* the **pool database** holds everything else — the metadata an agent reasons
  over, plus lease state.

So a :class:`Credential` never carries a password. The only place a password and
its metadata travel together is :class:`AcquiredCredential`, which exists solely
to be serialised into a ``.workhorse/`` output file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

# Sentinel used by the pool for "no lease".
NO_LEASE: str | None = None


def utcnow() -> datetime:
    """Current UTC time. Indirected so tests can freeze it."""
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


@dataclass(frozen=True)
class Credential:
    """A test identity. Metadata only — the password lives in the secret store."""

    id: str
    username: str
    env: str
    project: str | None = None
    roles: tuple[str, ...] = ()
    features: tuple[str, ...] = ()
    surface: str | None = None
    last_used: datetime | None = None
    lease_id: str | None = None
    run_id: str | None = None
    expires_at: datetime | None = None

    def is_locked(self, now: datetime | None = None) -> bool:
        """A credential is locked while it holds a lease that has not expired."""
        if self.lease_id is None or self.expires_at is None:
            return False
        return self.expires_at > (now or utcnow())

    def is_stale(self, now: datetime | None = None) -> bool:
        """Holds a lease whose TTL has elapsed — reclaimable by ``expire``."""
        if self.lease_id is None or self.expires_at is None:
            return False
        return self.expires_at <= (now or utcnow())

    def to_dict(self, now: datetime | None = None) -> dict[str, Any]:
        """Redacted form. Never contains a password — safe for ``list`` and ``scan``."""
        return {
            "id": self.id,
            "username": self.username,
            "env": self.env,
            "project": self.project,
            "roles": list(self.roles),
            "features": list(self.features),
            "surface": self.surface,
            "locked": self.is_locked(now),
            "last_used": _iso(self.last_used),
            "lease_id": self.lease_id,
        }


@dataclass(frozen=True)
class Lease:
    """An exclusive checkout of a credential, bounded by a hard TTL."""

    lease_id: str
    credential_id: str
    acquired_at: datetime
    expires_at: datetime
    run_id: str | None = None

    def is_expired(self, now: datetime | None = None) -> bool:
        return self.expires_at <= (now or utcnow())

    def to_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "credential_id": self.credential_id,
            "run_id": self.run_id,
            "acquired_at": _iso(self.acquired_at),
            "expires_at": _iso(self.expires_at),
        }


@dataclass(frozen=True)
class AcquiredCredential:
    """A leased credential *with* its password, bound for a ``.workhorse/`` file.

    This is the only object in saddlebag that carries a secret. Build it late,
    serialise it once, and never log it.
    """

    credential: Credential
    lease: Lease
    password: str

    def to_dict(self) -> dict[str, Any]:
        cred = self.credential
        return {
            "id": cred.id,
            "username": cred.username,
            "password": self.password,
            "env": cred.env,
            "roles": list(cred.roles),
            "features": list(cred.features),
            "surface": cred.surface,
            "lease_id": self.lease.lease_id,
            "run_id": self.lease.run_id,
            "expires_at": _iso(self.lease.expires_at),
        }


@dataclass(frozen=True)
class Requirement:
    """What a run needs. Mirrors an ostler seed's spec fields."""

    env: str | None = None
    project: str | None = None
    roles: tuple[str, ...] = ()
    features: tuple[str, ...] = ()
    surface: str | None = None

    def describe(self) -> str:
        """A one-line rendering for the selection prompt."""
        parts: list[str] = []
        if self.env:
            parts.append(f"env={self.env}")
        if self.project:
            parts.append(f"project={self.project}")
        if self.roles:
            parts.append(f"roles=[{', '.join(self.roles)}]")
        if self.features:
            parts.append(f"features=[{', '.join(self.features)}]")
        if self.surface:
            parts.append(f"surface={self.surface}")
        return ", ".join(parts) if parts else "(no constraints)"
