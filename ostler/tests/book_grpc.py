"""The books of `fixtures/book_grpc`: a gateway over HTTP and the teams service it asks over gRPC."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

FIXTURE = Path(__file__).parent / "fixtures" / "book_grpc"


def module(name: str) -> ModuleType:
    """A module of the fixture books, with the fixture's root on the import path."""
    if str(FIXTURE) not in sys.path:
        sys.path.insert(0, str(FIXTURE))
    return importlib.import_module(name)
