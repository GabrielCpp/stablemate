"""The lap's check set: the plan's services plus every service a changed directory reaches."""
from __future__ import annotations

import json
import logging
import posixpath
import re
import subprocess
import tomllib
from collections.abc import Mapping
from pathlib import Path

import yaml
from git.exc import GitError
from workhorse.pyflow import WorkflowFailed

from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.contract import declared_service_paths, normalize_service_path
from workhorse_workflows.coder.shared.okf import story_base
from workhorse_workflows.coder.shared.schemas.dev import CheckSet, DispatchEntry
from workhorse_workflows.kit import resolve_workspace

MANIFESTS = ("go.mod", "package.json", "pubspec.yaml", "pyproject.toml")
EXCLUDE_DOCS = ":(exclude)*.md"
RELATIVE_IMPORT = re.compile(r"[\"'](\.{1,2}/[^\"'\s]*)[\"']")
GO_MODULE = re.compile(r"^module\s+(\S+)", re.MULTILINE)
IMPORT_KEYWORDS = ("from ", "import ", "require(", "import(")


def _imported(name: str) -> list[str]:
    return [
        f"{keyword}{quote}{name}{end}"
        for keyword in IMPORT_KEYWORDS
        for quote in "\"'"
        for end in (quote, "/")
    ]


def _git(root: Path, *args: str, accept: tuple[int, ...] = (0,)) -> str:
    done = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )
    if done.returncode not in accept:
        raise WorkflowFailed(f"git {' '.join(args[:2])} failed in {root}: {done.stderr.strip()}")
    return done.stdout


def _changed_files(root: Path, base: str) -> list[str]:
    tracked = _git(root, "diff", "--name-only", "--no-renames", base).splitlines()
    untracked = _git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    return list(dict.fromkeys(line.strip() for line in [*tracked, *untracked] if line.strip()))


def _units(files: list[str]) -> list[str]:
    units = {posixpath.dirname(name) or "." for name in files if not name.endswith(".md")}
    return sorted(unit for unit in units if unit != ".")


def edited_units(root: Path, base: str) -> list[str]:
    """The directories holding a non-document file this story changed since `base`."""
    return _units(_changed_files(root, base))


def _manifest_dir(root: Path, unit: str) -> Path:
    here = root / unit
    while here != root and not here.exists():
        here = here.parent
    while True:
        if any((here / name).is_file() for name in MANIFESTS) or here == root:
            break
        here = here.parent
    return here


def _manifest_name(path: Path) -> str:
    try:
        if path.name == "go.mod":
            found = GO_MODULE.search(path.read_text(encoding="utf-8"))
            return found.group(1) if found else ""
        if path.name == "package.json":
            data = json.loads(path.read_text(encoding="utf-8"))
        elif path.name == "pubspec.yaml":
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        else:
            data = tomllib.loads(path.read_text(encoding="utf-8")).get("project")
    except (OSError, ValueError, yaml.YAMLError):
        return ""
    name = data.get("name") if isinstance(data, Mapping) else ""
    return name if isinstance(name, str) else ""


def _manifest_identities(directory: Path, rel: str) -> list[str]:
    found: list[str] = []
    for manifest in MANIFESTS:
        path = directory / manifest
        if not path.is_file():
            continue
        name = _manifest_name(path)
        if not name:
            continue
        if manifest == "go.mod":
            found.append(f'"{name}"' if rel == "." else f'"{name}/{rel}"')
        elif manifest == "package.json":
            found += _imported(name)
        elif manifest == "pubspec.yaml":
            found.append(f"package:{name}/")
        else:
            imp = name.lower().replace("-", "_")
            found += [f"from {imp}", f"import {imp}"]
    return found


def unit_identities(root: Path, unit: str) -> list[str]:
    """The fixed strings a caller imports the directory `unit` by."""
    found = _imported(unit)
    if all(part.isidentifier() for part in unit.split("/")):
        dot = unit.replace("/", ".")
        found += [f"from {dot} ", f"import {dot}"]
    directory = _manifest_dir(root, unit)
    rel = posixpath.relpath(unit, directory.relative_to(root).as_posix())
    found += _manifest_identities(directory, rel)
    return list(dict.fromkeys(found))


