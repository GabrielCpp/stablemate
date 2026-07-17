"""Resolving an environment to values, and checking it without writing.

This is the one place in saddlebag where an environment's secrets are read, and
it is deliberately small. Two entry points:

* :func:`resolve` turns entries into values — reading ``config`` from the pool DB,
  ``secret`` from the store, and ``credential-ref`` from a **leased** credential.
* :func:`check` resolves the same way but takes no lease and writes nothing, then
  diffs the result against the target file. It is the gate a QA preflight calls,
  and it is safe to run anywhere because its report names keys, never values.

Two properties are worth stating outright, because they are why this module is
shaped the way it is:

**The store is opened lazily.** ``open_store`` arrives as a zero-argument callable,
not an open store, and is called only when an entry actually needs it. An
environment made entirely of ``config`` entries therefore renders on a host with no
keyring and no Vault — which is exactly the host (a container, a CI box) where a
stack most needs to be reproducible. The no-plaintext-fallback rule is untouched:
it governs material that *is* secret.

**Nothing is written until everything resolves.** Resolution runs in two passes:
one that reads and collects gaps, and — only if there are none — one that takes
the leases. A missing key can never leave a half-rendered file behind, and a lease
that fails to be taken rolls back the leases taken beside it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from saddlebag import envfile
from saddlebag.db import DEFAULT_TTL, Pool, PoolError
from saddlebag.models import KIND_CONFIG, KIND_CREDENTIAL_REF, KIND_PENDING, KIND_SECRET, Environment, parse_cred_ref
from saddlebag.store import SecretStore

#: A zero-argument opener, so the store is touched only when an entry needs it.
StoreOpener = Callable[[], SecretStore]

#: Why an entry could not be resolved. These are the only reasons.
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

    #: KEY -> value, in render order. Optional entries that resolved to nothing are
    #: simply absent. This is the only object in the module that holds a secret.
    values: dict[str, str] = field(default_factory=dict)
    #: Required entries that could not be resolved. Non-empty means: do not write.
    gaps: list[Gap] = field(default_factory=list)
    #: credential id -> lease id, for the credential-refs this resolution leased.
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

    password = open_store().get(cred.store_key)
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
    """Resolve every entry to a value.

    With ``lease=True`` the credentials behind any ``credential-ref`` entries are
    leased for ``run_id`` — the same exclusive checkout ``saddlebag acquire`` takes,
    released by the same ``saddlebag release --run-id``. With ``lease=False``
    (what ``--check`` uses) they are read but not leased, so the gate has no side
    effects at all.

    An entry that is *not* required and has no value is dropped from the output
    rather than recorded as a gap: the rendered file simply omits the key.
    """
    result = Resolution()
    refs: dict[str, str] = {}  # KEY -> credential id, for the leasing pass

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
            # An optional key with nothing behind it is not a gap — it is a key the
            # rendered file leaves out, which is what "not required" means.
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
    """Lease each referenced credential exactly once, all-or-nothing.

    Two entries may point at the same credential (``TEST_USER_EMAIL`` and
    ``TEST_USER_PASSWORD`` routinely do), so leases are taken per *credential*, not
    per entry. A credential this run already holds is reused rather than re-leased —
    otherwise a second ``env render`` inside one run would collide with its own
    first one. If any lease cannot be taken, the ones taken alongside it are handed
    back before the error propagates, so a failed render strands nothing.
    """
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
    """What ``env render --check`` found. Names keys; never emits a value."""

    environment: str
    id: str
    target: str | None
    gaps: list[Gap] = field(default_factory=list)
    #: In the environment, absent from the target file.
    missing: list[str] = field(default_factory=list)
    #: In the target file, not in the environment.
    extra: list[str] = field(default_factory=list)
    #: In both, but the file's value is not the one the environment would render.
    drift: list[str] = field(default_factory=list)
    #: Whether the target file exists at all.
    target_exists: bool = False

    @property
    def resolvable(self) -> bool:
        """Every required key has a value behind it. Nothing here needs a human."""
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
    """Resolve the environment and diff it against its target file — writing nothing.

    Drift is reported by key name only. The comparison itself does look at values
    (it has to, to know a key drifted), but no value reaches the report, so the
    output stays safe to print in CI, hand to an agent, or paste into an issue.
    """
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
        # Not rendered yet: every key it should hold is missing.
        report.missing = list(resolution.values)
        return report

    report.target_exists = True
    report.missing = [k for k in resolution.values if k not in on_disk]
    report.extra = [k for k in on_disk if k not in resolution.values]
    report.drift = [k for k, v in resolution.values.items() if k in on_disk and on_disk[k] != v]
    return report
