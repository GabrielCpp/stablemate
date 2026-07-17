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
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import platformdirs

from saddlebag.models import FORMATS, Credential, Environment, EnvironmentEntry, Lease, Requirement, utcnow

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

CREATE TABLE IF NOT EXISTS environments (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    project     TEXT,
    env         TEXT NOT NULL,
    target      TEXT,
    format      TEXT NOT NULL DEFAULT 'dotenv',
    description TEXT,
    last_used   REAL,
    UNIQUE (project, name)
);

CREATE TABLE IF NOT EXISTS environment_entries (
    environment_id TEXT NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
    key            TEXT NOT NULL,
    kind           TEXT NOT NULL DEFAULT 'pending',
    value          TEXT,
    cred_ref       TEXT,
    required       INTEGER NOT NULL DEFAULT 1,
    note           TEXT,
    position       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (environment_id, key),
    CHECK (kind IN ('pending', 'config', 'secret', 'credential-ref')),
    CHECK (kind = 'config' OR value IS NULL)
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
CREATE INDEX IF NOT EXISTS idx_environments_project ON environments(project);
CREATE INDEX IF NOT EXISTS idx_environments_env ON environments(env);
"""

_CRED_ID_RE = re.compile(r"^cred-(\d+)$")
_ENV_ID_RE = re.compile(r"^env-(\d+)$")


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


def _row_to_entry(row: sqlite3.Row) -> EnvironmentEntry:
    return EnvironmentEntry(
        key=row["key"],
        kind=row["kind"],
        value=row["value"],
        cred_ref=row["cred_ref"],
        required=bool(row["required"]),
        note=row["note"],
        position=row["position"],
    )


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
        # Off by default in SQLite, and the environment_entries -> environments
        # cascade is load-bearing: without it, removing an environment would strand
        # its entries as unreachable rows.
        self._conn.execute("PRAGMA foreign_keys=ON")
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

    def _mint_id(self, table: str, prefix: str, pattern: re.Pattern[str]) -> str:
        """Mint the next free ``<prefix>-NNN``. ``table`` is always a module literal."""
        rows = self._conn.execute(f"SELECT id FROM {table}").fetchall()
        used = [int(m.group(1)) for r in rows if (m := pattern.match(r["id"]))]
        return f"{prefix}-{max(used, default=0) + 1:03d}"

    def _next_id(self) -> str:
        return self._mint_id("credentials", "cred", _CRED_ID_RE)

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

    # -- environments --------------------------------------------------------
    #
    # An environment is *not* leased — it is shared, read-only configuration, so
    # ten runs may render it concurrently. Only the credentials its credential-ref
    # entries point at are exclusive, and those go through `acquire` above.

    def _entries_of(self, environment_id: str) -> tuple[EnvironmentEntry, ...]:
        rows = self._conn.execute(
            "SELECT * FROM environment_entries WHERE environment_id = ? "
            "ORDER BY position, key",
            (environment_id,),
        ).fetchall()
        return tuple(_row_to_entry(r) for r in rows)

    def _row_to_environment(self, row: sqlite3.Row) -> Environment:
        return Environment(
            id=row["id"],
            name=row["name"],
            env=row["env"],
            project=row["project"],
            target=row["target"],
            format=row["format"],
            description=row["description"],
            last_used=_dt(row["last_used"]),
            entries=self._entries_of(row["id"]),
        )

    def env_get(self, environment_id: str) -> Environment | None:
        row = self._conn.execute(
            "SELECT * FROM environments WHERE id = ?", (environment_id,)
        ).fetchone()
        return self._row_to_environment(row) if row else None

    def env_by_name(self, name: str, project: str | None = None) -> Environment | None:
        """Look an environment up the way a human refers to it: by name, within a project.

        ``project IS ?`` rather than ``=``: SQL equality against NULL is never true,
        so an unscoped environment would be unfindable with ``=``.
        """
        row = self._conn.execute(
            "SELECT * FROM environments WHERE name = ? AND project IS ?", (name, project)
        ).fetchone()
        return self._row_to_environment(row) if row else None

    def env_all(self) -> list[Environment]:
        """Every environment in the pool, unscoped."""
        rows = self._conn.execute("SELECT * FROM environments ORDER BY id").fetchall()
        return [self._row_to_environment(r) for r in rows]

    def env_find(self, project: str | None) -> list[Environment]:
        """The environments in one project — where ``None`` means *the unscoped ones*.

        Distinct from :meth:`env_all`, and the distinction matters: ``None`` here is
        a project to match (with ``IS``, so it matches NULL), not an absent filter.
        """
        rows = self._conn.execute(
            "SELECT * FROM environments WHERE project IS ? ORDER BY id", (project,)
        ).fetchall()
        return [self._row_to_environment(r) for r in rows]

    def env_add(
        self,
        *,
        name: str,
        env: str,
        project: str | None = None,
        target: str | None = None,
        format: str = "dotenv",
        description: str | None = None,
        environment_id: str | None = None,
    ) -> Environment:
        if format not in FORMATS:
            raise PoolError(f"unknown format {format!r} (expected one of {', '.join(FORMATS)})")
        # UNIQUE (project, name) does not catch a duplicate when project is NULL —
        # in SQL, two NULLs are not equal — so the unscoped case is checked here.
        if self.env_by_name(name, project) is not None:
            scope = f" in project {project}" if project else ""
            raise PoolError(f"environment {name} already exists{scope}")

        environment = Environment(
            id=environment_id or self._mint_id("environments", "env", _ENV_ID_RE),
            name=name,
            env=env,
            project=project,
            target=target,
            format=format,
            description=description,
        )
        try:
            self._conn.execute(
                "INSERT INTO environments (id, name, project, env, target, format, description) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    environment.id,
                    environment.name,
                    environment.project,
                    environment.env,
                    environment.target,
                    environment.format,
                    environment.description,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise PoolError(f"environment {environment.id} already exists") from exc
        return environment

    def env_update(
        self,
        environment_id: str,
        *,
        env: str | None = None,
        target: str | None = None,
        format: str | None = None,
        description: str | None = None,
    ) -> None:
        """Update an environment's metadata. ``None`` means "leave this field alone"."""
        if format is not None and format not in FORMATS:
            raise PoolError(f"unknown format {format!r} (expected one of {', '.join(FORMATS)})")
        fields = {"env": env, "target": target, "format": format, "description": description}
        assignments = {k: v for k, v in fields.items() if v is not None}
        if not assignments:
            return
        columns = ", ".join(f"{k} = ?" for k in assignments)
        self._conn.execute(
            f"UPDATE environments SET {columns} WHERE id = ?",
            (*assignments.values(), environment_id),
        )

    def env_remove(self, environment_id: str) -> bool:
        """Drop an environment. Its entries go with it, via ON DELETE CASCADE."""
        cur = self._conn.execute("DELETE FROM environments WHERE id = ?", (environment_id,))
        return cur.rowcount > 0

    def env_touch(self, environment_id: str, now: datetime | None = None) -> None:
        """Record that an environment was rendered."""
        self._conn.execute(
            "UPDATE environments SET last_used = ? WHERE id = ?",
            ((now or utcnow()).timestamp(), environment_id),
        )

    def env_put_entry(self, environment_id: str, entry: EnvironmentEntry) -> EnvironmentEntry:
        """Insert or replace one entry.

        A new key lands at the end of the render order; an existing key keeps the
        position it already had, so re-supplying a value never reshuffles a file.
        Passing a non-zero ``position`` pins it explicitly (that is what manifest
        import does).
        """
        position = entry.position
        if not position:
            existing = self._conn.execute(
                "SELECT position FROM environment_entries WHERE environment_id = ? AND key = ?",
                (environment_id, entry.key),
            ).fetchone()
            if existing is not None:
                position = existing["position"]
            else:
                row = self._conn.execute(
                    "SELECT COALESCE(MAX(position), 0) + 1 AS next "
                    "FROM environment_entries WHERE environment_id = ?",
                    (environment_id,),
                ).fetchone()
                position = row["next"]

        stored = replace(entry, position=position)
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO environment_entries "
                "(environment_id, key, kind, value, cred_ref, required, note, position) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    environment_id,
                    stored.key,
                    stored.kind,
                    stored.value,
                    stored.cred_ref,
                    int(stored.required),
                    stored.note,
                    stored.position,
                ),
            )
        except sqlite3.IntegrityError as exc:
            # The CHECK constraints are the last line of the no-secret-in-the-DB
            # defence; surface a breach as an error, never as a silent write.
            raise PoolError(f"rejected entry {stored.key}: {exc}") from exc
        return stored

    def env_get_entry(self, environment_id: str, key: str) -> EnvironmentEntry | None:
        row = self._conn.execute(
            "SELECT * FROM environment_entries WHERE environment_id = ? AND key = ?",
            (environment_id, key),
        ).fetchone()
        return _row_to_entry(row) if row else None

    def env_remove_entry(self, environment_id: str, key: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM environment_entries WHERE environment_id = ? AND key = ?",
            (environment_id, key),
        )
        return cur.rowcount > 0
