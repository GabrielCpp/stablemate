"""The `ostler env` commands: render, bring up, list, read and tear down a copy of the stack."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

from ostler import model
from ostler.environments import inject, page
from ostler.environments import render as render_mod
from ostler.environments import runtime, secrets
from ostler.environments import spec
from ostler.environments.render import SHARED, Copy, RenderError
from ostler.environments.runtime import Compose, Runner, run_command
from ostler.qa import addresses

DEFAULT_WAIT_SECONDS = 900
OUTPUTS_ENV = "outputs.env"
ABOUT_WIDTH = 45


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
        return _fail(f"no book under {root} has an {spec.OPS_DIR}/{spec.STACK_FILE}")
    chosen = list(targets) or _default_targets(catalog, cwd or Path.cwd())
    copy = runtime.copy_for(root, copy_name)
    previous = runtime.read_manifest(copy.directory)
    try:
        named = {catalog.services[ref].book
                 for target in chosen for ref in spec.resolve_target(catalog, target)}
        kept = [ref for ref in _listed(previous, "targets")
                if ref in catalog.services and catalog.services[ref].book not in named]
        services = spec.closure(catalog, [*kept, *chosen])
        carried = [service for service in services if service.ref in kept]
        sets = _fixture_sets(catalog, services, carried, fixtures, _listed(previous, "fixtures"))
    except (KeyError, RenderError) as exc:
        return _fail(str(exc.args[0]) if exc.args else str(exc))
    return Prepared(catalog, services, copy, sets)


def _listed(manifest: dict[str, object], key: str) -> list[str]:
    listed = manifest.get(key)
    return [str(item) for item in listed] if isinstance(listed, list) else []


def _fixture_sets(
    catalog: spec.Catalog, services: list[spec.Service], carried: list[spec.Service],
    chosen: Sequence[str], loaded: Sequence[str],
) -> list[str]:
    if chosen or not carried:
        return render_mod.fixture_sets(catalog, services, chosen)
    held = {name for service in carried for name in service.fixtures}
    retained = [name for name in loaded if name in held]
    fresh = [service for service in services if service not in carried]
    added = [name for name in render_mod.fixture_sets(catalog, fresh, ())
             if name not in held]
    return list(dict.fromkeys([*retained, *added]))


def cmd_check(root: Path, *, runner: Runner = run_command) -> EnvOutcome:
    """Every reason the books' stack files do not fit together, and every `${NAME}` no source defines."""
    catalog = spec.load(root)
    if not catalog.errors and catalog.books:
        catalog.errors += _name_problems(root, catalog, runner)
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
        written = _write(root, prepared, _rendered(root, prepared), started=False)
    except RenderError as exc:
        return _fail(str(exc))
    return EnvOutcome(True, f"rendered {prepared.copy.name} into {prepared.copy.directory}",
                      _summary(prepared, files=[str(path) for path in written]))


