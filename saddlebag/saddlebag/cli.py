"""saddlebag command-line entry point."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from importlib.metadata import version as _pkg_version
from pathlib import Path

from . import envfile
from .context import infer_project
from .db import DEFAULT_TTL, Pool, PoolError, default_db_path
from .models import AcquiredCredential, Credential, Requirement, utcnow
from .selector import SelectionError, select
from .store import SecretStore, StoreUnavailableError, open_store
from .workhorse import write_credential

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
    """The secret-store key for a credential.

    Project-qualified, so per-project pools (via ``SADDLEBAG_DB``) cannot collide
    in the global keyring namespace: two repos each minting ``cred-001`` resolve to
    ``repo-a/cred-001`` and ``repo-b/cred-001``. An unscoped credential keeps the
    bare id — which is also what every credential created before projects existed
    used, so no already-stored secret needs migrating.
    """
    return f"{cred.project}/{cred.id}" if cred.project else cred.id


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

    return p


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
