"""Which agent CLI and model profile a run is on, and the models a power resolves to under it."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from workhorse import otel
from workhorse._vendor.stablemate_core.config import (
    ConfigError,
    UnknownProfileError,
    config_path,
    load_config,
    profile_backends,
    profile_has_backend,
    resolve_backend_default,
    resolve_default_cli,
    resolve_power,
    select_active_profile,
    select_profile,
)
from workhorse.records import parse_run_record
from workhorse.runner.backends.registry import backend_names, get_backend

if TYPE_CHECKING:
    from workhorse.artifacts import ArtifactWriter
    from workhorse.runner.backends import AgentBackend
    from workhorse.runner.ladder import AgentRunner


class ProfileError(Exception):
    """A profile or CLI choice a run cannot start on."""


_BACKEND_FLAGS = ("--cli", "--profile")

_warned_missing_profile: set[str] = set()


def _profile_config(profile: str) -> dict[str, Any] | None:
    """The config the resolvers below read: narrowed to ``profile``, or the whole file."""
    if not profile:
        return None
    try:
        return select_profile(load_config(), profile)
    except UnknownProfileError as exc:
        if profile not in _warned_missing_profile:
            _warned_missing_profile.add(profile)
            print(f"[workhorse] WARNING: {exc}; resolving no models from it", flush=True)
        return {}


def resolved_profile(profile: str) -> dict[str, Any]:
    """What ``profile`` holds right now, for the record rather than for a resolution."""
    return _profile_config(profile) or {}


@dataclass
class ProfileSelection:
    """Which named model set the run is on *now* — one box every frame shares."""

    name: str = ""


def switch_profile(runner: AgentRunner | None, name: str) -> dict[str, object]:
    """Move a live run onto the ``name`` model set, and say what happened."""
    if runner is None:
        return {"ok": False, "error": "this run drives no agent, so it resolves no models"}
    try:
        tables = select_profile(load_config(), name)
    except UnknownProfileError as exc:
        return {"ok": False, "error": str(exc)}
    backend = runner.backend.name
    if not profile_has_backend(tables, backend):
        return {
            "ok": False,
            "error": f"profile {name!r} declares cli = {tables.get('cli')!r} which does "
            f"not match the CLI backend {backend!r} this run is driving. Switch-cli "
            f"first, or pick a profile whose cli matches the new backend.",
        }
    was, runner.profile.name = runner.profile.name, name
    _warned_missing_profile.discard(name)
    otel.run_attribute("workhorse.profile", name)
    return {"ok": True, "profile": name, "was": was}


def resolve_power_settings(
    power: str | None,
    backend_name: str,
    model_override: str | None,
    profile: str = "",
) -> tuple[str | None, str | None, float]:
    """Resolve a node's abstract ``power`` into concrete backend settings."""
    cfg = _profile_config(profile)
    mapped = resolve_power(power, backend_name, cfg)
    fallback = resolve_backend_default(backend_name, cfg)
    model = mapped.model or model_override or fallback.model
    scale = mapped.timeout_scale or fallback.timeout_scale or 1.0
    return model, mapped.effort or fallback.effort, scale


def select_backend(cfg: dict[str, Any], profile_name: str, cli: str | None) -> AgentBackend:
    """The backend a named profile, or else a bare CLI, selects; a bad pick raises with its fix."""
    try:
        if profile_name:
            profile = select_profile(cfg, profile_name)
            resolved_cli = _profile_cli_or_raise(profile, profile_name)
        else:
            active_cli = _resolve_active_cli(cli, cfg)
            profile = select_active_profile(cfg, active_cli=active_cli)
            resolved_cli = active_cli
    except (UnknownProfileError, ConfigError) as exc:
        raise ProfileError(str(exc)) from exc

    os.environ["AGENT_CLI"] = resolved_cli

    try:
        backend = get_backend()
    except ValueError as e:
        raise ProfileError(str(e)) from e

    _check_profile_resolves(profile_name, profile, backend.name)
    return backend


