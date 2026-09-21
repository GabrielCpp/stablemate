"""Dataclasses for the pool's two concepts: the credential and the environment."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

NO_LEASE: str | None = None

KIND_PENDING = "pending"
KIND_CONFIG = "config"
KIND_SECRET = "secret"
KIND_CREDENTIAL_REF = "credential-ref"

ENTRY_KINDS: tuple[str, ...] = (KIND_PENDING, KIND_CONFIG, KIND_SECRET, KIND_CREDENTIAL_REF)

CRED_REF_FIELDS: tuple[str, ...] = ("username", "password")

FORMATS: tuple[str, ...] = ("dotenv", "json")


def utcnow() -> datetime:
    """Current UTC time."""
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def qualify(project: str | None, *parts: str) -> str:
    """Project-qualify a secret-store key."""
    return "/".join([project, *parts]) if project else "/".join(parts)


def parse_cred_ref(ref: str) -> tuple[str, str]:
    """Split a ``credential-ref`` into ``(credential_id, field)``."""
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
class KeychainRef:
    """Where a secret lives in the OS keychain, when saddlebag does not hold it."""

    attributes: tuple[tuple[str, str], ...]

    @classmethod
    def of(cls, attributes: Mapping[str, str]) -> KeychainRef:
        return cls(tuple(sorted(attributes.items())))

    def as_dict(self) -> dict[str, str]:
        return dict(self.attributes)

    def describe(self) -> str:
        """One line, for a human deciding whether this names the item they meant."""
        return " ".join(f"{name}={value}" for name, value in self.attributes)


@dataclass(frozen=True)
class Credential:
    """A test identity."""

    id: str
    username: str
    env: str
    project: str | None = None
    roles: tuple[str, ...] = ()
    features: tuple[str, ...] = ()
    surface: str | None = None
    password_ref: KeychainRef | None = None
    totp_ref: KeychainRef | None = None
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

    @property
    def totp_store_key(self) -> str:
        """Where this credential's TOTP enrolment seed lives, if it has one."""
        return qualify(self.project, self.id, "totp")

    def to_dict(self, now: datetime | None = None) -> dict[str, Any]:
        """Redacted form."""
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
            "password_ref": self.password_ref.describe() if self.password_ref else None,
            "totp_ref": self.totp_ref.describe() if self.totp_ref else None,
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
class EnvironmentEntry:
    """One ``KEY`` in an environment, plus a declaration of where its value lives."""

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
        """Whether resolving this entry requires opening the secret store."""
        return self.kind in (KIND_SECRET, KIND_CREDENTIAL_REF)

    def display_value(self) -> str:
        """What ``env show`` prints."""
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
    """A named, project-scoped, ordered set of entries — a ``.env``-shaped bundle."""

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
        """True once any entry requires the secret store."""
        return any(entry.needs_store for entry in self.entries)

    def to_dict(self) -> dict[str, Any]:
        """Redacted form."""
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
    """What a run needs."""

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
