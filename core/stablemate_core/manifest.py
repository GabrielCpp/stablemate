"""Loading: find a repository's manifest, parse it, lift its older shapes and validate it into a :class:`Manifest`."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError

from .config import ConfigError, validation_message, warn_strays
from .schema import HARNESSES, Manifest

logger = logging.getLogger(__name__)

MANIFEST_NAME = "agents.yml"

LEGACY_MANIFEST_NAMES = ("ostler.yml", "ostler.yaml", ".agents.yml")

_FREE_KEYS = ("template", "vars", "repo")

_WORKFLOW_FOLDS = ("services", "lint")

_RACY_NS = 2_000_000_000

_warned_legacy: set[Path] = set()

_warned_prompts: set[Path] = set()


def locate_manifest(root: Path) -> Path | None:
    """The manifest file directly in ``root``: ``agents.yml``, else a legacy name, else ``None``."""
    for name in (MANIFEST_NAME, *LEGACY_MANIFEST_NAMES):
        candidate = root / name
        if not candidate.is_file():
            continue
        if name != MANIFEST_NAME and candidate not in _warned_legacy:
            _warned_legacy.add(candidate)
            logger.warning(
                "%s is a legacy manifest name; rename it to %s.", candidate, MANIFEST_NAME
            )
        return candidate
    return None


def find_manifest(start: Path) -> Path | None:
    """The nearest manifest at or above ``start``, or ``None``."""
    for directory in (start, *start.parents):
        found = locate_manifest(directory)
        if found is not None:
            return found
    return None


def _without_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_none(item)
            for key, item in cast("dict[Any, Any]", value).items()
            if item is not None
        }
    if isinstance(value, list):
        return [_without_none(item) for item in cast("list[Any]", value)]
    return value


def _unset_blanks(tree: dict[str, Any]) -> dict[str, Any]:
    """``tree`` with every ``null`` dropped, except inside the free-value tables, which keep theirs."""
    data = {
        key: value if key in _FREE_KEYS else _without_none(value)
        for key, value in tree.items()
        if value is not None
    }
    return data


def _fold_vars(data: dict[str, Any], source: Path) -> None:
    legacy = data.pop("vars", None)
    if legacy is None:
        return
    if not isinstance(legacy, dict):
        raise ConfigError(f"{source}: vars must be a YAML mapping when present")
    template = data.get("template")
    if template is None:
        data["template"] = dict(cast("dict[str, Any]", legacy))
    elif isinstance(template, dict):
        data["template"] = {**cast("dict[str, Any]", legacy), **cast("dict[str, Any]", template)}


def _fold_workflow(data: dict[str, Any]) -> None:
    workflow = data.get("workflow")
    if not isinstance(workflow, dict):
        return
    table = dict(cast("dict[str, Any]", workflow))
    token = table.pop("github_token_env", None)
    if token and not table.get("githubTokenEnv"):
        table["githubTokenEnv"] = token
    for key in _WORKFLOW_FOLDS:
        legacy = table.pop(key, None)
        if legacy and not data.get(key):
            data[key] = legacy
    data["workflow"] = table


def _fold_prompts(data: dict[str, Any], source: Path) -> None:
    legacy = data.get("prompts")
    if not isinstance(legacy, dict):
        return
    roles = cast("dict[str, Any]", data.pop("prompts"))
    if source not in _warned_prompts:
        _warned_prompts.add(source)
        logger.warning(
            "%s: a top-level prompts mapping is a legacy shape; move it to workflow.prompts.",
            source,
        )
    workflow = data.get("workflow")
    table = dict(cast("dict[str, Any]", workflow)) if isinstance(workflow, dict) else {}
    inner = table.get("prompts")
    if isinstance(inner, dict):
        table["prompts"] = {**cast("dict[str, Any]", inner), **roles}
    else:
        table["prompts"] = roles
    data["workflow"] = table


def _fold_agents(data: dict[str, Any]) -> None:
    agents = data.get("agents")
    if isinstance(agents, list):
        chosen = cast("list[Any]", agents)
        data["agents"] = {name: name in chosen for name in HARNESSES}


def lifted(tree: Mapping[str, Any], source: Path) -> dict[str, Any]:
    """``tree`` with every older shape of the manifest folded into the current one, no I/O."""
    data = _unset_blanks(dict(tree))
    _fold_vars(data, source)
    _fold_workflow(data)
    _fold_prompts(data, source)
    _fold_agents(data)
    return data


def parse_manifest(tree: Mapping[str, Any], source: Path) -> Manifest:
    """``tree``, a manifest read from anywhere, lifted and validated; ``source`` names it in the error."""
    try:
        return Manifest.model_validate(lifted(tree, source))
    except ValidationError as exc:
        raise ConfigError(
            f"{source} is not a valid manifest:\n{validation_message(exc)}"
        ) from exc


def _tree_of(text: str, source: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{source} could not be read: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigError(f"{source} is not a YAML mapping")
    return cast("dict[str, Any]", loaded)


def parse_manifest_text(text: str, source: Path) -> Manifest:
    """The manifest held in ``text``, parsed and validated; ``source`` names it in the error."""
    return parse_manifest(_tree_of(text, source), source)


_Stamp = tuple[int, int]


@dataclass
class _Held:
    stamp: _Stamp
    document: Manifest
    read_ns: int
    failed: _Stamp | None = None
    failed_read_ns: int = 0


_held: dict[Path, _Held] = {}


def _stamp(path: Path) -> _Stamp | None:
    try:
        info = path.stat()
    except OSError:
        return None
    return (info.st_mtime_ns, info.st_size)


def _settled(stamp: _Stamp, read_ns: int) -> bool:
    return read_ns - stamp[0] > _RACY_NS


def _read(path: Path) -> Manifest:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{path} could not be read: {exc}") from exc
    return parse_manifest_text(text, path)


def load_manifest(path: Path) -> Manifest:
    """The manifest at ``path`` as a validated :class:`Manifest`, shared and read-only.

    The first load of a path that fails raises :class:`ConfigError` naming the key path. A
    re-read of a path that loaded before and now fails keeps the last good document and logs
    the key path. A file unchanged since the last load is not read again.
    """
    path = path.resolve()
    stamp = _stamp(path)
    held = _held.get(path)
    if held is not None and stamp is not None:
        if held.stamp == stamp and _settled(stamp, held.read_ns):
            return held.document
        if held.failed == stamp and _settled(stamp, held.failed_read_ns):
            return held.document
    read_ns = time.time_ns()
    try:
        document = _read(path)
    except ConfigError as exc:
        if held is None or stamp is None:
            raise
        held.failed = stamp
        held.failed_read_ns = read_ns
        logger.warning(
            "%s no longer loads; keeping the last good manifest. %s",
            path,
            str(exc).replace("\n", " "),
        )
        return held.document
    warn_strays(document, path)
    if stamp is not None:
        _held[path] = _Held(stamp, document, read_ns)
    return document


def read_manifest(root: str | Path) -> Manifest | None:
    """The manifest directly in *root*, or ``None`` when there is none.

    A manifest that fails validation raises :class:`ConfigError` naming its key paths. A re-read
    of a file that broke after a good load keeps the last good document.
    """
    path = locate_manifest(Path(root))
    if path is None:
        return None
    return load_manifest(path)
