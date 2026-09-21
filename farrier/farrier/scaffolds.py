"""Scaffold definitions — loading, param resolution, tree flattening, fetching."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from farrier.frontmatter import read_yaml
from farrier.layers import layer_dirs
from farrier.naming import repo_prefix
from farrier.sources import collect_selection



SCAFFOLD_TREE_FILE_KEYS = {"url"}


def load_scaffold_defs() -> dict[str, dict[str, Any]]:
    """All scaffold definitions across the layers, keyed by scaffold id."""
    defs: dict[str, dict[str, Any]] = {}
    origin: dict[str, Path] = {}
    for layer, scaffolds_dir in layer_dirs("scaffolds"):
        layer_origin: dict[str, Path] = {}
        for path in sorted(
            list(scaffolds_dir.glob("*.yml")) + list(scaffolds_dir.glob("*.yaml"))
        ):
            data = read_yaml(path)
            for scaffold_id, definition in data.items():
                sid = str(scaffold_id)
                if sid in layer_origin:
                    raise SystemExit(
                        f"Duplicate scaffold id {sid!r} in layer {layer.name}: "
                        f"defined in {layer_origin[sid]} and {path}"
                    )
                if not isinstance(definition, dict) or not isinstance(
                    definition.get("tree"), dict
                ):
                    raise SystemExit(
                        f"Scaffold {sid!r} in {path} must be a mapping with a "
                        "`tree:` mapping"
                    )
                layer_origin[sid] = path
                if sid not in defs:
                    defs[sid] = definition
                    origin[sid] = path
    return defs


def resolve_scaffold_params(
    scaffold_id: str, definition: dict[str, Any], overrides: dict[str, str], repo: Path
) -> dict[str, str]:
    """Merge declared param defaults with CLI overrides; reject unknown params, require a value for every default-less (null) param."""
    declared = definition.get("params") or {}
    if not isinstance(declared, dict):
        raise SystemExit(f"Scaffold {scaffold_id!r}: params must be a YAML mapping")

    unknown = sorted(set(overrides) - set(declared))
    if unknown:
        accepted = ", ".join(sorted(declared)) or "(none)"
        raise SystemExit(
            f"Scaffold {scaffold_id!r} does not accept param(s): "
            f"{', '.join(unknown)}. Accepted params: {accepted}"
        )

    params: dict[str, str] = {}
    missing: list[str] = []
    for name, default in declared.items():
        if name in overrides:
            params[name] = overrides[name]
        elif default is None:
            missing.append(name)
        else:
            params[name] = str(default)
    if missing:
        raise SystemExit(
            f"Scaffold {scaffold_id!r} requires --param for: {', '.join(missing)}"
        )

    repo_name = repo_prefix(repo)
    params.setdefault("repo_name", repo_name)
    params.setdefault("repo_title", repo_name.replace("-", " ").title())
    return params


def flatten_scaffold_tree(
    scaffold_id: str, tree: dict[str, Any], base: str = ""
) -> tuple[dict[str, Any], list[str]]:
    """Flatten a nested `tree:` mapping into ({rel path: file spec}, [empty dirs])."""
    files: dict[str, Any] = {}
    dirs: list[str] = []
    for key, value in tree.items():
        rel = f"{base}{key}".strip("/")
        if value is None:
            dirs.append(rel)
        elif isinstance(value, str):
            files[rel] = value
        elif isinstance(value, dict):
            if SCAFFOLD_TREE_FILE_KEYS & set(value):
                extra = set(value) - SCAFFOLD_TREE_FILE_KEYS
                if extra:
                    raise SystemExit(
                        f"Scaffold {scaffold_id!r}: file node {rel!r} has "
                        f"unsupported key(s): {', '.join(sorted(str(k) for k in extra))}"
                    )
                files[rel] = value
            elif not value:
                dirs.append(rel)
            else:
                sub_files, sub_dirs = flatten_scaffold_tree(
                    scaffold_id, value, f"{rel}/"
                )
                files.update(sub_files)
                dirs.extend(sub_dirs)
        else:
            raise SystemExit(
                f"Scaffold {scaffold_id!r}: tree node {rel!r} must be file "
                f"content (string), a {{url: ...}} mapping, a sub-tree "
                f"mapping, or null/{{}} (empty directory) — got "
                f"{type(value).__name__}"
            )
    return files, dirs


def substitute_scaffold_path(scaffold_id: str, rel: str, params: dict[str, str]) -> str:
    """Substitute `$param` placeholders in a tree path."""
    from string import Template

    try:
        resolved = Template(rel).substitute(params)
    except (KeyError, ValueError) as exc:
        raise SystemExit(
            f"Scaffold {scaffold_id!r}: cannot resolve path {rel!r}: {exc}"
        ) from exc
    resolved = resolved.strip("/")
    parts = Path(resolved).parts
    if not resolved or Path(resolved).is_absolute() or ".." in parts:
        raise SystemExit(
            f"Scaffold {scaffold_id!r}: path {rel!r} resolves outside the repo: "
            f"{resolved!r}"
        )
    return resolved


def fetch_scaffold_url(scaffold_id: str, rel: str, url: str) -> str:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
            return response.read().decode("utf-8")
    except (urllib.error.URLError, OSError, UnicodeDecodeError) as exc:
        raise SystemExit(
            f"Scaffold {scaffold_id!r}: failed to download {rel!r} from {url}: {exc}"
        ) from exc


def available_scaffold_ids(repo: Path, defs: dict[str, dict[str, Any]]) -> set[str]:
    """The scaffold ids this repo may use."""
    config_path = repo / "agents.yml"
    if not config_path.is_file():
        return set(defs)
    config = read_yaml(config_path)
    _, _, _, scaffold_ids = collect_selection(config)
    return scaffold_ids


def parse_param_overrides(entries: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for entry in entries or []:
        key, sep, value = entry.partition("=")
        if not sep or not key.strip():
            raise SystemExit(f"--param must be key=value (got {entry!r})")
        overrides[key.strip()] = value
    return overrides
