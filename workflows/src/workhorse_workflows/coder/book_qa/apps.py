"""Which code repository a service's book describes: the book root's own, or the workspace member that holds the service."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from workhorse._vendor.stablemate_core import books
from workhorse._vendor.stablemate_core import config as core_config

from workhorse_workflows.kit import find_book_package, find_book_root, find_repo_root, resolve_workspace
from workhorse_workflows.kit.manifest import read_manifest

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ServiceApp:
    package: str
    app: Path
    cwd: Path


def book_dir(package: str, service: str) -> str:
    """The folder a service's executable book lives in, relative to the book root."""
    return f"{books.package_folder(package)}/{service}"


def book_modules(root: Path, package: str, service: str) -> tuple[str, ...]:
    """The modules of a service's book: its package when one surface reaches it, one per surface when several do."""
    folder = root / book_dir(package, service)
    base = f"{package}.{service}"
    if (folder / "service.py").is_file():
        return (base,)
    return tuple(sorted(f"{base}.{found.parent.name}" for found in folder.glob("*/service.py")))


def members(repo_dir: str, workspace: str) -> list[tuple[str, Path]]:
    """The code repositories of the run as `(name, checkout)`; without a named workspace, the docs home is left out."""
    if workspace:
        return [(name, Path(info["path"])) for name, info in resolve_workspace(workspace, repo_dir).items()]
    home = find_book_root(repo_dir).resolve()
    found = [(core_config.repository_name(path), path) for path in books.book_checkouts(home).values()]
    return [(name, path) for name, path in found if path.resolve() != home]


def _declares(path: Path, service: str) -> bool:
    manifest = read_manifest(path)
    return manifest is not None and service in manifest.services


def _booked(root: Path, package: str) -> list[str]:
    folder = root / books.package_folder(package)
    if not folder.is_dir():
        return []
    return [found.name for found in sorted(folder.iterdir()) if found.is_dir() and book_modules(root, package, found.name)]


def _flat(home: Path, name: str, repos: set[str]) -> bool:
    if name in repos:
        return (home / book_dir("services", name) / "service.py").is_file()
    return bool(book_modules(home, "services", name))


def service_app(repo_dir: str, workspace: str, service: str) -> ServiceApp | None:
    """The package, code checkout and working directory of the service's book, or None when no code repository holds it."""
    root = find_repo_root(repo_dir)
    if not books.namespaced(root):
        return ServiceApp(find_book_package(repo_dir), root, find_book_root(repo_dir))
    home = find_book_root(repo_dir)
    found = members(repo_dir, workspace)
    holders = [(name, path) for name, path in found if book_modules(home, f"services.{name}", service)]
    if holders:
        declaring = [holder for holder in holders if _declares(holder[1], service)]
        name, path = (declaring or holders)[0]
        if len(holders) > 1:
            LOGGER.warning(
                "the book of %s sits under %s; the code is read from %s",
                service, ", ".join(f"services/{held}" for held, _ in holders), name,
            )
        return ServiceApp(f"services.{name}", path, path)
    if _flat(home, service, {name for name, _ in found}):
        holding = [path for _, path in found if _declares(path, service)]
        holding = holding or [path for _, path in found if path.resolve() == home.resolve()]
        if holding:
            return ServiceApp("services", holding[0], home)
    return None


def booked_services(repo_dir: str, workspace: str) -> list[str]:
    """The bare names of the services that have an executable book under the book root."""
    root = find_repo_root(repo_dir)
    home = find_book_root(repo_dir)
    if not books.namespaced(root):
        return _booked(home, find_book_package(repo_dir))
    names = {name for name, _ in members(repo_dir, workspace)}
    folder = home / "services"
    found = [found.name for found in sorted(folder.iterdir()) if found.is_dir() and _flat(home, found.name, names)] if folder.is_dir() else []
    for name in sorted(names):
        found += [service for service in _booked(home, f"services.{name}") if service not in found]
    return found
