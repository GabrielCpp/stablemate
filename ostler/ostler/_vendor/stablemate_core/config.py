"""Home-config persistence, shared by every stablemate tool."""

from __future__ import annotations

import logging
import math
import os
import shutil
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any

import tomli_w
from platformdirs import user_config_dir

logger = logging.getLogger(__name__)

CONFIG_PATH_ENV = "STABLEMATE_CONFIG"
LEGACY_CONFIG_PATH_ENV = "WORKHORSE_CONFIG"

_LEGACY_APPS = ("workhorse", "farrier")

CONFIG_VERSION = 2

CONFIG_VERSION_KEY = "config_version"

DEFAULT_CLI_KEY = "default_cli"
BUILTIN_DEFAULT_CLI = "claude"

PROFILES_KEY = "profiles"

PROFILE_CLI_KEY = "cli"

PROFILE_POWERS_KEY = "powers"

PROFILE_DEFAULT_KEY = "default"

CLI_KEY = "cli"

CLI_ENV_KEY = "env"

BACKEND_FALLBACK_KEY = "default"

_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


class ConfigVersionError(RuntimeError):
    """A config this build must not touch — it was written by a newer stablemate-core."""


class ConfigError(ValueError):
    """The config is shaped wrong for the schema it declares."""


def _core_version() -> str:
    try:
        return metadata.version("stablemate-core")
    except metadata.PackageNotFoundError:  # pragma: no cover - source checkout
        return "unknown"


def _default_config_path() -> Path:
    """~/Library/Application Support/stablemate on macOS, %APPDATA%\\stablemate on
    Windows, ~/.config/stablemate on Linux."""
    return Path(user_config_dir("stablemate")) / "config.toml"


def legacy_config_paths() -> list[Path]:
    return [Path(user_config_dir(app)) / "config.toml" for app in _LEGACY_APPS]


@dataclass(frozen=True)
class PowerMapping:
    model: str | None = None
    effort: str | None = None
    timeout_scale: float | None = None


def config_path() -> Path:
    raw = os.environ.get(CONFIG_PATH_ENV) or os.environ.get(LEGACY_CONFIG_PATH_ENV)
    if raw:
        return Path(raw).expanduser()
    return _default_config_path()


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _path_is_explicit() -> bool:
    return bool(
        os.environ.get(CONFIG_PATH_ENV) or os.environ.get(LEGACY_CONFIG_PATH_ENV)
    )


def config_version_of(cfg: dict[str, Any]) -> int:
    """The schema version a loaded config declares."""
    raw = cfg.get(CONFIG_VERSION_KEY)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        return 1
    return raw


def _too_new_message(found: int) -> str:
    return (
        f"{config_path()} uses config schema v{found}, written by a newer "
        f"stablemate-core; this is stablemate-core {_core_version()}, which supports up to "
        f"v{CONFIG_VERSION}. Refusing to write it — doing so would drop the keys this "
        f"build does not understand. Upgrade this tool (its stablemate-core), or set "
        f"${CONFIG_PATH_ENV} to a different file."
    )


_warned_too_new: set[int] = set()


def _warn_if_too_new(cfg: dict[str, Any]) -> None:
    found = config_version_of(cfg)
    if found <= CONFIG_VERSION or found in _warned_too_new:
        return
    _warned_too_new.add(found)
    logger.warning(
        "%s uses config schema v%d; this build understands v%d. Reading it anyway, but "
        "keys it does not share may be missing or misread — upgrade this tool.",
        config_path(),
        found,
        CONFIG_VERSION,
    )


def check_config_version(cfg: dict[str, Any] | None = None) -> int:
    """Raise :class:`ConfigVersionError` if the config is newer than this build."""
    data = cfg if cfg is not None else load_config()
    found = config_version_of(data)
    if found > CONFIG_VERSION:
        raise ConfigVersionError(_too_new_message(found))
    return found


def load_config() -> dict[str, Any]:
    """The effective config: the unified file, else the merged legacy per-tool files."""
    path = config_path()
    if path.is_file():
        data = _read(path)
        found = config_version_of(data)
        if found < CONFIG_VERSION:
            try:
                data = _walk_migrations(data, found)
            except ConfigVersionError:
                pass
        _warn_if_too_new(data)
        return data
    if _path_is_explicit():
        return {}

    merged: dict[str, Any] = {}
    for legacy in legacy_config_paths():
        merged.update(_read(legacy))
    found = config_version_of(merged)
    if found < CONFIG_VERSION:
        try:
            merged = _walk_migrations(merged, found)
        except ConfigVersionError:
            pass
    _warn_if_too_new(merged)
    return merged


