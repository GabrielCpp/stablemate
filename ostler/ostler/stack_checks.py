"""`ostler doctor`'s check that the books' `stack.yml` files describe one stack that can boot.

`ostler env up` refuses a stack whose files do not fit together, and says why. The same reasons
belong in doctor, so a book with a broken stack fails where its other pages are checked, before
any run asks for a copy of it.
"""

from __future__ import annotations

from ostler.environments import spec
from ostler.finding import Finding
from ostler.model import Graph


def check_stack(graph: Graph, f: list[Finding]) -> None:
    """Each reason the books' stack files do not fit together, on the file it was found in."""
    catalog = spec.load(graph.root)
    files = [spec.shown(graph.root, stack_file) for stack_file in spec.stack_files(graph.root)]
    for error in catalog.errors:
        path = next((shown for shown in files if error.startswith(f"{shown}: ")), "")
        message = error.removeprefix(f"{path}: ") if path else error
        f.append(Finding(
            "error", "stack-invalid", message, path=path,
            suggestion="`ostler env check` lists every problem the stack files have"))


__all__ = ["check_stack"]
