"""Home-config persistence, shared by every stablemate tool."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

import tomlkit
from platformdirs import user_config_dir, user_data_dir
from pydantic import ValidationError
from tomlkit import TOMLDocument
from tomlkit.exceptions import TOMLKitError

from .schema import HomeConfig, Section, StrayKey, WorkspaceEntry, stray_keys

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


class ConfigError(ValueError):
    """The config is shaped wrong for the schema it declares."""


class ConfigVersionError(ConfigError):
    """A config this build must not touch — it was written by a newer stablemate-core."""


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


class _Unreadable(Exception):
    """A config file that exists but cannot be read as TOML."""


def _read(path: Path, *, strict: bool = False) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        if strict:
            raise _Unreadable(f"{path}: {exc}") from exc
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


def _warn_if_too_new(cfg: dict[str, Any], path: Path) -> None:
    found = config_version_of(cfg)
    if found <= CONFIG_VERSION or found in _warned_too_new:
        return
    _warned_too_new.add(found)
    logger.warning(
        "%s uses config schema v%d; this build understands v%d. Reading it anyway, but "
        "keys it does not share may be missing or misread — upgrade this tool.",
        path,
        found,
        CONFIG_VERSION,
    )


def check_config_version() -> int:
    """Raise :class:`ConfigVersionError` if the config is newer than this build."""
    path = config_path()
    found = config_version_of(_effective_tree(path, _path_is_explicit(), strict=False))
    if found > CONFIG_VERSION:
        raise ConfigVersionError(_too_new_message(found))
    return found


def _lifted(data: dict[str, Any], path: Path) -> dict[str, Any]:
    found = config_version_of(data)
    if found < CONFIG_VERSION:
        data = _walk_migrations(data, found)
    _warn_if_too_new(data, path)
    return data


def _effective_tree(path: Path, explicit: bool, *, strict: bool) -> dict[str, Any]:
    if path.is_file():
        tree = _read(path, strict=strict)
    elif explicit:
        return {}
    else:
        tree = {}
        for legacy in legacy_config_paths():
            tree.update(_read(legacy, strict=strict))
    return _lifted(tree, path)


def _key_path(location: tuple[int | str, ...]) -> str:
    return ".".join(str(part) for part in location)


def validation_message(exc: ValidationError) -> str:
    """One line per invalid key, each naming its key path."""
    return "\n".join(
        f"  {_key_path(error['loc'])}: {error['msg']}" for error in exc.errors()
    )


_warned_strays: set[tuple[str, str]] = set()


def warn_strays(document: Section, path: Path) -> list[StrayKey]:
    strays = stray_keys(document)
    for stray in strays:
        marker = (str(path), stray.path)
        if marker in _warned_strays:
            continue
        _warned_strays.add(marker)
        hint = f"; did you mean {stray.closest!r}?" if stray.closest else ""
        logger.warning(
            "%s has a key no stablemate tool declares: %s%s. It is kept, and read by nothing.",
            path,
            stray.path,
            hint,
        )
    return strays


_Stamp = tuple[tuple[str, int, int], ...]


@dataclass
class _Held:
    stamp: _Stamp
    document: HomeConfig
    read_ns: int
    failed: _Stamp | None = None
    failed_read_ns: int = 0


_held: dict[Path, _Held] = {}

_RACY_NS = 2_000_000_000


def _stamp(path: Path, explicit: bool) -> _Stamp:
    sources = [path] if path.is_file() or explicit else [path, *legacy_config_paths()]
    stamp: list[tuple[str, int, int]] = []
    for source in sources:
        try:
            info = source.stat()
        except OSError:
            continue
        stamp.append((str(source), info.st_mtime_ns, info.st_size))
    return tuple(stamp)


def _settled(stamp: _Stamp, read_ns: int) -> bool:
    return all(read_ns - mtime > _RACY_NS for _, mtime, _ in stamp)


def _validated(tree: dict[str, Any], source: Path) -> HomeConfig:
    try:
        return HomeConfig.model_validate(tree)
    except ValidationError as exc:
        raise ConfigError(
            f"{source} is not a valid stablemate config:\n{validation_message(exc)}"
        ) from exc


def parse_home_config(tree: Mapping[str, Any], source: Path) -> HomeConfig:
    """``tree``, a config read from somewhere other than the effective file, lifted and validated; ``source`` names it in the error."""
    return _validated(_lifted(dict(tree), source), source)


def _keep_last_good(
    held: _Held, stamp: _Stamp, read_ns: int, path: Path, reason: object
) -> HomeConfig:
    held.failed = stamp
    held.failed_read_ns = read_ns
    logger.warning(
        "%s no longer loads; keeping the last good config. %s",
        path,
        str(reason).replace("\n", " "),
    )
    return held.document


def load_home_config(path: Path | None = None) -> HomeConfig:
    """The effective config as a validated :class:`HomeConfig`, shared and read-only.

    ``path`` names one file to read alone; without it the effective file is found as usual.
    The first load of a path that fails validation raises :class:`ConfigError` naming the key
    path. A re-read of a path that loaded before and now fails keeps the last good document
    and logs the key path. A file unchanged since the last load is not read again.
    """
    explicit = path is not None or _path_is_explicit()
    path = path if path is not None else config_path()
    stamp = _stamp(path, explicit)
    held = _held.get(path)
    if held is not None and held.stamp == stamp and _settled(stamp, held.read_ns):
        return held.document
    if held is not None and held.failed == stamp and _settled(stamp, held.failed_read_ns):
        return held.document
    read_ns = time.time_ns()
    try:
        document = _validated(_effective_tree(path, explicit, strict=True), path)
    except (ConfigError, _Unreadable) as exc:
        if held is not None:
            return _keep_last_good(held, stamp, read_ns, path, exc)
        if isinstance(exc, _Unreadable):
            raise ConfigError(f"{exc}") from exc
        raise
    warn_strays(document, path)
    _held[path] = _Held(stamp, document, read_ns)
    return document


def _forget(path: Path) -> None:
    _held.pop(path, None)


def _backup_before_migrating(path: Path, from_version: int) -> None:
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


def _fold(document: TOMLDocument, tree: dict[str, Any]) -> None:
    """Make ``document`` hold ``tree``, touching only the top-level keys whose value differs."""
    current = document.unwrap()
    for key in [key for key in current if key not in tree]:
        del document[key]
    for key, value in tree.items():
        if key not in current or current[key] != value:
            document[key] = value


def _editable(path: Path) -> TOMLDocument:
    """The file as a comment-preserving document, lifted to :data:`CONFIG_VERSION`, or refused when newer."""
    if not path.is_file():
        document = tomlkit.document()
        _fold(document, _effective_tree(path, _path_is_explicit(), strict=False))
        return document
    try:
        document = tomlkit.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, TOMLKitError) as exc:
        raise ConfigError(f"{path} cannot be edited, it is not valid TOML: {exc}") from exc
    tree = document.unwrap()
    found = config_version_of(tree)
    if found > CONFIG_VERSION:
        raise ConfigVersionError(_too_new_message(found))
    if found < CONFIG_VERSION:
        lifted = _walk_migrations(tree, found)
        _backup_before_migrating(path, found)
        _fold(document, lifted)
    return document


def _save(path: Path, document: TOMLDocument) -> None:
    document[CONFIG_VERSION_KEY] = CONFIG_VERSION
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    _forget(path)


def write_config_key(key: str, value: str) -> None:
    """Persist a single top-level string key, preserving every other key and comment."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    document = _editable(path)
    document[key] = value
    _save(path, document)


