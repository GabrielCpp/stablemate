"""Read every book's `stack.yml` into one catalog of services and what each needs."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.resolver import BaseResolver

from ostler import path as path_mod
from ostler.qa import addresses

STACK_FILE = "stack.yml"
_OUTPUT_NAME = re.compile(r"[A-Z_][A-Z0-9_]*")
OPS_DIR = "ops"


@dataclass(frozen=True)
class Key:
    """One key `stack.yml` accepts: the level it sits at, its JSON Schema and what it says."""

    level: str
    name: str
    json_type: dict[str, Any]
    meaning: str


_STRINGS: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
_SECRETS: dict[str, Any] = {
    "type": "object",
    "properties": {"file": {"type": "string"}, "decrypt": {"type": "string"},
                   "saddlebag": {"type": "string"}},
    "additionalProperties": False,
    "oneOf": [{"required": ["file"]}, {"required": ["decrypt"]}, {"required": ["saddlebag"]}],
}

KEYS: tuple[Key, ...] = (
    Key("book", "services", {"type": "object"},
        "one entry per service this book defines, named in lowercase letters, digits and `-`"),
    Key("root", "secrets", _SECRETS,
        "the one source of `${VAR}` values: `file:` a dotenv file, `decrypt:` a command "
        "whose stdout is dotenv, or `saddlebag:` the `key=value` tags that select secrets in "
        "saddlebag, under which every compose command runs. Valid only in the stack root, "
        "docs/services/ops/stack.yml"),
    Key("book", "needs", _STRINGS,
        "the books whose every service this book's services need, so they come up first"),
    Key("book", "default-fixtures", _STRINGS,
        "the fixture sets loaded when a bring-up names none"),
    Key("service", "about", {"type": "string"},
        "one line on what the service is, the line `ostler env ls` shows for it"),
    Key("service", "define", {"type": "string"},
        "the template that renders to this service's compose block"),
    Key("service", "needs", _STRINGS,
        "the services that must be up first: `name` is this book's, `book:name` another book's"),
    Key("service", "once", {"type": "boolean"},
        "`true` for a job that runs to completion, such as a migration"),
    Key("service", "files", {"type": "object", "additionalProperties": {"type": "string"}},
        "files placed in the service's folder of the copy, target to source: a `.j2` source "
        "is rendered, any other is copied byte for byte, a folder is walked"),
    Key("service", "outputs", {"type": "array", "items": {"type": "string",
                                                         "pattern": "^[A-Z_][A-Z0-9_]*$"}},
        "for a `once` job, the environment names it writes to `$STABLEMATE_OUTPUTS`, which the "
        "services that need it read as `${NAME}`"),
    Key("service", "fixtures", {"type": "object", "additionalProperties": _STRINGS},
        "fixture sets by name, each a list of files the service loads"),
    Key("service", "address", {"type": "string"},
        "the name a run reads this service's URL by"),
    Key("service", "port", {"type": "integer", "minimum": 1, "maximum": 65535},
        "the container port the address publishes"),
    Key("service", "host-port", {"type": "integer", "minimum": 1, "maximum": 65535},
        "the host port the shared copy keeps"),
    Key("service", "scheme", {"type": "string"},
        "the address's URL scheme, `http` unless stated"),
)


def keys_at(level: str) -> frozenset[str]:
    """The names of the keys the key table gives *level*."""
    return frozenset(key.name for key in KEYS if key.level == level)


def schema() -> dict[str, Any]:
    """A JSON Schema (draft 2020-12) for `stack.yml`, generated from the key table."""

    def properties(level: str) -> dict[str, Any]:
        return {key.name: {**key.json_type, "description": key.meaning}
                for key in KEYS if key.level == level}

    service = {
        "type": "object",
        "properties": properties("service"),
        "required": ["about", "define"],
        "additionalProperties": False,
    }
    book = properties("root") | properties("book")
    book["services"] = {**book["services"], "additionalProperties": service}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": STACK_FILE,
        "type": "object",
        "properties": book,
        "additionalProperties": False,
    }


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
    ops_dir: Path
    define: Path
    about: str = ""
    needs: tuple[str, ...] = ()
    address: str = ""
    port: int = 0
    host_port: int = 0
    scheme: str = "http"
    once: bool = False
    outputs: tuple[str, ...] = ()
    files: dict[str, Path] = field(default_factory=dict)
    fixtures: dict[str, tuple[Path, ...]] = field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"{self.book}:{self.name}"

    @property
    def compose_name(self) -> str:
        return f"{self.book}-{self.name}"


@dataclass(frozen=True)
class Book:
    """One book's stack: its folder, its `ops/` folder, its services and fixtures."""

    name: str
    directory: Path
    ops_dir: Path
    needs: tuple[str, ...] = ()
    default_fixtures: tuple[str, ...] = ()
    services: tuple[str, ...] = ()


