"""Where a book lives: the artifacts folder, or the repository when its agents.yml says so."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import config
from .manifest import load_manifest, locate_manifest

MOVE_GUIDE = "docs/guide/moving-a-book-to-the-artifacts-folder.md"


class UnmovedBook(config.ConfigError):
    """The repository still holds an ostler book where the artifacts folder is now the home."""


@dataclass(frozen=True)
class BookSettings:
    folder: Path
    home: str
    product: str
    team: str


def book_settings(start: Path) -> BookSettings:
    """The ``book`` settings of the nearest manifest at or above ``start``, the walk ending at the repository top."""
    origin = start.resolve()
    folder = origin
    found: Path | None = None
    for directory in (origin, *origin.parents):
        found = locate_manifest(directory)
        if found is not None:
            folder = directory
            break
        if (directory / ".git").exists():
            folder = directory
            break
    default = config.repository_name(origin)
    if found is None:
        return BookSettings(folder, "artifacts", default, "")
    table = load_manifest(found).book
    return BookSettings(folder, table.home, table.product or default, table.team or "")


def book_in_repo(start: Path) -> bool:
    return book_settings(start).home == "repo"


def _holds_ostler_book(folder: Path) -> bool:
    modules = [*folder.glob("services/*/service.py"), *folder.glob("services/*/*/service.py")]
    for module in modules:
        try:
            if "ostler.book" in module.read_text(encoding="utf-8"):
                return True
        except (OSError, UnicodeDecodeError):
            continue
    return False


def unmoved_book(start: Path) -> Path | None:
    """The repository folder that still holds an ostler book, or None."""
    folder = book_settings(start).folder
    return folder if _holds_ostler_book(folder) else None


def unmoved_message(folder: Path, artifacts: Path) -> str:
    return (
        f"{folder} holds an ostler book, and the book now lives in the artifacts folder. "
        f"Either keep it beside the code by setting `book: {{home: repo}}` in {folder}/agents.yml, "
        f"or move the book to {artifacts} following {MOVE_GUIDE}."
    )


def _symbolic_head(start: Path) -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(start), "symbolic-ref", "--quiet", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() or None if done.returncode == 0 else None


def _under(start: Path, root: Path) -> bool:
    return start.resolve().is_relative_to(root.resolve())


def _in_artifacts_repo(start: Path, top: Path | None) -> bool:
    return top is not None and config.repository_identity(start).main_folder == top


def book_home(start: Path) -> Path:
    """The folder that holds the book of the code at ``start``; never None."""
    artifacts = config.resolve_artifacts_dir()
    if _under(start, artifacts):
        return artifacts
    settings = book_settings(start)
    if settings.home == "repo":
        return settings.folder
    top = config.artifacts_toplevel()
    identity = config.repository_identity(start)
    if top is not None and identity.main_folder == top:
        return identity.folder / config.artifacts_subpath()
    if _holds_ostler_book(settings.folder):
        raise UnmovedBook(unmoved_message(settings.folder, artifacts))
    branch = _symbolic_head(start)
    if top is None or branch is None:
        return artifacts
    return config.checkout_on(top, branch) / config.artifacts_subpath()


def namespaced(root: Path) -> bool:
    """Whether the book root ``root`` is the artifacts folder or a checkout of it, where each repository's service books sit under services/<repo>/."""
    return _under(root, config.resolve_artifacts_dir()) or _in_artifacts_repo(root, config.artifacts_toplevel())


def service_package(start: Path) -> str:
    """The package holding the service books of the code at ``start``: ``services`` beside the code, in the artifacts folder or a checkout of it, else ``services.<repo>``."""
    if namespaced(start) or book_in_repo(start):
        return "services"
    return f"services.{config.repository_name(start)}"


def package_folder(package: str) -> str:
    return package.replace(".", "/")


def service_module(start: Path, name: str) -> str:
    return f"{service_package(start)}.{name}"


def service_folder(start: Path, name: str) -> str:
    """The folder of the book of the bare service ``name`` for the code at ``start``, relative to the book root."""
    return f"{package_folder(service_package(start))}/{name}"


def book_product(start: Path) -> str | None:
    """The product whose pages the code at ``start`` reads, None when ``start`` is in the artifacts folder."""
    if _under(start, config.resolve_artifacts_dir()):
        return None
    if _in_artifacts_repo(start, config.artifacts_toplevel()):
        return None
    return book_settings(start).product


def product_home(start: Path, artifacts: Path | None = None) -> Path | None:
    """The folder of the product of the code at ``start`` in the artifacts folder, None when ``start`` has no product; ``book.home: repo`` does not move it."""
    product = book_product(start)
    if product is None:
        return None
    return (artifacts or config.resolve_artifacts_dir()) / "products" / product


def milestones_home(start: Path, artifacts: Path | None = None) -> Path | None:
    """Where the milestones of the product of the code at ``start`` live, None when ``start`` has no product."""
    home = product_home(start, artifacts)
    return None if home is None else home / "milestones"


def designs_home(start: Path, artifacts: Path | None = None) -> Path | None:
    """Where the design notes of the product of the code at ``start`` live, None when ``start`` has no product."""
    home = product_home(start, artifacts)
    return None if home is None else home / "designs"


def product_folder(start: Path) -> Path | None:
    """The folder holding the product pages of the code at ``start``, None when ``start`` is in the artifacts folder."""
    if _under(start, config.resolve_artifacts_dir()):
        return None
    settings = book_settings(start)
    if settings.home == "repo":
        return settings.folder / "product"
    product = book_product(start)
    if product is None:
        return None
    return book_home(start) / "products" / product


def _in_git_repository(start: Path) -> bool:
    try:
        done = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0 and done.stdout.strip() == "true"


def book_checkouts(start: Path) -> dict[str, Path]:
    """The workspace members by name, plus the repository holding ``start`` when it is a git repository other than the artifacts repo."""
    found = dict(config.workspace_checkouts(start))
    if not _in_git_repository(start) or _in_artifacts_repo(start, config.artifacts_toplevel()):
        return found
    name = config.repository_name(start)
    if name not in found:
        found[name] = config.repository_identity(start).folder
    return found