def write_config_section(name: str, values: dict[str, Any]) -> None:
    """Persist one dotted table, preserving every other key and comment."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    document = _editable(path)
    parts = name.split(".")
    table: Any = document
    for part in parts[:-1]:
        if not isinstance(table.get(part), dict):
            table[part] = tomlkit.table(is_super_table=True)
        table = table[part]
    table[parts[-1]] = dict(values)
    _save(path, document)


def write_config_value(key: str, value: Any) -> None:
    """Persist ``value`` at the dotted ``key``, refused unless the whole file still validates."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    document = _editable(path)
    parts = key.split(".")
    table: Any = document
    for part in parts[:-1]:
        if not isinstance(table.get(part), dict):
            table[part] = tomlkit.table(is_super_table=True)
        table = table[part]
    table[parts[-1]] = value
    read: Any = _validated(document.unwrap(), path).model_dump(exclude_none=True)
    for part in parts:
        read = read.get(part) if isinstance(read, dict) else None
    if not isinstance(value, dict) and read != value:
        raise ConfigError(f"{key} = {value!r} does not fit the schema: the tools would read it as {read!r}.")
    _save(path, document)


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
            cli = _profile_cli(profile)
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


def _profile_cli(profile: dict[str, Any]) -> str | None:
    """The ``cli`` field a profile declares, lowercased and stripped."""
    raw = profile.get(PROFILE_CLI_KEY)
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip().lower()


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
    configured = load_home_config().stablemate_dir
    if configured:
        return Path(configured).expanduser().resolve()
    return None


