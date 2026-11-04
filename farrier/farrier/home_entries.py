"""Home records that live as one named entry inside a file another program also writes."""
from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import tomlkit

from farrier._vendor.stablemate_core.schema import HomeConfig, Selection
from farrier.layers import available_names, find_in_layers, searched_layers
from farrier.sources import load_pack, read_yaml
from farrier.user_library import user_library_tables

LEDGER = ".agents/.farrier-home.json"
SERVER_KEYS = {"command", "args", "env"}
GUARD_CONTAINER = "hooks.PreToolUse"
OPENCODE_CONFIG = ".config/opencode/opencode.json"
OVERRIDES = {OPENCODE_CONFIG: ".config/opencode/opencode.jsonc"}


@dataclass(frozen=True)
class ToolServer:
    """One MCP server as the library declares it, in no harness's spelling."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Entry:
    """One value farrier intends to hold under *container*.*name* in the file at *rel*."""

    rel: str
    container: str
    name: str
    value: dict[str, Any]


@dataclass(frozen=True)
class EntryDrift:
    """How one entry departs from the intended setup."""

    kind: str
    rel: str
    container: str
    name: str

    def label(self) -> str:
        return f"{self.kind} entry: {self.rel} {self.container}.{self.name}"


class EntryFile(Protocol):
    """A config file edited one entry at a time, everything else left as it was."""

    def entries(self, container: str) -> dict[str, Any]: ...

    def put(self, container: str, name: str, value: dict[str, Any]) -> None: ...

    def drop(self, container: str, name: str) -> None: ...

    def text(self) -> str: ...


class JsonEntryFile:
    """A JSON config, written back with its two-space indent and its original ending.

    Guard groups have no name of their own, so each is addressed by the command it runs.
    """

    def __init__(self, text: str) -> None:
        self._document: dict[str, Any] = json.loads(text) if text.strip() else {}
        self._ending = text[len(text.rstrip()) :]

    def _guard_groups(self) -> list[dict[str, Any]]:
        return (self._document.get("hooks") or {}).get("PreToolUse") or []

    def entries(self, container: str) -> dict[str, Any]:
        if container == GUARD_CONTAINER:
            return {
                hook["command"]: group
                for group in self._guard_groups()
                for hook in group.get("hooks", [])
                if "command" in hook
            }
        return dict(self._document.get(container) or {})

    def put(self, container: str, name: str, value: dict[str, Any]) -> None:
        if container != GUARD_CONTAINER:
            self._document.setdefault(container, {})[name] = value
            return
        groups = self._document.setdefault("hooks", {}).setdefault("PreToolUse", [])
        held = self.entries(container).get(name)
        if held is None:
            groups.append(value)
        else:
            groups[groups.index(held)] = value

    def drop(self, container: str, name: str) -> None:
        if container != GUARD_CONTAINER:
            del self._document[container][name]
            return
        hooks = self._document["hooks"]
        hooks["PreToolUse"].remove(self.entries(container)[name])
        if not hooks["PreToolUse"]:
            del hooks["PreToolUse"]
        if not hooks:
            del self._document["hooks"]

    def text(self) -> str:
        return json.dumps(self._document, indent=2, ensure_ascii=False) + self._ending


class TomlEntryFile:
    """A TOML config, whose comments and layout tomlkit carries through, with its original ending."""

    def __init__(self, text: str) -> None:
        self._document = tomlkit.parse(text)
        self._ending = text[len(text.rstrip()) :] if text.strip() else "\n"

    def entries(self, container: str) -> dict[str, Any]:
        table = self._document.get(container)
        return {} if table is None else dict(table.unwrap())

    def put(self, container: str, name: str, value: dict[str, Any]) -> None:
        if container not in self._document:
            self._document.add(container, tomlkit.table(is_super_table=True))
        self._document[container][name] = value  # pyright: ignore[reportIndexIssue]

    def drop(self, container: str, name: str) -> None:
        del self._document[container][name]  # pyright: ignore[reportIndexIssue]

    def text(self) -> str:
        return tomlkit.dumps(self._document).rstrip() + self._ending


def plain_json(text: str) -> str:
    """JSONC *text* as JSON, without its comments and trailing commas."""
    plain: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == '"':
            end = index + 1
            while text[end] != '"':
                end += 2 if text[end] == "\\" else 1
            plain.append(text[index : end + 1])
            index = end + 1
        elif text.startswith("//", index):
            index = text.find("\n", index) % (len(text) + 1)
        elif text.startswith("/*", index):
            index = text.index("*/", index) + 2
        else:
            if char in "}]" and "".join(plain).rstrip().endswith(","):
                plain = ["".join(plain).rstrip()[:-1]]
            plain.append(char)
            index += 1
    return "".join(plain)


def read_only_jsonc(text: str) -> EntryFile:
    """A JSONC config farrier only ever reads, because writing it back would lose its comments."""
    return JsonEntryFile(plain_json(text))


ENTRY_FORMATS: dict[str, Callable[[str], EntryFile]] = {
    ".json": JsonEntryFile,
    ".jsonc": read_only_jsonc,
    ".toml": TomlEntryFile,
}


def read_entry_file(path: Path) -> EntryFile:
    """The file at *path* ready to edit, an absent one reading as empty."""
    text = path.read_bytes().decode("utf-8") if path.exists() else ""
    try:
        return ENTRY_FORMATS[path.suffix](text)
    except (ValueError, IndexError) as exc:
        raise SystemExit(f"error: cannot parse {path}: {exc}. Nothing was written.") from exc


def replace_file(path: Path, text: str) -> None:
    """Swap *text* in at *path* in one rename, through a symlink and keeping the file's mode."""
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = target.stat().st_mode & 0o777 if target.exists() else 0o600
    handle, temporary = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    with os.fdopen(handle, "wb") as stream:
        stream.write(text.encode("utf-8"))
    os.chmod(temporary, mode)
    os.replace(temporary, target)


