"""Read every book's `stack.yml` into one catalog of services and what each needs."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.resolver import BaseResolver

from ostler import path as path_mod
from ostler.qa import addresses

STACK_FILE = "stack.yml"
BOOK_KEYS = frozenset({"services", "secrets", "default-fixtures"})
SERVICE_KEYS = frozenset({
    "about", "define", "needs", "address", "port", "host-port", "scheme", "once",
    "render", "fixtures",
})


class _UniqueKeyLoader(yaml.SafeLoader):
    """A loader that refuses a mapping naming one key twice, where plain YAML keeps the last."""


def _unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node)
        if key in seen:
            raise ConstructorError(
                None, None, f"`{key}` is defined twice", key_node.start_mark)
        seen.add(key)
    return loader.construct_mapping(node)


_UniqueKeyLoader.add_constructor(
    BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


@dataclass(frozen=True)
class Service:
    """One service a book defines: the template that describes it and what it waits for."""

    book: str
    name: str
    book_dir: Path
    define: Path
    about: str = ""
    needs: tuple[str, ...] = ()
    address: str = ""
    port: int = 0
    host_port: int = 0
    scheme: str = "http"
    once: bool = False
    render: tuple[Path, ...] = ()
    fixtures: dict[str, tuple[Path, ...]] = field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"{self.book}:{self.name}"

    @property
    def compose_name(self) -> str:
        return f"{self.book}-{self.name}"


@dataclass(frozen=True)
class Book:
    """One book's stack: its services, the saddlebag environment it boots with, its fixtures."""

    name: str
    directory: Path
    secrets: str = ""
    default_fixtures: tuple[str, ...] = ()
    services: tuple[str, ...] = ()


@dataclass
class Catalog:
    """Every book's services by reference, and every reason the books do not fit together."""

    books: dict[str, Book] = field(default_factory=dict)
    services: dict[str, Service] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def stack_files(root: Path) -> list[Path]:
    """The `stack.yml` of the book at the features root and of each book one level below it."""
    base = path_mod.features_root_in(root)
    if not base.is_dir():
        return []
    found = [base / STACK_FILE] if (base / STACK_FILE).is_file() else []
    found += sorted(child / STACK_FILE for child in base.iterdir()
                    if (child / STACK_FILE).is_file())
    return found


def book_name(root: Path, stack_file: Path) -> str:
    """The name other books reference *stack_file*'s services by."""
    directory = stack_file.parent
    return root.name.lower() if directory == path_mod.features_root_in(root) else directory.name


def load(root: Path) -> Catalog:
    """The catalog of every book under *root*, with each problem found in it."""
    catalog = Catalog()
    for stack_file in stack_files(root):
        _read_book(catalog, book_name(root, stack_file), stack_file)
    _check_needs(catalog)
    _check_cycles(catalog)
    _check_shared(catalog)
    return catalog


