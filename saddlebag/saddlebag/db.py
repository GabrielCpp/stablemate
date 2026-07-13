"""The credential pool — SQLite metadata and lease management.

This module knows nothing about passwords. It stores the metadata an agent
reasons over (env, roles, features, surface) and the lease state that keeps
parallel workhorse runs from colliding. Secrets live in :mod:`saddlebag.store`.

Timestamps are persisted as epoch seconds (REAL) rather than ISO strings, so
that lease-expiry comparisons happen in SQL as numeric comparisons. Comparing
ISO strings lexicographically happens to work for a fixed format, but breaks the
moment a microsecond component appears or disappears.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import platformdirs

from .models import Credential, Lease, Requirement, utcnow

#: Default lease lifetime, in seconds (2 hours).
DEFAULT_TTL = 7200

_SCHEMA = """
CREATE TABLE IF NOT EXISTS credentials (
    id          TEXT PRIMARY KEY,
    username    TEXT NOT NULL,
    env         TEXT NOT NULL,
    project     TEXT,
    roles       TEXT NOT NULL DEFAULT '[]',
    features    TEXT NOT NULL DEFAULT '[]',
    surface     TEXT,
    last_used   REAL,
    lease_id    TEXT UNIQUE,
    run_id      TEXT,
    acquired_at REAL,
    expires_at  REAL
);
"""

# Columns added after the initial release, applied to pre-existing pools on open.
# Each entry is (column_name, "ALTER TABLE ... ADD COLUMN ..." statement).
_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("project", "ALTER TABLE credentials ADD COLUMN project TEXT"),
)

# Indexes are created after migrations, so an index may reference a migrated
# column that an old pool did not originally have.
_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_credentials_env ON credentials(env);
CREATE INDEX IF NOT EXISTS idx_credentials_project ON credentials(project);
CREATE INDEX IF NOT EXISTS idx_credentials_run ON credentials(run_id);
"""

_ID_RE = re.compile(r"^cred-(\d+)$")


class PoolError(RuntimeError):
    """A pool operation could not be completed."""


def default_db_path() -> Path:
    """Where the pool lives, honouring each OS's convention.

    ``$SADDLEBAG_DB`` overrides everything. Otherwise the location follows the
    platform's user-data directory via :mod:`platformdirs`:

    * Linux:   ``~/.local/share/saddlebag/pool.db`` (or ``$XDG_DATA_HOME``)
    * macOS:   ``~/Library/Application Support/saddlebag/pool.db``
    * Windows: ``%LOCALAPPDATA%\\saddlebag\\pool.db``
    """
    if override := os.environ.get("SADDLEBAG_DB"):
        return Path(override).expanduser()
    return Path(platformdirs.user_data_dir("saddlebag")) / "pool.db"


def _dt(value: float | None) -> datetime | None:
    # Test `is not None`, not truthiness: epoch 0 is a real instant (1970-01-01)
    # and a falsy float. Reading it back as None would make an expired lease look
    # like no lease at all.
    return datetime.fromtimestamp(value, tz=UTC) if value is not None else None