@dataclass(frozen=True)
class SecretSpec:
    """The stack root's `secrets:`: a dotenv file, a command whose stdout is dotenv, or saddlebag tags."""

    file: str = ""
    decrypt: str = ""
    saddlebag: str = ""


@dataclass
class Catalog:
    """Every book's services by reference, and every reason the books do not fit together."""

    books: dict[str, Book] = field(default_factory=dict)
    secrets: SecretSpec = field(default_factory=SecretSpec)
    services: dict[str, Service] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def stack_files(root: Path) -> list[Path]:
    """The `ops/stack.yml` of the book at the services root and of each book one level below it."""
    base = path_mod.services_root_in(root)
    if not base.is_dir():
        return []
    found = [base / OPS_DIR / STACK_FILE] if (base / OPS_DIR / STACK_FILE).is_file() else []
    found += sorted(child / OPS_DIR / STACK_FILE for child in base.iterdir()
                    if (child / OPS_DIR / STACK_FILE).is_file())
    return found


def old_stack_files(root: Path) -> list[Path]:
    """The `stack.yml` files that sit where books kept them before `ops/`."""
    base = path_mod.services_root_in(root)
    if not base.is_dir():
        return []
    found = [base / STACK_FILE] if (base / STACK_FILE).is_file() else []
    found += sorted(child / STACK_FILE for child in base.iterdir()
                    if child.name != OPS_DIR and (child / STACK_FILE).is_file())
    return found


def book_dir(stack_file: Path) -> Path:
    """The book's folder, the parent of the `ops/` folder *stack_file* sits in."""
    return stack_file.parent.parent


def book_name(root: Path, stack_file: Path) -> str:
    """The name other books reference *stack_file*'s services by."""
    directory = book_dir(stack_file)
    return root.name.lower() if directory == path_mod.services_root_in(root) else directory.name


def load(root: Path) -> Catalog:
    """The catalog of every book under *root*, with each problem found in it."""
    catalog = Catalog()
    for old in old_stack_files(root):
        new = old.parent / OPS_DIR / STACK_FILE
        catalog.errors.append(
            f"{shown(root, old)}: is the old place: move it to {shown(root, new)}, "
            f"whose paths are read from {OPS_DIR}/")
    for stack_file in stack_files(root):
        _read_book(catalog, root, book_name(root, stack_file), stack_file)
    _expand_book_needs(catalog, root)
    _check_needs(catalog)
    _check_cycles(catalog)
    _check_shared(catalog)
    return catalog


def shown(root: Path, stack_file: Path) -> str:
    """How a problem names *stack_file*: from *root* when it sits under it."""
    return (stack_file.relative_to(root).as_posix() if stack_file.is_relative_to(root)
            else stack_file.as_posix())


def _read_book(catalog: Catalog, root: Path, name: str, stack_file: Path) -> None:
    where = shown(root, stack_file)
    is_root = book_dir(stack_file) == path_mod.services_root_in(root)
    root_file = shown(root, path_mod.services_root_in(root) / OPS_DIR / STACK_FILE)
    try:
        raw = yaml.load(stack_file.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        catalog.errors.append(f"{where}: {exc}")
        return
    if not isinstance(raw, dict):
        catalog.errors.append(f"{where}: is not a mapping with a `services:` key")
        return
    accepted = keys_at("book") | keys_at("root") if is_root else keys_at("book")
    for key in sorted(str(key) for key in raw):
        if key in keys_at("root") and not is_root:
            catalog.errors.append(f"{where}: `{key}:` belongs in the stack root, {root_file}: "
                                  "one repo has one secret source" + _old_secrets(raw[key]))
        elif key not in accepted:
            catalog.errors.append(f"{where}: `{key}` is not a stack key ({_listing(accepted)})")
    if is_root and "secrets" in raw:
        catalog.secrets = _read_secrets(catalog, where, raw["secrets"])
    services = raw.get("services") or {}
    if not isinstance(services, dict):
        catalog.errors.append(f"{where}: `services:` is not a mapping of name to service")
        return
    refs: list[str] = []
    for service_name, body in services.items():
        service = _read_service(catalog, name, stack_file, where, str(service_name), body)
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
        directory=book_dir(stack_file),
        ops_dir=stack_file.parent,
        needs=tuple(str(item) for item in _as_list(raw.get("needs"))),
        default_fixtures=defaults,
        services=tuple(refs),
    )


