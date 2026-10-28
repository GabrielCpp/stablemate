"""Home-config persistence, shared by every stablemate tool."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

import tomli_w
from platformdirs import user_config_dir, user_data_dir

logger = logging.getLogger(__name__)

CONFIG_PATH_ENV = "STABLEMATE_CONFIG"
LEGACY_CONFIG_PATH_ENV = "WORKHORSE_CONFIG"

ARTIFACTS_DIR_ENV = "STABLEMATE_ARTIFACTS_DIR"

WORKSPACES_KEY = "workspaces"

_LEGACY_APPS = ("workhorse", "farrier")

CONFIG_VERSION = 2

CONFIG_VERSION_KEY = "config_version"

PROFILES_KEY = "profiles"

PROFILE_CLI_KEY = "cli"

PROFILE_POWERS_KEY = "powers"

PROFILE_DEFAULT_KEY = "default"

CLI_KEY = "cli"

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


def write_config_section(name: str, values: dict[str, Any]) -> None:
    """Persist one dotted table, preserving every other key."""
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


def profile_cli(profile: dict[str, Any]) -> str | None:
    """The ``cli`` field a profile declares, lowercased and stripped."""
    raw = profile.get(PROFILE_CLI_KEY)
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip().lower()


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


def write_artifacts_dir(path: Path) -> None:
    """Persist ``artifacts_dir`` (where per-user story artifacts live, outside git)."""
    write_config_key("artifacts_dir", str(path))


def write_paddock_dir(path: Path) -> None:
    """Persist ``paddock_dir`` (the benchmark root: gold, workspace and results)."""
    write_config_key("paddock_dir", str(path))


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


def resolve_artifacts_dir() -> Path:
    """The per-user artifacts folder: the env var, then ``artifacts_dir``, then the data dir."""
    env = os.environ.get(ARTIFACTS_DIR_ENV)
    if env:
        return Path(env).expanduser().resolve()
    configured = get_config_value("artifacts_dir")
    if isinstance(configured, str) and configured:
        return Path(configured).expanduser().resolve()
    return (Path(user_data_dir("stablemate")) / "artifacts").expanduser().resolve()


def resolve_paddock_dir() -> Path:
    """The benchmark root: ``paddock_dir``, then the data dir."""
    configured = get_config_value("paddock_dir")
    if isinstance(configured, str) and configured:
        return Path(configured).expanduser().resolve()
    return (Path(user_data_dir("stablemate")) / "paddock").expanduser().resolve()


@dataclass(frozen=True)
class WorkspaceMember:
    """One repository of a named workspace."""

    name: str
    path: Path
    url: str = ""
    branch: str = ""


def member_name(path: Path) -> str:
    """A folder's workspace name: its basename, normalised the way farrier derives an install prefix."""
    raw = path.name
    name = re.sub(r"[^a-zA-Z0-9/-]+", "-", raw.replace(".", "-").replace("_", "-"))
    return re.sub(r"-+", "-", name).strip("-").lower()


def _member_of(workspace: str, entry: Any) -> WorkspaceMember:
    if isinstance(entry, str):
        entry = {"path": entry}
    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not entry["path"]:
        raise ConfigError(
            f"workspace {workspace!r}: every entry is a path string or a table with a `path`"
        )
    path = Path(entry["path"]).expanduser()
    name = entry.get("name")
    return WorkspaceMember(
        name=str(name) if name else member_name(path),
        path=path,
        url=str(entry.get("url") or ""),
        branch=str(entry.get("branch") or ""),
    )


def resolve_workspace(name: str) -> list[WorkspaceMember]:
    """The members of the workspace ``name`` in the home config; an unknown name lists the known ones."""
    table = load_config().get(WORKSPACES_KEY)
    workspaces = table if isinstance(table, dict) else {}
    if name not in workspaces:
        known = ", ".join(sorted(workspaces)) or "(none)"
        raise ValueError(f"unknown workspace {name!r}; known workspaces: {known}")
    entries = workspaces[name]
    if not isinstance(entries, list):
        raise ConfigError(f"workspace {name!r} must be a list of entries")
    members = [_member_of(name, entry) for entry in entries]
    seen: set[str] = set()
    for member in members:
        if member.name in seen:
            raise ValueError(f"workspace {name!r} names {member.name!r} twice")
        seen.add(member.name)
    return members


def _all_members() -> list[WorkspaceMember]:
    table = load_config().get(WORKSPACES_KEY)
    workspaces = table if isinstance(table, dict) else {}
    return [member for name in workspaces for member in resolve_workspace(name)]


def _bind(members: list[WorkspaceMember]) -> dict[str, Path]:
    merged: dict[str, Path] = {}
    for member in members:
        folder = member.path.resolve()
        known = merged.setdefault(member.name, folder)
        if known != folder:
            raise ConfigError(
                f"member {member.name!r} is bound to two folders in [{WORKSPACES_KEY}]: "
                f"{known} and {folder}"
            )
    return merged


def workspace_members() -> dict[str, Path]:
    """Every workspace's members as ``{name: folder}``; one name bound to two folders raises :class:`ConfigError`."""
    return _bind(_all_members())


@dataclass(frozen=True)
class RepositoryIdentity:
    """The facts that make a checkout one repository: its folder, its worktree's main folder and its origin URL."""

    folder: Path
    main_folder: Path
    origin_url: str = ""


def _git(folder: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(folder), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def repository_identity(start: Path) -> RepositoryIdentity:
    """The identity of the repository holding ``start``; a folder outside any repository is its own."""
    folder = start.resolve()
    probe = _git(folder, "rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir")
    lines = probe.splitlines() if probe else []
    if len(lines) != 2:
        return RepositoryIdentity(folder, folder)
    toplevel, common = Path(lines[0]).resolve(), Path(lines[1]).resolve()
    return RepositoryIdentity(toplevel, common.parent, _git(toplevel, "remote", "get-url", "origin") or "")


def _normal_url(url: str) -> str:
    text = url.strip().rstrip("/")
    return text.removesuffix(".git").rstrip("/")


def is_workspace_member(identity: RepositoryIdentity) -> bool:
    """Whether ``identity`` matches any member of any workspace by folder, main worktree folder or origin URL."""
    folders = {identity.folder, identity.main_folder}
    origin = _normal_url(identity.origin_url)
    members = _all_members()
    _bind(members)
    for member in members:
        if member.path.resolve() in folders:
            return True
        if origin and member.url and _normal_url(member.url) == origin:
            return True
    return False


def docs_home(start: Path) -> Path | None:
    """The artifacts dir when the repository holding ``start`` is in any workspace, else None so the caller walks up from ``start``."""
    if not _all_members():
        return None
    if is_workspace_member(repository_identity(start)):
        return resolve_artifacts_dir()
    return None


ARTIFACTS_IGNORED = ("specs/", "scratch/", "researches/")


def ensure_artifacts_repo() -> Path:
    """Create the artifacts dir as a git repository that ignores the session-owned folders; never adds a remote."""
    root = resolve_artifacts_dir()
    root.mkdir(parents=True, exist_ok=True)
    if not (root / ".git").exists():
        subprocess.run(["git", "-C", str(root), "init", "--quiet"], check=True, timeout=30)
    ignore = root / ".gitignore"
    existing = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    present = {line.strip() for line in existing.splitlines()}
    missing = [line for line in ARTIFACTS_IGNORED if line not in present]
    if missing:
        head = existing if not existing or existing.endswith("\n") else existing + "\n"
        ignore.write_text(head + "".join(f"{line}\n" for line in missing), encoding="utf-8")
    return root