class Pool:
    """The credential pool. Metadata and leases only — never a password."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else default_db_path()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._conn.executescript(_INDEXES)

    def _migrate(self) -> None:
        """Bring a pre-existing pool up to the current schema.

        ``CREATE TABLE IF NOT EXISTS`` never alters an existing table, so a pool
        created before a column existed keeps the old shape. Add any missing
        column here — additively, so an old pool opened by a new saddlebag simply
        gains the column (NULL for existing rows) rather than erroring.
        """
        have = {r["name"] for r in self._conn.execute("PRAGMA table_info(credentials)")}
        for column, statement in _MIGRATIONS:
            if column not in have:
                self._conn.execute(statement)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Pool:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- reads ---------------------------------------------------------------

    def _row_to_credential(self, row: sqlite3.Row) -> Credential:
        return Credential(
            id=row["id"],
            username=row["username"],
            env=row["env"],
            project=row["project"],
            roles=tuple(json.loads(row["roles"])),
            features=tuple(json.loads(row["features"])),
            surface=row["surface"],
            last_used=_dt(row["last_used"]),
            lease_id=row["lease_id"],
            run_id=row["run_id"],
            expires_at=_dt(row["expires_at"]),
        )

    def get(self, credential_id: str) -> Credential | None:
        row = self._conn.execute(
            "SELECT * FROM credentials WHERE id = ?", (credential_id,)
        ).fetchone()
        return self._row_to_credential(row) if row else None

    def all(self) -> list[Credential]:
        rows = self._conn.execute("SELECT * FROM credentials ORDER BY id").fetchall()
        return [self._row_to_credential(r) for r in rows]

    def find(
        self,
        requirement: Requirement | None = None,
        *,
        include_locked: bool = False,
        now: datetime | None = None,
    ) -> list[Credential]:
        """Credentials satisfying ``requirement``.

        ``roles`` and ``features`` are **superset** matches: a credential
        qualifies when it holds every required role, extras allowed. ``env``,
        ``project`` and ``surface`` are exact.
        """
        now = now or utcnow()
        req = requirement or Requirement()
        out: list[Credential] = []
        for cred in self.all():
            if req.env and cred.env != req.env:
                continue
            if req.project and cred.project != req.project:
                continue
            if req.surface and cred.surface != req.surface:
                continue
            if not set(req.roles).issubset(cred.roles):
                continue
            if not set(req.features).issubset(cred.features):
                continue
            if not include_locked and cred.is_locked(now):
                continue
            out.append(cred)
        return out

    def leases(self, now: datetime | None = None) -> list[Lease]:
        """Every outstanding lease, expired ones included."""
        now = now or utcnow()
        rows = self._conn.execute(
            "SELECT * FROM credentials WHERE lease_id IS NOT NULL ORDER BY id"
        ).fetchall()
        return [
            Lease(
                lease_id=r["lease_id"],
                credential_id=r["id"],
                run_id=r["run_id"],
                acquired_at=_dt(r["acquired_at"]),
                expires_at=_dt(r["expires_at"]),
            )
            for r in rows
        ]

    # -- writes --------------------------------------------------------------

    def _next_id(self) -> str:
        rows = self._conn.execute("SELECT id FROM credentials").fetchall()
        used = [int(m.group(1)) for r in rows if (m := _ID_RE.match(r["id"]))]
        return f"cred-{max(used, default=0) + 1:03d}"

    def add(
        self,
        *,
        username: str,
        env: str,
        project: str | None = None,
        roles: Iterable[str] = (),
        features: Iterable[str] = (),
        surface: str | None = None,
        credential_id: str | None = None,
    ) -> Credential:
        cred = Credential(
            id=credential_id or self._next_id(),
            username=username,
            env=env,
            project=project,
            roles=tuple(roles),
            features=tuple(features),
            surface=surface,
        )
        try:
            self._conn.execute(
                "INSERT INTO credentials (id, username, env, project, roles, features, surface) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    cred.id,
                    cred.username,
                    cred.env,
                    cred.project,
                    json.dumps(list(cred.roles)),
                    json.dumps(list(cred.features)),
                    cred.surface,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise PoolError(f"credential {cred.id} already exists") from exc
        return cred

    def remove(self, credential_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM credentials WHERE id = ?", (credential_id,))
        return cur.rowcount > 0

    def acquire(
        self,
        credential_id: str,
        *,
        ttl: int = DEFAULT_TTL,
        run_id: str | None = None,
        now: datetime | None = None,
    ) -> Lease:
        """Take an exclusive lease. Raises :class:`PoolError` if already locked.

        The guard lives in the ``WHERE`` clause, so two concurrent callers racing
        for the same credential cannot both win: SQLite serialises the writes and
        the loser's ``UPDATE`` matches zero rows.
        """
        if ttl <= 0:
            raise PoolError(f"ttl must be positive, got {ttl}")
        now = now or utcnow()
        expires = now.timestamp() + ttl
        lease_id = uuid.uuid4().hex

        cur = self._conn.execute(
            "UPDATE credentials SET lease_id = ?, run_id = ?, acquired_at = ?, "
            "expires_at = ?, last_used = ? "
            "WHERE id = ? AND (lease_id IS NULL OR expires_at <= ?)",
            (lease_id, run_id, now.timestamp(), expires, now.timestamp(),
             credential_id, now.timestamp()),
        )
        if cur.rowcount == 0:
            if self.get(credential_id) is None:
                raise PoolError(f"no such credential: {credential_id}")
            raise PoolError(f"credential {credential_id} is already leased")

        return Lease(
            lease_id=lease_id,
            credential_id=credential_id,
            run_id=run_id,
            acquired_at=now,
            expires_at=datetime.fromtimestamp(expires, tz=UTC),
        )

    def _clear(self, where: str, params: Sequence[object]) -> int:
        cur = self._conn.execute(
            "UPDATE credentials SET lease_id = NULL, run_id = NULL, "
            f"acquired_at = NULL, expires_at = NULL WHERE {where}",
            tuple(params),
        )
        return cur.rowcount

    def release_lease(self, lease_id: str) -> int:
        """Release one lease by id. Returns the number of credentials freed."""
        return self._clear("lease_id = ?", (lease_id,))

    def release_run(self, run_id: str) -> int:
        """Release every lease tagged with a workhorse run id."""
        return self._clear("run_id = ?", (run_id,))

    def expire(self, now: datetime | None = None) -> int:
        """Force-release leases past their TTL. Safe to run in CI cleanup."""
        now = now or utcnow()
        return self._clear(
            "lease_id IS NOT NULL AND expires_at <= ?", (now.timestamp(),)
        )