def _grep(root: Path, patterns: list[str], paths: list[str]) -> list[str]:
    scope = [] if "." in paths else paths
    args = ["grep", "-l", "-F"]
    for pattern in patterns:
        args += ["-e", pattern]
    out = _git(root, *args, "--", *scope, EXCLUDE_DOCS, accept=(0, 1))
    return [line for line in out.splitlines() if line]


def relative_importers(root: Path, unit: str, paths: list[str]) -> list[str]:
    """Files whose relative import resolves into the directory `unit`."""
    found: list[str] = []
    for name in _grep(root, [f"/{posixpath.basename(unit)}"], paths):
        try:
            text = (root / name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for spelled in RELATIVE_IMPORT.findall(text):
            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), spelled))
            if target.startswith(".."):
                continue
            if target == unit or target.startswith(f"{unit}/"):
                found.append(name)
                break
    return found


def importers(root: Path, identities: list[str], paths: list[str]) -> list[str]:
    """Files holding any of the identities."""
    if not identities:
        return []
    return _grep(root, identities, paths)


def owner(path: str, service_paths: list[str]) -> str | None:
    """The declared service path that owns `path`, the longest match."""
    owning = [
        declared
        for declared in service_paths
        if declared == "." or path == declared or path.startswith(f"{declared}/")
    ]
    return max(owning, key=len) if owning else None


def _service_type(services: Mapping, path: str) -> str:
    for key, entry in services.items():
        if isinstance(entry, Mapping) and normalize_service_path(entry.get("path")) == path:
            return str(entry.get("type") or key)
    return ""


def _reach(
    repo: str, root: Path, base: str, services: Mapping, paths: list[str]
) -> tuple[list[str], list[str], list[str], int]:
    files = [name for name in _changed_files(root, base) if not name.endswith(".md")]
    units = _units(files)
    owners = list(dict.fromkeys(o for o in (owner(name, paths) for name in files) if o))
    identities = list(
        dict.fromkeys(i for unit in units for i in unit_identities(root, unit))
    )
    reached = set(importers(root, identities, paths))
    for unit in units:
        reached.update(relative_importers(root, unit, paths))
    dependents = sorted(
        {o for o in (owner(name, paths) for name in reached) if o} - set(owners)
    )
    shared = [f"{repo}::{unit}" for unit in units if owner(unit, paths) is None]
    return owners, dependents, shared, len(units)


@blueprint.node
def resolve_check_set(
    logger: logging.Logger,
    dispatch: tuple[DispatchEntry, ...],
    story_slug: str = "",
    story_id: str = "",
    repo_dir: str = "",
    workspace: str = "",
) -> CheckSet:
    """The plan's services, then each service a changed file or a changed import reaches."""
    checks = list(dispatch)
    present = {
        f"{entry.repo}::{normalize_service_path(entry.service_path)}" for entry in dispatch
    }
    repos = resolve_workspace(workspace, repo_dir)
    refs = tuple(dict.fromkeys(ref for ref in (story_id, story_slug) if ref))
    shared: list[str] = []
    scanned: set[str] = set()
    for entry in dispatch:
        if entry.type == "docs" or entry.repo in scanned:
            continue
        scanned.add(entry.repo)
        info = repos.get(entry.repo, {})
        services = info.get("services") or {}
        paths = declared_service_paths(services)
        if not paths:
            continue
        root = Path(info.get("path") or entry.cwd)
        try:
            base = story_base(root, refs)
        except (GitError, ValueError) as exc:
            raise WorkflowFailed(f"the check set found no story base in {root}: {exc}") from exc
        owners, dependents, outside, unit_count = _reach(entry.repo, root, base, services, paths)
        shared += outside
        added: list[str] = []
        for path in [*owners, *dependents]:
            key = f"{entry.repo}::{path}"
            if key in present:
                continue
            present.add(key)
            added.append(key)
            kind = _service_type(services, path)
            checks.append(
                DispatchEntry(
                    service=key,
                    repo=entry.repo,
                    cwd=str(root),
                    service_path=path,
                    type=kind,
                    plan_file="",
                    label=kind,
                )
            )
        logger.info(
            "check set in %s from %s: %d changed unit(s), added %s",
            root,
            base,
            unit_count,
            ", ".join(added) or "none",
        )
    return CheckSet(checks=checks, shared=shared)


__all__ = [
    "edited_units",
    "importers",
    "owner",
    "relative_importers",
    "resolve_check_set",
    "unit_identities",
]