def claude_server(server: ToolServer) -> dict[str, Any]:
    return {"type": "stdio", "command": server.command, "args": server.args, "env": server.env}


def codex_server(server: ToolServer) -> dict[str, Any]:
    spelled: dict[str, Any] = {"command": server.command, "args": server.args}
    if server.env:
        spelled["env"] = server.env
    return spelled


def opencode_server(server: ToolServer) -> dict[str, Any]:
    spelled: dict[str, Any] = {"type": "local", "command": [server.command, *server.args]}
    if server.env:
        spelled["environment"] = server.env
    return spelled


@dataclass(frozen=True)
class McpDialect:
    """Where one harness reads its home MCP servers, and how it spells one."""

    rel: str
    container: str
    spell: Callable[[ToolServer], dict[str, Any]]


MCP_DIALECTS = {
    "claude": McpDialect(".claude.json", "mcpServers", claude_server),
    "codex": McpDialect(".codex/config.toml", "mcp_servers", codex_server),
    "opencode": McpDialect(OPENCODE_CONFIG, "mcp", opencode_server),
}


def load_tool_server(name: str) -> ToolServer:
    """The server record ``library/mcp/<name>.yml`` from the highest layer holding it."""
    hit = find_in_layers("library", "mcp", f"{name}.yml")
    if hit is None:
        available = ", ".join(available_names("library", "mcp", suffix=".yml")) or "none"
        raise SystemExit(
            f"error: unknown MCP server {name!r}. Available: {available}.\n"
            f"Searched these library layers:\n{searched_layers()}"
        )
    _layer, path = hit
    data = read_yaml(path)
    unknown = sorted(set(data) - SERVER_KEYS)
    if unknown:
        raise SystemExit(f"error: {path} has unknown keys: {', '.join(unknown)}.")
    command = data.get("command")
    if not isinstance(command, str) or not command:
        raise SystemExit(f"error: {path} needs a `command`.")
    return ToolServer(
        name,
        command,
        [str(arg) for arg in data.get("args") or []],
        {str(key): str(value) for key, value in (data.get("env") or {}).items()},
    )


def tool_server_names(table: Selection) -> set[str]:
    """The servers one harness table selects, directly or through its packs."""
    names = set(table.mcp)
    for pack in table.packs:
        names.update(load_pack(str(pack))["mcp"])
    return names


def user_entries(home: HomeConfig) -> list[Entry]:
    """Every merged entry the user_library tables intend, in a stable order."""
    entries: list[Entry] = []
    for harness, table in user_library_tables(home).items():
        names = tool_server_names(table)
        if not names:
            continue
        dialect = MCP_DIALECTS.get(harness)
        if dialect is None:
            raise SystemExit(
                f"error: [user_library.{harness}] names MCP servers, and farrier writes "
                f"them only for {', '.join(MCP_DIALECTS)}."
            )
        for name in sorted(names):
            entries.append(
                Entry(dialect.rel, dialect.container, name, dialect.spell(load_tool_server(name)))
            )
    return entries


Ledger = dict[str, dict[str, list[str]]]


