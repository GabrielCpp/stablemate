"""Where a service's book lives and what it is called, for the owner's turns."""
from __future__ import annotations

from pathlib import Path


def book_module(service: str) -> str:
    return f"services.{service}"


def owner_chain(service: str) -> str:
    return f"pybook:{service}"


def finished_books(root: Path, service: str) -> list[str]:
    """The repo's other book packages, which the owner reads for the shape of each file."""
    patterns = ("services/*/service.py", "services/*/*/service.py")
    found = {path.relative_to(root).parts[1] for pattern in patterns for path in root.glob(pattern)}
    return [f"services/{name}" for name in sorted(found - {service})]
