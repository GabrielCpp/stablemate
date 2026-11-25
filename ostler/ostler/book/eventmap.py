"""Every book under a root read together: who emits an event and who hears it, joined by its name."""

from __future__ import annotations

import importlib
import os
from typing import Any

from ostler.book.arrange import Arrange
from ostler.book.domain import Action
from ostler.book.event import Event
from ostler.book.index import package_dir, services_of
from ostler.book.search import actions_of
from ostler.book.service import Service

Books = dict[str, Service[Any]]


def root_of(module: str) -> str | None:
    parts = module.split(".")
    if parts[0] != "services":
        return None
    root = package_dir(module)
    for _ in parts:
        root = os.path.dirname(root)
    return root if os.path.isdir(os.path.join(root, "services")) else None


def scoped(module: str, service: Service[Any], root: str | None) -> list[str]:
    """The books a book is read with: its own product's, and each owner it names with a `Foreign`."""
    from ostler.book.check import references

    if root is None:
        return []
    parts = module.split(".")
    every = services_of(root)
    if len(parts) >= 3:
        names = [name for name in every if name.startswith(".".join(parts[:2]) + ".")]
    else:
        names = [name for name in every if name.count(".") == 1]
    for reference in references(module, service):
        if reference.owner in every and reference.owner not in names:
            names.append(reference.owner)
    return names


def books(module: str, service: Service[Any]) -> tuple[Books, dict[str, str]]:
    """The books under the root of `module`, this one as given, and why each other book that cannot be loaded was left out."""
    found: Books = {module: service}
    skipped: dict[str, str] = {}
    root = root_of(module)
    for name in scoped(module, service, root):
        if name == module:
            continue
        try:
            found[name] = importlib.import_module(f"{name}.service").service
        except Exception as crash:
            skipped[name] = f"{type(crash).__name__}: {str(crash).splitlines()[0] if str(crash) else ''}"
    return found, skipped


def emitters(found: Books, event: type[Event]) -> list[tuple[str, type[Action[Any, Any]]]]:
    return [(name, action) for name, service in found.items() for action in actions_of(service, name)
            if any(e.name == event.name for e in action.emits)]


def hearers(found: Books, event: type[Event]) -> list[tuple[str, type[Arrange[Any]]]]:
    return [(name, outside) for name, service in found.items() for outside in service.outside
            if outside.heard is not None and outside.heard.name == event.name]


def owner_of(found: Books, event: type[Event]) -> str:
    for name, service in found.items():
        if event in service.events:
            return f"{name}, which {event.owner} emits" if event.owner else name
    return "no book under the root"
