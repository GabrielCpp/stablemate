"""The ``[groom.attend]`` and ``[groom.dispatch]`` tables of the home config, resolved with where each value came from."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from workhorse._vendor.stablemate_core.config import load_home_config, write_config_section
from workhorse._vendor.stablemate_core.schema import DispatchParam, HomeConfig

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


def resolve_attend_settings(home: HomeConfig | None = None) -> AttendSettings:
    """The effective attendant settings: the config wins, the environment is the fallback."""
    document = home if home is not None else load_home_config()
    section = document.groom.attend if document.groom is not None else None
    given = section.model_fields_set if section is not None else set()
    sources: dict[str, str] = {}

    env_mode = os.environ.get(ATTEND_MODE_ENV)
    if section is not None and "mode" in given:
        mode = _attend_mode(section.mode, ATTEND_OFF)
        sources["mode"] = CONFIG_SOURCE
    elif env_mode is not None:
        mode = _attend_mode(env_mode, ATTEND_OFF)
        sources["mode"] = ENV_SOURCE
    else:
        mode = ATTEND_OFF
        sources["mode"] = DEFAULT_SOURCE

    if section is not None and "last_mode" in given:
        last_mode = _attend_mode(section.last_mode, ATTEND_HEADLESS)
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
    raw_cli = section.cli if section is not None and "cli" in given else ""
    if raw_cli.strip():
        cli = raw_cli.strip()
        sources["cli"] = CONFIG_SOURCE
    elif env_cli is not None and env_cli.strip():
        cli = env_cli.strip()
        sources["cli"] = ENV_SOURCE
    else:
        cli = BUILTIN_ATTEND_CLI
        sources["cli"] = DEFAULT_SOURCE

    if section is not None and "deny" in given:
        deny = tuple(item.strip().lower() for item in section.deny if item.strip())
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


def _dispatch_params(raw: list[DispatchParam]) -> tuple[DispatchParamSettings, ...]:
    """A queue's ``params`` array; an entry without a name is skipped, the rest are kept."""
    params: list[DispatchParamSettings] = []
    for entry in raw:
        name = entry.name.strip()
        if not name:
            continue
        params.append(
            DispatchParamSettings(
                name=name,
                label=entry.label or name,
                type=entry.type.strip().lower() or "string",
                required=entry.required,
                default=entry.default,
                options=tuple(entry.options),
                template=entry.template,
            )
        )
    return tuple(params)


def resolve_dispatch_queues(home: HomeConfig | None = None) -> dict[str, DispatchQueueSettings]:
    """Every configured ``[groom.dispatch.<name>]`` queue, keyed by name."""
    document = home if home is not None else load_home_config()
    section = document.groom.dispatch if document.groom is not None else {}
    queues: dict[str, DispatchQueueSettings] = {}
    for name, raw in section.items():
        command = raw.command.strip()
        if not command:
            continue
        queues[name] = DispatchQueueSettings(
            name=name,
            command=command,
            concurrency=max(1, raw.concurrency),
            params=_dispatch_params(raw.params),
        )
    return queues
