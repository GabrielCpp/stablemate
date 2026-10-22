"""Whether a story names the services it changes, and whether each is a book."""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from ostler import Ostler


def service_errors(okf: Ostler, subject: str, services: Sequence[str]) -> list[str]:
    """One error per defect in *services*: an empty list, or a name that is no book."""
    if not services:
        return [
            f"{subject} lists no `services:`, so no book is named as the one it changes: give "
            "every seed it covers a `services:` tag naming books under `docs/services/`"
        ]
    books = okf.service_books()
    return [
        f"{subject} names the service `{name}`, which is no book under `docs/services/`"
        for name in services
        if name not in books
    ]


def ui_service_names(okf: Ostler, services: Iterable[str]) -> list[str]:
    """The UI books among *services*, sorted."""
    return sorted(okf.ui_services(services))


__all__ = ["service_errors", "ui_service_names"]