def _read_service(
    catalog: Catalog, book: str, stack_file: Path, shown_file: str, name: str, body: object
) -> Service | None:
    where = f"{shown_file}: service `{name}`"
    if not addresses.is_name(name):
        catalog.errors.append(f"{where}: a service name is lowercase letters, digits and `-`")
        return None
    if not isinstance(body, dict):
        catalog.errors.append(f"{where}: is not a mapping")
        return None
    for key in sorted({str(key) for key in body} - keys_at("service") - {"render"}):
        catalog.errors.append(
            f"{where}: `{key}` is not a service key ({_listing(keys_at('service'))})")
    about = str(body.get("about") or "").strip()
    if not about:
        catalog.errors.append(f"{where}: names no `about:`, the line `ostler env ls` shows for it")
    directory = stack_file.parent
    define = str(body.get("define") or "")
    if not define:
        catalog.errors.append(f"{where}: names no `define:` template")
        return None
    files = [directory / define]
    if "render" in body:
        catalog.errors.append(
            f"{where}: `render:` is gone: list each helper as `files: {{<target>: <source>}}`")
    placed = _read_files(catalog, where, directory, body.get("files"))
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
    outputs = tuple(str(item) for item in _as_list(body.get("outputs")))
    for name_ in outputs:
        if not _OUTPUT_NAME.fullmatch(name_):
            catalog.errors.append(f"{where}: output `{name_}` is not an environment name "
                                  "(capital letters, digits and `_`)")
    if outputs and not body.get("once"):
        catalog.errors.append(f"{where}: `outputs:` needs `once: true`, since only a job that "
                              "has run to completion has written them")
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
        ops_dir=directory,
        define=directory / define,
        about=about,
        needs=needs,
        address=address,
        port=port,
        host_port=_as_port(catalog, where, "host-port", body.get("host-port")),
        scheme=str(body.get("scheme") or "http"),
        once=bool(body.get("once")),
        outputs=outputs,
        files=placed,
        fixtures=fixtures,
    )


def _expand_book_needs(catalog: Catalog, root: Path) -> None:
    for book in catalog.books.values():
        where = shown(root, book.ops_dir / STACK_FILE)
        wanted: list[str] = []
        for name in book.needs:
            if name == book.name:
                catalog.errors.append(f"{where}: book `{book.name}` lists itself in `needs:`")
            elif name not in catalog.books:
                catalog.errors.append(f"{where}: `needs:` names the book `{name}`, which no "
                                      "stack.yml defines")
            else:
                wanted += catalog.books[name].services
        for ref in book.services:
            service = catalog.services[ref]
            catalog.services[ref] = replace(
                service, needs=tuple(dict.fromkeys([*service.needs, *wanted])))


def _old_secrets(value: object) -> str:
    if isinstance(value, str):
        return (f" (`{value}` was a saddlebag environment, which is gone: the stack root writes "
                "`file: <path>`, `decrypt: <command>` or `saddlebag: \"<key>=<value>\"`)")
    return ""


def _tag_pairs(text: str) -> bool:
    for token in text.split():
        name, separator, value = token.partition("=")
        if not separator or not name or not value:
            return False
    return True


def _read_secrets(catalog: Catalog, where: str, value: object) -> SecretSpec:
    if isinstance(value, str):
        catalog.errors.append(
            f"{where}: `secrets: {value}` names a saddlebag environment, which is gone: write "
            "`secrets: {saddlebag: \"<key>=<value>\"}`, `secrets: {file: <path>}` or "
            "`secrets: {decrypt: <command>}`")
        return SecretSpec()
    if not isinstance(value, dict):
        catalog.errors.append(f"{where}: `secrets:` is not a mapping with `file:`, `decrypt:` or `saddlebag:`")
        return SecretSpec()
    stray = sorted(str(key) for key in value if key not in {"file", "decrypt", "saddlebag"})
    if stray or len(value) != 1:
        catalog.errors.append(
            f"{where}: `secrets:` takes exactly one of `file:`, `decrypt:` or `saddlebag:`"
            + (f", not {', '.join(f'`{key}`' for key in stray)}" if stray else ""))
        return SecretSpec()
    key, item = next(iter(value.items()))
    if not isinstance(item, str) or not item.strip():
        catalog.errors.append(f"{where}: `secrets: {key}:` is not a path or command")
        return SecretSpec()
    if key == "saddlebag" and not _tag_pairs(item):
        catalog.errors.append(
            f"{where}: `secrets: saddlebag:` is not one or more `key=value` tags separated by "
            "spaces")
        return SecretSpec()
    return SecretSpec(**{str(key): item.strip()})


def _read_files(
    catalog: Catalog, where: str, directory: Path, raw: object
) -> dict[str, Path]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        catalog.errors.append(f"{where}: `files:` is not a mapping of target to source")
        return {}
    placed: dict[str, Path] = {}
    for target, source in raw.items():
        name = str(target)
        parts = PurePosixPath(name).parts
        if not name or PurePosixPath(name).is_absolute() or ".." in parts:
            catalog.errors.append(
                f"{where}: `files:` target `{name}` is not a path inside the service's folder")
            continue
        path = directory / str(source)
        if not path.exists():
            catalog.errors.append(f"{where}: `{str(source)}` does not exist")
            continue
        placed[name] = path
    return placed


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
        raise KeyError(f"no book is named `{target}` (books with an {OPS_DIR}/{STACK_FILE}: {known})")
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
