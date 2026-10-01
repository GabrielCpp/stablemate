"""The ``[groom.attend]`` and ``[groom.dispatch]`` tables of the home config, resolved with where each value came from."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from workhorse._vendor.stablemate_core.config import get_config_value, load_config, write_config_section

ATTEND_SECTION = "groom.attend"

ATTEND_OFF, ATTEND_SESSION, ATTEND_HEADLESS = "off", "session", "headless"
_ATTEND_MODES = (ATTEND_OFF, ATTEND_SESSION, ATTEND_HEADLESS)

ATTEND_MODE_ENV = "GROOM_ATTEND"
ATTEND_CLI_ENV = "GROOM_ATTEND_CLI"
ATTEND_DENY_ENV = "GROOM_ATTEND_DENY"

BUILTIN_ATTEND_CLI = "claude"

CONFIG_SOURCE, ENV_SOURCE, DEFAULT_SOURCE = "config", "environment", "default"


@dataclass(frozen=True)
class AttendSettings:
    """The effective ``[groom.attend]`` settings, and where each one was read from."""

    mode: str = ATTEND_OFF
    last_mode: str = ATTEND_HEADLESS
    cli: str = BUILTIN_ATTEND_CLI
    deny: tuple[str, ...] = ()
    sources: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "last_mode": self.last_mode,
            "cli": self.cli,
            "deny": list(self.deny),
            "sources": dict(self.sources),
        }


def _attend_mode(value: Any, fallback: str) -> str:
    text = str(value).strip().lower() if value is not None else ""
    return text if text in _ATTEND_MODES else fallback


def resolve_attend_settings(cfg: dict[str, Any] | None = None) -> AttendSettings:
    """The effective attendant settings: the config wins, the environment is the fallback."""
    data = cfg if cfg is not None else load_config()
    table = get_config_value(ATTEND_SECTION, data)
    section: dict[str, Any] = table if isinstance(table, dict) else {}
    sources: dict[str, str] = {}

    env_mode = os.environ.get(ATTEND_MODE_ENV)
    if "mode" in section:
        mode = _attend_mode(section.get("mode"), ATTEND_OFF)
        sources["mode"] = CONFIG_SOURCE
    elif env_mode is not None:
        mode = _attend_mode(env_mode, ATTEND_OFF)
        sources["mode"] = ENV_SOURCE
    else:
        mode = ATTEND_OFF
        sources["mode"] = DEFAULT_SOURCE

    if "last_mode" in section:
        last_mode = _attend_mode(section.get("last_mode"), ATTEND_HEADLESS)
        sources["last_mode"] = CONFIG_SOURCE
    elif mode != ATTEND_OFF:
        last_mode = mode
        sources["last_mode"] = sources["mode"]
    else:
        last_mode = ATTEND_HEADLESS
        sources["last_mode"] = DEFAULT_SOURCE
    if last_mode == ATTEND_OFF:
        last_mode = ATTEND_HEADLESS

    env_cli = os.environ.get(ATTEND_CLI_ENV)
    raw_cli = section.get("cli")
    if isinstance(raw_cli, str) and raw_cli.strip():
        cli = raw_cli.strip()
        sources["cli"] = CONFIG_SOURCE
    elif env_cli is not None and env_cli.strip():
        cli = env_cli.strip()
        sources["cli"] = ENV_SOURCE
    else:
        cli = BUILTIN_ATTEND_CLI
        sources["cli"] = DEFAULT_SOURCE

    raw_deny = section.get("deny")
    if isinstance(raw_deny, list):
        deny = tuple(str(item).strip().lower() for item in raw_deny if str(item).strip())
        sources["deny"] = CONFIG_SOURCE
    elif os.environ.get(ATTEND_DENY_ENV):
        raw_env = os.environ.get(ATTEND_DENY_ENV, "")
        deny = tuple(part.strip().lower() for part in raw_env.split(",") if part.strip())
        sources["deny"] = ENV_SOURCE
    else:
        deny = ()
        sources["deny"] = DEFAULT_SOURCE

    return AttendSettings(
        mode=mode, last_mode=last_mode, cli=cli, deny=deny, sources=sources
    )


def write_attend_settings(settings: AttendSettings) -> None:
    """Persist the whole ``[groom.attend]`` table from a resolved settings object."""
    write_config_section(
        ATTEND_SECTION,
        {
            "mode": settings.mode,
            "last_mode": settings.last_mode,
            "cli": settings.cli,
            "deny": list(settings.deny),
        },
    )



DISPATCH_SECTION = "groom.dispatch"

DEFAULT_DISPATCH_CONCURRENCY = 1


@dataclass(frozen=True)
class DispatchParamSettings:
    """One field of a queue's enqueue-time form, declared as ``[[groom.dispatch.<name>.params]]``."""

    name: str
    label: str
    type: str = "string"
    required: bool = False
    default: str = ""
    options: tuple[str, ...] = ()
    template: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "type": self.type,
            "required": self.required,
            "default": self.default,
            "options": list(self.options),
        }


@dataclass(frozen=True)
class DispatchQueueSettings:
    """One configured queue: its name, the workflow command it launches, how many of its items may run at once, and the enqueue-time fields its dashboard form offers."""

    name: str
    command: str
    concurrency: int = DEFAULT_DISPATCH_CONCURRENCY
    params: tuple[DispatchParamSettings, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "command": self.command,
            "concurrency": self.concurrency,
            "params": [param.as_dict() for param in self.params],
        }


def _parse_dispatch_params(raw: Any) -> tuple[DispatchParamSettings, ...]:
    """The ``params`` array of a queue's table, tolerating a malformed entry the same way the queue itself tolerates a malformed table: skip it, keep the rest."""
    if not isinstance(raw, list):
        return ()
    params: list[DispatchParamSettings] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        options_raw = entry.get("options")
        options = (
            tuple(str(opt) for opt in options_raw) if isinstance(options_raw, list) else ()
        )
        params.append(
            DispatchParamSettings(
                name=name,
                label=str(entry.get("label") or name),
                type=str(entry.get("type") or "string").strip().lower() or "string",
                required=bool(entry.get("required", False)),
                default=str(entry.get("default") or ""),
                options=options,
                template=str(entry.get("template") or ""),
            )
        )
    return tuple(params)


def resolve_dispatch_queues(cfg: dict[str, Any] | None = None) -> dict[str, DispatchQueueSettings]:
    """Every configured ``[groom.dispatch.<name>]`` queue, keyed by name."""
    data = cfg if cfg is not None else load_config()
    table = get_config_value(DISPATCH_SECTION, data)
    section: dict[str, Any] = table if isinstance(table, dict) else {}
    queues: dict[str, DispatchQueueSettings] = {}
    for name, raw in section.items():
        if not isinstance(raw, dict):
            continue
        command = str(raw.get("command") or "").strip()
        if not command:
            continue
        try:
            concurrency = int(raw.get("concurrency", DEFAULT_DISPATCH_CONCURRENCY))
        except (TypeError, ValueError):
            concurrency = DEFAULT_DISPATCH_CONCURRENCY
        queues[name] = DispatchQueueSettings(
            name=name,
            command=command,
            concurrency=max(1, concurrency),
            params=_parse_dispatch_params(raw.get("params")),
        )
    return queues
