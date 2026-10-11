"""The `ostler env` commands: render, bring up, list, read and tear down a copy of the stack."""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ostler.environments import render as render_mod
from ostler.environments import runtime
from ostler.environments import spec
from ostler.environments.render import SHARED, Copy, RenderError
from ostler.environments.runtime import Compose, Runner, run_command
from ostler.qa import addresses

DEFAULT_WAIT_SECONDS = 900


@dataclass
class EnvOutcome:
    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Prepared:
    catalog: spec.Catalog
    services: list[spec.Service]
    copy: Copy
    fixtures: list[str]


def _fail(message: str, **data: Any) -> EnvOutcome:
    return EnvOutcome(False, message, {"ok": False, "error": message, **data})


def _default_targets(catalog: spec.Catalog, cwd: Path) -> list[str]:
    here = cwd.resolve()
    inside = [book for book in catalog.books.values()
              if here.is_relative_to(book.directory.resolve())]
    if inside:
        return [max(inside, key=lambda book: len(book.directory.parts)).name]
    return sorted(catalog.books)


def prepare(
    root: Path, targets: Sequence[str], *, copy_name: str, fixtures: Sequence[str],
    cwd: Path | None = None,
) -> Prepared | EnvOutcome:
    """The services, copy and fixture sets one bring-up of *targets* works with."""
    problem = addresses.lease_problem(copy_name)
    if problem:
        return _fail(f"`{copy_name}` cannot name a copy: {problem}")
    catalog = spec.load(root)
    if catalog.errors:
        return _fail("the stack files do not fit together:\n- " + "\n- ".join(catalog.errors),
                     errors=catalog.errors)
    if not catalog.books:
        return _fail(f"no book under {root} has a {spec.STACK_FILE}")
    chosen = list(targets) or _default_targets(catalog, cwd or Path.cwd())
    try:
        services = spec.closure(catalog, chosen)
        sets = render_mod.fixture_sets(catalog, services, fixtures)
    except (KeyError, RenderError) as exc:
        return _fail(str(exc.args[0]) if exc.args else str(exc))
    return Prepared(catalog, services, runtime.copy_for(root, copy_name), sets)


def cmd_check(root: Path) -> EnvOutcome:
    """Every reason the books' stack files do not fit together."""
    catalog = spec.load(root)
    data = {"ok": not catalog.errors, "books": sorted(catalog.books),
            "services": sorted(catalog.services), "errors": catalog.errors}
    if catalog.errors:
        return EnvOutcome(False, "\n".join(catalog.errors), data)
    return EnvOutcome(True, f"{len(catalog.services)} services in {len(catalog.books)} books fit "
                            "together", data)


def cmd_render(
    root: Path, targets: Sequence[str] = (), *, copy_name: str = SHARED,
    fixtures: Sequence[str] = (), cwd: Path | None = None,
) -> EnvOutcome:
    """Write the copy's compose file and helper files without starting anything."""
    prepared = prepare(root, targets, copy_name=copy_name, fixtures=fixtures, cwd=cwd)
    if isinstance(prepared, EnvOutcome):
        return prepared
    try:
        written = _write(root, prepared, started=False)
    except RenderError as exc:
        return _fail(str(exc))
    return EnvOutcome(True, f"rendered {prepared.copy.name} into {prepared.copy.directory}",
                      _summary(prepared, files=[str(path) for path in written]))


def cmd_up(
    root: Path, targets: Sequence[str] = (), *, copy_name: str = SHARED,
    fixtures: Sequence[str] = (), fresh: bool = False, cwd: Path | None = None,
    wait_seconds: int = DEFAULT_WAIT_SECONDS, runner: Runner = run_command,
) -> EnvOutcome:
    """Bring *targets* and everything they need up as the copy *copy_name*, then read its addresses."""
    prepared = prepare(root, targets, copy_name=copy_name, fixtures=fixtures, cwd=cwd)
    if isinstance(prepared, EnvOutcome):
        return prepared
    copy = prepared.copy
    compose = Compose(copy, runner)
    if fresh and (copy.directory / render_mod.COMPOSE_FILE).is_file():
        compose.down(keep_data=False)
    secret_problem = _render_secrets(prepared, runner)
    if secret_problem:
        return _fail(secret_problem, copy=copy.name)
    try:
        _write(root, prepared, started=True)
    except RenderError as exc:
        return _fail(str(exc), copy=copy.name)
    outcome = compose.up(wait_seconds=wait_seconds)
    if outcome.returncode != 0:
        return _fail(f"docker compose could not bring {copy.name} up (exit {outcome.returncode}); "
                     f"read `ostler env compose --copy {copy.name} -- logs`", copy=copy.name)
    book: dict[str, str] = {}
    for service in prepared.services:
        if not service.address:
            continue
        published = compose.port(service.compose_name, service.port)
        if not published:
            return _fail(f"{service.ref} is up but compose reports no host port for "
                         f"{service.port}", copy=copy.name)
        book[service.address] = runtime.host_url(service.scheme, published)
    book_file = copy.directory / runtime.ADDRESSES
    addresses.write_book(book_file, book)
    entry = next((book[service.address] for service in reversed(prepared.services)
                  if service.address), "")
    lines = [f"{name}: {url}" for name, url in sorted(book.items())]
    return EnvOutcome(True, "\n".join([f"{copy.name} is up", *lines]),
                      _summary(prepared, addresses=book, address_book=str(book_file),
                               entry_url=entry))