def _resolve_active_cli(cli: str | None, cfg: dict[str, Any]) -> str:
    """Resolve the active CLI for a non-`--profile` run: --cli → $AGENT_CLI → config."""
    return (
        cli
        or os.environ.get("AGENT_CLI")
        or resolve_default_cli(cfg)
    ).strip().lower()


def _profile_cli_or_raise(profile: dict[str, Any], name: str) -> str:
    """The CLI a `--profile`-selected profile declares, stripped and lowercased."""
    cli = profile.get("cli")
    if not isinstance(cli, str) or not cli.strip():
        raise ConfigError(f"[profiles.{name}] has no cli field")
    return cli.strip().lower()


def _check_profile_resolves(name: str, profile: dict[str, Any], backend: str) -> None:
    """Refuse a selected profile whose `cli` field names a backend workhorse does not drive."""
    if not name:
        return
    consulted = f"(in {config_path()})"

    unknown = [n for n in profile_backends(profile) if n not in backend_names()]
    if unknown:
        raise ProfileError(
            f"profile {name!r} declares cli = {unknown[0]!r} {consulted}; that "
            f"is not a backend this build of workhorse drives. Known backends: "
            f"{', '.join(backend_names())}"
        )

    if not profile_has_backend(profile, backend):
        raise ProfileError(
            f"profile {name!r} declares cli = {backend!r} but carries no "
            f"models for it {consulted}. Add a [profiles.{name}.powers.<tier>] "
            f"table or a [profiles.{name}.default] entry, or run with --cli "
            f"<this-cli> and no --profile (bare-CLI mode)."
        )


def resume_backend_flags(cli: str = "", profile: str = "") -> list[str]:
    """The flags that resume a run onto ``cli`` and ``profile``: the CLI wins, and keeps a profile that names it."""
    if profile and (not cli or _profile_names_cli(profile, cli)):
        return ["--profile", profile]
    if profile:
        print(
            f"[workhorse] resume: dropping profile {profile!r}, which does not name cli {cli!r}",
            flush=True,
        )
    return ["--cli", cli] if cli else []


def with_backend_flags(argv: list[str], *, cli: str = "", profile: str = "") -> list[str]:
    """``argv`` with its backend flags replaced by the ones that resume onto ``cli`` and ``profile``."""
    kept: list[str] = []
    skip = False
    for token in argv:
        if skip:
            skip = False
            continue
        if token in _BACKEND_FLAGS:
            skip = True
            continue
        if any(token.startswith(f"{flag}=") for flag in _BACKEND_FLAGS):
            continue
        kept.append(token)
    return [*kept, *resume_backend_flags(cli, profile)]


def flag_value(argv: list[str], flag: str) -> str:
    """The value ``argv`` gives ``flag``, in either spelling, or ``""``."""
    for i, token in enumerate(argv):
        if token == flag and i + 1 < len(argv):
            return argv[i + 1]
        if token.startswith(f"{flag}="):
            return token.removeprefix(f"{flag}=")
    return ""


def _profile_names_cli(profile: str, cli: str) -> bool:
    try:
        return profile_has_backend(select_profile(load_config(), profile), cli)
    except (UnknownProfileError, ConfigError):
        return False


def record_switch(writer: ArtifactWriter, name: str) -> None:
    """Point the run's records at the profile a live switch moved it onto, so a resume comes back on it."""
    writer.record_profile(name, resolved_profile(name))
    record = writer.launch_record()
    if record is not None:
        writer.record_resume_argv(with_backend_flags(record.resume_argv, profile=name))


def recorded_profile(run_dir: Path) -> str:
    """The profile a run was started under, read back off its `run.json`."""
    try:
        return parse_run_record((run_dir / "run.json").read_text()).profile
    except (OSError, ValidationError):
        return ""