def write_config_key(key: str, value: str) -> None:
    """Persist a single top-level string key, preserving every other key."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = _read(path)
    cfg = load_config()

    found = config_version_of(raw)
    if found > CONFIG_VERSION:
        raise ConfigVersionError(_too_new_message(found))
    if found < CONFIG_VERSION:
        cfg = _migrate_forward(cfg, found, path)

    cfg[key] = value
    cfg[CONFIG_VERSION_KEY] = CONFIG_VERSION
    with path.open("wb") as handle:
        tomli_w.dump(cfg, handle)


def _migrate_forward(cfg: dict[str, Any], from_version: int, path: Path) -> dict[str, Any]:
    """Carry a config from ``from_version`` up to :data:`CONFIG_VERSION`, one step at a time."""
    if path.is_file():
        backup = path.with_name(f"{path.name}.v{from_version}.bak")
        try:
            shutil.copy2(path, backup)
        except OSError as exc:
            raise ConfigVersionError(
                f"cannot back up {path} to {backup} before migrating it to schema "
                f"v{CONFIG_VERSION}: {exc}"
            ) from exc
        logger.warning(
            "migrating %s from config schema v%d to v%d; the previous file is saved at "
            "%s. Tools still on an older stablemate-core will refuse to write it.",
            path,
            from_version,
            CONFIG_VERSION,
            backup,
        )

    return _walk_migrations(cfg, from_version)


def _walk_migrations(cfg: dict[str, Any], from_version: int) -> dict[str, Any]:
    """Apply the migrations from ``from_version`` up to :data:`CONFIG_VERSION`, no I/O."""
    data = dict(cfg)
    for version in range(from_version, CONFIG_VERSION):
        step = _MIGRATIONS.get(version)
        if step is None:
            raise ConfigVersionError(
                f"no migration registered from config schema v{version} to "
                f"v{version + 1}; cannot carry forward safely."
            )
        data = step(data)
    return data


def _migrate_v1_to_v2(cfg: dict[str, Any]) -> dict[str, Any]:
    """Carry a v1 config to v2."""
    data = dict(cfg)
    profiles = data.setdefault(PROFILES_KEY, {})
    if not isinstance(profiles, dict):
        profiles = {}
        data[PROFILES_KEY] = profiles

    power = data.pop("power", None)
    if isinstance(power, dict):
        for tier, by_backend in power.items():
            if not isinstance(by_backend, dict):
                continue
            for backend, mapping in by_backend.items():
                if not isinstance(mapping, dict):
                    continue
                profile = _ensure_cli_profile(profiles, str(backend))
                powers = profile.setdefault(PROFILE_POWERS_KEY, {})
                if not isinstance(powers, dict):
                    powers = {}
                    profile[PROFILE_POWERS_KEY] = powers
                powers.setdefault(tier, mapping)

    default_table = data.pop("default", None)
    if isinstance(default_table, dict):
        for backend, mapping in default_table.items():
            if isinstance(mapping, dict):
                entry = mapping
            elif isinstance(mapping, str) and mapping.strip():
                entry = {"model": mapping.strip()}
            else:
                continue
            profile = _ensure_cli_profile(profiles, str(backend))
            profile.setdefault(PROFILE_DEFAULT_KEY, entry)

    harness = data.pop("harness", None)
    if isinstance(harness, dict):
        data[CLI_KEY] = harness

    for name, profile in list(profiles.items()):
        if not isinstance(profile, dict):
            continue
        if PROFILE_CLI_KEY not in profile:
            legacy = profile.pop("default_cli", None)
            if isinstance(legacy, str) and legacy.strip():
                profile[PROFILE_CLI_KEY] = legacy.strip().lower()
            else:
                raise ConfigVersionError(
                    f"[profiles.{name}] has no cli field and no legacy default_cli — "
                    f"cannot migrate to schema v{CONFIG_VERSION}. Add "
                    f'cli = "<one of the configured CLIs>" to {name!r}.'
                )
        else:
            profile.pop("default_cli", None)

        nested_power = profile.pop("power", None)
        if isinstance(nested_power, dict):
            powers = profile.setdefault(PROFILE_POWERS_KEY, {})
            if not isinstance(powers, dict):
                powers = {}
                profile[PROFILE_POWERS_KEY] = powers
            for tier, by_backend in nested_power.items():
                if not isinstance(by_backend, dict):
                    continue
                for backend, mapping in by_backend.items():
                    if not isinstance(mapping, dict):
                        continue
                    powers.setdefault(tier, mapping)

        nested_default = profile.pop("default", None)
        if isinstance(nested_default, dict):
            cli = profile_cli(profile)
            if cli and any(
                key not in {"model", "effort", "timeout_scale"} for key in nested_default
            ):
                entry = nested_default.get(cli)
                if isinstance(entry, dict):
                    profile.setdefault(PROFILE_DEFAULT_KEY, entry)
            else:
                profile.setdefault(PROFILE_DEFAULT_KEY, nested_default)

    _reject_duplicate_cli(profiles)

    data[CONFIG_VERSION_KEY] = CONFIG_VERSION
    return data


def _ensure_cli_profile(profiles: dict[str, Any], cli: str) -> dict[str, Any]:
    """Get-or-create the profile that names ``cli`` as its CLI."""
    profile = profiles.get(cli)
    if not isinstance(profile, dict):
        profile = {PROFILE_CLI_KEY: cli}
        profiles[cli] = profile
    profile.setdefault(PROFILE_CLI_KEY, cli)
    return profile


def _reject_duplicate_cli(profiles: dict[str, Any]) -> None:
    """Reject only the auto-default conflict — two profiles claiming to be the auto-default for the same CLI."""
    seen: dict[str, str] = {}
    for name, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        cli = profile.get(PROFILE_CLI_KEY)
        if not isinstance(cli, str) or not cli.strip():
            continue
        normalized = cli.strip().lower()
        if normalized == name and normalized in seen:
            raise ConfigVersionError(
                f"[profiles.{name}] and [profiles.{seen[normalized]}] both claim to be "
                f"the auto-default for cli = {normalized!r}; a config may have at most "
                f"one CLI-named profile per CLI."
            )
        if normalized == name:
            seen[normalized] = name


_MIGRATIONS[1] = _migrate_v1_to_v2


class UnknownProfileError(LookupError):
    """``--profile <name>`` named a profile the config does not define."""


def _profiles_table(cfg: dict[str, Any]) -> dict[str, Any]:
    table = cfg.get(PROFILES_KEY)
    return table if isinstance(table, dict) else {}


def profile_names(cfg: dict[str, Any] | None = None) -> list[str]:
    """The names `[profiles.<name>]` defines, sorted."""
    data = cfg if cfg is not None else load_config()
    return sorted(name for name in _profiles_table(data) if isinstance(name, str))


def profile_cli(profile: dict[str, Any]) -> str | None:
    """The ``cli`` field a profile declares, lowercased and stripped."""
    raw = profile.get(PROFILE_CLI_KEY)
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip().lower()


def select_profile(cfg: dict[str, Any] | None, name: str) -> dict[str, Any]:
    """Narrow ``cfg`` to the named profile: the config every model resolver then reads."""
    data = cfg if cfg is not None else load_config()
    if not name:
        return {}
    profile = _profiles_table(data).get(name)
    if not isinstance(profile, dict):
        known = profile_names(data)
        listed = ", ".join(known) if known else "none defined"
        raise UnknownProfileError(
            f"unknown profile {name!r} in {config_path()} (known: {listed})"
        )
    if profile_cli(profile) is None:
        raise ConfigError(
            f"[profiles.{name}] has no cli field — every profile must declare the CLI "
            f"it runs under. Add `cli = \"<name>\"` to {name!r}."
        )
    return profile


def auto_select_profile(cfg: dict[str, Any] | None, active_cli: str) -> dict[str, Any] | None:
    """Find the profile whose ``cli`` field matches ``active_cli``."""
    if not active_cli:
        return None
    cli = active_cli.strip().lower()
    for name, profile in _profiles_table(cfg if cfg is not None else load_config()).items():
        if not isinstance(profile, dict):
            continue
        if profile_cli(profile) == cli:
            return profile
    return None


def select_active_profile(
    cfg: dict[str, Any] | None,
    *,
    name: str = "",
    active_cli: str = "",
) -> dict[str, Any]:
    """The profile a run resolves models from: explicit name, else auto-pick by CLI, else none."""
    if name:
        return select_profile(cfg, name)
    if active_cli:
        match = auto_select_profile(cfg, active_cli)
        if match is not None:
            return match
    return {}


def profile_backends(profile: dict[str, Any]) -> list[str]:
    """The CLI name a profile declares, lowercased, or empty."""
    cli = profile_cli(profile)
    return [cli] if cli else []


def profile_has_backend(profile: dict[str, Any], backend: str) -> bool:
    """Whether a profile is for ``backend``."""
    return profile_cli(profile) == backend


def _positive_finite(raw: Any) -> float | None:
    """A strictly positive, finite float, or ``None`` for anything else."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def _mapping_from_table(table: dict[str, Any]) -> PowerMapping:
    model = table.get("model")
    effort = table.get("effort")
    return PowerMapping(
        model=model if isinstance(model, str) and model else None,
        effort=effort if isinstance(effort, str) and effort else None,
        timeout_scale=_positive_finite(table.get("timeout_scale")),
    )