def cmd_down(root: Path, *, copy_name: str = SHARED, keep_data: bool = False,
             runner: Runner = run_command) -> EnvOutcome:
    """Stop the copy and delete its secrets, then its data and directory unless they are kept."""
    copy = runtime.copy_for(root, copy_name)
    if not (copy.directory / render_mod.COMPOSE_FILE).is_file():
        runtime.remove(copy)
        return EnvOutcome(True, f"{copy.name} is not up", {"ok": True, "copy": copy.name})
    outcome = Compose(copy, runner).down(keep_data=keep_data)
    if outcome.returncode != 0:
        return _fail(f"docker compose could not tear {copy.name} down (exit {outcome.returncode})",
                     copy=copy.name)
    if keep_data:
        runtime.remove_secrets(copy)
        return EnvOutcome(True, f"tore {copy.name} down and kept its data; `ostler env down "
                                f"--copy {copy.name}` drops it", {"ok": True, "copy": copy.name})
    runtime.remove(copy)
    return EnvOutcome(True, f"tore {copy.name} down", {"ok": True, "copy": copy.name})


def cmd_ls(root: Path, *, runner: Runner = run_command) -> EnvOutcome:
    """Every copy of this repo's stack, with what docker says of it."""
    status = runtime.running_projects(runner)
    rows: list[dict[str, Any]] = []
    lines: list[str] = []
    for copy in runtime.copies(root):
        manifest = runtime.read_manifest(copy.directory)
        listed = manifest.get("targets")
        targets = [str(item) for item in listed] if isinstance(listed, list) else []
        state = status.get(copy.project, "not running")
        rows.append({
            "copy": copy.name,
            "project": copy.project,
            "status": state,
            "targets": targets,
            "rendered_at": manifest.get("rendered_at", ""),
            "addresses": _read_book(copy),
        })
        lines.append(f"{copy.name}  {state}  {', '.join(targets)}")
    return EnvOutcome(True, "\n".join(lines) or "no copy of this stack exists",
                      {"ok": True, "copies": rows})


def cmd_address(root: Path, name: str, *, copy_name: str = SHARED) -> EnvOutcome:
    """The URL the copy publishes *name* at."""
    copy = runtime.copy_for(root, copy_name)
    book = _read_book(copy)
    if name not in book:
        known = ", ".join(sorted(book)) or "none, since it is not up"
        return _fail(f"{copy.name} publishes no `{name}` (it publishes {known})")
    return EnvOutcome(True, book[name], {"ok": True, "name": name, "url": book[name]})


def compose_argv(root: Path, args: Sequence[str], *, copy_name: str = SHARED) -> list[str] | EnvOutcome:
    """The docker compose command line for *args*, pointed at the copy."""
    copy = runtime.copy_for(root, copy_name)
    if not (copy.directory / render_mod.COMPOSE_FILE).is_file():
        return _fail(f"{copy.name} has not been rendered: run `ostler env up` first")
    return Compose(copy).argv(args)


def _read_book(copy: Copy) -> dict[str, str]:
    try:
        return addresses.read_book(copy.directory / runtime.ADDRESSES)
    except addresses.AddressError:
        return {}


def _write(root: Path, prepared: Prepared, *, started: bool) -> list[Path]:
    rendered = render_mod.render(prepared.catalog, prepared.services, prepared.copy, repo=root,
                                 fixtures=prepared.fixtures)
    written = render_mod.write(rendered)
    written.append(runtime.write_manifest(prepared.copy, {
        "repo": str(root),
        "copy": prepared.copy.name,
        "targets": [service.ref for service in prepared.services],
        "fixtures": prepared.fixtures,
        "rendered_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "started": started,
    }))
    return written


def _render_secrets(prepared: Prepared, runner: Runner) -> str:
    books = dict.fromkeys(service.book for service in prepared.services)
    wanted = [(book, prepared.catalog.books[book].secrets) for book in books
              if prepared.catalog.books[book].secrets]
    if not wanted:
        return ""
    if shutil.which("saddlebag") is None:
        return ("the stack boots with saddlebag environments "
                f"({', '.join(name for _, name in wanted)}) but `saddlebag` is not on PATH")
    for book, name in wanted:
        target = prepared.copy.directory / runtime.SECRETS_DIR / f"{book}.env"
        outcome = runner(["saddlebag", "env", "render", name, "--output", str(target),
                          "--run-id", prepared.copy.project], capture=True)
        if outcome.returncode != 0:
            return f"saddlebag could not render `{name}` for {book} (exit {outcome.returncode})"
    return ""


def _summary(prepared: Prepared, **extra: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "copy": prepared.copy.name,
        "project": prepared.copy.project,
        "directory": str(prepared.copy.directory),
        "services": [service.ref for service in prepared.services],
        "fixtures": prepared.fixtures,
        **extra,
    }
