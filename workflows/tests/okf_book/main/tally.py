"""The tally app the okf-book flow tests drive: its surface and its page."""
from __future__ import annotations

from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind

TALLY = Surface(service="tally", kind=SurfaceKind.CLI, entry="tally/__main__.py")
PAGE = "docs/services/tally/tally.md"
