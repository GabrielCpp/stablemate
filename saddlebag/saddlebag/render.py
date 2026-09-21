"""Resolving an environment to values, and checking it without writing."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from saddlebag import envfile, keychain
from saddlebag.db import DEFAULT_TTL, Pool, PoolError
from saddlebag.models import KIND_CONFIG, KIND_CREDENTIAL_REF, KIND_PENDING, KIND_SECRET, Environment, parse_cred_ref
from saddlebag.store import SecretStore

StoreOpener = Callable[[], SecretStore]

PENDING = "pending"
UNSET = "unset"
DANGLING = "dangling"


@dataclass(frozen=True)
class Gap:
    """One required key that could not be resolved, and why."""

    key: str
    reason: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"key": self.key, "reason": self.reason, "detail": self.detail}

    def __str__(self) -> str:
        return f"{self.key}: {self.detail}"


@dataclass
class Resolution:
    """The resolved environment: values to write, gaps that stop the write."""

    values: dict[str, str] = field(default_factory=dict)
    gaps: list[Gap] = field(default_factory=list)
    leases: dict[str, str] = field(default_factory=dict)

    @property
    def resolvable(self) -> bool:
        return not self.gaps


def _cred_value(
    pool: Pool,
    open_store: StoreOpener,
    credential_id: str,
    cred_field: str,
) -> tuple[str | None, str | None]:
    """The value behind a credential-ref, or ``(None, why-not)``."""
    cred = pool.get(credential_id)
    if cred is None:
        return None, f"no such credential: {credential_id}"
    if cred_field == "username":
        return cred.username, None

    try:
        password = keychain.password_for(cred, open_store())
    except keychain.KeychainError as exc:
        return None, f"{credential_id}: {exc}"
    if password is None:
        return None, f"{credential_id} has no password in the store"
    return password, None


def resolve(
    environment: Environment,
    pool: Pool,
    open_store: StoreOpener,
    *,
    lease: bool = True,
    run_id: str | None = None,
    ttl: int = DEFAULT_TTL,
) -> Resolution:
    """Resolve every entry to a value."""
    result = Resolution()
    refs: dict[str, str] = {}

    for entry in environment.entries:
        value: str | None = None
        gap: Gap | None = None

        if entry.kind == KIND_CONFIG:
            value = entry.value or ""
        elif entry.kind == KIND_PENDING:
            gap = Gap(entry.key, PENDING, "no value has been supplied yet")
        elif entry.kind == KIND_SECRET:
            value = open_store().get(environment.store_key(entry.key))
            if value is None:
                gap = Gap(entry.key, UNSET, "declared secret, but the store has no value for it")
        elif entry.kind == KIND_CREDENTIAL_REF:
            credential_id, cred_field = parse_cred_ref(str(entry.cred_ref))
            value, problem = _cred_value(pool, open_store, credential_id, cred_field)
            if problem:
                gap = Gap(entry.key, DANGLING, problem)
            else:
                refs[entry.key] = credential_id

        if gap is not None:
            if entry.required:
                result.gaps.append(gap)
            continue

        if value is not None:
            result.values[entry.key] = value

    if lease and result.resolvable and refs:
        result.leases = _take_leases(pool, set(refs.values()), run_id=run_id, ttl=ttl)
    return result


def _take_leases(
    pool: Pool, credential_ids: set[str], *, run_id: str | None, ttl: int
) -> dict[str, str]:
    """Lease each referenced credential exactly once, all-or-nothing."""
    taken: dict[str, str] = {}
    try:
        for credential_id in sorted(credential_ids):
            cred = pool.get(credential_id)
            if cred is not None and run_id and cred.run_id == run_id and cred.is_locked():
                taken[credential_id] = str(cred.lease_id)
                continue
            taken[credential_id] = pool.acquire(credential_id, ttl=ttl, run_id=run_id).lease_id
    except PoolError:
        for credential_id, lease_id in taken.items():
            cred = pool.get(credential_id)
            if cred is not None and cred.lease_id == lease_id:
                pool.release_lease(lease_id)
        raise
    return taken


def format_values(values: dict[str, str], fmt: str) -> str:
    """Render resolved values as the environment's file format."""
    if fmt == "json":
        return json.dumps(values, indent=2) + "\n"
    return envfile.dumps(values)


def read_target(path: Path | str, fmt: str) -> dict[str, str] | None:
    """Parse an already-rendered target file, or ``None`` if it is not there."""
    path = Path(path)
    if not path.exists():
        return None
    if fmt == "json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()}
    return envfile.parse(path)


@dataclass
class CheckReport:
    """What ``env render --check`` found."""

    environment: str
    id: str
    target: str | None
    gaps: list[Gap] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    drift: list[str] = field(default_factory=list)
    target_exists: bool = False

    @property
    def resolvable(self) -> bool:
        """Every required key has a value behind it."""
        return not self.gaps

    @property
    def in_sync(self) -> bool:
        """The target file on disk is exactly what a render would produce."""
        return self.target_exists and not (self.missing or self.extra or self.drift)

    @property
    def ok(self) -> bool:
        return self.resolvable and self.in_sync

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            "id": self.id,
            "target": self.target,
            "gaps": [g.to_dict() for g in self.gaps],
            "target_exists": self.target_exists,
            "missing": self.missing,
            "extra": self.extra,
            "drift": self.drift,
            "resolvable": self.resolvable,
            "in_sync": self.in_sync,
        }


def check(
    environment: Environment,
    pool: Pool,
    open_store: StoreOpener,
    *,
    target: Path | str | None = None,
) -> CheckReport:
    """Resolve the environment and diff it against its target file — writing nothing."""
    resolution = resolve(environment, pool, open_store, lease=False)
    target = target or environment.target
    report = CheckReport(
        environment=environment.name,
        id=environment.id,
        target=str(target) if target else None,
        gaps=resolution.gaps,
    )
    if target is None:
        return report

    on_disk = read_target(target, environment.format)
    if on_disk is None:
        report.missing = list(resolution.values)
        return report

    report.target_exists = True
    report.missing = [k for k in resolution.values if k not in on_disk]
    report.extra = [k for k in on_disk if k not in resolution.values]
    report.drift = [k for k, v in resolution.values.items() if k in on_disk and on_disk[k] != v]
    return report
