"""Where a service's book lives and what it is called, for the owner's turns."""
from __future__ import annotations

from pathlib import Path

from workhorse._vendor.stablemate_core import books


def book_module(package: str, service: str) -> str:
    return f"{package}.{service}"


def owner_chain(service: str) -> str:
    return f"pybook:{service}"


def finished_books(root: Path, package: str, service: str) -> list[str]:
    """The package's other book folders, which the owner reads for the shape of each file."""
    folder = books.package_folder(package)
    depth = len(folder.split("/"))
    patterns = (f"{folder}/*/service.py", f"{folder}/*/*/service.py")
    found = {path.relative_to(root).parts[depth] for pattern in patterns for path in root.glob(pattern)}
    return [f"{folder}/{name}" for name in sorted(found - {service})]