def _read_book(catalog: Catalog, name: str, stack_file: Path) -> None:
    where = stack_file.as_posix()
    try:
        raw = yaml.load(stack_file.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        catalog.errors.append(f"{where}: {exc}")
        return
    if not isinstance(raw, dict):
        catalog.errors.append(f"{where}: is not a mapping with a `services:` key")
        return
    for key in sorted({str(key) for key in raw} - BOOK_KEYS):
        catalog.errors.append(f"{where}: `{key}` is not a stack key ({_listing(BOOK_KEYS)})")
    services = raw.get("services") or {}
    if not isinstance(services, dict):
        catalog.errors.append(f"{where}: `services:` is not a mapping of name to service")
        return
    refs: list[str] = []
    for service_name, body in services.items():
        service = _read_service(catalog, name, stack_file, str(service_name), body)
        if service is not None:
            catalog.services[service.ref] = service
            refs.append(service.ref)
    defaults = tuple(str(item) for item in _as_list(raw.get("default-fixtures")))
    declared = {fixture for ref in refs for fixture in catalog.services[ref].fixtures}
    for fixture in defaults:
        if fixture not in declared:
            catalog.errors.append(
                f"{where}: default fixture set `{fixture}` is declared by none of its services")
    catalog.books[name] = Book(
        name=name,
        directory=stack_file.parent,
        secrets=str(raw.get("secrets") or ""),
        default_fixtures=defaults,
        services=tuple(refs),
    )


def _read_service(
    catalog: Catalog, book: str, stack_file: Path, name: str, body: object
) -> Service | None:
    where = f"{stack_file.as_posix()}: service `{name}`"
    if not addresses.is_name(name):
        catalog.errors.append(f"{where}: a service name is lowercase letters, digits and `-`")
        return None
    if not isinstance(body, dict):
        catalog.errors.append(f"{where}: is not a mapping")
        return None
    for key in sorted({str(key) for key in body} - SERVICE_KEYS):
        catalog.errors.append(f"{where}: `{key}` is not a service key ({_listing(SERVICE_KEYS)})")
    directory = stack_file.parent
    define = str(body.get("define") or "")
    if not define:
        catalog.errors.append(f"{where}: names no `define:` template")
        return None
    files = [directory / define]
    render = tuple(directory / str(item) for item in _as_list(body.get("render")))
    files += render
    fixtures: dict[str, tuple[Path, ...]] = {}
    raw_fixtures = body.get("fixtures") or {}
    if not isinstance(raw_fixtures, dict):
        catalog.errors.append(f"{where}: `fixtures:` is not a mapping of set name to files")
        raw_fixtures = {}
    for set_name, items in raw_fixtures.items():
        fixtures[str(set_name)] = tuple(directory / str(item) for item in _as_list(items))
        files += fixtures[str(set_name)]
    for file in files:
        if not file.is_file():
            catalog.errors.append(f"{where}: `{file.relative_to(directory).as_posix()}` "
                                  "does not exist")
    address = str(body.get("address") or "")
    port = _as_port(catalog, where, "port", body.get("port"))
    if address and not addresses.is_name(address):
        catalog.errors.append(f"{where}: address `{address}` is not lowercase letters, "
                              "digits and `-`")
    if address and not port:
        catalog.errors.append(f"{where}: publishes `{address}` but names no `port:` to publish")
    needs = tuple(_qualify(book, str(item)) for item in _as_list(body.get("needs")))
    return Service(
        book=book,
        name=name,
        book_dir=directory,
        define=directory / define,
        about=str(body.get("about") or ""),
        needs=needs,
        address=address,
        port=port,
        host_port=_as_port(catalog, where, "host-port", body.get("host-port")),
        scheme=str(body.get("scheme") or "http"),
        once=bool(body.get("once")),
        render=render,
        fixtures=fixtures,
    )


def _check_needs(catalog: Catalog) -> None:
    for service in catalog.services.values():
        for need in service.needs:
            if need not in catalog.services:
                catalog.errors.append(f"{service.ref} needs `{need}`, which no book defines")


def _check_cycles(catalog: Catalog) -> None:
    state: dict[str, int] = {}

    def visit(ref: str, trail: list[str]) -> None:
        state[ref] = 1
        for need in catalog.services[ref].needs:
            if need not in catalog.services:
                continue
            if state.get(need) == 1:
                cycle = [*trail[trail.index(need):], need] if need in trail else [ref, need]
                catalog.errors.append(f"the needs form a cycle: {' -> '.join(cycle)}")
            elif need not in state:
                visit(need, [*trail, need])
        state[ref] = 2

    for ref in sorted(catalog.services):
        if ref not in state:
            visit(ref, [ref])


def _check_shared(catalog: Catalog) -> None:
    by_define: dict[Path, str] = {}
    by_address: dict[str, str] = {}
    for ref, service in sorted(catalog.services.items()):
        other = by_define.setdefault(service.define.resolve(), ref)
        if other != ref:
            catalog.errors.append(
                f"{ref} and {other} are both defined by `{service.define.name}`: define it once "
                f"and name it in the other book's `needs:`")
        if service.address:
            owner = by_address.setdefault(service.address, ref)
            if owner != ref:
                catalog.errors.append(f"{ref} and {owner} both publish `{service.address}`")


def closure(catalog: Catalog, targets: Iterable[str]) -> list[Service]:
    """The services *targets* name and every service they need, each needed one first."""
    ordered: list[Service] = []
    seen: set[str] = set()

    def visit(ref: str) -> None:
        if ref in seen:
            return
        seen.add(ref)
        service = catalog.services[ref]
        for need in service.needs:
            visit(need)
        ordered.append(service)

    for target in targets:
        for ref in resolve_target(catalog, target):
            visit(ref)
    return ordered


def resolve_target(catalog: Catalog, target: str) -> list[str]:
    """The service references *target* names: a book's every service, or one `book:service`."""
    if ":" in target:
        if target not in catalog.services:
            raise KeyError(f"no book defines the service `{target}`")
        return [target]
    if target not in catalog.books:
        known = ", ".join(sorted(catalog.books)) or "none"
        raise KeyError(f"no book is named `{target}` (books with a {STACK_FILE}: {known})")
    return list(catalog.books[target].services)


def _qualify(book: str, ref: str) -> str:
    return ref if ":" in ref else f"{book}:{ref}"


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _as_port(catalog: Catalog, where: str, key: str, value: object) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, int) and not isinstance(value, bool) and 0 < value < 65536:
        return value
    catalog.errors.append(f"{where}: `{key}: {value}` is not a port number")
    return 0


def _listing(keys: Iterable[str]) -> str:
    return ", ".join(f"`{key}`" for key in sorted(keys))
