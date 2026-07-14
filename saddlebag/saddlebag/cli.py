"""saddlebag command-line entry point."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from importlib.metadata import version as _pkg_version
from pathlib import Path

from . import envfile, manifest, render
from .context import infer_project
from .db import DEFAULT_TTL, Pool, PoolError, default_db_path
from .models import (
    FORMATS,
    KIND_CONFIG,
    KIND_CREDENTIAL_REF,
    KIND_PENDING,
    KIND_SECRET,
    AcquiredCredential,
    Credential,
    Environment,
    EnvironmentEntry,
    Requirement,
    parse_cred_ref,
    utcnow,
)
from .selector import SelectionError, select
from .store import SecretStore, StoreUnavailableError, open_store
from .workhorse import write_credential, write_private

logger = logging.getLogger(__name__)


def _resolve_project(args: argparse.Namespace) -> str | None:
    """The project to assign (add) or filter by (list, scan).

    ``--all-projects`` means "no project scoping". An explicit ``--project`` wins
    next (empty string is an explicit "no project"). Otherwise it is inferred from
    the working directory — usually the enclosing repo's name.
    """
    if getattr(args, "all_projects", False):
        return None
    if args.project is not None:
        return args.project or None
    return infer_project()


def _requirement(args: argparse.Namespace) -> Requirement:
    return Requirement(
        env=args.env,
        project=_resolve_project(args),
        roles=tuple(args.roles or ()),
        features=tuple(args.features or ()),
        surface=args.surface,
    )


def _store_key(cred: Credential) -> str:
    """The secret-store key for a credential. See :func:`saddlebag.models.qualify`."""
    return cred.store_key


def _emit(data: object) -> None:
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _table(creds: list[Credential]) -> None:
    if not creds:
        print("(pool is empty)")
        return
    now = utcnow()
    width = max(len(c.id) for c in creds)
    pwidth = max((len(c.project or "-") for c in creds), default=1)
    for c in creds:
        state = "locked" if c.is_locked(now) else "free"
        roles = ",".join(c.roles) or "-"
        project = c.project or "-"
        print(f"{c.id:<{width}}  {state:<6}  {project:<{pwidth}}  {c.env:<10}  "
              f"{roles:<24}  {c.username}")


def _read_password() -> str:
    password = sys.stdin.read().strip()
    if not password:
        logger.error("no password on stdin")
        raise SystemExit(2)
    return password


def _resolve_password(args: argparse.Namespace) -> str:
    """The password to store, from whichever source was requested.

    Two sources, never argv: stdin, or a named variable in a ``.env`` file. The
    ``.env`` carries only the secret — every piece of metadata comes from the
    ``add`` flags, because a flat ``.env`` cannot express it.
    """
    if args.password_env_file:
        if not args.password_var:
            logger.error("--password-env-file requires --password-var NAME")
            raise SystemExit(2)
        try:
            value = envfile.read_var(args.password_env_file, args.password_var)
        except FileNotFoundError:
            logger.error("no such env file: %s", args.password_env_file)
            raise SystemExit(2) from None
        except KeyError:
            logger.error("variable %s not found in %s", args.password_var, args.password_env_file)
            raise SystemExit(2) from None
        if not value:
            logger.error("variable %s in %s is empty", args.password_var, args.password_env_file)
            raise SystemExit(2)
        return value
    if args.password_stdin:
        return _read_password()
    logger.error(
        "a password source is required: --password-stdin, "
        "or --password-env-file FILE --password-var NAME"
    )
    raise SystemExit(2)


# -- commands ---------------------------------------------------------------


def cmd_add(args: argparse.Namespace, pool: Pool) -> int:
    password = _resolve_password(args)
    store = _open_store(args)

    cred = pool.add(
        username=args.username,
        env=args.env,
        project=_resolve_project(args),
        roles=args.roles or (),
        features=args.features or (),
        surface=args.surface,
    )
    try:
        store.put(_store_key(cred), password)
    except Exception:
        # Never leave metadata pointing at a secret that was not stored.
        pool.remove(cred.id)
        raise

    if args.json:
        _emit(cred.to_dict())
    else:
        scope = f" in project {cred.project}" if cred.project else ""
        print(f"added {cred.id} ({cred.username}){scope} to the {store.name} store")
    return 0


def cmd_list(args: argparse.Namespace, pool: Pool) -> int:
    creds = pool.find(_requirement(args), include_locked=True)
    if args.json:
        _emit([c.to_dict() for c in creds])
    else:
        _table(creds)
    return 0


def cmd_remove(args: argparse.Namespace, pool: Pool) -> int:
    cred = pool.get(args.credential_id)
    if cred is None:
        logger.error("no such credential: %s", args.credential_id)
        return 1
    if cred.is_locked() and not args.force:
        logger.error("%s is leased; release it first or pass --force", cred.id)
        return 1

    _open_store(args).delete(_store_key(cred))
    pool.remove(cred.id)
    print(f"removed {cred.id}")
    return 0


def cmd_scan(args: argparse.Namespace, pool: Pool) -> int:
    requirement = _requirement(args)
    candidates = pool.find(requirement)

    if not args.select_via:
        if args.json:
            _emit([c.to_dict() for c in candidates])
        else:
            _table(candidates)
        return 0

    if not candidates:
        logger.error("no available credential matches %s", requirement.describe())
        return 1

    try:
        cred, selection = select(requirement, candidates, args.select_via)
    except SelectionError as exc:
        logger.error("selection failed: %s", exc)
        return 1

    logger.info("selected %s: %s", cred.id, selection.reason)
    return _lease_and_emit(args, pool, cred.id)


def cmd_acquire(args: argparse.Namespace, pool: Pool) -> int:
    return _lease_and_emit(args, pool, args.credential_id)


def _lease_and_emit(args: argparse.Namespace, pool: Pool, credential_id: str) -> int:
    cred = pool.get(credential_id)
    if cred is None:
        logger.error("no such credential: %s", credential_id)
        return 1

    store = _open_store(args)
    password = store.get(_store_key(cred))
    if password is None:
        logger.error(
            "%s has no password in the %s store — the pool and the store disagree; "
            "run 'saddlebag doctor'",
            credential_id,
            store.name,
        )
        return 1

    lease = pool.acquire(credential_id, ttl=args.ttl, run_id=args.run_id)
    acquired = AcquiredCredential(credential=cred, lease=lease, password=password)

    if args.output:
        path = write_credential(args.output, acquired)
        logger.info("wrote %s (mode 0600), lease %s", path, lease.lease_id)
    elif args.output_json or args.json:
        _emit(acquired.to_dict())
    else:
        print(f"leased {cred.id} as {lease.lease_id} until {lease.expires_at:%Y-%m-%d %H:%M:%SZ}")
    return 0


def cmd_release(args: argparse.Namespace, pool: Pool) -> int:
    if args.lease_id:
        freed = pool.release_lease(args.lease_id)
        label = f"lease {args.lease_id}"
    else:
        freed = pool.release_run(args.run_id)
        label = f"run {args.run_id}"

    if freed == 0:
        logger.warning("nothing to release for %s", label)
        return 0
    print(f"released {freed} credential{'s' if freed != 1 else ''} for {label}")
    return 0


def cmd_expire(args: argparse.Namespace, pool: Pool) -> int:
    freed = pool.expire()
    print(f"expired {freed} stale lease{'s' if freed != 1 else ''}")
    return 0


def cmd_doctor(args: argparse.Namespace, pool: Pool) -> int:
    now = utcnow()
    creds = pool.all()
    problems: list[str] = []

    try:
        store: SecretStore | None = open_store(args.backend)
    except StoreUnavailableError as exc:
        # doctor is the one command that reports an unavailable store instead of
        # dying on it — that is precisely what it exists to diagnose. The error
        # already reads as a full sentence; do not prefix it.
        store = None
        problems.append(str(exc))

    locked = [c for c in creds if c.is_locked(now)]
    stale = [c for c in creds if c.is_stale(now)]

    orphans: list[str] = []
    if store is not None:
        orphans = [c.id for c in creds if store.get(_store_key(c)) is None]
        problems.extend(f"{cid}: metadata in pool, no password in store" for cid in orphans)

    if args.json:
        _emit({
            "db": str(pool.path),
            "store": store.name if store else None,
            "credentials": len(creds),
            "locked": [c.id for c in locked],
            "stale": [c.id for c in stale],
            "orphans": orphans,
            "problems": problems,
        })
        return 1 if problems else 0

    print(f"pool:  {pool.path} ({len(creds)} credentials)")
    print(f"store: {store.name if store else 'UNAVAILABLE'}")
    print(f"locked: {len(locked)}   stale (expired, reclaimable): {len(stale)}")
    for cred in stale:
        print(f"  stale  {cred.id}  lease {cred.lease_id}  expired {cred.expires_at:%Y-%m-%d %H:%M:%SZ}")
    if stale:
        print("run 'saddlebag expire' to reclaim them")
    for problem in problems:
        print(f"  error  {problem}")
    return 1 if problems else 0


def _open_store(args: argparse.Namespace) -> SecretStore:
    try:
        return open_store(getattr(args, "backend", None))
    except StoreUnavailableError as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc


class _LazyStore:
    """Opens the secret store on first use — and only then.

    saddlebag refuses to run without a store, deliberately: a credential without
    one is meaningless. But an environment made entirely of ``config`` entries needs
    no store at all, and the hosts where that matters most (containers, CI, headless
    boxes) are exactly the ones with no keyring. Opening the store eagerly would
    fail a config-only environment on precisely the machines it was built for, so
    every environment command routes through this and pays only for what it uses.
    """

    def __init__(self, args: argparse.Namespace) -> None:
        self._args = args
        self._store: SecretStore | None = None

    def __call__(self) -> SecretStore:
        if self._store is None:
            self._store = _open_store(self._args)
        return self._store

    @property
    def opened(self) -> SecretStore | None:
        """The store, if anything has needed it yet. Never opens it."""
        return self._store


# -- environments -----------------------------------------------------------
#
# The safety properties here mirror the credential pool's, and they are load-bearing:
# `env list`, `env show` and `env doctor` read the pool DB for everything sensitive,
# so they cannot leak a secret even when handed to an agent. `env render` is the
# single point where a secret becomes a file.


def _lookup_env(args: argparse.Namespace, pool: Pool) -> Environment | None:
    project = _resolve_project(args)
    environment = pool.env_by_name(args.name, project)
    if environment is None:
        scope = f" in project {project}" if project else ""
        logger.error("no such environment: %s%s", args.name, scope)
    return environment


def _read_secret() -> str:
    secret = sys.stdin.read().strip()
    if not secret:
        logger.error("no secret on stdin")
        raise SystemExit(2)
    return secret


def cmd_env_add(args: argparse.Namespace, pool: Pool) -> int:
    environment = pool.env_add(
        name=args.name,
        env=args.env,
        project=_resolve_project(args),
        target=args.target,
        format=args.format,
        description=args.description,
    )
    if args.json:
        _emit(environment.to_dict())
    else:
        scope = f" in project {environment.project}" if environment.project else ""
        print(f"added environment {environment.name} ({environment.id}){scope}")
    return 0


def cmd_env_import(args: argparse.Namespace, pool: Pool) -> int:
    """Seed an environment from a manifest, or from a checked-in ``.env.example``.

    A manifest reconstitutes the whole environment — metadata, kinds, notes, config
    values — and creates it if this host has never seen it. A ``.env``-shaped file
    carries none of that, so it can only contribute **key names**: every key lands
    ``pending``, its value is read and discarded, and ``env doctor`` then reports
    exactly what a human still has to supply. Nothing is ever guessed.
    """
    path = Path(args.from_path)

    if manifest.is_manifest_path(path):
        try:
            parsed = manifest.load(path)
        except FileNotFoundError:
            logger.error("no such manifest: %s", path)
            return 2
        except manifest.ManifestError as exc:
            logger.error("%s: %s", path, exc)
            return 1

        project = _resolve_project(args)
        environment = pool.env_by_name(args.name, project)
        if environment is None:
            environment = pool.env_add(
                name=args.name,
                env=parsed.env,
                project=project,
                target=parsed.target,
                format=parsed.format,
                description=parsed.description,
            )
            verb = "reconstituted"
        else:
            # The manifest is the checked-in source of truth, so it is authoritative
            # over the local row it is being imported into.
            pool.env_update(
                environment.id,
                env=parsed.env,
                target=parsed.target,
                format=parsed.format,
                description=parsed.description,
            )
            verb = "updated"

        for entry in parsed.entries:
            pool.env_put_entry(environment.id, entry)
        print(f"{verb} {environment.name} ({environment.id}) with {len(parsed.entries)} keys "
              f"from {path}")
        return 0

    environment = _lookup_env(args, pool)
    if environment is None:
        return 1
    try:
        keys = envfile.read_keys(path)
    except FileNotFoundError:
        logger.error("no such env file: %s", path)
        return 2

    added = [k for k in keys if pool.env_get_entry(environment.id, k) is None]
    for key in added:
        pool.env_put_entry(environment.id, EnvironmentEntry(key=key, kind=KIND_PENDING))

    skipped = len(keys) - len(added)
    note = f" ({skipped} already known)" if skipped else ""
    print(f"imported {len(added)} key{'s' if len(added) != 1 else ''} into "
          f"{environment.name} from {path}{note}")
    if added:
        print("every key is pending — run 'saddlebag env doctor' to see what needs a value")
    return 0


def cmd_env_set(args: argparse.Namespace, pool: Pool) -> int:
    """Supply a value. **The channel decides the kind**, not a flag and not a default.

    A value on argv is already in the process table and the shell history, so it
    cannot be treated as a secret without lying about its exposure — it is
    ``config``. A value on stdin is a ``secret``, the same discipline
    ``saddlebag add --password-stdin`` already enforces. This is self-enforcing
    rather than conventional: there is no way to put a secret in the pool DB by
    accident, because the only channel that reaches the DB is the one that has
    already published the value.
    """
    environment = _lookup_env(args, pool)
    if environment is None:
        return 1

    key, sep, value = args.assignment.partition("=")
    key = key.strip()
    if not key:
        logger.error("expected KEY=value or KEY, got %r", args.assignment)
        return 2

    existing = pool.env_get_entry(environment.id, key)
    required = existing.required if existing else True
    if args.optional:
        required = False
    if args.required:
        required = True
    note = args.note if args.note is not None else (existing.note if existing else None)

    secret: str | None = None
    if sep:
        if args.secret_stdin or args.from_credential:
            logger.error("KEY=value supplies the value on argv; drop the other value source")
            return 2
        entry = EnvironmentEntry(key=key, kind=KIND_CONFIG, value=value,
                                 required=required, note=note)
    elif args.secret_stdin:
        secret = _read_secret()
        entry = EnvironmentEntry(key=key, kind=KIND_SECRET, required=required, note=note)
    elif args.from_credential:
        try:
            credential_id, _field = parse_cred_ref(args.from_credential)
        except ValueError as exc:
            logger.error("--from-credential %s", exc)
            return 2
        if pool.get(credential_id) is None:
            # Not fatal: an environment may legitimately be defined before the
            # credential it points at exists. `env doctor` reports it until it does.
            logger.warning("%s does not exist yet — %s will be a dangling reference "
                           "until it does", credential_id, key)
        entry = EnvironmentEntry(key=key, kind=KIND_CREDENTIAL_REF,
                                 cred_ref=args.from_credential, required=required, note=note)
    elif args.note is not None or args.optional or args.required:
        # Metadata-only: annotate or re-flag a key without touching its value.
        entry = (
            EnvironmentEntry(key=key, kind=existing.kind, value=existing.value,
                             cred_ref=existing.cred_ref, required=required, note=note,
                             position=existing.position)
            if existing
            else EnvironmentEntry(key=key, kind=KIND_PENDING, required=required, note=note)
        )
    else:
        logger.error(
            "a value source is required: KEY=value (config), KEY --secret-stdin (secret), "
            "or KEY --from-credential cred-007:password (credential-ref)"
        )
        return 2

    store = _LazyStore(args)
    if secret is not None:
        # Store first: if the pool write then fails, the entry stays as it was and a
        # retry overwrites the stored value. The other order would leave the pool
        # claiming a secret the store does not have.
        store().put(environment.store_key(key), secret)
    elif existing is not None and existing.kind == KIND_SECRET:
        # The key is no longer a secret. Drop the stored value rather than leave it
        # behind as an orphan nothing references.
        store().delete(environment.store_key(key))

    pool.env_put_entry(environment.id, entry)
    print(f"set {key} ({entry.kind}) in {environment.name}")
    return 0


def cmd_env_unset(args: argparse.Namespace, pool: Pool) -> int:
    environment = _lookup_env(args, pool)
    if environment is None:
        return 1
    entry = pool.env_get_entry(environment.id, args.key)
    if entry is None:
        logger.error("%s has no key %s", environment.name, args.key)
        return 1
    if entry.kind == KIND_SECRET:
        _LazyStore(args)().delete(environment.store_key(args.key))
    pool.env_remove_entry(environment.id, args.key)
    print(f"removed {args.key} from {environment.name}")
    return 0


def cmd_env_list(args: argparse.Namespace, pool: Pool) -> int:
    envs = pool.env_all() if args.all_projects else pool.env_find(_resolve_project(args))
    if args.json:
        _emit([e.to_dict() for e in envs])
        return 0
    if not envs:
        print("(no environments)")
        return 0

    width = max(len(e.name) for e in envs)
    for environment in envs:
        pending = sum(1 for e in environment.entries if e.kind == KIND_PENDING and e.required)
        state = f"{len(environment.entries)} keys"
        if pending:
            state += f", {pending} pending"
        print(f"{environment.name:<{width}}  {environment.id}  {environment.env:<8}  "
              f"{environment.target or '-':<24}  {state}")
    return 0


def cmd_env_show(args: argparse.Namespace, pool: Pool) -> int:
    """Print an environment. Structurally incapable of emitting a secret.

    Config values are shown in the clear — that is the point of config, and what
    makes it reviewable. A secret entry reports as ``<set>``, which is enough to
    reason about and is never the value. Neither needs the secret store to say so.
    """
    environment = _lookup_env(args, pool)
    if environment is None:
        return 1
    if args.json:
        _emit(environment.to_dict())
        return 0

    scope = f"  project={environment.project}" if environment.project else ""
    print(f"{environment.name}  ({environment.id}){scope}  env={environment.env}  "
          f"target={environment.target or '-'}  format={environment.format}")
    if environment.description:
        print(f"  {environment.description}")
    if not environment.entries:
        print("  (no keys — seed them with 'saddlebag env import')")
        return 0

    width = max(len(e.key) for e in environment.entries)
    kwidth = max(len(e.kind) for e in environment.entries)
    for entry in environment.entries:
        flag = "" if entry.required else "  (optional)"
        note = f"  # {entry.note}" if entry.note else ""
        print(f"  {entry.key:<{width}}  {entry.kind:<{kwidth}}  "
              f"{entry.display_value()}{flag}{note}")
    return 0


def cmd_env_export(args: argparse.Namespace, pool: Pool) -> int:
    """Write the manifest — the artefact that travels, and the one to commit.

    It carries no secret values, so unlike ``env render`` it is written with normal
    permissions and is safe on stdout: that is exactly what makes it committable.
    """
    environment = _lookup_env(args, pool)
    if environment is None:
        return 1
    text = manifest.dumps(environment)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path}")
    else:
        sys.stdout.write(text)
    return 0


def cmd_env_render(args: argparse.Namespace, pool: Pool) -> int:
    """Materialise the environment — the only command that turns a secret into a file."""
    environment = _lookup_env(args, pool)
    if environment is None:
        return 1
    store = _LazyStore(args)

    if args.check:
        return _env_check(args, pool, environment, store)

    target = args.output or environment.target
    if not target:
        logger.error("%s has no render target: pass --output PATH, or set one with "
                     "'saddlebag env add --target'", environment.name)
        return 2

    resolution = render.resolve(environment, pool, store,
                                run_id=args.run_id, ttl=args.ttl)
    if not resolution.resolvable:
        _report_gaps(environment, resolution.gaps)
        return 1

    try:
        text = render.format_values(resolution.values, environment.format)
    except ValueError as exc:
        logger.error("cannot render %s as %s: %s", environment.name, environment.format, exc)
        return 1

    path = write_private(target, text)
    pool.env_touch(environment.id)
    for credential_id, lease_id in resolution.leases.items():
        logger.info("leased %s as %s for %s", credential_id, lease_id, args.run_id or "no run")
    # Nothing on stdout but the path: the file holds secrets, the path does not.
    print(path)
    return 0


def _report_gaps(environment: Environment, gaps: list[render.Gap]) -> None:
    """The human-only wall, named precisely.

    An agent that hits this cannot fix it by guessing — that is the entire point.
    It reports `unfixable` and names these keys, and a human supplies them.
    """
    logger.error("cannot render %s — %d required key%s cannot be resolved:",
                 environment.name, len(gaps), "s" if len(gaps) != 1 else "")
    for gap in gaps:
        logger.error("  %s", gap)


def _env_check(
    args: argparse.Namespace, pool: Pool, environment: Environment, store: _LazyStore
) -> int:
    """``--check``: resolve everything, write nothing, take no lease.

    Safe to run anywhere, because the report names keys and never values — including
    for drift, where the comparison looks at values but the output does not.
    """
    report = render.check(environment, pool, store, target=args.output)
    if args.json:
        _emit(report.to_dict())
        return 0 if report.ok else 1

    print(f"{environment.name} -> {report.target or '(no target)'}")
    for gap in report.gaps:
        print(f"  gap      {gap}")
    if not report.target_exists and report.target:
        print("  missing  the target file does not exist yet")
    for key in report.missing:
        print(f"  missing  {key}")
    for key in report.extra:
        print(f"  extra    {key} (in the file, not in the environment)")
    for key in report.drift:
        print(f"  drift    {key} (the file's value is not the one saddlebag would render)")
    if report.ok:
        print("  ok       in sync")
    return 0 if report.ok else 1


def cmd_env_doctor(args: argparse.Namespace, pool: Pool) -> int:
    """Report what a human still has to supply, and what the pool and store disagree on.

    The store is opened only if some environment in scope actually needs it: a pool
    of config-only environments is healthy on a host with no keyring and no Vault,
    and must not be reported as broken there.
    """
    envs = pool.env_all() if args.all_projects else pool.env_find(_resolve_project(args))
    problems: list[str] = []

    store: SecretStore | None = None
    if any(e.needs_store for e in envs):
        try:
            store = open_store(args.backend)
        except StoreUnavailableError as exc:
            problems.append(str(exc))

    reports: list[dict[str, list[str] | str]] = []
    for environment in envs:
        pending = [e.key for e in environment.entries if e.kind == KIND_PENDING and e.required]
        unset: list[str] = []
        dangling: list[str] = []

        for entry in environment.entries:
            if entry.kind == KIND_SECRET and store is not None:
                if store.get(environment.store_key(entry.key)) is None:
                    unset.append(entry.key)
            elif entry.kind == KIND_CREDENTIAL_REF:
                credential_id, cred_field = parse_cred_ref(str(entry.cred_ref))
                cred = pool.get(credential_id)
                if cred is None:
                    dangling.append(f"{entry.key} -> {credential_id} (no such credential)")
                elif (cred_field == "password" and store is not None
                      and store.get(cred.store_key) is None):
                    dangling.append(f"{entry.key} -> {credential_id} (no password in the store)")

        problems.extend(f"{environment.name}: {k} is pending — a human must supply it"
                        for k in pending)
        problems.extend(f"{environment.name}: {k} is declared secret but the store has "
                        "no value for it" for k in unset)
        problems.extend(f"{environment.name}: {d}" for d in dangling)
        reports.append({
            "id": environment.id,
            "name": environment.name,
            "pending": pending,
            "unset": unset,
            "dangling": dangling,
        })

    if args.json:
        _emit({
            "db": str(pool.path),
            "store": store.name if store else None,
            "environments": reports,
            "problems": problems,
        })
        return 1 if problems else 0

    print(f"pool:  {pool.path} ({len(envs)} environments)")
    print(f"store: {store.name if store else 'not needed'}")
    for report in reports:
        counts = [f"{len(report[k])} {k}" for k in ("pending", "unset", "dangling")
                  if report[k]]
        summary = ", ".join(counts) if counts else "ok"
        print(f"  {report['name']:<16} {summary}")
    for problem in problems:
        print(f"  error  {problem}")
    return 1 if problems else 0


def cmd_env_remove(args: argparse.Namespace, pool: Pool) -> int:
    environment = _lookup_env(args, pool)
    if environment is None:
        return 1
    store = _LazyStore(args)
    for entry in environment.entries:
        if entry.kind == KIND_SECRET:
            store().delete(environment.store_key(entry.key))
    pool.env_remove(environment.id)
    print(f"removed environment {environment.name} ({environment.id})")
    return 0


# -- parser -----------------------------------------------------------------


def _add_requirement_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env", help="environment, e.g. staging")
    parser.add_argument("--project", help="project scope (default: inferred from the working "
                        "directory; pass '' for none)")
    parser.add_argument("--roles", nargs="+", metavar="ROLE", help="roles the credential must hold")
    parser.add_argument("--features", nargs="+", metavar="FEATURE", help="features it must have")
    parser.add_argument("--surface", help="ostler surface, e.g. checkout/login")


def _add_lease_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ttl", type=int, default=DEFAULT_TTL, help=f"lease seconds (default {DEFAULT_TTL})")
    parser.add_argument("--run-id", help="tag the lease with a workhorse run id")
    parser.add_argument("--output", metavar="PATH", help="write the credential JSON to PATH, mode 0600")
    parser.add_argument("--output-json", action="store_true", help="write the credential JSON to stdout")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="saddlebag", description="Carry the right credentials for every ride.")
    p.add_argument("--version", action="version", version=f"saddlebag {_pkg_version('saddlebag')}")
    p.add_argument("--db", metavar="PATH", help=f"pool database (default {default_db_path()})")
    p.add_argument("--backend", choices=("keyring", "vault"), help="force a secret store (default: autodetect)")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging on stderr")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("add", help="add a credential to the pool")
    a.add_argument("--username", required=True)
    pw = a.add_mutually_exclusive_group()
    pw.add_argument("--password-stdin", action="store_true", help="read the password from stdin")
    pw.add_argument("--password-env-file", metavar="ENVFILE",
                    help="read the password from a variable in a .env file")
    a.add_argument("--password-var", metavar="NAME",
                   help="the variable in --password-env-file to import as the password")
    a.add_argument("--json", action="store_true")
    _add_requirement_flags(a)
    a.set_defaults(func=cmd_add)

    ls = sub.add_parser("list", help="list the pool (never shows passwords)")
    ls.add_argument("--json", action="store_true")
    ls.add_argument("--all-projects", action="store_true",
                    help="do not scope to the current project")
    _add_requirement_flags(ls)
    ls.set_defaults(func=cmd_list)

    rm = sub.add_parser("remove", help="remove a credential and its password")
    rm.add_argument("credential_id", metavar="ID")
    rm.add_argument("--force", action="store_true", help="remove even while leased")
    rm.set_defaults(func=cmd_remove)

    sc = sub.add_parser("scan", help="find candidates, optionally let an agent pick one")
    sc.add_argument("--all-projects", action="store_true",
                    help="do not scope to the current project")
    _add_requirement_flags(sc)
    _add_lease_flags(sc)
    sc.add_argument("--select-via", metavar="CLI", help="agent CLI that picks the credential, e.g. claude")
    sc.add_argument("--json", action="store_true", help="emit candidates as JSON (no selection)")
    sc.set_defaults(func=cmd_scan)

    ac = sub.add_parser("acquire", help="lease a credential by exact id")
    ac.add_argument("credential_id", metavar="ID")
    ac.add_argument("--json", action="store_true")
    _add_lease_flags(ac)
    ac.set_defaults(func=cmd_acquire)

    rl = sub.add_parser("release", help="release leases")
    group = rl.add_mutually_exclusive_group(required=True)
    group.add_argument("--lease-id")
    group.add_argument("--run-id")
    rl.set_defaults(func=cmd_release)

    ex = sub.add_parser("expire", help="force-release leases past their TTL")
    ex.set_defaults(func=cmd_expire)

    dr = sub.add_parser("doctor", help="health check: store, locked and stale leases")
    dr.add_argument("--json", action="store_true")
    dr.set_defaults(func=cmd_doctor)

    _add_env_commands(sub)
    return p


def _add_project_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", help="project scope (default: inferred from the working "
                        "directory; pass '' for none)")


def _add_env_commands(sub: argparse._SubParsersAction) -> None:
    """The environment pool: what a stack needs to *boot*, secret and non-secret alike.

    An environment is a ``.env``-shaped bundle, not an identity: it is shared rather
    than leased, and most of what it holds is not sensitive at all. The point is that
    an agent can bring a stack up without ever reading or writing a ``.env`` file,
    and without a secret value entering its context.
    """
    env = sub.add_parser("env", help="environments: the config a stack needs to boot")
    esub = env.add_subparsers(dest="env_command", required=True)

    add = esub.add_parser("add", help="define an environment and its render target")
    add.add_argument("name", metavar="NAME")
    add.add_argument("--env", required=True, help="environment, e.g. local")
    add.add_argument("--target", metavar="PATH", help="default render path, e.g. web/.env.local")
    add.add_argument("--format", choices=FORMATS, default="dotenv")
    add.add_argument("--description")
    add.add_argument("--json", action="store_true")
    _add_project_flag(add)
    add.set_defaults(func=cmd_env_add)

    imp = esub.add_parser("import", help="seed keys from a manifest or a .env.example")
    imp.add_argument("name", metavar="NAME")
    imp.add_argument("--from", dest="from_path", required=True, metavar="PATH",
                     help="a .yaml manifest (reconstitutes the environment), or any "
                          ".env-shaped file (keys only — values are read and discarded)")
    _add_project_flag(imp)
    imp.set_defaults(func=cmd_env_import)

    st = esub.add_parser("set", help="supply a value (the channel decides the kind)")
    st.add_argument("name", metavar="NAME")
    st.add_argument("assignment", metavar="KEY[=VALUE]",
                    help="KEY=value stores config in the pool DB; a bare KEY takes its "
                         "value from --secret-stdin or --from-credential")
    source = st.add_mutually_exclusive_group()
    source.add_argument("--secret-stdin", action="store_true",
                        help="read the value from stdin and put it in the secret store")
    source.add_argument("--from-credential", metavar="REF",
                        help="resolve at render time from a leased credential, "
                             "e.g. cred-007:password")
    st.add_argument("--note", help="why this key exists; surfaced in 'env show'")
    flag = st.add_mutually_exclusive_group()
    flag.add_argument("--optional", action="store_true",
                      help="omit this key from the rendered file when it has no value")
    flag.add_argument("--required", action="store_true", help="the default; undoes --optional")
    _add_project_flag(st)
    st.set_defaults(func=cmd_env_set)

    un = esub.add_parser("unset", help="drop a key, and its stored secret if it had one")
    un.add_argument("name", metavar="NAME")
    un.add_argument("key", metavar="KEY")
    _add_project_flag(un)
    un.set_defaults(func=cmd_env_unset)

    ls = esub.add_parser("list", help="list environments (cannot emit a secret)")
    ls.add_argument("--json", action="store_true")
    ls.add_argument("--all-projects", action="store_true")
    _add_project_flag(ls)
    ls.set_defaults(func=cmd_env_list)

    sh = esub.add_parser("show", help="show one environment (cannot emit a secret)")
    sh.add_argument("name", metavar="NAME")
    sh.add_argument("--json", action="store_true")
    _add_project_flag(sh)
    sh.set_defaults(func=cmd_env_show)

    ex = esub.add_parser("export", help="write the manifest — safe to commit")
    ex.add_argument("name", metavar="NAME")
    ex.add_argument("--output", metavar="PATH", help="default: stdout")
    _add_project_flag(ex)
    ex.set_defaults(func=cmd_env_export)

    rn = esub.add_parser("render", help="materialise the environment to its target file")
    rn.add_argument("name", metavar="NAME")
    rn.add_argument("--output", metavar="PATH", help="override the environment's target")
    rn.add_argument("--check", action="store_true",
                    help="resolve everything, write nothing, take no lease; exit non-zero "
                         "when the target is missing, drifted, or unresolvable")
    rn.add_argument("--run-id", help="tag any credential-ref leases with a workhorse run id")
    rn.add_argument("--ttl", type=int, default=DEFAULT_TTL,
                    help=f"lease seconds for credential-refs (default {DEFAULT_TTL})")
    rn.add_argument("--json", action="store_true", help="machine-readable --check report")
    _add_project_flag(rn)
    rn.set_defaults(func=cmd_env_render)

    dr = esub.add_parser("doctor", help="pending keys, unset secrets, dangling credential-refs")
    dr.add_argument("--json", action="store_true")
    dr.add_argument("--all-projects", action="store_true")
    _add_project_flag(dr)
    dr.set_defaults(func=cmd_env_doctor)

    rm = esub.add_parser("remove", help="drop an environment and its stored secrets")
    rm.add_argument("name", metavar="NAME")
    _add_project_flag(rm)
    rm.set_defaults(func=cmd_env_remove)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(name)s %(levelname)s: %(message)s",
    )

    db_path = Path(args.db) if args.db else None
    try:
        with Pool(db_path) as pool:
            raise SystemExit(args.func(args, pool))
    except PoolError as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc
    except BrokenPipeError:  # pragma: no cover - `saddlebag list | head`
        raise SystemExit(0) from None


if __name__ == "__main__":
    main()
