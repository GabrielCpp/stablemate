"""Which profile a run resolves from, and the model, effort, timeout scale, harness env and default CLI it yields."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from . import config
from .config import (
    CLI_KEY,
    PROFILE_DEFAULT_KEY,
    PROFILE_POWERS_KEY,
    PROFILES_KEY,
    ConfigError,
    profile_cli,
)

DEFAULT_CLI_KEY = "default_cli"
BUILTIN_DEFAULT_CLI = "claude"

CLI_ENV_KEY = "env"


@dataclass(frozen=True)
class PowerMapping:
    model: str | None = None
    effort: str | None = None
    timeout_scale: float | None = None


class UnknownProfileError(LookupError):
    """``--profile <name>`` named a profile the config does not define."""


def _profiles_table(cfg: dict[str, Any]) -> dict[str, Any]:
    table = cfg.get(PROFILES_KEY)
    return table if isinstance(table, dict) else {}


def profile_names(cfg: dict[str, Any] | None = None) -> list[str]:
    """The names `[profiles.<name>]` defines, sorted."""
    data = cfg if cfg is not None else config.load_config()
    return sorted(name for name in _profiles_table(data) if isinstance(name, str))


def select_profile(cfg: dict[str, Any] | None, name: str) -> dict[str, Any]:
    """Narrow ``cfg`` to the named profile: the config every model resolver then reads."""
    data = cfg if cfg is not None else config.load_config()
    if not name:
        return {}
    profile = _profiles_table(data).get(name)
    if not isinstance(profile, dict):
        known = profile_names(data)
        listed = ", ".join(known) if known else "none defined"
        raise UnknownProfileError(
            f"unknown profile {name!r} in {config.config_path()} (known: {listed})"
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
    for name, profile in _profiles_table(cfg if cfg is not None else config.load_config()).items():
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
    data = cfg if cfg is not None else config.load_config()
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
    data = cfg if cfg is not None else config.load_config()
    if profile_cli(data) is not None and profile_cli(data) != backend:
        return PowerMapping()
    default_table = data.get(PROFILE_DEFAULT_KEY)
    if not isinstance(default_table, dict):
        return PowerMapping()
    return _mapping_from_table(default_table)


def resolve_harness_env(backend: str, cfg: dict[str, Any] | None = None) -> dict[str, str]:
    """Extra environment variables to hand the ``<backend>`` CLI, from ``[cli.<backend>]``."""
    data = cfg if cfg is not None else config.load_config()
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
    value = config.get_config_value(DEFAULT_CLI_KEY, cfg)
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    return BUILTIN_DEFAULT_CLI


def write_default_cli(name: str) -> None:
    """Persist ``default_cli`` (the agent CLI a run drives when nothing names one)."""
    config.write_config_key(DEFAULT_CLI_KEY, name.strip().lower())
