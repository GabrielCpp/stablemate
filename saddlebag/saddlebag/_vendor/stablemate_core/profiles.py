"""Which profile a run resolves from, and the model, effort, timeout scale, delegates, harness env and default CLI it yields."""

from __future__ import annotations

from dataclasses import dataclass

from . import config
from .config import ConfigError
from .schema import BUILTIN_DEFAULT_CLI as BUILTIN_DEFAULT_CLI
from .schema import HomeConfig, PowerTier, Profile


@dataclass(frozen=True)
class PowerMapping:
    model: str | None = None
    effort: str | None = None
    timeout_scale: float | None = None


class UnknownProfileError(LookupError):
    """``--profile <name>`` named a profile the config does not define."""


def _home(home: HomeConfig | None) -> HomeConfig:
    return home if home is not None else config.load_home_config()


def profile_names(home: HomeConfig | None = None) -> list[str]:
    """The names `[profiles.<name>]` defines, sorted."""
    return sorted(_home(home).profiles)


def select_profile(home: HomeConfig | None, name: str) -> Profile | None:
    """The profile called ``name``; ``None`` for an empty name, an unknown one raises."""
    if not name:
        return None
    profiles = _home(home).profiles
    profile = profiles.get(name)
    if profile is None:
        known = ", ".join(sorted(profiles)) if profiles else "none defined"
        raise UnknownProfileError(
            f"unknown profile {name!r} in {config.config_path()} (known: {known})"
        )
    if profile.cli_name() is None:
        raise ConfigError(
            f"[profiles.{name}] has no cli field — every profile must declare the CLI "
            f"it runs under. Add `cli = \"<name>\"` to {name!r}."
        )
    return profile


def auto_select_profile(home: HomeConfig | None, active_cli: str) -> Profile | None:
    """Find the profile whose ``cli`` field matches ``active_cli``."""
    if not active_cli:
        return None
    cli = active_cli.strip().lower()
    for profile in _home(home).profiles.values():
        if profile.cli_name() == cli:
            return profile
    return None


def select_active_profile(
    home: HomeConfig | None,
    *,
    name: str = "",
    active_cli: str = "",
) -> Profile | None:
    """The profile a run resolves models from: explicit name, else auto-pick by CLI, else none."""
    if name:
        return select_profile(home, name)
    if active_cli:
        return auto_select_profile(home, active_cli)
    return None


def profile_backends(profile: Profile) -> list[str]:
    """The CLI name a profile declares, lowercased, or empty."""
    cli = profile.cli_name()
    return [cli] if cli else []


def profile_has_backend(profile: Profile | None, backend: str) -> bool:
    """Whether a profile is for ``backend``."""
    return profile is not None and profile.cli_name() == backend


def _mapping(tier: PowerTier | None) -> PowerMapping:
    if tier is None:
        return PowerMapping()
    return PowerMapping(
        model=tier.model or None,
        effort=tier.effort or None,
        timeout_scale=tier.timeout_scale,
    )


def _runs(profile: Profile | None, backend: str) -> bool:
    return profile is not None and profile.cli_name() in (None, backend)


def resolve_power(power: str | None, backend: str, profile: Profile | None = None) -> PowerMapping:
    """The model/effort/timeout_scale for ``power`` on the ``backend`` the ``profile`` runs; none without a profile."""
    if not power or profile is None or not _runs(profile, backend):
        return PowerMapping()
    return _mapping(profile.powers.get(power))


def resolve_backend_default(backend: str, profile: Profile | None = None) -> PowerMapping:
    """The profile's fallback model/effort from ``profile.default``."""
    if profile is None or not _runs(profile, backend):
        return PowerMapping()
    return _mapping(profile.default)


def resolve_delegates(backend: str, profile: Profile | None = None) -> dict[str, PowerMapping]:
    """The model/effort per subagent role from ``profile.delegates``, for roles that name a model."""
    if profile is None or not _runs(profile, backend):
        return {}
    mappings = {role: _mapping(entry) for role, entry in profile.delegates.items() if role}
    return {role: mapping for role, mapping in mappings.items() if mapping.model}


def resolve_harness_env(backend: str, home: HomeConfig | None = None) -> dict[str, str]:
    """Extra environment variables to hand the ``<backend>`` CLI, from ``[cli.<backend>]``."""
    entry = _home(home).cli.get(backend)
    return {} if entry is None else {key: value for key, value in entry.env.items() if key}


def resolve_default_cli(home: HomeConfig | None = None) -> str:
    """The agent CLI to drive when nothing on the invocation names one."""
    return _home(home).default_cli