def cmd_up(
    root: Path, targets: Sequence[str] = (), *, copy_name: str = SHARED,
    fixtures: Sequence[str] = (), fresh: bool = False, cwd: Path | None = None,
    wait_seconds: int = DEFAULT_WAIT_SECONDS, holder: int | None = None,
    runner: Runner = run_command,
) -> EnvOutcome:
    """Bring *targets* and everything they need up as the copy *copy_name*, then read its addresses."""
    prepared = prepare(root, targets, copy_name=copy_name, fixtures=fixtures, cwd=cwd)
    if isinstance(prepared, EnvOutcome):
        return prepared
    copy = prepared.copy
    if copy.shared:
        taken = _taken_ports(prepared, targets, runner)
        if taken:
            return _fail(taken, copy=copy.name)
    reclaimed = reclaim(keep=copy, runner=runner) if copy.name != SHARED else []
    if holder is None and os.environ.get(addresses.LEASE_ENV, "") == copy.name:
        holder = runtime.holder_from_env()
    compose = Compose(copy, runner)
    if fresh and (copy.directory / render_mod.COMPOSE_FILE).is_file():
        compose.down(keep_data=False)
    source = secrets.source_for(prepared.catalog, root, runner)
    try:
        rendered = _rendered(root, prepared)
        problems = secrets.missing_names(rendered, prepared.catalog, prepared.services, source)
        if problems:
            return _fail(_missing_message(problems), copy=copy.name)
        env_files = source.files(copy)
    except RenderError as exc:
        return _fail(str(exc), copy=copy.name)
    except secrets.SecretError as exc:
        return _fail(str(exc), copy=copy.name)
    jobs = [service for service in prepared.services if service.outputs]
    produced = copy.directory / runtime.SECRETS_DIR / OUTPUTS_ENV
    _write(root, prepared, rendered, started=True, holder=holder,
           env_files=[*env_files, produced] if jobs else env_files,
           exec_prefix=source.exec_prefix())
    if jobs:
        problem = _run_jobs(prepared, jobs, produced, compose, wait_seconds)
        if problem:
            return _fail(problem, copy=copy.name)
    outcome = compose.up(wait_seconds=wait_seconds)
    _drop_raw_outputs(copy, jobs)
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
    lines += [f"reclaimed {name}, whose run is gone" for name in reclaimed]
    return EnvOutcome(True, "\n".join([f"{copy.name} is up", *lines]),
                      _summary(prepared, addresses=book, address_book=str(book_file),
                               entry_url=entry, reclaimed=reclaimed))


def _taken_ports(prepared: Prepared, targets: Sequence[str], runner: Runner) -> str:
    """Why the shared copy cannot publish its fixed host ports, or empty when every one is free."""
    fixed = [service for service in prepared.services if service.address and service.host_port]
    if not fixed:
        return ""
    occupants = runtime.port_occupants(runner)
    owners = {copy.project: (copy.name, str(manifest.get("repo", "")))
              for copy, manifest in runtime.held_copies()}
    lines: list[str] = []
    for service in fixed:
        occupant = occupants.get(service.host_port)
        if occupant is not None and occupant.project == prepared.copy.project:
            continue
        if occupant is None and runtime.port_free(service.host_port):
            continue
        lines.append(_taken_line(service, occupant, owners))
    if not lines:
        return ""
    again = " ".join(["ostler env up", *targets, "--copy NAME"])
    return "\n".join([f"the {prepared.copy.name} copy cannot take its fixed host ports:", *lines,
                      f"stop what holds them, or bring up a named copy, which takes free ports: "
                      f"`{again}`"])


def _taken_line(service: spec.Service, occupant: runtime.Occupant | None,
                owners: dict[str, tuple[str, str]]) -> str:
    port = service.host_port
    if occupant is None:
        return f"- {service.ref} needs host port {port}, which a process outside docker holds"
    if occupant.service and occupant.project in owners:
        name, repo = owners[occupant.project]
        return (f"- {occupant.service} is already running on host port {port} in the {name} "
                f"copy of {repo or occupant.project}")
    project = f" of compose project {occupant.project}" if occupant.project else ""
    return (f"- {service.ref} needs host port {port}, which container {occupant.container}"
            f"{project} holds")


def cmd_down(root: Path, *, copy_name: str = SHARED, keep_data: bool = False,
             runner: Runner = run_command) -> EnvOutcome:
    """Stop the copy and delete its secrets, then its data and directory unless they are kept."""
    return _down(runtime.copy_for(root, copy_name), keep_data=keep_data, runner=runner)


def reclaim(*, keep: Copy | None = None, runner: Runner = run_command) -> list[str]:
    """Tear down every copy on this machine whose holding run is gone, and name each one."""
    gone: list[str] = []
    for copy, manifest in runtime.held_copies():
        if keep is not None and copy.directory == keep.directory:
            continue
        if runtime.holder_alive(manifest.get("holder")):
            continue
        if _down(copy, keep_data=False, runner=runner).ok:
            gone.append(copy.project)
    return gone


