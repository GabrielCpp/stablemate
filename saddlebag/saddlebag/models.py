"""Dataclasses for the pool's two concepts: the credential and the environment.

The split is deliberate and load-bearing:

* the **secret store** (OS keyring, or Vault) holds only sensitive values — a
  credential's password, an environment's ``secret`` entries;
* the **pool database** holds everything else — the metadata an agent reasons
  over, lease state, and an environment's *non-sensitive* ``config`` values.

So a :class:`Credential` never carries a password, and an
:class:`EnvironmentEntry` carries a value only when its kind is ``config``. The
only places a secret and its metadata travel together are
:class:`AcquiredCredential` and a rendered environment file — both of which exist
solely to be serialised to disk, with owner-only permissions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

# Sentinel used by the pool for "no lease".
NO_LEASE: str | None = None

#: An entry whose value has not arrived yet: a name, a ``required`` flag, a note.
KIND_PENDING = "pending"
#: A non-sensitive value, held in the clear in the pool DB.
KIND_CONFIG = "config"
#: A sensitive value, held in the secret store.
KIND_SECRET = "secret"
#: A value resolved at render time from a leased credential.
KIND_CREDENTIAL_REF = "credential-ref"

ENTRY_KINDS: tuple[str, ...] = (KIND_PENDING, KIND_CONFIG, KIND_SECRET, KIND_CREDENTIAL_REF)

#: The credential fields a ``credential-ref`` may point at.
CRED_REF_FIELDS: tuple[str, ...] = ("username", "password")

#: How a rendered environment file is written.
FORMATS: tuple[str, ...] = ("dotenv", "json")


def utcnow() -> datetime:
    """Current UTC time. Indirected so tests can freeze it."""
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def qualify(project: str | None, *parts: str) -> str:
    """Project-qualify a secret-store key.

    The keyring is one global namespace, so two repos with their own pools (via
    ``SADDLEBAG_DB``) must not collide: each minting a ``cred-001`` resolves to
    ``repo-a/cred-001`` and ``repo-b/cred-001``. An unscoped object keeps the bare
    key — which is also what everything created before projects existed used, so no
    already-stored secret needs migrating.
    """
    return "/".join([project, *parts]) if project else "/".join(parts)


def parse_cred_ref(ref: str) -> tuple[str, str]:
    """Split a ``credential-ref`` into ``(credential_id, field)``.

    Raises :class:`ValueError` on anything but ``<cred-id>:<field>`` with a field
    in :data:`CRED_REF_FIELDS` — a typo here would otherwise surface as a silently
    empty value in a rendered file.
    """
    credential_id, sep, field = ref.partition(":")
    if not sep or not credential_id:
        raise ValueError(f"expected <credential-id>:<field>, got {ref!r}")
    if field not in CRED_REF_FIELDS:
        raise ValueError(
            f"unknown credential field {field!r} in {ref!r} "
            f"(expected one of {', '.join(CRED_REF_FIELDS)})"
        )
    return credential_id, field


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

    @property
    def store_key(self) -> str:
        """Where this credential's password lives in the secret store."""
        return qualify(self.project, self.id)

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
class EnvironmentEntry:
    """One ``KEY`` in an environment, plus a declaration of where its value lives.

    The invariant this class exists to hold: **a value is present only when the
    kind is** ``config``. Everything sensitive resolves elsewhere — from the secret
    store, or from a leased credential — so an entry read out of the pool DB is
    structurally incapable of carrying a secret. The database enforces the same
    rule with a ``CHECK`` constraint; this is the same fence, one layer up.
    """

    key: str
    kind: str = KIND_PENDING
    value: str | None = None
    cred_ref: str | None = None
    required: bool = True
    note: str | None = None
    position: int = 0

    def __post_init__(self) -> None:
        if self.kind not in ENTRY_KINDS:
            raise ValueError(f"unknown entry kind {self.kind!r} for {self.key}")
        if self.kind != KIND_CONFIG and self.value is not None:
            raise ValueError(f"a {self.kind} entry ({self.key}) cannot hold a value")
        if self.kind == KIND_CONFIG and self.value is None:
            raise ValueError(f"a config entry ({self.key}) needs a value")
        if self.kind == KIND_CREDENTIAL_REF:
            if not self.cred_ref:
                raise ValueError(f"a credential-ref entry ({self.key}) needs a reference")
            parse_cred_ref(self.cred_ref)
        elif self.cred_ref is not None:
            raise ValueError(f"a {self.kind} entry ({self.key}) cannot hold a credential-ref")

    @property
    def needs_store(self) -> bool:
        """Whether resolving this entry requires opening the secret store.

        A ``config`` entry never does — which is what lets a config-only
        environment render on a host with no keyring and no Vault at all.
        """
        return self.kind in (KIND_SECRET, KIND_CREDENTIAL_REF)

    def display_value(self) -> str:
        """What ``env show`` prints. Never a secret — by construction, not by redaction."""
        if self.kind == KIND_CONFIG:
            return self.value or ""
        if self.kind == KIND_SECRET:
            return "<set>"
        if self.kind == KIND_CREDENTIAL_REF:
            return f"<{self.cred_ref}>"
        return "<pending>"

    def to_dict(self) -> dict[str, Any]:
        """Redacted form — safe for ``env show --json``, which agents read."""
        return {
            "key": self.key,
            "kind": self.kind,
            "value": self.value,
            "from": self.cred_ref,
            "required": self.required,
            "note": self.note,
        }


@dataclass(frozen=True)
class Environment:
    """A named, project-scoped, ordered set of entries — a ``.env``-shaped bundle.

    Unlike a credential, an environment is **not leased**: it is shared, read-only
    configuration, and ten runs may render it at once. Only the credentials its
    ``credential-ref`` entries point at are exclusive.
    """

    id: str
    name: str
    env: str
    project: str | None = None
    target: str | None = None
    format: str = "dotenv"
    description: str | None = None
    last_used: datetime | None = None
    entries: tuple[EnvironmentEntry, ...] = ()

    def store_key(self, key: str) -> str:
        """Where entry ``key``'s secret lives — ``<project>/<env-id>/<KEY>``."""
        return qualify(self.project, self.id, key)

    @property
    def needs_store(self) -> bool:
        """True once any entry requires the secret store. See :meth:`EnvironmentEntry.needs_store`."""
        return any(entry.needs_store for entry in self.entries)

    def to_dict(self) -> dict[str, Any]:
        """Redacted form. Cannot contain a secret — its entries cannot."""
        return {
            "id": self.id,
            "name": self.name,
            "env": self.env,
            "project": self.project,
            "target": self.target,
            "format": self.format,
            "description": self.description,
            "last_used": _iso(self.last_used),
            "entries": [e.to_dict() for e in self.entries],
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