def read_ledger(home: Path) -> Ledger:
    """Which entries farrier installed: file, then container, then names."""
    path = home / LEDGER
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"error: cannot parse {path}: {exc}. Nothing was written.") from exc


def write_ledger(home: Path, ledger: Ledger) -> None:
    """Record *ledger*, leaving a home that never held an entry without the file."""
    if ledger or (home / LEDGER).exists():
        replace_file(home / LEDGER, json.dumps(ledger, indent=2, sort_keys=True) + "\n")


def ledger_with(ledger: Ledger, owned: list[Entry]) -> Ledger:
    """*ledger* with every entry of *owned* added."""
    merged = {rel: {key: list(names) for key, names in kept.items()} for rel, kept in ledger.items()}
    for entry in owned:
        names = merged.setdefault(entry.rel, {}).setdefault(entry.container, [])
        if entry.name not in names:
            names.append(entry.name)
    return merged


def significant(value: Mapping[str, Any]) -> dict[str, Any]:
    """*value* without its empty keys, because a harness may write or omit an empty list."""
    return {key: item for key, item in value.items() if item not in ({}, [], None)}


def in_ledger(ledger: Ledger, rel: str, container: str, name: str) -> bool:
    return name in ledger.get(rel, {}).get(container, [])


def entry_drift(home: Path, intended: list[Entry], ledger: Ledger) -> list[EntryDrift]:
    """Each difference between the intended entries, the ledger and the files in the home."""
    drift: list[EntryDrift] = []
    wanted = {(entry.rel, entry.container, entry.name) for entry in intended}
    for entry in intended:
        overridden = OVERRIDES.get(entry.rel)
        if overridden is not None:
            beside = read_entry_file(home / overridden).entries(entry.container).get(entry.name)
            if beside is not None and significant(beside) != significant(entry.value):
                drift.append(EntryDrift("foreign", overridden, entry.container, entry.name))
        held = read_entry_file(home / entry.rel).entries(entry.container).get(entry.name)
        if held is None:
            kind = "missing"
        elif significant(held) == significant(entry.value):
            continue
        else:
            kind = "changed" if in_ledger(ledger, entry.rel, entry.container, entry.name) else "foreign"
        drift.append(EntryDrift(kind, entry.rel, entry.container, entry.name))
    for rel, containers in ledger.items():
        for container, names in containers.items():
            present = read_entry_file(home / rel).entries(container)
            for name in names:
                if name in present and (rel, container, name) not in wanted:
                    drift.append(EntryDrift("extra", rel, container, name))
    return drift


def check_entries(home: Path, intended: list[Entry], regenerate: str) -> int:
    """Report entry drift by name, never by value because an env value can be a secret."""
    drift = entry_drift(home, intended, read_ledger(home))
    if not drift:
        return 0
    for item in drift:
        print(item.label())
    print(f"Run `{regenerate}` to bring these in line. A foreign entry is yours to remove first.")
    return 1


def refuse_foreign_entries(home: Path, intended: list[Entry]) -> None:
    """Stop before any write when a value farrier did not install holds an entry it intends."""
    foreign = [
        item for item in entry_drift(home, intended, read_ledger(home)) if item.kind == "foreign"
    ]
    if not foreign:
        return
    listing = "\n".join(f"  {item.rel} {item.container}.{item.name}" for item in foreign)
    raise SystemExit(
        f"farrier will not overwrite entries it did not install. {len(foreign)} entry(ies) "
        f"hold a different value:\n{listing}\n"
        "Remove each one or make it match the library, then install again. Nothing was written."
    )


def install_entries(home: Path, intended: list[Entry]) -> int:
    """Write the drifted entries and delete the ones dropped, returning how many changed."""
    ledger = read_ledger(home)
    drift = entry_drift(home, intended, ledger)
    by_key = {(entry.rel, entry.container, entry.name): entry for entry in intended}
    drifted = {(item.rel, item.container, item.name) for item in drift}
    owned = [
        entry
        for entry in intended
        if in_ledger(ledger, entry.rel, entry.container, entry.name)
        or (entry.rel, entry.container, entry.name) in drifted
    ]
    write_ledger(home, ledger_with(ledger, owned))
    for rel in sorted({item.rel for item in drift}):
        document = read_entry_file(home / rel)
        for item in drift:
            if item.rel != rel:
                continue
            if item.kind == "extra":
                document.drop(item.container, item.name)
            else:
                document.put(item.container, item.name, by_key[(rel, item.container, item.name)].value)
        replace_file(home / rel, document.text())
    write_ledger(home, ledger_with({}, owned))
    return len(drift)