def _down(copy: Copy, *, keep_data: bool, runner: Runner) -> EnvOutcome:
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
    """Every service of this repo's stack with what it is and the copies running it, then the copies."""
    catalog = spec.load(root)
    status = runtime.running_projects(runner)
    rows: list[dict[str, Any]] = []
    copy_lines: list[str] = []
    by_ref: dict[str, list[str]] = {}
    states: dict[str, str] = {}
    for copy in runtime.copies(root):
        manifest = runtime.read_manifest(copy.directory)
        targets = _listed(manifest, "targets")
        state = status.get(copy.project, "not running")
        states[copy.name] = state
        for ref in targets:
            by_ref.setdefault(ref, []).append(copy.name)
        rows.append({
            "copy": copy.name,
            "project": copy.project,
            "status": state,
            "targets": targets,
            "rendered_at": manifest.get("rendered_at", ""),
            "addresses": _read_book(copy),
        })
        copy_lines.append(f"{copy.name}  {state}  {', '.join(targets)}")
    services = [_service_row(service, by_ref.get(service.ref, [])) for service in catalog.services.values()]
    lines = _service_lines(catalog, services, states) if services else [
        f"no book has an {spec.OPS_DIR}/{spec.STACK_FILE}", *copy_lines]
    if catalog.errors:
        lines += ["", "the stack files do not fit together:", *(f"- {error}" for error in catalog.errors)]
    message = "\n".join(lines) or "no copy of this stack exists"
    return EnvOutcome(not catalog.errors, message,
                      {"ok": not catalog.errors, "copies": rows, "services": services,
                       "errors": catalog.errors})


def _service_row(service: spec.Service, copies: list[str]) -> dict[str, Any]:
    return {
        "ref": service.ref,
        "book": service.book,
        "name": service.name,
        "about": service.about,
        "address": service.address,
        "host_port": service.host_port,
        "copies": copies,
    }


def _service_lines(catalog: spec.Catalog, services: list[dict[str, Any]],
                   states: dict[str, str]) -> list[str]:
    cells = [(row["book"], row["ref"], _short(row["about"]), _published(row),
              ", ".join(name if states[name].startswith("running") else f"{name} ({states[name]})"
                        for name in row["copies"])) for row in services]
    widths = [max(len(cell[column]) for cell in cells) for column in (1, 2, 3)]
    lines: list[str] = []
    for book in sorted(catalog.books):
        owned = [cell for cell in cells if cell[0] == book]
        if not owned:
            continue
        lines.append(book)
        lines += ["  " + "  ".join(
            [cell[1].ljust(widths[0]), cell[2].ljust(widths[1]), cell[3].ljust(widths[2]),
             cell[4]]).rstrip() for cell in owned]
    return lines


def _published(row: dict[str, Any]) -> str:
    if not row["address"]:
        return ""
    return f"{row['address']} :{row['host_port']}" if row["host_port"] else str(row["address"])


def _short(about: str) -> str:
    return about if len(about) <= ABOUT_WIDTH else about[:ABOUT_WIDTH - 1].rstrip() + "…"


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


def _run_jobs(
    prepared: Prepared, jobs: list[spec.Service], produced: Path, compose: Compose,
    wait_seconds: int,
) -> str:
    copy = prepared.copy
    names = [name for job in jobs for name in job.outputs]
    secrets.write_private(produced, "".join(f"{name}=pending\n" for name in names))
    outcome = compose.up(wait_seconds=wait_seconds,
                         services=[job.compose_name for job in jobs])
    if outcome.returncode != 0:
        return (f"docker compose could not bring the jobs {', '.join(job.ref for job in jobs)} "
                f"up (exit {outcome.returncode}); read `ostler env compose --copy {copy.name} "
                "-- logs`")
    lines: list[str] = []
    for job in jobs:
        written = _output_lines(render_mod.outputs_dir(copy, job) / render_mod.OUTPUTS_FILE)
        absent = [name for name in job.outputs if name not in written]
        if absent:
            return (f"{job.ref} exited 0 without writing {', '.join(f'`{n}`' for n in absent)} "
                    f"to ${render_mod.OUTPUTS_VAR}")
        lines += [written[name] for name in job.outputs]
    secrets.write_private(produced, "".join(f"{line}\n" for line in lines))
    _drop_raw_outputs(copy, jobs)
    return ""


