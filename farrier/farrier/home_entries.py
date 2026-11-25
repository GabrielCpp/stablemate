"""Home records that live as one named entry inside a file another program also writes."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import tomlkit

from farrier._vendor.stablemate_core.schema import HomeConfig, Selection
from farrier.home_mcp import (
    MCP_DIALECTS,
    OPENCODE_CONFIG,
    load_tool_server,
    tool_server_names,
)
from farrier.layers import available_names, find_in_layers, searched_layers
from farrier.user_library import user_library_tables

LEDGER = ".agents/.farrier-home.json"
GUARD_CONTAINER = "hooks.PreToolUse"
DONE_CONTAINER = "hooks.Stop"
HOOK_CONTAINERS = {GUARD_CONTAINER: "PreToolUse", DONE_CONTAINER: "Stop"}
TOP_LEVEL = "."
SETTINGS_FILES = {
    "claude": ".claude/settings.json",
    "codex": ".codex/config.toml",
    "copilot": ".copilot/settings.json",
    "antigravity": ".gemini/antigravity-cli/settings.json",
    "pi": ".pi/agent/settings.json",
}
SETTINGS_OWNED_ELSEWHERE = {"hooks": "library/hooks guards"}
OVERRIDES = {OPENCODE_CONFIG: ".config/opencode/opencode.jsonc"}


@dataclass(frozen=True)
class Entry:
    """One value farrier intends to hold under *container*.*name* in the file at *rel*."""

    rel: str
    container: str
    name: str
    value: Any


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

    def put(self, container: str, name: str, value: Any) -> None: ...

    def drop(self, container: str, name: str) -> None: ...

    def text(self) -> str: ...


class JsonEntryFile:
    """A JSON config, written back with its two-space indent and its original ending.

    Guard groups have no name of their own, so each is addressed by the command it runs.
    """

    def __init__(self, text: str) -> None:
        self._document: dict[str, Any] = json.loads(text) if text.strip() else {}
        self._ending = text[len(text.rstrip()) :]

    def _hook_groups(self, event: str) -> list[dict[str, Any]]:
        return (self._document.get("hooks") or {}).get(event) or []

    def entries(self, container: str) -> dict[str, Any]:
        if container in HOOK_CONTAINERS:
            return {
                hook["command"]: group
                for group in self._hook_groups(HOOK_CONTAINERS[container])
                for hook in group.get("hooks", [])
                if "command" in hook
            }
        if container == TOP_LEVEL:
            return dict(self._document)
        return dict(self._document.get(container) or {})

    def put(self, container: str, name: str, value: Any) -> None:
        if container == TOP_LEVEL:
            self._document[name] = value
            return
        if container not in HOOK_CONTAINERS:
            self._document.setdefault(container, {})[name] = value
            return
        groups = self._document.setdefault("hooks", {}).setdefault(
            HOOK_CONTAINERS[container], []
        )
        held = self.entries(container).get(name)
        if held is None:
            groups.append(value)
        else:
            groups[groups.index(held)] = value

    def drop(self, container: str, name: str) -> None:
        if container == TOP_LEVEL:
            del self._document[name]
            return
        if container not in HOOK_CONTAINERS:
            del self._document[container][name]
            return
        event = HOOK_CONTAINERS[container]
        hooks = self._document["hooks"]
        hooks[event].remove(self.entries(container)[name])
        if not hooks[event]:
            del hooks[event]
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
        if container == TOP_LEVEL:
            return dict(self._document.unwrap())
        table = self._document.get(container)
        return {} if table is None else dict(table.unwrap())

    def put(self, container: str, name: str, value: Any) -> None:
        if container == TOP_LEVEL:
            self._document[name] = value
            return
        if container not in self._document:
            self._document.add(container, tomlkit.table(is_super_table=True))
        self._document[container][name] = value  # pyright: ignore[reportIndexIssue]

    def drop(self, container: str, name: str) -> None:
        if container == TOP_LEVEL:
            del self._document[name]
            return
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
        raise SystemExit(
            f"error: cannot parse {path}: {exc}. Nothing was written."
        ) from exc


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


def load_settings(name: str) -> dict[str, Any]:
    """The settings object ``library/settings/<name>.json`` from the highest layer holding it."""
    hit = find_in_layers("library", "settings", f"{name}.json")
    if hit is None:
        available = (
            ", ".join(available_names("library", "settings", suffix=".json")) or "none"
        )
        raise SystemExit(
            f"error: unknown settings file {name!r}. Available: {available}.\n"
            f"Searched these library layers:\n{searched_layers()}"
        )
    _layer, path = hit
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"error: cannot parse {path}: {exc}.") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"error: {path} must hold one JSON object.")
    for key, owner in SETTINGS_OWNED_ELSEWHERE.items():
        if key in data:
            raise SystemExit(
                f"error: {path} sets `{key}`, which farrier writes from {owner}."
            )
    return data


def settings_entries(harness: str, table: Selection) -> list[Entry]:
    """One top-level entry per key of the settings files *table* names."""
    if not table.settings:
        return []
    rel = SETTINGS_FILES.get(harness)
    if rel is None:
        raise SystemExit(
            f"error: [user_library.{harness}] names settings, and farrier merges "
            f"them only for {', '.join(SETTINGS_FILES)}."
        )
    owners: dict[str, str] = {}
    entries: list[Entry] = []
    for name in table.settings:
        for key, value in load_settings(name).items():
            if key in owners:
                raise SystemExit(
                    f"error: settings files {owners[key]!r} and {name!r} both set `{key}`."
                )
            owners[key] = name
            entries.append(Entry(rel, TOP_LEVEL, key, value))
    return entries


def user_entries(home: HomeConfig) -> list[Entry]:
    """Every merged entry the user_library tables intend, in a stable order."""
    entries: list[Entry] = []
    for harness, table in user_library_tables(home).items():
        entries.extend(settings_entries(harness, table))
        names = tool_server_names(table)
        if not names:
            continue
        dialect = MCP_DIALECTS[harness]
        for name in sorted(names):
            entries.append(
                Entry(
                    dialect.rel,
                    dialect.container,
                    name,
                    dialect.spell(load_tool_server(name)),
                )
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
        raise SystemExit(
            f"error: cannot parse {path}: {exc}. Nothing was written."
        ) from exc


def write_ledger(home: Path, ledger: Ledger) -> None:
    """Record *ledger*, leaving a home that never held an entry without the file."""
    if ledger or (home / LEDGER).exists():
        replace_file(home / LEDGER, json.dumps(ledger, indent=2, sort_keys=True) + "\n")


def ledger_with(ledger: Ledger, owned: list[Entry]) -> Ledger:
    """*ledger* with every entry of *owned* added."""
    merged = {
        rel: {key: list(names) for key, names in kept.items()}
        for rel, kept in ledger.items()
    }
    for entry in owned:
        names = merged.setdefault(entry.rel, {}).setdefault(entry.container, [])
        if entry.name not in names:
            names.append(entry.name)
    return merged


def significant(value: Any) -> Any:
    """*value* without its empty keys, because a harness may write or omit an empty list."""
    if not isinstance(value, Mapping):
        return value
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
            beside = (
                read_entry_file(home / overridden)
                .entries(entry.container)
                .get(entry.name)
            )
            if beside is not None and significant(beside) != significant(entry.value):
                drift.append(
                    EntryDrift("foreign", overridden, entry.container, entry.name)
                )
        held = (
            read_entry_file(home / entry.rel).entries(entry.container).get(entry.name)
        )
        if held is None:
            kind = "missing"
        elif significant(held) == significant(entry.value):
            continue
        else:
            kind = (
                "changed"
                if in_ledger(ledger, entry.rel, entry.container, entry.name)
                else "foreign"
            )
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
    print(
        f"Run `{regenerate}` to bring these in line. A foreign entry is yours to remove first."
    )
    return 1


def refuse_foreign_entries(home: Path, intended: list[Entry]) -> None:
    """Stop before any write when a value farrier did not install holds an entry it intends."""
    foreign = [
        item
        for item in entry_drift(home, intended, read_ledger(home))
        if item.kind == "foreign"
    ]
    if not foreign:
        return
    listing = "\n".join(
        f"  {item.rel} {item.container}.{item.name}" for item in foreign
    )
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
                document.put(
                    item.container,
                    item.name,
                    by_key[(rel, item.container, item.name)].value,
                )
        replace_file(home / rel, document.text())
    write_ledger(home, ledger_with({}, owned))
    return len(drift)
