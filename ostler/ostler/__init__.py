"""ostler: define, validate, search and mutate a repository's planning graph."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ostler.api import Ostler
    from ostler.model import Graph, load

__all__ = ["Ostler", "Graph", "load"]

_HOMES = {"Ostler": "ostler.api", "Graph": "ostler.model", "load": "ostler.model"}


def __getattr__(name: str) -> Any:
    home = _HOMES.get(name)
    if home is None:
        raise AttributeError(f"module 'ostler' has no attribute {name!r}")
    return getattr(import_module(home), name)