def resolve_power(power: str | None, backend: str, cfg: dict[str, Any] | None = None) -> PowerMapping:
    """The model/effort/timeout_scale for ``power`` on the ``backend`` the ``cfg`` runs."""
    if not power:
        return PowerMapping()
    data = cfg if cfg is not None else load_config()
    if profile_cli(data) is not None and profile_cli(data) != backend:
        return PowerMapping()
    powers = data.get(PROFILE_POWERS_KEY)
    if not isinstance(powers, dict):
        return PowerMapping()
    tier_table = powers.get(power)
    if not isinstance(tier_table, dict):
        return PowerMapping()
    return _mapping_from_table(tier_table)


def resolve_backend_default(backend: str, cfg: dict[str, Any] | None = None) -> PowerMapping:
    """The profile's fallback model/effort from ``profile.default``."""
    data = cfg if cfg is not None else load_config()
    if profile_cli(data) is not None and profile_cli(data) != backend:
        return PowerMapping()
    default_table = data.get(PROFILE_DEFAULT_KEY)
    if not isinstance(default_table, dict):
        return PowerMapping()
    return _mapping_from_table(default_table)


def resolve_harness_env(backend: str, cfg: dict[str, Any] | None = None) -> dict[str, str]:
    """Extra environment variables to hand the ``<backend>`` CLI, from ``[cli.<backend>]``."""
    data = cfg if cfg is not None else load_config()
    cli_table = data.get(CLI_KEY)
    if not isinstance(cli_table, dict):
        return {}
    backend_table = cli_table.get(backend)
    if not isinstance(backend_table, dict):
        return {}
    env_table = backend_table.get(CLI_ENV_KEY)
    if not isinstance(env_table, dict):
        return {}
    return {
        key: value
        for key, value in env_table.items()
        if isinstance(key, str) and key and isinstance(value, str)
    }