def resolve_worktree_dir() -> Path | None:
    """The directory new git worktrees are cut into, or None if unset."""
    configured = load_home_config().worktree_dir
    if configured:
        return Path(configured).expanduser().resolve()
    return None


def resolve_artifacts_dir() -> Path:
    """The per-user artifacts folder: the env var, then ``artifacts_dir``, then the data dir."""
    env = os.environ.get(ARTIFACTS_DIR_ENV)
    if env:
        return Path(env).expanduser().resolve()
    configured = load_home_config().artifacts_dir
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(user_data_dir("stablemate")) / "artifacts").expanduser().resolve()


def resolve_paddock_dir() -> Path:
    """The benchmark root: ``paddock_dir``, then the data dir."""
    configured = load_home_config().paddock_dir
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(user_data_dir("stablemate")) / "paddock").expanduser().resolve()


@dataclass(frozen=True)
class WorkspaceMember:
    """One repository of a named workspace."""

    name: str
    path: Path
    url: str = ""
    branch: str = ""


def repo_slug(raw: str) -> str:
    """A repo name normalised the way farrier derives an install prefix."""
    name = re.sub(r"[^a-zA-Z0-9/-]+", "-", raw.replace(".", "-").replace("_", "-"))
    return re.sub(r"-+", "-", name).strip("-").lower()


def member_name(path: Path) -> str:
    """A folder's workspace name: its basename, normalised the way farrier derives an install prefix."""
    return repo_slug(path.name)


def _member_of(entry: WorkspaceEntry) -> WorkspaceMember:
    path = Path(entry.path).expanduser()
    return WorkspaceMember(
        name=entry.name or member_name(path),
        path=path,
        url=entry.url or "",
        branch=entry.branch or "",
    )


def _members_in(home: HomeConfig, name: str) -> list[WorkspaceMember]:
    if name not in home.workspaces:
        known = ", ".join(sorted(home.workspaces)) or "(none)"
        raise ValueError(f"unknown workspace {name!r}; known workspaces: {known}")
    members = [_member_of(entry) for entry in home.workspaces[name]]
    seen: set[str] = set()
    for member in members:
        if member.name in seen:
            raise ValueError(f"workspace {name!r} names {member.name!r} twice")
        seen.add(member.name)
    return members


def resolve_workspace(name: str) -> list[WorkspaceMember]:
    """The members of the workspace ``name`` in the home config; an unknown name lists the known ones."""
    return _members_in(load_home_config(), name)


def _all_members() -> list[WorkspaceMember]:
    home = load_home_config()
    return [member for name in home.workspaces for member in _members_in(home, name)]


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


def _matching_member(identity: RepositoryIdentity) -> WorkspaceMember | None:
    folders = {identity.folder, identity.main_folder}
    origin = _normal_url(identity.origin_url)
    members = _all_members()
    _bind(members)
    for member in members:
        if member.path.resolve() in folders:
            return member
        if origin and member.url and _normal_url(member.url) == origin:
            return member
    return None


def is_workspace_member(identity: RepositoryIdentity) -> bool:
    """Whether ``identity`` matches any member of any workspace by folder, main worktree folder or origin URL."""
    return _matching_member(identity) is not None


def repository_name(start: Path) -> str:
    """The workspace member name of the repository holding ``start``; a repository in no workspace gets its main folder's normalised basename."""
    identity = repository_identity(start)
    member = _matching_member(identity)
    return member.name if member is not None else member_name(identity.main_folder)


def docs_home(start: Path) -> Path | None:
    """The artifacts dir when the repository holding ``start`` is in any workspace, else None so the caller walks up from ``start``."""
    if not _all_members():
        return None
    if is_workspace_member(repository_identity(start)):
        return resolve_artifacts_dir()
    return None


ARTIFACTS_IGNORED = ("backlogs/", "epics/", "specs/", "researches/", "benchmarks/", "scratch/")


def _tracked_by_enclosing_repo(root: Path) -> bool:
    if (root / ".git").exists():
        return False
    probe = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    return probe.returncode == 0 and probe.stdout.strip() == "true"


def ensure_artifacts_repo() -> Path:
    """Create the artifacts dir as a git repository that ignores the session-owned folders; never adds a remote.

    An artifacts dir inside another repository's work tree is that repository's to track, so it is left as it is.
    """
    root = resolve_artifacts_dir()
    root.mkdir(parents=True, exist_ok=True)
    if _tracked_by_enclosing_repo(root):
        return root
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