def _output_lines(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    found: dict[str, str] = {}
    for line in text.splitlines():
        for name in secrets.parse_names(line):
            found[name] = line
    return found


def _drop_raw_outputs(copy: Copy, jobs: list[spec.Service]) -> None:
    for job in jobs:
        (render_mod.outputs_dir(copy, job) / render_mod.OUTPUTS_FILE).unlink(missing_ok=True)


def _rendered(root: Path, prepared: Prepared) -> render_mod.Rendered:
    return render_mod.render(prepared.catalog, prepared.services, prepared.copy, repo=root,
                             fixtures=prepared.fixtures)


def _missing_message(problems: list[str]) -> str:
    return ("a `${NAME}` the templates require is in no secret source:\n- "
            + "\n- ".join(problems))


def _name_problems(root: Path, catalog: spec.Catalog, runner: Runner) -> list[str]:
    services = spec.closure(catalog, sorted(catalog.books))
    copy = runtime.copy_for(root, SHARED)
    try:
        rendered = render_mod.render(catalog, services, copy, repo=root,
                                     fixtures=render_mod.fixture_sets(catalog, services, []))
        problems = secrets.missing_names(
            rendered, catalog, services, secrets.source_for(catalog, root, runner))
    except (RenderError, secrets.SecretError) as exc:
        return [str(exc)]
    return [f"a `${{NAME}}` the templates require is in no secret source: {line}"
            for line in problems]


def _write(
    root: Path, prepared: Prepared, rendered: render_mod.Rendered, *, started: bool,
    holder: int | None = None, env_files: list[Path] | None = None,
    exec_prefix: list[str] | None = None,
) -> list[Path]:
    written = render_mod.write(rendered)
    previous = runtime.read_manifest(prepared.copy.directory)
    kept = previous.get("env_files", [])
    kept_prefix = previous.get("exec_prefix", [])
    written.append(runtime.write_manifest(prepared.copy, {
        "repo": str(root),
        "copy": prepared.copy.name,
        "targets": [service.ref for service in prepared.services],
        "fixtures": prepared.fixtures,
        "rendered_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "started": started,
        "holder": runtime.holder_stamp(holder) if holder else {},
        "env_files": [str(path) for path in env_files] if env_files is not None else kept,
        "exec_prefix": exec_prefix if exec_prefix is not None else kept_prefix,
    }))
    return written


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


def replace_process(argv: list[str], env: Mapping[str, str]) -> NoReturn:
    os.execvpe(argv[0], argv, dict(env))


def cmd_exec(
    root: Path, token: str, command: Sequence[str], *, runner: Runner = run_command,
    execute: Callable[[list[str], Mapping[str, str]], NoReturn] = replace_process,
    base: Mapping[str, str] | None = None,
) -> EnvOutcome:
    """Replace this process with *command*, run under the environment page *token* names."""
    try:
        node = page.find_environment(model.load(root), token)
        resolved = inject.resolve(node, runner)
        argv = inject.exec_argv(resolved, list(command))
        env = inject.composed_environment(resolved, os.environ if base is None else base)
    except (LookupError, page.VariableError, inject.ResolutionError) as exc:
        return _fail(str(exc))
    execute(argv, env)


def cmd_dotenv(root: Path, token: str, to: str = ".env") -> EnvOutcome:
    """Write the environment page *token* names as a dotenv file, the held names blank."""
    try:
        node = page.find_environment(model.load(root), token)
        variables = page.read_variables(node)
    except (LookupError, page.VariableError) as exc:
        return _fail(str(exc))
    target = Path(to) if Path(to).is_absolute() else root / to
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(inject.render_dotenv(variables, node.id), encoding="utf-8")
    lines = [f"wrote {target} ({len(variables.entries)} variables, {len(variables.held)} held)"]
    if target.resolve().is_relative_to(root.resolve()):
        relative = target.resolve().relative_to(root.resolve()).as_posix()
        if inject.ensure_ignored(root, relative):
            lines.append(f"added {relative} to .gitignore")
    else:
        print(f"{target} is outside {root}; .gitignore left alone", file=sys.stderr)
    return EnvOutcome(True, "\n".join(lines), {"ok": True, "path": str(target)})