def resolve_default_cli(cfg: dict[str, Any] | None = None) -> str:
    """The agent CLI to drive when nothing on the invocation names one."""
    value = get_config_value(DEFAULT_CLI_KEY, cfg)
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    return BUILTIN_DEFAULT_CLI


def write_default_cli(name: str) -> None:
    """Persist ``default_cli`` (the agent CLI a run drives when nothing names one)."""
    write_config_key(DEFAULT_CLI_KEY, name.strip().lower())


def get_config_value(name: str, cfg: dict[str, Any] | None = None) -> Any:
    data = cfg if cfg is not None else load_config()
    value: Any = data
    for part in name.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


read_config = load_config


def write_library_dir(path: Path) -> None:
    """Persist ``library_dir`` (the overlay library root)."""
    write_config_key("library_dir", str(path))


def write_stablemate_dir(path: Path) -> None:
    """Persist ``stablemate_dir`` (a stablemate checkout)."""
    write_config_key("stablemate_dir", str(path))


def write_base_dir(path: Path) -> None:
    """Persist ``base_dir`` (the base library content path)."""
    write_config_key("base_dir", str(path))


def write_worktree_dir(path: Path) -> None:
    """Persist ``worktree_dir`` (the parent directory new git worktrees are cut into)."""
    write_config_key("worktree_dir", str(path))


def resolve_stablemate_dir() -> Path | None:
    """The configured stablemate checkout path, or None if unset."""
    configured = get_config_value("stablemate_dir")
    if isinstance(configured, str) and configured:
        return Path(configured).expanduser().resolve()
    return None


def resolve_worktree_dir() -> Path | None:
    """The directory new git worktrees are cut into, or None if unset."""
    configured = get_config_value("worktree_dir")
    if isinstance(configured, str) and configured:
        return Path(configured).expanduser().resolve()
    return None



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


def write_config_section(name: str, values: dict[str, Any]) -> None:
    """Persist one dotted table (``groom.attend``), preserving every other key."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = _read(path)
    cfg = load_config()

    found = config_version_of(raw)
    if found > CONFIG_VERSION:
        raise ConfigVersionError(_too_new_message(found))
    if found < CONFIG_VERSION:
        cfg = _migrate_forward(cfg, found, path)

    parts = name.split(".")
    table = cfg
    for part in parts[:-1]:
        nested = table.get(part)
        if not isinstance(nested, dict):
            nested = {}
            table[part] = nested
        table = nested
    table[parts[-1]] = dict(values)

    cfg[CONFIG_VERSION_KEY] = CONFIG_VERSION
    with path.open("wb") as handle:
        tomli_w.dump(cfg, handle)


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
